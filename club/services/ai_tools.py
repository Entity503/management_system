"""
AI 工具集
=========
给运营助手用的 function calling 工具，分两类：

1. **只读查询**：活动 / 题目 / 资料 / 平台统计 —— 让 AI 回答基于真实数据
2. **生成草稿**：题目 / 公告 / 活动 —— 只写 AIDraft(pending)，绝不直接发布

所有工具的入参都经过白名单校验，权限判断在服务端完成，模型输出视为不可信输入。
"""

import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone

from ..models import Activity, Announcement, Problem, Resource, ResourceCategory
from .ai_actions import DraftError, can_publish, create_draft, permission_message

TOOL_LABELS = {
    'search_activities': '查询活动',
    'search_problems': '搜索题目',
    'search_resources': '搜索资料',
    'platform_stats': '平台统计',
    'draft_problem': '起草题目',
    'draft_announcement': '起草公告',
    'draft_activity': '起草活动',
}

TOOL_SCHEMAS = [
    {
        'type': 'function',
        'function': {
            'name': 'search_activities',
            'description': '查询社团活动。回答“这周/最近有什么活动”时必须先调用它，不要凭空编造。',
            'parameters': {
                'type': 'object',
                'properties': {
                    'keyword': {'type': 'string', 'description': '标题/地点关键词，可省略'},
                    'time_range': {
                        'type': 'string', 'enum': ['upcoming', 'past', 'all'],
                        'description': 'upcoming=即将开始（默认），past=已结束，all=全部',
                    },
                    'days': {'type': 'integer', 'description': 'upcoming 时只看未来 N 天内，可省略'},
                    'status': {
                        'type': 'string', 'enum': ['published', 'closed', 'finished', 'all'],
                        'description': '活动状态，默认 all（不含草稿）',
                    },
                    'limit': {'type': 'integer', 'description': '最多返回条数，默认 5，最大 10'},
                },
                'required': [],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'search_problems',
            'description': '在题库中搜索已发布题目，可按关键词、模块、难度过滤。',
            'parameters': {
                'type': 'object',
                'properties': {
                    'keyword': {'type': 'string', 'description': '标题/题干关键词'},
                    'category': {'type': 'string', 'description': '模块中文名，如 计算机网络'},
                    'difficulty': {
                        'type': 'string', 'enum': ['easy', 'medium', 'hard'],
                        'description': '难度',
                    },
                    'limit': {'type': 'integer', 'description': '最多返回条数，默认 5，最大 10'},
                },
                'required': [],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'search_resources',
            'description': '搜索学习资料（标题/简介），用于推荐资料。',
            'parameters': {
                'type': 'object',
                'properties': {
                    'keyword': {'type': 'string', 'description': '标题/简介关键词'},
                    'limit': {'type': 'integer', 'description': '最多返回条数，默认 5，最大 10'},
                },
                'required': [],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'platform_stats',
            'description': '获取平台统计：成员数、资料数、已发布题目数、公告数、活动数。',
            'parameters': {'type': 'object', 'properties': {}, 'required': []},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'draft_problem',
            'description': (
                '生成一道题目草稿。只创建待确认草稿，不会直接发布；'
                '用户需要在界面上点“确认发布”才会真正写入题库。'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'title': {'type': 'string', 'description': '题目标题，不超过 200 字'},
                    'content': {'type': 'string', 'description': '题干，支持 Markdown；选择题把 A/B/C/D 写在题干里'},
                    'problem_type': {
                        'type': 'string',
                        'enum': ['single', 'multiple', 'judge', 'fill', 'short_answer', 'comprehensive', 'code'],
                        'description': '题型，默认 single',
                    },
                    'difficulty': {'type': 'string', 'enum': ['easy', 'medium', 'hard'], 'description': '难度'},
                    'category': {'type': 'string', 'description': '模块中文名，如 计算机网络'},
                    'answer': {'type': 'string', 'description': '单选 A；多选 A,C；判断 T/F；填空写答案；开放题留空'},
                    'explanation': {'type': 'string', 'description': '解析，支持 Markdown'},
                },
                'required': ['title', 'content'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'draft_announcement',
            'description': '生成一条公告草稿（需要管理员权限才能最终发布）。',
            'parameters': {
                'type': 'object',
                'properties': {
                    'title': {'type': 'string', 'description': '标题，不超过 200 字'},
                    'content': {'type': 'string', 'description': '正文，支持 Markdown'},
                    'category': {
                        'type': 'string', 'enum': ['general', 'event', 'study'],
                        'description': 'general 综合 / event 活动 / study 学习',
                    },
                    'is_pinned': {'type': 'boolean', 'description': '是否置顶，默认 false'},
                },
                'required': ['title', 'content'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'draft_activity',
            'description': '生成一个活动草稿（需要管理员权限才能最终发布）。',
            'parameters': {
                'type': 'object',
                'properties': {
                    'title': {'type': 'string', 'description': '活动名称'},
                    'content': {'type': 'string', 'description': '活动详情，支持 Markdown'},
                    'location': {'type': 'string', 'description': '地点，线上活动留空字符串'},
                    'start_time': {'type': 'string', 'description': 'ISO 8601，如 2026-11-07T19:00'},
                    'end_time': {'type': 'string', 'description': 'ISO 8601'},
                    'signup_deadline': {'type': 'string', 'description': 'ISO 8601，缺省等于开始时间'},
                    'capacity': {'type': 'integer', 'description': '人数上限，默认 30'},
                    'status': {
                        'type': 'string', 'enum': ['draft', 'published'],
                        'description': '默认 draft（草稿）',
                    },
                },
                'required': ['title', 'content', 'start_time', 'end_time'],
            },
        },
    },
]

TOOL_NAMES = {schema['function']['name'] for schema in TOOL_SCHEMAS}


def _clamp(value, default, minimum, maximum):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def _fmt(dt):
    if not dt:
        return ''
    return timezone.localtime(dt).strftime('%m-%d %H:%M')


def _ok(summary, **payload):
    return {'ok': True, 'summary': summary, 'data': payload}


def _fail(summary):
    return {'ok': False, 'summary': summary, 'error': summary}


def _parse_arguments(raw):
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


# ---------------------------------------------------------------------------
# 只读工具
# ---------------------------------------------------------------------------
def _search_activities(args):
    now = timezone.now()
    queryset = Activity.objects.exclude(status='draft')
    time_range = str(args.get('time_range') or 'upcoming')
    status = str(args.get('status') or 'all')
    keyword = str(args.get('keyword') or '').strip()
    days = args.get('days')
    limit = _clamp(args.get('limit'), 5, 1, 10)

    if time_range == 'upcoming':
        queryset = queryset.filter(start_time__gte=now).order_by('start_time')
        if days:
            queryset = queryset.filter(start_time__lte=now + timedelta(days=_clamp(days, 7, 1, 365)))
    elif time_range == 'past':
        queryset = queryset.filter(start_time__lt=now).order_by('-start_time')
    else:
        queryset = queryset.order_by('-start_time')

    if status != 'all' and status in dict(Activity.STATUS_CHOICES):
        queryset = queryset.filter(status=status)
    if keyword:
        queryset = queryset.filter(
            Q(title__icontains=keyword) | Q(location__icontains=keyword) | Q(content__icontains=keyword)
        )

    items = [
        {
            'id': activity.pk,
            'title': activity.title,
            'start_time': _fmt(activity.start_time),
            'end_time': _fmt(activity.end_time),
            'location': activity.location or '线上',
            'status': activity.get_status_display(),
            'signup': f'{activity.signup_count}/{activity.capacity}',
        }
        for activity in queryset[:limit]
    ]
    total = queryset.count()
    return _ok(f'查到 {len(items)} 场活动（共 {total} 场）', total=total, items=items)


def _search_problems(args):
    queryset = Problem.objects.filter(is_published=True).select_related('category')
    keyword = str(args.get('keyword') or '').strip()
    category = str(args.get('category') or '').strip()
    difficulty = str(args.get('difficulty') or '').strip()
    limit = _clamp(args.get('limit'), 5, 1, 10)

    if keyword:
        queryset = queryset.filter(Q(title__icontains=keyword) | Q(content__icontains=keyword))
    if category:
        cat = (
            ResourceCategory.objects.filter(name__iexact=category).first()
            or ResourceCategory.objects.filter(slug__iexact=category).first()
            or ResourceCategory.objects.filter(name__icontains=category).first()
        )
        if cat:
            queryset = queryset.filter(category=cat)
    if difficulty in dict(Problem.DIFFICULTY_CHOICES):
        queryset = queryset.filter(difficulty=difficulty)

    items = [
        {
            'id': problem.pk,
            'title': problem.title,
            'type': problem.get_problem_type_display(),
            'difficulty': problem.get_difficulty_display(),
            'category': problem.category.name if problem.category else '',
        }
        for problem in queryset[:limit]
    ]
    return _ok(f'查到 {len(items)} 道题', items=items, total=queryset.count())


def _search_resources(args):
    queryset = Resource.objects.select_related('category')
    keyword = str(args.get('keyword') or '').strip()
    limit = _clamp(args.get('limit'), 5, 1, 10)
    if keyword:
        queryset = queryset.filter(Q(title__icontains=keyword) | Q(description__icontains=keyword))

    items = [
        {
            'id': resource.pk,
            'title': resource.title,
            'category': resource.category.name if resource.category else '',
            'type': resource.get_resource_type_display(),
            'downloads': resource.download_count,
        }
        for resource in queryset[:limit]
    ]
    return _ok(f'查到 {len(items)} 份资料', items=items, total=queryset.count())


def _platform_stats(_args):
    now = timezone.now()
    data = {
        'members': User.objects.filter(is_active=True).count(),
        'resources': Resource.objects.count(),
        'problems': Problem.objects.filter(is_published=True).count(),
        'announcements': Announcement.objects.filter(is_published=True).count(),
        'activities': Activity.objects.exclude(status='draft').count(),
        'upcoming_activities': Activity.objects.filter(
            status='published', start_time__gte=now
        ).count(),
    }
    return _ok('已获取平台统计', **data)


# ---------------------------------------------------------------------------
# 建稿工具
# ---------------------------------------------------------------------------
def _draft(kind, args, user):
    if not can_publish(user, kind):
        return _fail(permission_message(kind))
    try:
        draft = create_draft(user, kind, args)
    except DraftError as exc:
        return _fail(str(exc))

    if draft.status == 'failed':
        # 草稿已按审计要求落库，但不给前端展示，只把错误喂回模型让它修正
        return _fail(f'草稿校验未通过：{draft.error}')

    return {
        'ok': True,
        'summary': f'已生成{draft.get_kind_display()}草稿《{draft.display_title}》',
        'draft': draft,
    }


def _draft_problem(args, user):
    return _draft('problem', args, user)


def _draft_announcement(args, user):
    return _draft('announcement', args, user)


def _draft_activity(args, user):
    return _draft('activity', args, user)


READ_TOOLS = {
    'search_activities': _search_activities,
    'search_problems': _search_problems,
    'search_resources': _search_resources,
    'platform_stats': _platform_stats,
}

DRAFT_TOOLS = {
    'draft_problem': _draft_problem,
    'draft_announcement': _draft_announcement,
    'draft_activity': _draft_activity,
}


def execute_tool(name, raw_arguments, user):
    """
    执行一个工具调用。

    返回统一结构：
    {
        'ok': bool,
        'summary': 给用户看的一句话,
        'data': 只读工具的结构化结果（可选）,
        'error': 错误信息（ok=False 时）,
        'draft': AIDraft 对象（建稿成功时）,
        'for_model': 喂回模型的 JSON 字符串,
    }
    """
    if name not in TOOL_NAMES:
        return {
            'ok': False,
            'summary': f'不支持的工具 {name}',
            'error': f'不支持的工具 {name}',
            'for_model': json.dumps({'error': 'unsupported tool'}, ensure_ascii=False),
        }

    args = _parse_arguments(raw_arguments)
    try:
        if name in READ_TOOLS:
            result = READ_TOOLS[name](args)
        else:
            result = DRAFT_TOOLS[name](args, user)
    except Exception as exc:  # noqa: BLE001  工具失败不能中断整轮对话
        result = {'ok': False, 'summary': f'工具执行失败：{exc}', 'error': str(exc)}

    draft = result.get('draft')
    for_model = {
        'ok': result.get('ok', False),
        'summary': result.get('summary', ''),
        'data': result.get('data'),
        'error': result.get('error'),
    }
    if draft is not None:
        for_model['draft'] = {
            'id': draft.pk,
            'kind': draft.kind,
            'title': draft.display_title,
            'note': '草稿已保存，等待用户在界面上确认发布。',
        }
    # data 为空时不要塞 None，减少 token
    for_model = {key: value for key, value in for_model.items() if value not in (None, '', {})}

    return {
        'ok': result.get('ok', False),
        'summary': result.get('summary', ''),
        'data': result.get('data'),
        'error': result.get('error'),
        'draft': draft,
        'for_model': json.dumps(for_model, ensure_ascii=False, default=str),
    }

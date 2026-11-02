"""
AI 草稿服务层
==============
负责三件事：**解析 → 校验 → 落库**。所有 AI 输出都视为不可信输入。

- ``extract_json``：从模型回复里稳健地抠出 JSON（容忍 ```json 围栏和前后废话）
- ``create_draft``：字段归一化 + 复用现有 ModelForm 校验，存成 AIDraft
- ``apply_draft``：再次校验 → 事务内落库 → 写审计日志

权限规则（与手工操作保持一致，且只在服务端判断）：
- 题目：任何登录用户都可以发布（对应 /practice/create/）
- 公告 / 活动：仅管理员（对应 /announcements/create/、/activities/create/）
"""

import json
import re
from datetime import datetime

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from ..forms import ActivityForm, ProblemForm
from ..models import (
    AIActionLog,
    AIDraft,
    Activity,
    Announcement,
    Problem,
    ResourceCategory,
)

# 每人每天最多生成多少条草稿（防止刷 AI 额度）
MAX_DRAFTS_PER_DAY = 20

# 用于"确认发布"的权限判断
ADMIN_ONLY_KINDS = ('announcement', 'activity')


class DraftError(Exception):
    """草稿校验 / 权限错误，消息直接给用户看。"""


# ---------------------------------------------------------------------------
# 枚举别名：模型可能吐中文，也可能吐英文，统一归一化
# ---------------------------------------------------------------------------
PROBLEM_TYPES = {
    'single': 'single', 'single_choice': 'single', 'singlechoice': 'single',
    '单选': 'single', '单选题': 'single',
    'multiple': 'multiple', 'multi': 'multiple', '多选': 'multiple', '多选题': 'multiple',
    'judge': 'judge', 'true_false': 'judge', 'truefalse': 'judge', '判断': 'judge', '判断题': 'judge',
    'fill': 'fill', 'blank': 'fill', '填空': 'fill', '填空题': 'fill',
    'short_answer': 'short_answer', 'shortanswer': 'short_answer', '简答': 'short_answer', '简答题': 'short_answer',
    'comprehensive': 'comprehensive', '综合': 'comprehensive', '综合题': 'comprehensive',
    'code': 'code', 'coding': 'code', '代码': 'code', '代码题': 'code',
}

DIFFICULTIES = {
    'easy': 'easy', '简单': 'easy',
    'medium': 'medium', 'normal': 'medium', '中等': 'medium',
    'hard': 'hard', '困难': 'hard', '难': 'hard',
}

ANNOUNCEMENT_CATEGORIES = {
    'general': 'general', '综合': 'general', '综合通知': 'general',
    'event': 'event', '活动': 'event', '活动通知': 'event',
    'study': 'study', '学习': 'study', '学习通知': 'study',
}

ACTIVITY_STATUS = {
    'draft': 'draft', '草稿': 'draft',
    'published': 'published', '报名中': 'published',
    'closed': 'closed', '已截止': 'closed',
    'finished': 'finished', '已结束': 'finished',
}

OPEN_PROBLEM_TYPES = ('short_answer', 'comprehensive', 'code')


# ---------------------------------------------------------------------------
# JSON 解析
# ---------------------------------------------------------------------------
def _balanced_json(text, start):
    """从 start 位置的 '{' 开始做括号配平，跳过字符串内的花括号。"""
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    return None


def extract_json(text):
    """
    从模型回复里提取第一个可解析的 JSON 对象。

    依次尝试：```json 围栏 → 裸 JSON 配平扫描。
    解析失败返回 None（调用方据此按普通对话处理）。
    """
    if not text:
        return None

    candidates = []
    fenced = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.S)
    if fenced:
        candidates.append(fenced.group(1))

    start = text.find('{')
    if start != -1:
        balanced = _balanced_json(text, start)
        if balanced:
            candidates.append(balanced)

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except (TypeError, ValueError):
            continue
        if isinstance(data, dict):
            return data
    return None


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------
def _coerce(value, aliases, default):
    if value is None or value == '':
        return default
    key = str(value).strip().lower()
    return aliases.get(key, default)


def _to_bool(value):
    if isinstance(value, bool):
        return value
    return str(value or '').strip().lower() in ('true', '1', 'yes', 'y', '是', '置顶')


def _to_int(value, default, minimum, maximum):
    try:
        number = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def _form_errors(form):
    messages = []
    for field, errors in form.errors.items():
        label = form.fields[field].label if field in form.fields else '表单'
        messages.append(f'{label}：{"、".join(errors)}')
    return '；'.join(messages)


def _parse_dt(value, label, default=None):
    """把模型给的时间字符串解析成 aware datetime。"""
    if value in (None, ''):
        if default is not None:
            return default
        raise DraftError(f'缺少{label}')

    if isinstance(value, datetime):
        result = value
    else:
        text = str(value).strip().replace('Z', '+00:00')
        result = parse_datetime(text)
        if result is None:
            for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%dT%H:%M',
                        '%Y/%m/%d %H:%M', '%Y年%m月%d日 %H:%M', '%Y-%m-%d'):
                try:
                    result = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
    if result is None:
        raise DraftError(f'{label}格式无法识别，请用 2026-11-07T19:00 这样的格式')

    if timezone.is_naive(result):
        result = timezone.make_aware(result, timezone.get_current_timezone())
    return result


def _resolve_category(value):
    """把分类名 / slug 解析成 ResourceCategory，解析不到就落到「其它」。"""
    queryset = ResourceCategory.objects.all()
    text = str(value or '').strip()
    if text:
        category = (
            queryset.filter(slug__iexact=text).first()
            or queryset.filter(name__iexact=text).first()
            or queryset.filter(name__icontains=text).first()
        )
        if category:
            return category
    return queryset.filter(slug='other').first() or queryset.order_by('id').first()


def _normalize_answer(problem_type, raw_answer):
    """按题型归一化参考答案。"""
    raw = '' if raw_answer is None else str(raw_answer).strip()

    if problem_type == 'multiple':
        letters = sorted({char.upper() for char in re.findall(r'[A-Ha-h]', raw)})
        if not letters:
            raise DraftError('多选题缺少参考答案（例如 A,C）')
        return ','.join(letters)

    if problem_type == 'single':
        match = re.search(r'[A-Ha-h]', raw)
        if not match:
            raise DraftError('单选题缺少参考答案（A-H 中的一个）')
        return match.group(0).upper()

    if problem_type == 'judge':
        lowered = raw.lower()
        if lowered in ('t', 'true', '对', '正确', '√', '是', '1'):
            return 'T'
        if lowered in ('f', 'false', '错', '错误', '×', '否', '0'):
            return 'F'
        raise DraftError('判断题答案必须是 T 或 F')

    if problem_type == 'fill' and not raw:
        raise DraftError('填空题缺少参考答案')

    return raw[:255]


# ---------------------------------------------------------------------------
# 校验器：返回归一化后的 payload（只存这个，不存模型原始输出）
# ---------------------------------------------------------------------------
def _validate_problem(payload):
    errors = []
    title = str(payload.get('title') or '').strip()
    content = str(payload.get('content') or '').strip()
    if not title:
        errors.append('缺少题目标题')
    if not content:
        errors.append('缺少题目内容')
    if len(title) > 200:
        errors.append('题目标题不能超过 200 字')

    problem_type = _coerce(payload.get('problem_type'), PROBLEM_TYPES, 'single')
    difficulty = _coerce(payload.get('difficulty'), DIFFICULTIES, 'easy')
    category = _resolve_category(payload.get('category'))
    if category is None:
        errors.append('题库还没有分类数据，请先在后台创建分类')

    answer = ''
    if not errors:
        try:
            answer = _normalize_answer(problem_type, payload.get('answer'))
        except DraftError as exc:
            errors.append(str(exc))

    if errors:
        raise DraftError('；'.join(errors))

    data = {
        'title': title,
        'content': content,
        'problem_type': problem_type,
        'difficulty': difficulty,
        'category': category.pk,
        'answer': answer,
        'explanation': str(payload.get('explanation') or '').strip(),
    }
    form = ProblemForm(data)
    if not form.is_valid():
        raise DraftError(_form_errors(form))

    return {
        'title': form.cleaned_data['title'],
        'content': form.cleaned_data['content'],
        'problem_type': problem_type,
        'difficulty': difficulty,
        'category_id': category.pk,
        'category_name': category.name,
        'answer': answer,
        'explanation': form.cleaned_data.get('explanation') or '',
    }


def _validate_announcement(payload):
    title = str(payload.get('title') or '').strip()
    content = str(payload.get('content') or '').strip()
    if not title:
        raise DraftError('缺少公告标题')
    if not content:
        raise DraftError('缺少公告正文')
    if len(title) > 200:
        raise DraftError('公告标题不能超过 200 字')

    return {
        'title': title,
        'content': content,
        'category': _coerce(payload.get('category'), ANNOUNCEMENT_CATEGORIES, 'general'),
        'is_pinned': _to_bool(payload.get('is_pinned')),
    }


def _validate_activity(payload):
    title = str(payload.get('title') or '').strip()
    content = str(payload.get('content') or '').strip()
    if not title:
        raise DraftError('缺少活动名称')
    if not content:
        raise DraftError('缺少活动详情')
    if len(title) > 200:
        raise DraftError('活动名称不能超过 200 字')

    start = _parse_dt(payload.get('start_time'), '开始时间')
    end = _parse_dt(payload.get('end_time'), '结束时间')
    deadline = _parse_dt(payload.get('signup_deadline'), '报名截止时间', default=start)

    data = {
        'title': title,
        'content': content,
        'location': str(payload.get('location') or '').strip()[:200],
        'start_time': timezone.localtime(start).strftime('%Y-%m-%dT%H:%M'),
        'end_time': timezone.localtime(end).strftime('%Y-%m-%dT%H:%M'),
        'signup_deadline': timezone.localtime(deadline).strftime('%Y-%m-%dT%H:%M'),
        'capacity': _to_int(payload.get('capacity'), 30, 1, 10000),
        'status': _coerce(payload.get('status'), ACTIVITY_STATUS, 'draft'),
    }
    form = ActivityForm(data)
    if not form.is_valid():
        raise DraftError(_form_errors(form))

    return {
        'title': form.cleaned_data['title'],
        'content': form.cleaned_data['content'],
        'location': form.cleaned_data['location'],
        'start_time': data['start_time'],
        'end_time': data['end_time'],
        'signup_deadline': data['signup_deadline'],
        'capacity': form.cleaned_data['capacity'],
        'status': data['status'],
    }


VALIDATORS = {
    'problem': _validate_problem,
    'announcement': _validate_announcement,
    'activity': _validate_activity,
}


# ---------------------------------------------------------------------------
# 权限
# ---------------------------------------------------------------------------
def can_publish(user, kind):
    """判断用户能否确认发布某类草稿（与手工入口的权限保持一致）。"""
    if not getattr(user, 'is_authenticated', False):
        return False
    if kind in ADMIN_ONLY_KINDS:
        return bool(user.is_staff)
    return True


def permission_message(kind):
    if kind == 'announcement':
        return '只有管理员可以发布公告。你可以先把内容整理好，再请管理员确认。'
    if kind == 'activity':
        return '只有管理员可以创建活动。你可以先把活动信息整理好，再请管理员确认。'
    return '你没有发布该内容的权限。'


# ---------------------------------------------------------------------------
# 审计
# ---------------------------------------------------------------------------
def _log(user, action, kind, target_pk, ok, detail):
    try:
        AIActionLog.objects.create(
            user=user,
            action=action,
            kind=kind or '',
            target_pk=target_pk,
            ok=ok,
            detail=json.dumps(detail, ensure_ascii=False, default=str)[:4000],
        )
    except Exception:  # 审计失败不能影响主流程
        pass


def _check_daily_limit(user):
    today = timezone.localdate()
    used = AIDraft.objects.filter(user=user, created_at__date=today).count()
    if used >= MAX_DRAFTS_PER_DAY:
        raise DraftError(f'今天生成的草稿已达上限（{MAX_DRAFTS_PER_DAY} 条），明天再来吧。')


# ---------------------------------------------------------------------------
# 对外接口
# ---------------------------------------------------------------------------
def create_draft(user, kind, payload, conversation=None):
    """
    创建一条草稿。

    校验失败也会落一条 status=failed 的记录（便于审计和排查），
    但不会创建任何业务对象。
    """
    if kind not in VALIDATORS:
        raise DraftError('不支持的草稿类型，只支持题目 / 公告 / 活动。')
    _check_daily_limit(user)

    raw_payload = payload if isinstance(payload, dict) else {}
    try:
        cleaned = VALIDATORS[kind](raw_payload)
    except DraftError as exc:
        draft = AIDraft.objects.create(
            user=user, conversation=conversation, kind=kind,
            payload=raw_payload, status='failed', error=str(exc),
        )
        _log(user, 'draft.create', kind, None, False, {'error': str(exc), 'payload': raw_payload})
        return draft

    draft = AIDraft.objects.create(
        user=user, conversation=conversation, kind=kind,
        payload=cleaned, status='pending',
    )
    _log(user, 'draft.create', kind, None, True, {'payload': cleaned})
    return draft


def apply_draft(draft, user):
    """用户点「确认发布」：再校验一次 → 事务内落库 → 写审计。"""
    if draft.user_id != user.pk:
        raise DraftError('这不是你的草稿。')
    if draft.status != 'pending':
        raise DraftError(f'该草稿状态是「{draft.get_status_display()}」，不能重复发布。')
    if not can_publish(user, draft.kind):
        raise DraftError(permission_message(draft.kind))

    try:
        cleaned = VALIDATORS[draft.kind](draft.payload)
    except DraftError as exc:
        draft.status = 'failed'
        draft.error = str(exc)
        draft.save(update_fields=['status', 'error', 'updated_at'])
        _log(user, 'draft.apply', draft.kind, draft.pk, False, {'error': str(exc)})
        raise

    with transaction.atomic():
        obj = _create_object(draft.kind, cleaned, user)
        draft.status = 'applied'
        draft.payload = cleaned
        draft.applied_pk = obj.pk
        draft.applied_at = timezone.now()
        draft.error = ''
        draft.save(update_fields=[
            'status', 'payload', 'applied_pk', 'applied_at', 'error', 'updated_at',
        ])

    _log(user, 'draft.apply', draft.kind, obj.pk, True, {'object_pk': obj.pk})
    return obj


def discard_draft(draft, user):
    if draft.user_id != user.pk:
        raise DraftError('这不是你的草稿。')
    if draft.status != 'pending':
        raise DraftError(f'该草稿状态是「{draft.get_status_display()}」，不能丢弃。')
    draft.status = 'discarded'
    draft.save(update_fields=['status', 'updated_at'])
    _log(user, 'draft.discard', draft.kind, draft.pk, True, {})
    return draft


def _create_object(kind, payload, user):
    """把校验后的 payload 落成业务对象。调用方负责事务。"""
    if kind == 'problem':
        return Problem.objects.create(
            title=payload['title'],
            content=payload['content'],
            problem_type=payload['problem_type'],
            difficulty=payload['difficulty'],
            category_id=payload['category_id'],
            answer=payload['answer'],
            explanation=payload['explanation'],
            created_by=user,
            is_published=True,  # 用户已人工确认，直接发布
        )

    if kind == 'announcement':
        return Announcement.objects.create(
            title=payload['title'],
            content=payload['content'],
            category=payload['category'],
            is_pinned=payload['is_pinned'],
            is_published=True,
            published_at=timezone.now(),
            author=user,
        )

    if kind == 'activity':
        return Activity.objects.create(
            title=payload['title'],
            content=payload['content'],
            location=payload.get('location', ''),
            start_time=_parse_dt(payload['start_time'], '开始时间'),
            end_time=_parse_dt(payload['end_time'], '结束时间'),
            signup_deadline=_parse_dt(payload['signup_deadline'], '报名截止时间'),
            capacity=payload['capacity'],
            status=payload['status'],
            organizer=user,
        )

    raise DraftError('不支持的草稿类型。')

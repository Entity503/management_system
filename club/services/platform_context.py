"""
平台快照
========
把数据库里的真实状态压成一小段文本，注入 System Prompt。
解决"AI 不知道社团现在有什么"的问题。

只用少量字段 + 60 秒缓存，避免每次对话都打一堆查询。
"""

from django.core.cache import cache
from django.utils import timezone

from ..models import Activity, Announcement, Problem, Resource, ResourceCategory

CACHE_KEY = 'club:ai:platform-context'
CACHE_TTL = 60
WEEKDAYS = '一二三四五六日'


def _fmt(dt):
    """把 aware datetime 转成本地时间的 '月-日 时:分'。"""
    if not dt:
        return ''
    return timezone.localtime(dt).strftime('%m-%d %H:%M')


def _global_lines():
    """与用户无关的平台概况，缓存 60 秒。"""
    cached = cache.get(CACHE_KEY)
    if cached is not None:
        return cached

    now = timezone.now()
    lines = []

    categories = list(ResourceCategory.objects.order_by('id').values_list('name', flat=True))
    if categories:
        lines.append('可用分类：' + ' / '.join(categories))

    announcements = Announcement.objects.filter(is_published=True)[:3]
    ann_total = Announcement.objects.filter(is_published=True).count()
    if announcements:
        titles = '；'.join(f'《{a.title}》{_fmt(a.published_at or a.created_at)}' for a in announcements)
        lines.append(f'公告：共 {ann_total} 条，最新 3 条：{titles}')
    else:
        lines.append('公告：暂无已发布公告')

    upcoming = Activity.objects.filter(
        status__in=['published', 'closed'], start_time__gte=now
    ).order_by('start_time')[:3]
    if upcoming:
        items = '；'.join(
            f'《{a.title}》{_fmt(a.start_time)} 地点{a.location or "线上"}（{a.get_status_display()}）'
            for a in upcoming
        )
        lines.append(f'活动：即将开始 {len(upcoming)} 场：{items}')
    else:
        lines.append('活动：暂无即将开始的活动')

    problem_total = Problem.objects.filter(is_published=True).count()
    latest_problems = '；'.join(
        f'《{p.title}》' for p in Problem.objects.filter(is_published=True)[:3]
    )
    lines.append(f'题库：{problem_total} 道已发布题目' + (f'，最新：{latest_problems}' if latest_problems else ''))

    resource_total = Resource.objects.count()
    lines.append(f'学习资料：{resource_total} 份')

    cache.set(CACHE_KEY, lines, CACHE_TTL)
    return lines


def _user_line(user):
    """当前用户的画像，帮助学习教练 / 运营助手少问一句。"""
    bits = []
    profile = getattr(user, 'profile', None)
    if profile:
        for label, value in (('昵称', profile.nickname), ('专业', profile.major),
                             ('年级', profile.grade), ('技能', profile.skills)):
            if value:
                bits.append(f'{label} {value}')
    if user.is_staff:
        bits.append('身份 管理员')
    else:
        bits.append('身份 普通成员')
    return '当前用户：' + '，'.join(bits)


def build_platform_context(user=None):
    """
    生成注入 System Prompt 的平台上下文。

    没有数据时也要返回一段话，让模型知道"平台还没内容"，
    而不是让它自己编。
    """
    now = timezone.localtime()
    lines = [f'【平台当前状态】（系统自动生成，当前时间 {now:%Y-%m-%d %H:%M} 周{WEEKDAYS[now.weekday()]}）']
    lines.extend(_global_lines())
    if user is not None and getattr(user, 'is_authenticated', False):
        lines.append(_user_line(user))
    lines.append('用户若要发布题目/公告/活动，请引导他找「运营助手」。')
    return '\n'.join(lines)

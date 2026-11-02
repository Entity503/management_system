"""
主动巡检 Agent
==============
目标：不等用户开口，主动发现「需要提醒的活动」，生成待确认的公告草稿。

四步闭环：
    观察  → 查询 24 小时内开始 / 报名截止的活动
    规划  → 规则判定 + 去重（同一活动 7 天内不重复提醒）
    生成  → 模板文案，可选调用 LLM 润色（失败自动回退模板）
    行动  → 写入 AIDraft(source=proactive)，等待管理员确认

所有产出仍然是草稿，必须由管理员点「确认发布」才落地，
与手动建稿共用同一条可信链路（校验、权限、审计）。
"""

import json
import logging
import os
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone

from .. import ai_service
from ..models import AIActionLog, AIDraft, Activity
from .ai_actions import DraftError, create_draft, extract_json

logger = logging.getLogger(__name__)

# 提前多久提醒
REMIND_WINDOW = timedelta(hours=24)
# 同一活动多久内不重复提醒
DEDUP_DAYS = 7

SYSTEM_PROMPT = (
    '你是计算机俱乐部的运营助手。根据给定的事实写一条公告，只输出 JSON：\n'
    '{"title": "标题", "content": "Markdown 正文"}\n'
    '要求：标题不超过 20 字；正文 2–4 句；只能使用给定事实，不要编造时间、地点或人数；\n'
    '不要输出 JSON 以外的任何文字。'
)


def _fmt(dt):
    if not dt:
        return ''
    return timezone.localtime(dt).strftime('%m月%d日 %H:%M')


def _llm_available():
    return bool(os.getenv('DEEPSEEK_API_KEY') or os.getenv('BAILIAN_API_KEY'))


def _owner_for(activity):
    """草稿归属：优先活动组织者（须为管理员），否则回退到超级管理员。"""
    organizer = activity.organizer
    if organizer and organizer.is_active and organizer.is_staff:
        return organizer

    super_email = getattr(settings, 'SUPER_ADMIN_EMAIL', '')
    if super_email:
        fallback = User.objects.filter(username=super_email, is_active=True).first()
        if fallback and fallback.is_staff:
            return fallback
    return None


def _recently_handled(key, now):
    return AIDraft.objects.filter(
        source_key=key, created_at__gte=now - timedelta(days=DEDUP_DAYS),
    ).exists()


def _candidates(now):
    """观察 + 规划：返回 [{rule, activity, key}]。"""
    window_end = now + REMIND_WINDOW
    seen = set()
    candidates = []

    starting = Activity.objects.filter(
        status='published', start_time__gt=now, start_time__lte=window_end,
    ).select_related('organizer').order_by('start_time')
    for activity in starting:
        seen.add(activity.pk)
        candidates.append({
            'rule': 'start',
            'activity': activity,
            'key': f'activity-start:{activity.pk}',
        })

    deadlines = Activity.objects.filter(
        status='published', signup_deadline__gt=now, signup_deadline__lte=window_end,
    ).exclude(pk__in=seen).select_related('organizer').order_by('signup_deadline')
    for activity in deadlines:
        candidates.append({
            'rule': 'deadline',
            'activity': activity,
            'key': f'activity-deadline:{activity.pk}',
        })

    return candidates


def _template_payload(rule, activity, now):
    """确定性模板：LLM 不可用或失败时使用，保证巡检永远有产出。"""
    start = _fmt(activity.start_time)
    deadline = _fmt(activity.signup_deadline)
    location = activity.location or '线上'
    signup = f'{activity.signup_count}/{activity.capacity} 人'

    if rule == 'start':
        title = f'提醒：{activity.title} 即将开始'
        lines = [
            f'**{activity.title}** 将于 {start} 在 {location} 开始。',
            f'目前已报名 {signup}。',
        ]
        if activity.signup_deadline > now:
            lines.append(f'报名截止：{deadline}，还没报名的同学抓紧。')
    else:
        title = f'报名即将截止：{activity.title}'
        lines = [
            f'**{activity.title}** 的报名将于 {deadline} 截止，目前 {signup}。',
            f'活动时间：{start}，地点：{location}。',
        ]

    return {
        'title': title[:200],
        'content': '\n\n'.join(lines),
        'category': 'event',
        'is_pinned': False,
    }


def _llm_payload(rule, activity, now):
    """让模型基于真实事实润色文案；解析失败返回 None。"""
    signup = f'{activity.signup_count}/{activity.capacity} 人'
    facts = [
        f'活动名称：{activity.title}',
        f'开始时间：{_fmt(activity.start_time)}',
        f'结束时间：{_fmt(activity.end_time)}',
        f'地点：{activity.location or "线上"}',
        f'报名截止：{_fmt(activity.signup_deadline)}',
        f'当前报名：{signup}',
    ]
    task = (
        '活动将在 24 小时内开始，请写一条开场提醒。'
        if rule == 'start'
        else '报名将在 24 小时内截止，请写一条催报名提醒。'
    )

    messages = [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {'role': 'user', 'content': '\n'.join(facts) + '\n\n' + task},
    ]
    result = ai_service.chat_messages(messages, temperature=0.4)
    data = extract_json(result.get('content', ''))
    if not data:
        return None

    title = str(data.get('title') or '').strip()
    content = str(data.get('content') or '').strip()
    if not title or not content:
        return None
    return {'title': title[:200], 'content': content[:2000]}


def _compose(rule, activity, now, use_llm):
    payload = _template_payload(rule, activity, now)
    if not use_llm or not _llm_available():
        return payload
    try:
        improved = _llm_payload(rule, activity, now)
    except Exception:  # noqa: BLE001  定时任务不能被模型异常打断
        logger.exception('主动巡检：LLM 生成失败，回退模板')
        return payload
    if improved:
        payload.update(improved)
    return payload


def run(dry_run=False, use_llm=True, limit=10, now=None):
    """
    执行一次巡检，返回报告：

    {'candidates': n, 'created': [...], 'skipped': [...]}
    """
    now = now or timezone.now()
    candidates = _candidates(now)
    report = {'candidates': len(candidates), 'created': [], 'skipped': []}

    for candidate in candidates[:limit]:
        activity = candidate['activity']
        key = candidate['key']

        if _recently_handled(key, now):
            report['skipped'].append({'activity': activity.title, 'reason': '最近 7 天已提醒过'})
            continue

        owner = _owner_for(activity)
        if owner is None:
            report['skipped'].append({'activity': activity.title, 'reason': '没有可接收草稿的管理员'})
            continue

        payload = _compose(candidate['rule'], activity, now, use_llm)

        if dry_run:
            report['created'].append({
                'activity': activity.title,
                'title': payload['title'],
                'owner': owner.username,
                'dry_run': True,
            })
            continue

        try:
            draft = create_draft(
                owner, 'announcement', payload,
                source='proactive', source_key=key,
            )
        except DraftError as exc:
            report['skipped'].append({'activity': activity.title, 'reason': str(exc)})
            continue

        AIActionLog.objects.create(
            user=owner,
            action='agent.proactive',
            kind='announcement',
            target_pk=activity.pk,
            ok=draft.status == 'pending',
            detail=json.dumps({
                'rule': candidate['rule'],
                'activity': activity.pk,
                'draft': draft.pk,
                'error': draft.error,
            }, ensure_ascii=False),
        )

        if draft.status == 'pending':
            report['created'].append({
                'activity': activity.title,
                'draft_id': draft.pk,
                'title': payload['title'],
                'owner': owner.username,
            })
        else:
            report['skipped'].append({'activity': activity.title, 'reason': draft.error})

    return report

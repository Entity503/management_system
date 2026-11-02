"""
AI 助手 & 配额系统
==================
AI 对话界面、会话管理、发送接口（普通 JSON + SSE 流式）、AI 草稿箱。

两条执行链路：
1. **聊天型智能体**：单轮调用，支持流式输出
2. **工具型智能体（运营助手）**：多轮 function calling —— 查数据 / 建草稿，
   写操作只到 AIDraft(pending)，必须由用户本人确认才落库

配额检查核心逻辑在 ``_enforce_ai_quota``：
- 超级管理员直接放行（SUPER_ADMIN_EMAIL 白名单）
- 普通用户检查每日会话数与请求数
"""

import json
import logging
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import transaction
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .. import ai_service
from ..agents import (
    AGENT_DESCRIPTIONS,
    AGENT_REGISTRY,
    DEFAULT_AGENT,
    TOOL_AGENTS,
)
from ..models import AIConversation, AIDraft, AIMessage, AIQuota
from ..services import agent_runner
from ..services.ai_actions import (
    DraftError,
    apply_draft,
    can_publish,
    create_draft,
    discard_draft,
    extract_json,
    permission_message,
)
from ..services.platform_context import build_platform_context

logger = logging.getLogger(__name__)

SUPER_ADMIN_EMAIL = settings.SUPER_ADMIN_EMAIL
AI_MESSAGE_MAX_LENGTH = 4000
AI_REQUEST_COOLDOWN_SECONDS = 3
# 只把最近 N 条消息发给模型，避免上下文无限膨胀
AI_HISTORY_LIMIT = 12
AI_DRAFT_KINDS = ('problem', 'announcement', 'activity')


def _is_super_admin(user):
    """判断某用户是不是超级管理员（username 与 settings.SUPER_ADMIN_EMAIL 一致）。"""
    return user.is_authenticated and user.username == settings.SUPER_ADMIN_EMAIL


def _enforce_ai_quota(user):
    """返回 (ok, reason, quota)；超级管理员的 quota 为 None。"""
    if _is_super_admin(user):
        return True, None, None
    quota, _ = AIQuota.objects.get_or_create(user=user)
    today = timezone.localdate()
    today_count = AIConversation.objects.filter(user=user, created_at__date=today).count()
    if today_count >= quota.max_conversations_per_day:
        return False, f'今日新建会话数已达上限（{quota.max_conversations_per_day}），明天再来吧。', quota
    return True, None, quota


def _consume_ai_request(user):
    """原子消耗一次每日 AI 请求额度，避免并发请求绕过限制。"""
    if _is_super_admin(user):
        return True, None

    with transaction.atomic():
        quota, _ = AIQuota.objects.select_for_update().get_or_create(user=user)
        today = timezone.localdate()
        if quota.daily_requests_date != today:
            quota.daily_requests = 0
            quota.daily_requests_date = today
        if quota.daily_requests >= quota.max_requests_per_day:
            return False, f'今日 AI 请求次数已达上限（{quota.max_requests_per_day}），明天再来吧。'
        quota.daily_requests += 1
        quota.save(update_fields=['daily_requests', 'daily_requests_date', 'updated_at'])
    return True, None


def _check_conversation_size(conversation, quota):
    """按 UTF-8 字节数检查单会话体积，防止上下文无限膨胀。"""
    total_bytes = sum(len(m.content.encode('utf-8')) for m in conversation.messages.all())
    if total_bytes > quota.max_conversation_bytes:
        return False, f'当前会话体积已达上限 {quota.max_conversation_size_mb} MB，请新建会话。'
    return True, None


def _get_user_quota_safe(user):
    if _is_super_admin(user):
        return None
    if hasattr(user, 'ai_quota') and user.ai_quota:
        return user.ai_quota
    quota, _ = AIQuota.objects.get_or_create(user=user)
    return quota


def _admin_users_query(today=False):
    """管理员后台「成员列表」基础查询集。"""
    from django.db.models import Count, Q

    qs = User.objects.select_related('profile', 'ai_quota').order_by('-is_staff', '-date_joined')
    if today:
        t = timezone.localdate()
        qs = qs.annotate(
            today_conv_count=Count('ai_conversations', filter=Q(ai_conversations__created_at__date=t))
        )
    return qs


def _recent_history(conversation):
    """取最近 N 条对话作为上下文。"""
    recent = conversation.messages.filter(
        role__in=['user', 'assistant']
    ).order_by('-created_at')[:AI_HISTORY_LIMIT]
    return list(reversed(recent))


def _normalize_agent_type(agent_type):
    return agent_type if agent_type in AGENT_REGISTRY else DEFAULT_AGENT


def _draft_payload(draft):
    """给前端渲染草稿卡片用的精简结构。"""
    return {
        'id': draft.pk,
        'kind': draft.kind,
        'kind_label': draft.get_kind_display(),
        'title': draft.display_title,
        'fields': [[label, str(value)] for label, value in draft.display_fields],
    }


def _json_fallback(user, conversation, content):
    """
    兼容不支持 function calling 的模型：如果它仍然按旧协议输出 JSON，也接住。

    返回 (最终展示文本, draft_or_none)。
    """
    data = extract_json(content)
    if not data or 'kind' not in data:
        return content, None

    kind = str(data.get('kind') or '').strip().lower()
    if kind not in AI_DRAFT_KINDS:
        return '抱歉，我只能生成题目 / 公告 / 活动这三类草稿。', None
    if not can_publish(user, kind):
        return permission_message(kind), None

    payload = data.get('payload')
    if not isinstance(payload, dict):
        payload = {}
    try:
        draft = create_draft(user, kind, payload, conversation=conversation)
    except DraftError as exc:
        return str(exc), None

    if draft.status == 'failed':
        return f'草稿校验没通过：{draft.error}。补充或修正信息后，我可以再生成一次。', None
    return f'已生成{draft.get_kind_display()}草稿《{draft.display_title}》，请在上方草稿卡片中确认后发布。', draft


# ---------------------------------------------------------------------------
# 请求预处理
# ---------------------------------------------------------------------------
def _read_message(request):
    """读取并校验 message，返回 (文本, 错误响应)。"""
    if request.method != 'POST':
        return '', JsonResponse({'error': '仅支持 POST'}, status=405)
    message_text = request.POST.get('message', '').strip()
    if not message_text:
        return '', JsonResponse({'error': '消息不能为空'}, status=400)
    if len(message_text) > AI_MESSAGE_MAX_LENGTH:
        return '', JsonResponse(
            {'error': f'单条消息不能超过 {AI_MESSAGE_MAX_LENGTH} 个字符。'}, status=400,
        )
    return message_text, None


def _prepare_exchange(request):
    """
    冷却 / 配额 / 会话解析。返回 (conversation, quota) 或 JsonResponse 错误。
    两个发送接口（JSON 与 SSE）共用。
    """
    cooldown_key = f'ai-request-cooldown:{request.user.pk}'
    if not cache.add(cooldown_key, True, AI_REQUEST_COOLDOWN_SECONDS):
        return JsonResponse({'ok': False, 'error': '请求过于频繁，请稍后再试。'}, status=429)

    ok, reason = _consume_ai_request(request.user)
    if not ok:
        return JsonResponse({'ok': False, 'error': reason}, status=403)

    conversation_id = request.POST.get('conversation_id')
    if not conversation_id:
        ok, reason, quota = _enforce_ai_quota(request.user)
        if not ok:
            return JsonResponse({'ok': False, 'error': reason}, status=403)
        agent_type = _normalize_agent_type(request.POST.get('agent_type', DEFAULT_AGENT))
        conversation = AIConversation.objects.create(user=request.user, agent_type=agent_type)
        if quota:
            quota.total_conversations += 1
            quota.save(update_fields=['total_conversations'])
        return conversation, quota

    conversation = AIConversation.objects.filter(pk=conversation_id, user=request.user).first()
    if conversation is None:
        return JsonResponse({'ok': False, 'error': '会话不存在或不属于你。'}, status=404)

    if _is_super_admin(request.user):
        return conversation, None

    quota = _get_user_quota_safe(request.user)
    ok, reason = _check_conversation_size(conversation, quota)
    if not ok:
        return JsonResponse({'ok': False, 'error': reason}, status=403)
    return conversation, quota


def _touch_conversation(conversation, message_text):
    """首次对话时用消息前 30 字生成标题。"""
    if not conversation.title:
        conversation.title = message_text[:30]
        conversation.save(update_fields=['title'])


# ---------------------------------------------------------------------------
# 页面
# ---------------------------------------------------------------------------
@login_required
def ai_chat(request, conversation_id=None):
    """AI 对话界面（GET）。"""
    conversations = AIConversation.objects.filter(user=request.user)
    if conversation_id:
        conversation = get_object_or_404(AIConversation, pk=conversation_id, user=request.user)
        messages_qs = conversation.messages.all()
        pending_drafts = list(
            AIDraft.objects.filter(
                user=request.user, conversation=conversation, status='pending'
            ).order_by('-created_at')
        )
    else:
        conversation = None
        messages_qs = AIMessage.objects.none()
        pending_drafts = []

    context = {
        'conversations': conversations,
        'current_conversation': conversation,
        'messages_list': messages_qs,
        'agent_labels': ai_service.AGENT_LABELS,
        'agent_descriptions': AGENT_DESCRIPTIONS,
        'agents': [
            {'key': key, 'label': item['label'], 'description': item['description'],
             'examples': item['examples']}
            for key, item in AGENT_REGISTRY.items()
        ],
        'pending_drafts': pending_drafts,
        'pending_draft_count': AIDraft.objects.filter(user=request.user, status='pending').count(),
        'prefill': request.GET.get('q', ''),
    }
    return render(request, 'club/ai_chat.html', context)


@login_required
@require_POST
def ai_conversation_new(request):
    """创建新 AI 会话（POST），支持 ?q= 预填。"""
    ok, reason, quota = _enforce_ai_quota(request.user)
    if not ok:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': reason}, status=403)
        messages.error(request, reason)
        return redirect('club:ai-chat')

    agent_type = _normalize_agent_type(request.POST.get('agent_type', DEFAULT_AGENT))
    conversation = AIConversation.objects.create(user=request.user, agent_type=agent_type)
    if quota:
        quota.total_conversations += 1
        quota.save(update_fields=['total_conversations'])

    url = reverse('club:ai-chat-id', kwargs={'conversation_id': conversation.pk})
    first_message = request.POST.get('first_message', '').strip()[:AI_MESSAGE_MAX_LENGTH]
    if first_message:
        url = f'{url}?{urlencode({"q": first_message})}'
    return redirect(url)


@login_required
@require_POST
def ai_conversation_delete(request, pk):
    """删除 AI 会话，同时级联删掉所有消息。"""
    conversation = get_object_or_404(AIConversation, pk=pk, user=request.user)
    deleted_count, _ = conversation.messages.all().delete()
    conversation.delete()
    messages.success(request, f'会话已删除（共清理 {deleted_count + 1} 条记录）')
    return redirect('club:ai-chat')


# ---------------------------------------------------------------------------
# 发送（非流式，JSON）
# ---------------------------------------------------------------------------
@login_required
def ai_api_send(request):
    """
    AI 消息发送（AJAX 核心接口，返回 JSON）。

    - 工具型智能体：走 agent_runner 多轮循环（查数据 / 建草稿）
    - 聊天型智能体：单轮调用
    """
    message_text, error = _read_message(request)
    if error:
        return error

    prepared = _prepare_exchange(request)
    if isinstance(prepared, JsonResponse):
        return prepared
    conversation, quota = prepared

    history = _recent_history(conversation)
    AIMessage.objects.create(conversation=conversation, role='user', content=message_text)
    _touch_conversation(conversation, message_text)

    draft = None
    trace = []
    try:
        context = build_platform_context(request.user)
        if conversation.agent_type in TOOL_AGENTS:
            result = agent_runner.run_with_tools(
                conversation.agent_type, history, message_text, context, request.user,
            )
            content = result['content']
            trace = result['tool_trace']
            draft = result['draft']
        else:
            result = ai_service.chat(
                conversation.agent_type, history, message_text, context=context,
            )
            content = result['content']
    except Exception:
        logger.exception('AI 调用失败 conversation=%s', conversation.pk)
        AIMessage.objects.create(
            conversation=conversation, role='assistant',
            content='⚠️ AI 暂时无法回复，请稍后再试。',
        )
        return JsonResponse(
            {'ok': False, 'error': 'AI 服务暂时不可用，请稍后再试。', 'conversation_id': conversation.pk},
            status=200,
        )

    if draft is None and conversation.agent_type in TOOL_AGENTS:
        content, draft = _json_fallback(request.user, conversation, content)

    assistant_msg = AIMessage.objects.create(
        conversation=conversation,
        role='assistant',
        content=content,
        model=result.get('model', ''),
        tokens=result.get('tokens', 0),
        tool_calls=trace,
    )

    if quota and assistant_msg.tokens:
        quota.total_tokens_used += assistant_msg.tokens
        quota.save(update_fields=['total_tokens_used'])

    response_data = {
        'ok': True,
        'conversation_id': conversation.pk,
        'content': content,
        'model': result.get('model', ''),
        'provider': result.get('provider', ''),
        'tools': trace,
    }
    if draft is not None and draft.status == 'pending':
        response_data['draft'] = _draft_payload(draft)
    return JsonResponse(response_data)


# ---------------------------------------------------------------------------
# 发送（SSE 流式）
# ---------------------------------------------------------------------------
def _sse(event):
    return f'data: {json.dumps(event, ensure_ascii=False)}\n\n'


@login_required
@require_POST
def ai_api_stream(request):
    """
    SSE 流式输出。

    事件类型：
    - {"type":"start"}
    - {"type":"tool","name","label","ok","summary"}   工具调用结果（运营助手）
    - {"type":"delta","text"}                          文本片段
    - {"type":"draft","draft":{...}}                   生成草稿
    - {"type":"done","conversation_id","model"}
    - {"type":"error","error"}

    工具型智能体先跑完多轮工具（非流式），再把最终文本一次性推给前端；
    聊天型智能体逐块流式输出。
    """
    message_text, error = _read_message(request)
    if error is not None:
        # 前端按普通 JSON 处理错误
        return error

    prepared = _prepare_exchange(request)
    if isinstance(prepared, JsonResponse):
        return prepared
    conversation, quota = prepared

    history = _recent_history(conversation)
    AIMessage.objects.create(conversation=conversation, role='user', content=message_text)
    _touch_conversation(conversation, message_text)
    context = build_platform_context(request.user)
    agent_type = conversation.agent_type
    is_tool_agent = agent_type in TOOL_AGENTS
    user = request.user

    def generator():
        parts = []
        trace = []
        draft = None
        model_name = ''
        tokens = 0
        try:
            yield _sse({'type': 'start'})

            if is_tool_agent:
                result = agent_runner.run_with_tools(agent_type, history, message_text, context, user)
                trace = result['tool_trace']
                draft = result['draft']
                model_name = result['model']
                tokens = result['tokens']

                for step in trace:
                    yield _sse({'type': 'tool', **step})

                text = result['content']
                if draft is None:
                    text, draft = _json_fallback(user, conversation, text)
                if text:
                    parts.append(text)
                    yield _sse({'type': 'delta', 'text': text})
            else:
                messages = ai_service.build_messages(agent_type, history, message_text, context=context)
                for kind, payload in ai_service.stream_messages(messages):
                    if kind == 'delta':
                        parts.append(payload)
                        yield _sse({'type': 'delta', 'text': payload})
                    else:
                        model_name = payload.get('model') or model_name
                        tokens = int(payload.get('tokens') or 0)

            full = ''.join(parts)
            AIMessage.objects.create(
                conversation=conversation,
                role='assistant',
                content=full,
                model=model_name,
                tokens=tokens,
                tool_calls=trace,
            )
            if quota and tokens:
                quota.total_tokens_used += tokens
                quota.save(update_fields=['total_tokens_used'])

            done_event = {'type': 'done', 'conversation_id': conversation.pk, 'model': model_name}
            if draft is not None and draft.status == 'pending':
                done_event['draft'] = _draft_payload(draft)
            yield _sse(done_event)

        except Exception:
            logger.exception('AI 流式调用失败 conversation=%s', conversation.pk)
            partial = ''.join(parts)
            AIMessage.objects.create(
                conversation=conversation,
                role='assistant',
                content=(partial + '\n\n⚠️ 回复中断，请稍后再试。').strip(),
            )
            yield _sse({'type': 'error', 'error': 'AI 服务暂时不可用，请稍后再试。'})

    response = StreamingHttpResponse(generator(), content_type='text/event-stream; charset=utf-8')
    response['Cache-Control'] = 'no-cache, no-store'
    response['X-Accel-Buffering'] = 'no'
    return response


# ---------------------------------------------------------------------------
# AI 草稿箱
# ---------------------------------------------------------------------------
def _wants_json(request):
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


@login_required
def ai_drafts(request):
    """草稿箱：待确认的排在前面，其余按时间倒序。"""
    drafts = list(
        AIDraft.objects.filter(user=request.user).select_related('conversation')[:100]
    )
    context = {
        'pending_drafts': [d for d in drafts if d.status == 'pending'],
        'history_drafts': [d for d in drafts if d.status != 'pending'],
        'pending_draft_count': sum(1 for d in drafts if d.status == 'pending'),
    }
    return render(request, 'club/ai_drafts.html', context)


@login_required
@require_POST
def ai_draft_apply(request, pk):
    """确认发布：把草稿落成业务对象（权限、校验都在服务层再做一次）。"""
    draft = get_object_or_404(AIDraft, pk=pk, user=request.user)
    try:
        obj = apply_draft(draft, request.user)
    except DraftError as exc:
        if _wants_json(request):
            return JsonResponse({'ok': False, 'error': str(exc)}, status=400)
        messages.error(request, str(exc))
        return redirect('club:ai-drafts')

    if _wants_json(request):
        return JsonResponse({
            'ok': True,
            'kind': draft.kind,
            'title': getattr(obj, 'title', draft.display_title),
            'url': draft.object_url,
        })

    messages.success(request, f'{draft.get_kind_display()}「{getattr(obj, "title", "")}」已发布。')
    return redirect(draft.object_url or 'club:ai-drafts')


@login_required
@require_POST
def ai_draft_discard(request, pk):
    """丢弃草稿（不落库，只改状态）。"""
    draft = get_object_or_404(AIDraft, pk=pk, user=request.user)
    try:
        discard_draft(draft, request.user)
    except DraftError as exc:
        if _wants_json(request):
            return JsonResponse({'ok': False, 'error': str(exc)}, status=400)
        messages.error(request, str(exc))
        return redirect('club:ai-drafts')

    if _wants_json(request):
        return JsonResponse({'ok': True})
    messages.success(request, '草稿已丢弃。')
    return redirect('club:ai-drafts')

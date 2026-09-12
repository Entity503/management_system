"""
AI 助手 & 配额系统
==================
AI 对话界面、创建/删除会话、核心 AJAX 发送接口。
以及配额检查的辅助函数（供 admin.py 和本模块共用）。

配额检查核心逻辑在 ``_enforce_ai_quota``：
1. 超级管理员直接放行（SUPER_ADMIN_EMAIL 白名单）
2. 普通用户 → get_or_create AIQuota → 检查今日新建会话数上限
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .. import ai_service
from ..models import AIConversation, AIMessage, AIQuota


SUPER_ADMIN_EMAIL = settings.SUPER_ADMIN_EMAIL


def _is_super_admin(user):
    """判断某用户是不是超级管理员（username 与 settings.SUPER_ADMIN_EMAIL 一致）。"""
    return user.is_authenticated and user.username == settings.SUPER_ADMIN_EMAIL


def _enforce_ai_quota(user):
    """
    AI 配额检查入口。

    返回三元组 (ok, reason, quota)：
    - ok=True  表示放行，reason=None
    - ok=False 表示拒绝，reason 是给用户看的中文提示
    - quota 是用户的 AIQuota 对象（超级管理员为 None，因为不受限）

    检查项：
    1. 超级管理员直接返回 True
    2. 其他用户 → 取 or 创建 AIQuota → 检查今日新建会话数上限
    """
    if _is_super_admin(user):
        return True, None, None
    quota, _ = AIQuota.objects.get_or_create(user=user)
    today = timezone.now().date()
    today_count = AIConversation.objects.filter(user=user, created_at__date=today).count()
    if today_count >= quota.max_conversations_per_day:
        return False, f'今日新建会话数已达上限（{quota.max_conversations_per_day}），明天再来吧。', quota
    return True, None, quota


def _check_conversation_size(conversation, quota):
    """
    检查单个会话的体积是否超限。

    体积计算方式：把会话里所有消息的 content 拼成 UTF-8 字节数求和。
    虽然不是精确的 Token 消耗（中文每个字 3 字节 vs 英文每个字母 1 字节），
    但对于「防止上下文无限膨胀」这个目的已经够用了。
    """
    total_bytes = sum(len(m.content.encode('utf-8')) for m in conversation.messages.all())
    if total_bytes > quota.max_conversation_bytes:
        return False, f'当前会话体积已达上限 {quota.max_conversation_size_mb} MB，请新建会话。'
    return True, None


def _get_user_quota_safe(user):
    """
    安全获取用户的 AIQuota 对象。

    先检查反向关系是否存在（避免 OneToOneField 抛 RelatedObjectDoesNotExist），
    不存在则 get_or_create 补一条。超级管理员返回 None。
    """
    if _is_super_admin(user):
        return None
    if hasattr(user, 'ai_quota') and user.ai_quota:
        return user.ai_quota
    quota, _ = AIQuota.objects.get_or_create(user=user)
    return quota


def _admin_users_query(today=False):
    """
    构造管理员后台「成员列表」的基础查询集。

    - select_related 把 profile 和 ai_quota 一起 JOIN 出来，避免列表循环 N+1
    - today=True 时额外 annotate 今日会话数，用于前端显示「今日活跃度」列
    """
    from django.db.models import Count, Q

    qs = User.objects.select_related('profile', 'ai_quota').order_by('-is_staff', '-date_joined')
    if today:
        t = timezone.now().date()
        qs = qs.annotate(
            today_conv_count=Count('ai_conversations', filter=Q(ai_conversations__created_at__date=t))
        )
    return qs


@login_required
def ai_chat(request, conversation_id=None):
    """
    AI 对话界面（GET）。

    两种用法：
    - 不带 conversation_id：左侧列表 + 空白编辑区，等用户点「新建会话」
    - 带 conversation_id：加载该会话的历史消息
    agent_labels 是 {'club_assistant': '社团助手', ...} 的映射，模板下拉框需要。
    """
    conversations = AIConversation.objects.filter(user=request.user)
    if conversation_id:
        conversation = get_object_or_404(AIConversation, pk=conversation_id, user=request.user)
        messages_qs = conversation.messages.all()
    else:
        conversation = None
        messages_qs = AIMessage.objects.none()
    context = {
        'conversations': conversations,
        'current_conversation': conversation,
        'messages_list': messages_qs,
        'agent_labels': ai_service.AGENT_LABELS,
    }
    return render(request, 'club/ai_chat.html', context)


@login_required
def ai_conversation_new(request):
    """
    创建新 AI 会话（POST）。

    创建前先过配额检查 _enforce_ai_quota：
    - 超级管理员直接放行（SUPER_ADMIN_EMAIL 白名单）
    - 普通用户检查「今日新建会话数」是否超 max_conversations_per_day
    """
    ok, reason, quota = _enforce_ai_quota(request.user)
    if not ok:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': reason}, status=403)
        messages.error(request, reason)
        return redirect('club:ai-chat')
    agent_type = request.POST.get('agent_type', 'club_assistant')
    conversation = AIConversation.objects.create(user=request.user, agent_type=agent_type)
    if quota:
        quota.total_conversations += 1
        quota.save(update_fields=['total_conversations'])
    return redirect('club:ai-chat-id', conversation_id=conversation.pk)


@login_required
def ai_conversation_delete(request, pk):
    """删除 AI 会话，同时级联删掉所有消息。返回清理的条数方便展示。"""
    conversation = get_object_or_404(AIConversation, pk=pk, user=request.user)
    deleted_count, _ = conversation.messages.all().delete()
    conversation.delete()
    messages.success(request, f'会话已删除（共清理 {deleted_count + 1} 条记录）')
    return redirect('club:ai-chat')


@login_required
def ai_api_send(request):
    """
    AI 消息发送（AJAX 核心接口，返回 JSON）。

    执行流程：
    1. 解析参数：message 必填；conversation_id 有值表示在已有会话继续聊，没值表示新会话
    2. 新会话 → 配额检查 → 创建会话 → total_conversations +1
    3. 已有会话 → 超管跳过体积检查 → 普通用户检查单会话体积
    4. 从数据库读完整历史 → 先落一条 user AIMessage → 调 ai_service.chat()
    5. 成功 → 落 assistant AIMessage → total_tokens_used +N → 返回渲染好的 content
    6. 异常 → 写一条带 ⚠️ 前缀的 assistant 消息（保证对话不中断），返回 ok=False

    如果用户是在首次发起对话（title 为空），自动用消息前 30 字填充会话标题。
    """
    if request.method != 'POST':
        return JsonResponse({'error': '仅支持 POST'}, status=405)
    message_text = request.POST.get('message', '').strip()
    if not message_text:
        return JsonResponse({'error': '消息不能为空'}, status=400)

    is_new = not request.POST.get('conversation_id')
    if is_new:
        ok, reason, quota = _enforce_ai_quota(request.user)
        if not ok:
            return JsonResponse({'ok': False, 'error': reason}, status=403)
        agent_type = request.POST.get('agent_type', 'club_assistant')
        conversation = AIConversation.objects.create(user=request.user, agent_type=agent_type)
        if quota:
            quota.total_conversations += 1
            quota.save(update_fields=['total_conversations'])
    else:
        conversation = get_object_or_404(AIConversation, pk=request.POST['conversation_id'], user=request.user)
        if not _is_super_admin(request.user):
            quota = _get_user_quota_safe(request.user)
            ok, reason = _check_conversation_size(conversation, quota)
            if not ok:
                return JsonResponse({'ok': False, 'error': reason}, status=403)
        else:
            quota = None

    try:
        history = list(conversation.messages.all().order_by('created_at'))
        AIMessage.objects.create(conversation=conversation, role='user', content=message_text)
        result = ai_service.chat(conversation.agent_type, history, message_text)
    except Exception as e:
        AIMessage.objects.create(
            conversation=conversation,
            role='assistant',
            content=f'⚠️ AI 暂时无法回复：{e}',
        )
        return JsonResponse({'ok': False, 'error': str(e), 'conversation_id': conversation.pk}, status=200)

    assistant_msg = AIMessage.objects.create(
        conversation=conversation,
        role='assistant',
        content=result['content'],
        model=result.get('model', ''),
        tokens=result.get('tokens', 0),
    )

    if quota and assistant_msg.tokens:
        quota.total_tokens_used += assistant_msg.tokens
        quota.save(update_fields=['total_tokens_used'])

    if not conversation.title:
        conversation.title = message_text[:30]
        conversation.save(update_fields=['title'])

    return JsonResponse({
        'ok': True,
        'conversation_id': conversation.pk,
        'content': result['content'],
        'model': result.get('model', ''),
        'provider': result.get('provider', ''),
    })
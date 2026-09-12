"""
管理员后台（自定义页面，不是 Django Admin）
============================================
成员管理（Staff 开关）、AI 配额管理（超管专属）、系统总览。

权限边界：
- admin_users / admin_toggle_staff：is_staff=True 即可
- admin_quotas / admin_quota_edit：只有 SUPER_ADMIN_EMAIL 一个人
"""

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.models import User
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render

from ..models import AIQuota, UserProfile
from .ai import (
    SUPER_ADMIN_EMAIL,
    _admin_users_query,
)


@user_passes_test(lambda u: u.is_authenticated and u.is_staff)
def admin_users(request):
    """
    管理员后台 - 成员管理。

    展示内容：
    - 每个用户的 Staff 开关、今日 AI 会话数、累计 Token 消耗
    - warn_threshold 是「今日配额的一半」，模板里超过这个值就高亮提醒管理员
    - is_super_admin 传给模板用来隐藏超管的 toggle 按钮（不能撤销超管权限）
    """
    super_admin = User.objects.filter(username=SUPER_ADMIN_EMAIL).first()
    users = _admin_users_query(today=True)
    for u in users:
        if not hasattr(u, 'ai_quota'):
            AIQuota.objects.get_or_create(user=u)
    users = _admin_users_query(today=True)
    for u in users:
        if hasattr(u, 'ai_quota') and u.ai_quota:
            u.warn_threshold = u.ai_quota.max_conversations_per_day // 2
        else:
            u.warn_threshold = 5
    return render(request, 'club/admin_users.html', {
        'users': users,
        'super_admin_email': SUPER_ADMIN_EMAIL,
        'is_super_admin': request.user.username == SUPER_ADMIN_EMAIL,
        'super_admin_obj': super_admin,
    })


@user_passes_test(lambda u: u.is_authenticated and u.username == SUPER_ADMIN_EMAIL)
def admin_quotas(request):
    """
    管理员后台 - AI 配额管理（仅超管可访问）。

    功能：调整每个用户的 max_conversations_per_day 和 max_conversation_size_mb。
    额外展示系统总览：累计消耗了多少 Token、累计创建了多少会话。
    """
    for u in User.objects.all():
        if not hasattr(u, 'ai_quota'):
            AIQuota.objects.get_or_create(user=u)
    users = _admin_users_query(today=True)
    for u in users:
        if hasattr(u, 'ai_quota') and u.ai_quota:
            u.warn_threshold = u.ai_quota.max_conversations_per_day // 2
        else:
            u.warn_threshold = 5
    total_tokens = sum((q.total_tokens_used or 0) for q in AIQuota.objects.all())
    total_convs = AIQuota.objects.aggregate(t=Sum('total_conversations'))['t'] or 0
    return render(request, 'club/admin_quotas.html', {
        'users': users,
        'super_admin_email': SUPER_ADMIN_EMAIL,
        'is_super_admin': True,
        'total_tokens': total_tokens,
        'total_convs': total_convs,
    })


@user_passes_test(lambda u: u.is_authenticated and u.username == SUPER_ADMIN_EMAIL)
def admin_quota_edit(request, pk):
    """
    编辑单个用户的 AI 配额。

    - 超管自己的配额不允许编辑（因为本来就不受限）
    - 两个字段做 max(1, ...) 保护，防止管理员不小心设成 0 导致用户连一个会话都建不了
    """
    target = get_object_or_404(User, pk=pk)
    if target.username == SUPER_ADMIN_EMAIL:
        messages.error(request, '超级管理员不受配额限制，无需编辑。')
        return redirect('club:admin-quotas')
    quota, _ = AIQuota.objects.get_or_create(user=target)
    if request.method == 'POST':
        try:
            quota.max_conversations_per_day = max(1, int(request.POST.get('max_conversations_per_day', 10)))
            quota.max_conversation_size_mb = max(1, int(request.POST.get('max_conversation_size_mb', 64)))
            quota.save()
            try:
                display_name = target.profile.nickname or target.profile.real_name or target.username
            except UserProfile.DoesNotExist:
                display_name = target.username
            messages.success(request, f'已更新 {display_name} 的 AI 配额。')
        except (TypeError, ValueError):
            messages.error(request, '请输入有效的数字。')
        return redirect('club:admin-quotas')
    return render(request, 'club/admin_quota_edit.html', {
        'target': target,
        'quota': quota,
    })


@user_passes_test(lambda u: u.is_authenticated and u.is_staff)
def admin_toggle_staff(request, pk):
    """
    切换用户的 Staff 权限。

    权限边界：
    - 不能撤销自己的 Staff（防止误操作把自己锁在系统外）
    - 不能撤销超级管理员（SUPER_ADMIN_EMAIL 白名单保护）
    - 普通 Staff 只能「授予」权限，「撤销」权限只有超管能做（防止 Staff 之间互掐）
    """
    target = get_object_or_404(User, pk=pk)
    target_is_current = target == request.user
    target_is_super = target.username == SUPER_ADMIN_EMAIL
    acting_is_super = request.user.username == SUPER_ADMIN_EMAIL

    try:
        display_name = target.profile.nickname or target.profile.real_name or target.username
    except UserProfile.DoesNotExist:
        display_name = target.username

    if request.method == 'POST':
        if target.is_staff:
            if target_is_current:
                messages.error(request, '不能撤销自己的管理员权限。')
            elif target_is_super:
                messages.error(request, '超级管理员的权限不可撤销。')
            elif not acting_is_super:
                messages.error(request, f'只有 {SUPER_ADMIN_EMAIL} 可以撤销管理员权限。')
            else:
                target.is_staff = False
                target.save(update_fields=['is_staff'])
                messages.success(request, f'已撤销 {display_name} 的管理员权限。')
        else:
            target.is_staff = True
            target.save(update_fields=['is_staff'])
            messages.success(request, f'已授予 {display_name} 的管理员权限。')
        return redirect('club:admin-users')

    return redirect('club:admin-users')
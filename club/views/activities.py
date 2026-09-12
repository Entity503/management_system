"""
活动管理
========
活动列表、详情（含权限判断）、创建/编辑/删除/状态切换。

权限规则：
- 列表：所有人可看（公开信息）
- 详情：已发布/已截止/已结束对所有人可见，草稿仅 Staff 可见
- 管理（增删改/状态切换）：Staff
"""

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

import markdown as md

from ..forms import ActivityForm
from ..models import Activity
from .comments import _inject_comments


STAFF_REQUIRED = user_passes_test(lambda u: u.is_authenticated and u.is_staff)


def activity_detail(request, pk):
    """
    活动详情页。

    权限规则：已发布/已截止/已结束的活动对所有人可见；
    草稿状态只有 Staff 能看到（用于管理员在后台预览未发布内容）。
    同样走 Markdown + 评论注入。
    """
    activity = get_object_or_404(Activity, pk=pk)
    can_view = activity.status in ['published', 'closed', 'finished'] or (request.user.is_authenticated and request.user.is_staff)
    if not can_view:
        raise Http404()
    activity.content_html = md.markdown(activity.content or '', extensions=['extra', 'fenced_code', 'tables'])
    context = {
        'activity': activity,
        'is_admin': request.user.is_authenticated and request.user.is_staff,
    }
    _inject_comments(request, context, activity)
    return render(request, 'club/activity_detail.html', context)


def activity_list(request):
    """
    活动列表。

    分为「即将开始」和「过往活动」两组，各自按时间方向排序。
    未登录用户也可以看（活动公开信息），模板里用 is_admin 控制是否显示管理按钮。
    """
    activities = Activity.objects.filter(status__in=['published', 'closed', 'finished']).select_related('organizer__profile')
    upcoming = activities.filter(start_time__gte=timezone.now()).order_by('start_time')
    past = activities.filter(start_time__lt=timezone.now()).order_by('-start_time')
    context = {
        'upcoming': upcoming,
        'past': past,
        'is_admin': request.user.is_authenticated and request.user.is_staff,
    }
    return render(request, 'club/activity_list.html', context)


@STAFF_REQUIRED
def activity_create(request):
    """创建活动。organizer 自动取当前管理员。"""
    form = ActivityForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        activity = form.save(commit=False)
        activity.organizer = request.user
        activity.save()
        messages.success(request, f'活动「{activity.title}」已{activity.get_status_display()}。')
        return redirect('club:activity-detail', pk=activity.pk)
    return render(request, 'club/activity_form.html', {'form': form, 'mode': '创建活动'})


@STAFF_REQUIRED
def activity_edit(request, pk):
    """编辑活动。复用 ActivityForm 校验时间逻辑。"""
    activity = get_object_or_404(Activity, pk=pk)
    form = ActivityForm(request.POST or None, request.FILES or None, instance=activity)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'活动「{activity.title}」已更新。')
        return redirect('club:activity-detail', pk=activity.pk)
    return render(request, 'club/activity_form.html', {'form': form, 'mode': '编辑活动', 'activity': activity})


@STAFF_REQUIRED
def activity_delete(request, pk):
    """删除活动。POST 才真正执行，GET 显示确认页避免误操作。"""
    activity = get_object_or_404(Activity, pk=pk)
    if request.method == 'POST':
        title = activity.title
        activity.delete()
        messages.success(request, f'活动「{title}」已删除。')
        return redirect('club:activity-list')
    return render(request, 'club/activity_confirm_delete.html', {'activity': activity})


@STAFF_REQUIRED
def activity_change_status(request, pk):
    """
    快速切换活动状态（草稿 → 报名中 → 已截止 → 已结束）。

    STATUS_CHOICES 的 value 必须是合法的 key，否则静默忽略，保持原状态不变。
    """
    activity = get_object_or_404(Activity, pk=pk)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in dict(Activity.STATUS_CHOICES):
            activity.status = new_status
            activity.save(update_fields=['status'])
            messages.success(request, f'状态已更新为「{activity.get_status_display()}」。')
    return redirect('club:activity-detail', pk=pk)
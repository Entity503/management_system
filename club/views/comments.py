"""
通用评论系统
============
基于 GenericForeignKey + ContentType 的跨模型评论。
被评论的实体统一走 ALLOWED_MODELS 白名单，防止非法模型注入。

本模块对外提供：
- _inject_comments(request, ctx, target)  —— 详情页统一评论注入（被 activities/resources/problems/announcements 引用）
- comment_create / comment_delete          —— URL 路由层
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect

import markdown as md

from ..models import Activity, Announcement, Comment, Problem, Resource


def _get_comment_target(model_name, pk):
    """
    根据模型名和主键拿到被评论的目标实体。

    利用 Comment.ALLOWED_MODELS 白名单防止非法模型注入。
    不支持的 model_name 直接 raise Http404，避免泄露 Django 内部表名。
    """
    if model_name not in Comment.ALLOWED_MODELS:
        raise Http404('不支持的评论对象类型。')
    MODEL_MAP = {
        'activity': Activity,
        'announcement': Announcement,
        'problem': Problem,
        'resource': Resource,
    }
    model_cls = MODEL_MAP[model_name]
    return get_object_or_404(model_cls, pk=pk)


def _get_comments_for(target):
    """
    从目标实体反向拿到所有评论。

    ContentType.objects.get_for_model(target) 会得到 Django 内部的 contentType 记录，
    结合 target.pk 就能过滤出挂在这个实体上的所有 Comment。
    """
    ct = ContentType.objects.get_for_model(target)
    return Comment.objects.filter(
        content_type=ct, object_id=target.pk
    ).select_related('author__profile')


def _inject_comments(request, ctx, target):
    """
    统一为详情页 context 注入评论相关数据（4 个详情页共用，避免重复代码）。

    注入内容：
    - comments：QuerySet，每条额外挂了 can_delete 和 html_content 属性
    - comment_count：整数
    - comment_target_ct / comment_target_id / comment_model：给评论提交表单拼 action 用

    渲染 Markdown 时加 extra 和 fenced_code 扩展，支持 GFM 表格和代码块。
    """
    comments = _get_comments_for(target)
    for c in comments:
        c.can_delete = (request.user.is_authenticated and (
            c.author == request.user or request.user.is_staff
        ))
        c.html_content = md.markdown(c.content or '', extensions=['extra', 'fenced_code'])
    ct = ContentType.objects.get_for_model(target)
    ctx['comments'] = comments
    ctx['comment_count'] = comments.count()
    ctx['comment_target_ct'] = ct.pk
    ctx['comment_target_id'] = target.pk
    ctx['comment_model'] = ct.model


_MODEL_URL_MAP = {
    'activity': 'club:activity-detail',
    'announcement': 'club:announcement-detail',
    'problem': 'club:problem-detail',
    'resource': 'club:resource-detail',
}


@login_required
def comment_create(request):
    """
    发表评论。

    前端表单要传三个参数：model（activity/announcement/problem/resource）、object_id、content。
    发表后 redirect 回目标详情页——用 _MODEL_URL_MAP 查表拼出目标 URL，避免写一堆 if-else。
    """
    if request.method != 'POST':
        return Http404
    model_name = request.POST.get('model', '').strip()
    try:
        obj_id = int(request.POST.get('object_id', '0'))
    except ValueError:
        obj_id = 0
    content = request.POST.get('content', '').strip()

    target = _get_comment_target(model_name, obj_id)
    if not content:
        messages.error(request, '评论内容不能为空。')
    elif len(content) > 1000:
        messages.error(request, '评论内容不能超过 1000 字。')
    else:
        Comment.objects.create(
            content=content, author=request.user, target=target,
        )
        messages.success(request, '评论已发布。')

    return redirect(_MODEL_URL_MAP[model_name], pk=obj_id)


@login_required
def comment_delete(request, pk):
    """
    删除评论。权限：作者本人 或 Staff。

    删除后同样用 _MODEL_URL_MAP 路由回原来的详情页，user 不会迷路。
    """
    comment = get_object_or_404(Comment.objects.select_related('author'), pk=pk)
    can_delete = comment.author == request.user or request.user.is_staff
    if not can_delete:
        raise Http404

    ct = comment.content_type
    model_name = ct.model
    obj_id = comment.object_id
    comment.delete()
    messages.success(request, '评论已删除。')

    return redirect(_MODEL_URL_MAP.get(model_name, 'club:dashboard'), pk=obj_id)
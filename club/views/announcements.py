"""
公告
====
列表（分类筛选 + 置顶）、详情、创建/编辑/删除。
Staff 可发布和管理公告，普通用户只读。
"""

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

import markdown as md

from ..models import Announcement
from .comments import _inject_comments


def announcement_list(request):
    """
    公告列表。

    按分类筛选 GET ?category=general|event|study，置顶公告自动排最前（Meta ordering 已配置）。
    category_labels 把模型里的 CATEGORY_CHOICES 字典塞给模板，用来显示中文标签。
    """
    qs = Announcement.objects.select_related('author__profile').all()
    cat = request.GET.get('category', '').strip()
    if cat in ('general', 'event', 'study'):
        qs = qs.filter(category=cat)
    return render(request, 'club/announcement_list.html', {
        'announcements': qs,
        'active_category': cat,
        'category_labels': dict(Announcement.CATEGORY_CHOICES),
    })


def announcement_detail(request, pk):
    """公告详情页。Markdown 渲染 + 权限判断（Staff 或 作者本人可编辑）+ 评论注入。"""
    announcement = get_object_or_404(Announcement.objects.select_related('author__profile'), pk=pk)
    can_edit = request.user.is_authenticated and (request.user.is_staff or request.user == announcement.author)
    html_content = md.markdown(announcement.content, extensions=['extra', 'fenced_code'])
    ctx = {
        'announcement': announcement,
        'html_content': html_content,
        'can_edit': can_edit,
    }
    _inject_comments(request, ctx, announcement)
    return render(request, 'club/announcement_detail.html', ctx)


@user_passes_test(lambda u: u.is_authenticated and u.is_staff)
def announcement_create(request):
    """
    创建公告。纯手写 request.POST 取值（不用 ModelForm），
    因为表单只有 title / content / category / is_pinned 四个字段，没必要引入完整 Form 类。
    """
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        content = request.POST.get('content', '').strip()
        category = request.POST.get('category', 'general')
        is_pinned = request.POST.get('is_pinned') == 'on'
        if not title or not content:
            messages.error(request, '标题和内容不能为空。')
        elif category not in ('general', 'event', 'study'):
            messages.error(request, '无效的分类。')
        else:
            ann = Announcement.objects.create(
                title=title, content=content, category=category,
                is_pinned=is_pinned, is_published=True,
                published_at=timezone.now(), author=request.user,
            )
            messages.success(request, f'公告「{title}」已发布。')
            return redirect('club:announcement-detail', pk=ann.pk)
    return render(request, 'club/announcement_form.html', {
        'mode': 'create',
        'category_choices': Announcement.CATEGORY_CHOICES,
    })


@user_passes_test(lambda u: u.is_authenticated and u.is_staff)
def announcement_edit(request, pk):
    """编辑公告，逻辑和 create 对称，只是先 get 出已有对象再 update。"""
    announcement = get_object_or_404(Announcement, pk=pk)
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        content = request.POST.get('content', '').strip()
        category = request.POST.get('category', 'general')
        is_pinned = request.POST.get('is_pinned') == 'on'
        announcement.title = title
        announcement.content = content
        announcement.category = category
        announcement.is_pinned = is_pinned
        announcement.save()
        messages.success(request, f'公告「{title}」已更新。')
        return redirect('club:announcement-detail', pk=announcement.pk)
    return render(request, 'club/announcement_form.html', {
        'mode': 'edit',
        'announcement': announcement,
        'category_choices': Announcement.CATEGORY_CHOICES,
    })


@user_passes_test(lambda u: u.is_authenticated and u.is_staff)
def announcement_delete(request, pk):
    """删除公告。POST 才真正执行，GET 显示确认页。"""
    announcement = get_object_or_404(Announcement, pk=pk)
    if request.method == 'POST':
        title = announcement.title
        announcement.delete()
        messages.success(request, f'公告「{title}」已删除。')
        return redirect('club:announcement-list')
    return render(request, 'club/announcement_confirm_delete.html', {
        'announcement': announcement,
    })
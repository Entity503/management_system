"""
学习资料
========
列表、详情（Markdown + 评论注入）、上传、下载计数、删除。

权限规则：
- 列表 / 详情 / 下载：所有登录用户
- 删除：Staff 或 上传者本人
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

import markdown as md

from ..forms import ResourceForm
from ..models import Resource, ResourceCategory
from .comments import _inject_comments


@login_required
def resource_list(request):
    """
    学习资料列表。

    分类筛选用 GET 参数 ?category=slug，URL 稳定便于分享和收藏。
    select_related 一次性 JOIN 出 category 和 uploader.profile，避免模板循环里 N+1 查询。
    """
    resources = Resource.objects.select_related('category', 'uploader__profile')
    category_slug = request.GET.get('category', '').strip()
    if category_slug:
        resources = resources.filter(category__slug=category_slug)
    context = {
        'resources': resources,
        'categories': ResourceCategory.objects.all(),
        'active_category': category_slug,
    }
    return render(request, 'club/resources.html', context)


@login_required
def resource_upload(request):
    """上传学习资料。uploader 自动取当前登录用户，resource_type 目前固定为文件。"""
    form = ResourceForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        resource = form.save(commit=False)
        resource.uploader = request.user
        resource.resource_type = 'file'
        resource.save()
        messages.success(request, '资料上传成功。')
        return redirect('club:resources')
    return render(request, 'club/resource_upload.html', {'form': form})


@login_required
def resource_detail(request, pk):
    """
    资料详情页。

    Markdown 渲染启用 fenced_code（```language 代码块）和 tables（Markdown 表格）扩展。
    底部通过 _inject_comments() 注入评论系统。
    """
    resource = get_object_or_404(Resource, pk=pk)
    content_html = md.markdown(
        resource.content or '',
        extensions=['fenced_code', 'tables'],
        output_format='html5',
    )
    ctx = {'resource': resource, 'content_html': content_html}
    _inject_comments(request, ctx, resource)
    return render(request, 'club/resource_detail.html', ctx)


@login_required
def resource_download(request, pk):
    """
    文件下载：先给数据库里的 download_count +1，再 redirect 到媒体文件 URL。

    将来接 OSS / CDN 存储时，只需要把这里的 redirect 改成 streaming 响应即可，
    download_count 的更新逻辑不受影响。
    """
    resource = get_object_or_404(Resource, pk=pk)
    if not resource.file:
        messages.error(request, '该资料没有可下载的文件。')
        return redirect('club:resources')
    resource.download_count += 1
    resource.save(update_fields=['download_count'])
    return redirect(resource.file.url)


@login_required
def resource_delete(request, pk):
    """
    删除资料。权限：Staff 或 上传者本人。
    同时删除磁盘上的文件（resource.file.delete(save=False)），避免留下孤立文件。
    """
    resource = get_object_or_404(Resource, pk=pk)
    can_delete = request.user.is_staff or request.user == resource.uploader
    if not can_delete:
        raise Http404()
    if request.method == 'POST':
        title = resource.title
        if resource.file:
            resource.file.delete(save=False)
        resource.delete()
        messages.success(request, f'资料「{title}」已删除。')
        return redirect('club:resources')
    return render(request, 'club/resource_confirm_delete.html', {'resource': resource})
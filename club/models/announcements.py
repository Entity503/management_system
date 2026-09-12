"""
公告域模型
==========
Announcement：公告通知，支持置顶和三级分类。内容使用 Markdown 编写。
"""

from django.contrib.auth.models import User
from django.db import models

from .base import TimeStampedModel


class Announcement(TimeStampedModel):
    """
    公告通知，支持置顶和分类。

    - is_pinned=True 的公告永远排在最前
    - category 用于前端 Tab 筛选
    - content 使用 Markdown 编写，在详情页渲染为 HTML
    """
    CATEGORY_CHOICES = [
        ('general', '综合通知'),
        ('event', '活动通知'),
        ('study', '学习通知'),
    ]
    title = models.CharField('标题', max_length=200)
    content = models.TextField('内容', help_text='支持 Markdown')
    category = models.CharField('分类', max_length=20, choices=CATEGORY_CHOICES, default='general')
    is_pinned = models.BooleanField('置顶', default=False, help_text='置顶公告排在列表最前')
    is_published = models.BooleanField('已发布', default=True)
    published_at = models.DateTimeField('发布时间', null=True, blank=True)
    author = models.ForeignKey(User, on_delete=models.PROTECT, related_name='announcements', help_text='发布者')

    class Meta:
        ordering = ['-is_pinned', '-published_at', '-created_at']
        verbose_name = '公告'
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.title
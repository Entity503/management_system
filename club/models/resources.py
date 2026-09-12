"""
资料域模型
==========
ResourceCategory：与题库共享的 10 个内置分类，迁移 0003 会自动写入初始数据。
Resource：学习资料，支持三种类型（文件/链接/视频）和三级可见性。
"""

from django.contrib.auth.models import User
from django.db import models

from .base import TimeStampedModel


class ResourceCategory(models.Model):
    """
    资料分类（与题库共享的 10 个内置分类）。

    slug 用于 URL 传递，迁移 ``0003_seed_resource_categories`` 会自动写入初始数据。
    """
    name = models.CharField('分类名称', max_length=50, unique=True)
    slug = models.SlugField('Slug', unique=True, help_text='用于 URL，如 data-structure')

    class Meta:
        verbose_name = '资料分类'
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class Resource(TimeStampedModel):
    """
    学习资料。

    支持三种类型：文件上传 / 外部链接 / 视频；
    三级可见性：public（公开）/ member（仅成员）/ admin（仅管理员）。
    content 字段用 Markdown 写详细教程，file 字段上传附件。
    """
    VISIBILITY_CHOICES = [('public', '公开'), ('member', '成员可见'), ('admin', '管理员可见')]
    TYPE_CHOICES = [('file', '文件'), ('link', '链接'), ('video', '视频')]
    title = models.CharField('标题', max_length=200)
    description = models.TextField('简介', blank=True)
    content = models.TextField('详细内容', blank=True, help_text='支持 Markdown，可嵌入代码块')
    category = models.ForeignKey(ResourceCategory, on_delete=models.PROTECT, related_name='resources')
    resource_type = models.CharField('资料类型', max_length=20, choices=TYPE_CHOICES, default='file')
    visibility = models.CharField('可见范围', max_length=20, choices=VISIBILITY_CHOICES, default='public')
    file = models.FileField('文件', upload_to='resources/', blank=True)
    external_url = models.URLField('外部链接', blank=True)
    uploader = models.ForeignKey(User, on_delete=models.PROTECT, related_name='resources')
    download_count = models.PositiveIntegerField('下载次数', default=0)

    class Meta:
        ordering = ['-created_at']
        verbose_name = '学习资料'
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.title
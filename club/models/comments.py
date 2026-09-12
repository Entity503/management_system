"""
通用评论域
==========
Comment：基于 Django ContentType 的 GenericForeignKey，
可挂在 Activity / Announcement / Problem / Resource 四种实体上。
ALLOWED_MODELS 白名单控制可评论范围，views._get_comment_target 会校验。
"""

from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from .base import TimeStampedModel


class Comment(TimeStampedModel):
    """
    通用评论系统。

    使用 Django ContentType 的 GenericForeignKey，
    一条评论可以挂在 Activity / Announcement / Problem / Resource 四种实体上。
    ALLOWED_MODELS 白名单控制可评论的模型范围，views._get_comment_target 会校验。
    """
    ALLOWED_MODELS = ('activity', 'announcement', 'problem', 'resource')

    content = models.TextField('评论内容', max_length=1000)
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comments')
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    target = GenericForeignKey('content_type', 'object_id')

    class Meta:
        ordering = ['-created_at']
        verbose_name = '评论'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f'{self.author}: {self.content[:30]}'
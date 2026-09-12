"""
用户域模型
==========
UserProfile：Django User 的一对一扩展，承载昵称、头像、学号、积分等社团业务字段。
敏感信息（real_name / student_id）前端默认不展示，仅 Admin 可见。
"""

from django.contrib.auth.models import User
from django.db import models

from .base import TimeStampedModel


class UserProfile(TimeStampedModel):
    """
    用户资料（User 的一对一扩展）。

    real_name / student_id 属于敏感信息，前端页面默认只展示 nickname，
    仅管理员可在 Django Admin 中查看真实姓名和学号。
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    real_name = models.CharField('真实姓名', max_length=50, blank=True)
    nickname = models.CharField('昵称', max_length=50, blank=True)
    avatar = models.ImageField('头像', upload_to='avatars/', blank=True)
    student_id = models.CharField('学号', max_length=30, blank=True)
    major = models.CharField('专业', max_length=100, blank=True)
    grade = models.CharField('年级', max_length=20, blank=True)
    skills = models.CharField('技能标签', max_length=255, blank=True, help_text='多个技能用英文逗号分隔')
    points = models.PositiveIntegerField('积分', default=0, help_text='可用于活跃度评估或兑换')

    class Meta:
        verbose_name = '用户资料'
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.nickname or self.user.get_username()
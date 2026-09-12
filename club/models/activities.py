"""
活动域模型
==========
Activity：社团活动，完整的生命周期状态机（草稿 → 报名中 → 已截止 → 已结束）。
ActivitySignup：报名记录，同一用户同一活动唯一约束。
"""

from django.contrib.auth.models import User
from django.db import models
from django.urls import reverse

from .base import TimeStampedModel


class Activity(TimeStampedModel):
    """
    社团活动，完整的生命周期状态机：
        draft（草稿）→ published（报名中）→ closed（已截止）→ finished（已结束）

    signup_deadline 控制报名截止时间，capacity 控制人数上限（超出后进入候补）。
    """
    STATUS_CHOICES = [
        ('draft', '草稿'),
        ('published', '报名中'),
        ('closed', '已截止'),
        ('finished', '已结束'),
    ]
    title = models.CharField('活动名称', max_length=200)
    content = models.TextField('活动详情', help_text='支持 Markdown')
    location = models.CharField('活动地点', max_length=200, blank=True, help_text='留空表示线上活动')
    start_time = models.DateTimeField('开始时间')
    end_time = models.DateTimeField('结束时间')
    signup_deadline = models.DateTimeField('报名截止')
    capacity = models.PositiveIntegerField('人数上限', default=30)
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='draft')
    cover = models.ImageField('封面', upload_to='activities/', blank=True)
    organizer = models.ForeignKey(User, on_delete=models.PROTECT, related_name='organized_activities', help_text='组织者')

    class Meta:
        ordering = ['start_time']
        verbose_name = '活动'
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('club:activity-detail', kwargs={'pk': self.pk})

    @property
    def signup_count(self):
        """返回当前已报名人数（不含已取消的）。"""
        return self.signups.filter(status='active').count()


class ActivitySignup(TimeStampedModel):
    """
    活动报名记录。

    同一用户对同一活动只能有一条报名记录（数据库唯一约束保证）。
    status 有三种：active（已报名）/ cancelled（已取消）/ waitlist（候补）。
    """
    STATUS_CHOICES = [('active', '已报名'), ('cancelled', '已取消'), ('waitlist', '候补')]
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='signups')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activity_signups')
    status = models.CharField('报名状态', max_length=20, choices=STATUS_CHOICES, default='active')
    checked_in_at = models.DateTimeField('签到时间', null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['activity', 'user'], name='unique_activity_signup')]
        verbose_name = '活动报名'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f'{self.user} - {self.activity}'
"""
面试模拟
========
InterviewSession：一场模拟面试，绑定一个 interview 智能体的会话。
InterviewTurn：逐题记录，面试结束后由模型总结生成。

流程：新建面试 → 正常对话（流式）→ 点「结束并生成报告」→ 模型评分 → 报告页。
"""

from django.contrib.auth.models import User
from django.db import models

from .ai import AIConversation
from .base import TimeStampedModel


class InterviewSession(TimeStampedModel):
    """一场模拟面试。"""

    STATUS_CHOICES = [
        ('active', '进行中'),
        ('finished', '已结束'),
    ]
    DIFFICULTY_CHOICES = [
        ('easy', '简单'),
        ('medium', '中等'),
        ('hard', '困难'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='interview_sessions')
    conversation = models.OneToOneField(
        AIConversation, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='interview_session',
    )
    topic = models.CharField('面试方向', max_length=100, default='综合')
    difficulty = models.CharField('难度', max_length=20, choices=DIFFICULTY_CHOICES, default='medium')
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='active')
    score = models.PositiveSmallIntegerField('总分', null=True, blank=True, help_text='0-100')
    summary = models.TextField('综合评价', blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = '模拟面试'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f'{self.user} 的{self.topic}面试'

    @property
    def is_finished(self):
        return self.status == 'finished'


class InterviewTurn(TimeStampedModel):
    """面试中的一问一答与评分。"""
    session = models.ForeignKey(InterviewSession, on_delete=models.CASCADE, related_name='turns')
    index = models.PositiveIntegerField('序号')
    question = models.TextField('问题')
    answer = models.TextField('回答', blank=True)
    score = models.PositiveSmallIntegerField('得分', null=True, blank=True, help_text='0-10')
    feedback = models.TextField('点评', blank=True)

    class Meta:
        ordering = ['index']
        verbose_name = '面试问答'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f'第 {self.index} 题'

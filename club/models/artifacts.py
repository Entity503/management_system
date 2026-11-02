"""
AI 产出物
=========
用户在对话里点「保存」后沉淀下来的个人内容（学习计划、代码评审记录）。

设计上只做"用户自己的东西"，不发布、不共享，所以不需要人工确认草稿流程；
保存动作本身由用户显式点击触发。
"""

from django.contrib.auth.models import User
from django.db import models

from .ai import AIMessage
from .base import TimeStampedModel


class AgentArtifact(TimeStampedModel):
    """AI 生成的个人产出物。"""

    KIND_CHOICES = [
        ('study_plan', '学习计划'),
        ('code_review', '代码评审'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ai_artifacts')
    agent_type = models.CharField('智能体', max_length=30)
    kind = models.CharField('类型', max_length=20, choices=KIND_CHOICES)
    title = models.CharField('标题', max_length=200)
    content = models.TextField('内容（Markdown）')
    message = models.ForeignKey(
        AIMessage, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='artifacts',
        help_text='来源消息，用于避免同一条回复重复保存',
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'AI 产出物'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f'{self.get_kind_display()}：{self.title}'

    @property
    def agent_label(self):
        from ..agents import AGENT_LABELS
        return AGENT_LABELS.get(self.agent_type, self.agent_type)

    @property
    def preview(self):
        text = (self.content or '').strip().replace('\n', ' ')
        return text[:80] + ('…' if len(text) > 80 else '')

"""
AI 域模型
==========
AIConversation：会话，绑定用户 + 智能体角色。
AIMessage：会话中的单条消息，记录 Token 消耗和模型名。
AIQuota：每用户一条配额记录，管理员后台可调。
"""

from django.contrib.auth.models import User
from django.db import models

from ..agents import AGENT_CHOICES
from .base import TimeStampedModel


class AIConversation(TimeStampedModel):
    """
    AI 会话。每个会话绑定一个用户和一个智能体角色，
    消息通过 AIMessage 反向关联。

    AGENT_CHOICES 由 club.agents.AGENT_REGISTRY 派生（单一数据源），
    新增智能体只需改注册表 + 生成迁移。
    """
    AGENT_CHOICES = AGENT_CHOICES
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ai_conversations')
    title = models.CharField('会话标题', max_length=200, blank=True, help_text='首次对话后自动填充')
    agent_type = models.CharField('智能体类型', max_length=30, choices=AGENT_CHOICES, default='club_assistant')
    context_label = models.CharField('上下文标签', max_length=200, blank=True, help_text='如「题目：TCP 三次握手」')
    context_note = models.TextField('上下文内容', blank=True, help_text='从详情页带入的题目/资料内容，注入 System Prompt')

    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'AI 会话'
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.title or f'{self.user} 的 AI 会话'


class AIMessage(TimeStampedModel):
    """
    AI 会话中的单条消息。

    role 取值：system（系统提示）/ user（用户输入）/ assistant（AI 回复）。
    tokens 和 model 记录每次 AI 调用的用量，用于配额统计。
    """
    ROLE_CHOICES = [('system', '系统'), ('user', '用户'), ('assistant', '助手')]
    conversation = models.ForeignKey(AIConversation, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField('角色', max_length=20, choices=ROLE_CHOICES)
    content = models.TextField('内容')
    model = models.CharField('模型', max_length=100, blank=True, help_text='如 deepseek-chat / qwen-plus')
    tokens = models.PositiveIntegerField('Token 数', default=0)
    tool_calls = models.JSONField(
        '工具调用轨迹', default=list, blank=True,
        help_text='[{"name","label","ok","summary"}]，用于刷新后仍能看到 AI 调用了哪些工具',
    )
    FEEDBACK_CHOICES = [('up', '有用'), ('down', '没用')]
    feedback = models.CharField('用户反馈', max_length=10, choices=FEEDBACK_CHOICES, blank=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'AI 消息'
        verbose_name_plural = verbose_name


class AIQuota(models.Model):
    """
    AI 使用配额。每个用户有一条记录，可在管理员后台调整。

    - max_conversations_per_day：每日新建会话上限
    - max_requests_per_day：每日实际调用 AI 接口上限
    - max_conversation_size_mb：单会话体积上限（防止上下文无限增长）
    - total_conversations / total_tokens_used：累计统计（只读）
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='ai_quota')
    max_conversations_per_day = models.PositiveIntegerField('每日新建会话上限', default=10)
    max_requests_per_day = models.PositiveIntegerField('每日 AI 请求上限', default=5)
    max_conversation_size_mb = models.PositiveIntegerField('单会话最大体积 (MB)', default=64)
    total_conversations = models.PositiveIntegerField('累计会话数', default=0)
    total_tokens_used = models.PositiveBigIntegerField('累计消耗 Token', default=0)
    daily_requests = models.PositiveIntegerField('今日请求数', default=0)
    daily_requests_date = models.DateField('请求统计日期', null=True, blank=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = 'AI 使用配额'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f'{self.user} 的 AI 配额'

    @property
    def max_conversation_bytes(self):
        """将 MB 上限转换为字节数，便于直接和 str.encode('utf-8') 长度比较。"""
        return self.max_conversation_size_mb * 1024 * 1024
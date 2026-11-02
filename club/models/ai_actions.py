"""
AI 草稿域模型
==============
AIDraft：AI 生成的内容草稿（题目 / 公告 / 活动），必须由用户确认后才落库。
AIActionLog：AI 写操作的审计日志，记录谁在什么时候确认了什么。

设计原则：AI 输出永远视为不可信输入，
payload 只保存服务端校验、归一化之后的结果，落库时再校验一次。
"""

from django.contrib.auth.models import User
from django.db import models
from django.urls import reverse

from .activities import Activity
from .ai import AIConversation
from .announcements import Announcement
from .base import TimeStampedModel
from .problems import Problem


class AIDraft(TimeStampedModel):
    """AI 生成的内容草稿。status=pending 时需要用户点「确认发布」。"""
    KIND_CHOICES = [
        ('problem', '题目'),
        ('announcement', '公告'),
        ('activity', '活动'),
    ]
    STATUS_CHOICES = [
        ('pending', '待确认'),
        ('applied', '已发布'),
        ('discarded', '已丢弃'),
        ('failed', '校验失败'),
    ]
    SOURCE_CHOICES = [
        ('manual', '人工触发'),
        ('proactive', '主动巡检'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ai_drafts')
    conversation = models.ForeignKey(
        AIConversation, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='drafts',
    )
    kind = models.CharField('草稿类型', max_length=20, choices=KIND_CHOICES)
    payload = models.JSONField('草稿内容', default=dict)
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='pending')
    source = models.CharField('来源', max_length=20, choices=SOURCE_CHOICES, default='manual')
    source_key = models.CharField(
        '去重键', max_length=200, blank=True, db_index=True,
        help_text='主动巡检用，如 activity-start:12，防止重复提醒',
    )
    applied_pk = models.PositiveIntegerField('落库对象 ID', null=True, blank=True)
    error = models.TextField('校验错误', blank=True)
    applied_at = models.DateTimeField('确认时间', null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'AI 草稿'
        verbose_name_plural = verbose_name
        indexes = [models.Index(fields=['user', 'status'], name='club_aidraft_user_status_idx')]

    def __str__(self):
        return f'{self.get_kind_display()}草稿：{self.payload.get("title", "未命名")}'

    # ------------------------------------------------------------------
    # 展示用字段：模板和 AJAX 返回都走这里，避免模板里解析 JSON
    # ------------------------------------------------------------------
    DISPLAY_FIELDS = {
        'problem': [
            ('title', '标题'), ('problem_type', '题型'), ('difficulty', '难度'),
            ('category_name', '模块'), ('answer', '答案'), ('content', '题干'), ('explanation', '解析'),
        ],
        'announcement': [
            ('title', '标题'), ('category', '分类'), ('is_pinned', '置顶'), ('content', '正文'),
        ],
        'activity': [
            ('title', '标题'), ('start_time', '开始'), ('end_time', '结束'),
            ('signup_deadline', '报名截止'), ('location', '地点'), ('capacity', '人数上限'),
            ('status', '状态'), ('content', '详情'),
        ],
    }

    def _display_value(self, key, value):
        """把 payload 里的枚举值/时间/布尔转换成中文，方便直接展示。"""
        if value in (None, ''):
            return '（无）'
        if key == 'problem_type':
            return dict(Problem.TYPE_CHOICES).get(value, value)
        if key == 'difficulty':
            return dict(Problem.DIFFICULTY_CHOICES).get(value, value)
        if key == 'category' and self.kind == 'announcement':
            return dict(Announcement.CATEGORY_CHOICES).get(value, value)
        if key == 'status':
            return dict(Activity.STATUS_CHOICES).get(value, value)
        if key == 'is_pinned':
            return '置顶' if value else '不置顶'
        if key in ('start_time', 'end_time', 'signup_deadline') and isinstance(value, str):
            return value.replace('T', ' ')
        return value

    @property
    def display_title(self):
        return str(self.payload.get('title') or '未命名草稿')

    @property
    def display_fields(self):
        """返回 [(label, value), ...]，已剔除空值的可选项。"""
        rows = []
        for key, label in self.DISPLAY_FIELDS.get(self.kind, []):
            if key not in self.payload:
                continue
            value = self._display_value(key, self.payload.get(key))
            if value in ('（无）', '') and key != 'title':
                continue
            rows.append((label, value))
        return rows

    @property
    def object_url(self):
        """已发布对象的站内链接；未发布返回空字符串。"""
        if not self.applied_pk:
            return ''
        url_name = {
            'problem': 'club:problem-detail',
            'announcement': 'club:announcement-detail',
            'activity': 'club:activity-detail',
        }.get(self.kind)
        if not url_name:
            return ''
        return reverse(url_name, kwargs={'pk': self.applied_pk})

    @property
    def can_apply(self):
        return self.status == 'pending'


class AIActionLog(models.Model):
    """
    AI 写操作审计日志。

    action 取值：draft.create / draft.apply / draft.discard
    detail 存 JSON 字符串（模型原始输出、校验错误、落库对象 ID 等）。
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ai_action_logs')
    action = models.CharField('动作', max_length=40)
    kind = models.CharField('草稿类型', max_length=20, blank=True)
    target_pk = models.PositiveIntegerField('目标对象 ID', null=True, blank=True)
    ok = models.BooleanField('是否成功', default=True)
    detail = models.TextField('详情', blank=True)
    created_at = models.DateTimeField('时间', auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'AI 操作日志'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f'{self.user} {self.action} {self.kind} {"OK" if self.ok else "FAIL"}'

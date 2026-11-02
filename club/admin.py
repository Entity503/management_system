"""
Django Admin 注册配置
======================
把 club 应用里的模型注册到 Django 后台管理界面，方便超级管理员做日常运维操作
（如审核题目、调整 AI 配额、查看活动报名明细等）。

每个 ModelAdmin 里 list_display 控制列表页显示哪些字段，
list_filter 控制右侧筛选器，search_fields 控制顶部搜索框搜索哪些字段。
"""

from django.contrib import admin

from .models import (
    AIActionLog,
    AIConversation,
    AIDraft,
    AIMessage,
    Activity,
    ActivitySignup,
    AgentArtifact,
    Announcement,
    InterviewSession,
    InterviewTurn,
    Problem,
    Resource,
    ResourceCategory,
    Submission,
    Tag,
    UserProfile,
)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """用户资料：支持按真实姓名、昵称、学号搜索——方便管理员线下核对身份。"""
    list_display = ('user', 'real_name', 'nickname', 'major', 'grade', 'points')
    search_fields = ('user__username', 'real_name', 'nickname', 'student_id', 'skills')


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    """公告：按分类/置顶状态快速筛选，支持按发布日期层级下钻。"""
    list_display = ('title', 'category', 'is_pinned', 'is_published', 'author', 'published_at')
    list_filter = ('category', 'is_pinned', 'is_published')
    search_fields = ('title', 'content')
    date_hierarchy = 'published_at'


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    """活动：按状态筛选，按开始日期下钻，快速查看已结束活动的报名情况。"""
    list_display = ('title', 'start_time', 'location', 'status', 'capacity', 'organizer')
    list_filter = ('status',)
    search_fields = ('title', 'location', 'content')
    date_hierarchy = 'start_time'


@admin.register(ActivitySignup)
class ActivitySignupAdmin(admin.ModelAdmin):
    """活动报名明细：管理员可在此手动调整报名状态（候补 / 取消）。"""
    list_display = ('activity', 'user', 'status', 'checked_in_at', 'created_at')
    list_filter = ('status',)
    search_fields = ('activity__title', 'user__username')


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    """学习资料：按分类 / 可见范围筛选，快速调整公开级别。"""
    list_display = ('title', 'category', 'resource_type', 'visibility', 'uploader', 'download_count')
    list_filter = ('resource_type', 'visibility', 'category')
    search_fields = ('title', 'description')


# 简单的模型直接 site.register，不配自定义 Admin
admin.site.register(ResourceCategory)
admin.site.register(Tag)


@admin.register(Problem)
class ProblemAdmin(admin.ModelAdmin):
    """
    题目审核面板：
    - 管理员可以把 is_published=False 的用户提交题目审核后改为 True 发布
    - filter_horizontal 让 tags 多对多编辑更直观（左右穿梭框）
    """
    list_display = ('title', 'problem_type', 'difficulty', 'is_published', 'created_by')
    list_filter = ('problem_type', 'difficulty', 'is_published')
    search_fields = ('title', 'content')
    filter_horizontal = ('tags',)


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    """答题记录：管理员用来复核开放题（简答/综合/代码）的人工判分。"""
    list_display = ('user', 'problem', 'is_correct', 'created_at')
    list_filter = ('is_correct',)
    search_fields = ('user__username', 'problem__title')


@admin.register(AIConversation)
class AIConversationAdmin(admin.ModelAdmin):
    """AI 会话：管理员可以帮用户清理异常会话，查看对话记录。"""
    list_display = ('title', 'user', 'agent_type', 'updated_at')
    list_filter = ('agent_type',)
    search_fields = ('title', 'user__username')


@admin.register(AIMessage)
class AIMessageAdmin(admin.ModelAdmin):
    """AI 消息明细：按角色 / 模型筛选，排查某次 AI 调用的 Token 消耗。"""
    list_display = ('conversation', 'role', 'model', 'tokens', 'created_at')
    list_filter = ('role', 'model')
    search_fields = ('content',)


@admin.register(AIDraft)
class AIDraftAdmin(admin.ModelAdmin):
    """
    AI 草稿：只读巡检用。

    草稿的确认/丢弃只允许草稿本人在站内操作（服务层会校验 user_id），
    这里不提供「一键发布」，避免绕过用户本人的确认。
    """
    list_display = ('id', 'kind', 'status', 'source', 'user', 'created_at', 'applied_pk')
    list_filter = ('kind', 'status', 'source')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('payload', 'error', 'applied_pk', 'applied_at')

    def has_add_permission(self, request):
        return False


@admin.register(AIActionLog)
class AIActionLogAdmin(admin.ModelAdmin):
    """AI 操作审计日志：谁在什么时候确认了什么，只读。"""
    list_display = ('created_at', 'user', 'action', 'kind', 'ok', 'target_pk')
    list_filter = ('action', 'ok', 'kind')
    search_fields = ('user__username', 'detail')
    readonly_fields = ('user', 'action', 'kind', 'target_pk', 'ok', 'detail', 'created_at')

    def has_add_permission(self, request):
        return False


@admin.register(AgentArtifact)
class AgentArtifactAdmin(admin.ModelAdmin):
    """AI 产出物：学习计划 / 代码评审记录，只读巡检。"""
    list_display = ('id', 'kind', 'title', 'user', 'agent_type', 'created_at')
    list_filter = ('kind', 'agent_type')
    search_fields = ('title', 'content', 'user__username')
    readonly_fields = ('message',)


@admin.register(InterviewSession)
class InterviewSessionAdmin(admin.ModelAdmin):
    """模拟面试记录：查看评分与状态。"""
    list_display = ('id', 'topic', 'user', 'difficulty', 'status', 'score', 'created_at')
    list_filter = ('status', 'difficulty')
    search_fields = ('topic', 'user__username')


@admin.register(InterviewTurn)
class InterviewTurnAdmin(admin.ModelAdmin):
    """面试逐题记录。"""
    list_display = ('session', 'index', 'score', 'created_at')
    search_fields = ('question', 'answer')
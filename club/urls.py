"""
club 应用路由表
===============
所有 URL 命名空间都是 ``club``，模板里用 ``{% url 'club:xxx' %}`` 反向解析。
路由风格参考 REST 的资源分层：``资源名/<id>/动作``。

分组结构：
- 首页 & 认证
- 学习资料
- 活动管理
- 刷题中心
- AI 助手
- 公告
- 管理员后台（Staff 专属）
- 通用评论系统（跨模型）
"""

from django.urls import path

from . import views

app_name = 'club'

urlpatterns = [

    # ------------------------------------------------------------------
    # 首页 & 认证
    # ------------------------------------------------------------------
    path('', views.dashboard, name='dashboard'),
    path('register/', views.register, name='register'),
    path('register/send-code/', views.send_register_code, name='send-register-code'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile, name='profile'),

    # ------------------------------------------------------------------
    # 学习资料
    # ------------------------------------------------------------------
    path('resources/', views.resource_list, name='resources'),
    path('resources/upload/', views.resource_upload, name='resource-upload'),
    path('resources/<int:pk>/', views.resource_detail, name='resource-detail'),
    path('resources/<int:pk>/download/', views.resource_download, name='resource-download'),
    path('resources/<int:pk>/delete/', views.resource_delete, name='resource-delete'),

    # ------------------------------------------------------------------
    # 活动管理
    # ------------------------------------------------------------------
    path('activities/', views.activity_list, name='activity-list'),
    path('activities/<int:pk>/', views.activity_detail, name='activity-detail'),
    path('activities/create/', views.activity_create, name='activity-create'),
    path('activities/<int:pk>/edit/', views.activity_edit, name='activity-edit'),
    path('activities/<int:pk>/delete/', views.activity_delete, name='activity-delete'),
    path('activities/<int:pk>/status/', views.activity_change_status, name='activity-status'),

    # ------------------------------------------------------------------
    # 刷题中心（题目）
    # ------------------------------------------------------------------
    path('practice/', views.practice, name='practice'),
    path('practice/create/', views.problem_create, name='problem-create'),
    path('practice/<int:pk>/edit/', views.problem_edit, name='problem-edit'),
    path('practice/<int:pk>/delete/', views.problem_delete, name='problem-delete'),
    path('practice/<int:pk>/', views.problem_detail, name='problem-detail'),

    # ------------------------------------------------------------------
    # AI 助手
    # ------------------------------------------------------------------
    path('ai/', views.ai_chat, name='ai-chat'),
    path('ai/<int:conversation_id>/', views.ai_chat, name='ai-chat-id'),
    path('ai/new/', views.ai_conversation_new, name='ai-new'),
    path('ai/<int:pk>/delete/', views.ai_conversation_delete, name='ai-delete'),
    path('ai/<int:pk>/rename/', views.ai_conversation_rename, name='ai-rename'),
    path('ai/api/send/', views.ai_api_send, name='ai-api-send'),
    path('ai/api/stream/', views.ai_api_stream, name='ai-api-stream'),
    path('ai/api/regenerate/', views.ai_api_regenerate, name='ai-api-regenerate'),
    path('ai/messages/<int:pk>/feedback/', views.ai_message_feedback, name='ai-message-feedback'),

    # 从题目 / 资料详情页带入上下文
    path('ai/explain/<str:kind>/<int:pk>/', views.ai_explain, name='ai-explain'),

    # ------------------------------------------------------------------
    # AI 草稿箱（所有发布都必须由当前登录用户自己确认）
    # ------------------------------------------------------------------
    path('ai/drafts/', views.ai_drafts, name='ai-drafts'),
    path('ai/drafts/<int:pk>/apply/', views.ai_draft_apply, name='ai-draft-apply'),
    path('ai/drafts/<int:pk>/discard/', views.ai_draft_discard, name='ai-draft-discard'),
    path('ai/drafts/<int:pk>/edit/', views.ai_draft_edit, name='ai-draft-edit'),

    # ------------------------------------------------------------------
    # 公告
    # ------------------------------------------------------------------
    path('announcements/', views.announcement_list, name='announcement-list'),
    path('announcements/<int:pk>/', views.announcement_detail, name='announcement-detail'),
    path('announcements/create/', views.announcement_create, name='announcement-create'),
    path('announcements/<int:pk>/edit/', views.announcement_edit, name='announcement-edit'),
    path('announcements/<int:pk>/delete/', views.announcement_delete, name='announcement-delete'),

    # ------------------------------------------------------------------
    # 管理员后台（Staff 专属，不是 Django Admin）
    # ------------------------------------------------------------------
    path('admin/users/', views.admin_users, name='admin-users'),
    path('admin/users/<int:pk>/toggle-staff/', views.admin_toggle_staff, name='admin-toggle-staff'),
    path('admin/users/<int:pk>/delete/', views.admin_user_delete, name='admin-user-delete'),
    path('admin/quotas/', views.admin_quotas, name='admin-quotas'),
    path('admin/quotas/<int:pk>/edit/', views.admin_quota_edit, name='admin-quota-edit'),

    # ------------------------------------------------------------------
    # 通用评论系统（跨模型，通过 POST 参数 model + object_id 路由）
    # ------------------------------------------------------------------
    path('comments/create/', views.comment_create, name='comment-create'),
    path('comments/<int:pk>/delete/', views.comment_delete, name='comment-delete'),
]
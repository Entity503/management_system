"""
club.views 包（re-export 层）
============================
各子模块按业务域拆分，本文件负责统一 re-export，保证外部 import 路径不变。

外部使用方式（完全兼容原 club/views.py）:
    from . import views              → views.dashboard, views.register, ...
    from club.views import dashboard → 直接引用函数
"""

from .activities import (
    STAFF_REQUIRED,
    activity_change_status,
    activity_create,
    activity_delete,
    activity_detail,
    activity_edit,
    activity_list,
)
from .admin import (
    admin_quotas,
    admin_quota_edit,
    admin_toggle_staff,
    admin_user_delete,
    admin_users,
)
from .ai import (
    SUPER_ADMIN_EMAIL,
    _admin_users_query,
    _check_conversation_size,
    _enforce_ai_quota,
    _is_super_admin,
    ai_api_send,
    ai_api_stream,
    ai_chat,
    ai_conversation_delete,
    ai_conversation_new,
    ai_draft_apply,
    ai_draft_discard,
    ai_drafts,
)
from .announcements import (
    announcement_create,
    announcement_delete,
    announcement_detail,
    announcement_edit,
    announcement_list,
)
from .auth import (
    login_view,
    logout_view,
    profile,
    register,
    send_register_code,
)
from .comments import (
    _get_comment_target,
    _get_comments_for,
    _inject_comments,
    comment_create,
    comment_delete,
)
from .dashboard import dashboard
from .problems import (
    practice,
    problem_create,
    problem_delete,
    problem_detail,
    problem_edit,
)
from .resources import (
    resource_delete,
    resource_detail,
    resource_download,
    resource_list,
    resource_upload,
)

__all__ = [
    'STAFF_REQUIRED',
    'SUPER_ADMIN_EMAIL',
    '_admin_users_query',
    '_check_conversation_size',
    '_enforce_ai_quota',
    '_get_comment_target',
    '_get_comments_for',
    '_inject_comments',
    '_is_super_admin',
    'activity_change_status',
    'activity_create',
    'activity_delete',
    'activity_detail',
    'activity_edit',
    'activity_list',
    'admin_quotas',
    'admin_quota_edit',
    'admin_toggle_staff',
    'admin_users',
    'ai_api_send',
    'ai_api_stream',
    'ai_chat',
    'ai_conversation_delete',
    'ai_conversation_new',
    'ai_draft_apply',
    'ai_draft_discard',
    'ai_drafts',
    'announcement_create',
    'announcement_delete',
    'announcement_detail',
    'announcement_edit',
    'announcement_list',
    'comment_create',
    'comment_delete',
    'dashboard',
    'login_view',
    'logout_view',
    'practice',
    'problem_create',
    'problem_delete',
    'problem_detail',
    'problem_edit',
    'profile',
    'register',
    'resource_delete',
    'resource_detail',
    'resource_download',
    'resource_list',
    'resource_upload',
    'send_register_code',
]
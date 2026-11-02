"""
club.models 包（re-export 层）
=============================
各子模块按业务域拆分，本文件负责统一 re-export，保证外部 import 路径不变。

外部使用方式（完全兼容原 club.models.py）:
    from club.models import UserProfile, Activity, Problem, Comment, ...
"""

from .activities import Activity, ActivitySignup
from .ai import AIConversation, AIMessage, AIQuota
from .ai_actions import AIActionLog, AIDraft
from .announcements import Announcement
from .artifacts import AgentArtifact
from .base import TimeStampedModel
from .comments import Comment
from .interviews import InterviewSession, InterviewTurn
from .problems import Problem, ProblemOption, Submission, Tag, _default_category
from .resources import Resource, ResourceCategory
from .user import UserProfile

__all__ = [
    'AIActionLog',
    'AIConversation',
    'AIDraft',
    'AIMessage',
    'AIQuota',
    'Activity',
    'ActivitySignup',
    'AgentArtifact',
    'Announcement',
    'Comment',
    'InterviewSession',
    'InterviewTurn',
    'Problem',
    'ProblemOption',
    'Resource',
    'ResourceCategory',
    'Submission',
    'Tag',
    'TimeStampedModel',
    'UserProfile',
    '_default_category',
]
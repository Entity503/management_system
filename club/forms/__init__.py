"""
club.forms 包（re-export 层）
=============================
各子模块按业务域拆分，本文件负责统一 re-export，保证外部 import 路径不变。

外部使用方式（完全兼容原 club.forms.py）:
    from club.forms import RegisterForm, LoginForm, ActivityForm, ProblemForm, ...
"""

from .activities import ActivityForm
from .auth import LoginForm, RegisterForm
from .problems import ProblemForm, ProblemOptionForm
from .profile import ProfileForm
from .resources import ResourceForm

__all__ = [
    'ActivityForm',
    'LoginForm',
    'ProblemForm',
    'ProblemOptionForm',
    'ProfileForm',
    'RegisterForm',
    'ResourceForm',
]
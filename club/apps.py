"""club 应用配置。default_auto_field 和 verbose_name 都是 Django startproject 默认值。"""

from django.apps import AppConfig


class ClubConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'club'
    verbose_name = '计算机俱乐部'
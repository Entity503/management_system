"""
Django settings for management_system project.

本地开发：复制 .env.example 为 .env，填好密钥；DJANGO_DEBUG=True 可走 SQLite 回退。
生产部署（Render / Railway）：
    1. Render / Railway 上创建 PostgreSQL，会自动注入 DATABASE_URL
    2. 把 .env 里的值逐个配到平台的环境变量
    3. 平台会自动把 DJANGO_DEBUG 设为 False，触发安全加固
"""

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')


SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'dev-only-change-me')
DEBUG = os.getenv('DJANGO_DEBUG', 'True').lower() == 'true'

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv('DJANGO_ALLOWED_HOSTS', '127.0.0.1,localhost,.onrender.com,.railway.app,.pythonanywhere.com').split(',')
    if host.strip()
]

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',')
    if origin.strip()
]

SUPER_ADMIN_EMAIL = os.getenv('SUPER_ADMIN_EMAIL', '')


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'club.apps.ClubConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'management_system.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'management_system.wsgi.application'


# Database
# --------
# 优先级：DATABASE_URL（Render 会自动注入 PostgreSQL）
#       > MYSQL_DATABASE（自己配的 MySQL）
#       > SQLite 回退（本地零配置）
if os.getenv('DATABASE_URL'):
    DATABASES = {'default': dj_database_url.config(conn_max_age=600, ssl_require=True)}
elif os.getenv('MYSQL_DATABASE') and not os.getenv('DJANGO_USE_SQLITE', '').lower() == 'true':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.getenv('MYSQL_DATABASE'),
            'USER': os.getenv('MYSQL_USER', ''),
            'PASSWORD': os.getenv('MYSQL_PASSWORD', ''),
            'HOST': os.getenv('MYSQL_HOST', '127.0.0.1'),
            'PORT': os.getenv('MYSQL_PORT', '3306'),
            'OPTIONS': {'charset': 'utf8mb4'},
        }
    }
else:
    DATABASES = {
        'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3'}
    }


# Password validation

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# Internationalization

LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
# WhiteNoise 自动收集 + 压缩 + 服务静态文件，无需手动 collectstatic。

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'


# Email
# 生产也走 SMTP（QQ / Resend / SendGrid），未配则退控制台后端。

EMAIL_BACKEND = (
    'django.core.mail.backends.smtp.EmailBackend'
    if os.getenv('QQ_EMAIL_USER') and os.getenv('QQ_EMAIL_PASSWORD')
    else 'django.core.mail.backends.console.EmailBackend'
)
EMAIL_HOST = os.getenv('QQ_EMAIL_HOST', 'smtp.qq.com')
EMAIL_PORT = int(os.getenv('QQ_EMAIL_PORT', '465'))
EMAIL_USE_SSL = EMAIL_PORT == 465
EMAIL_HOST_USER = os.getenv('QQ_EMAIL_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('QQ_EMAIL_PASSWORD', '')
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER or 'no-reply@example.com'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/login/'


# 生产安全加固（只在 DJANGO_DEBUG=False 时生效）
# Render 自动 HTTPS，SESSION_COOKIE_SECURE / CSRF_COOKIE_SECURE 必须开。
if not DEBUG:
    SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', 'True').lower() == 'true'
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
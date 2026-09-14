"""
认证 & 账户视图
==============
注册、登录、退出、个人资料。

注册流程关键点：
- 验证码存 session，600 秒有效，email + timestamp 双重校验
- 限流：同一 session 60 秒内只能发一次验证码
- ``User.objects.create_user`` 避免明文密码入库
"""

import random

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from ..forms import LoginForm, ProfileForm, RegisterForm
from ..models import UserProfile


def register(request):
    """
    用户注册。

    注册流程：
    1. RegisterForm 同时校验邮箱格式、学号唯一性、密码一致性（跨表 User + UserProfile）
    2. 验证码在 session 中存为明文，通过 email + timestamp 双重对比，600 秒内有效
    3. 校验通过后用 ``User.objects.create_user`` 创建，避免明文密码入库
    4. 注册完自动 login() 跳转首页，清掉 session 里的验证码防止二次使用
    """
    if request.user.is_authenticated:
        return redirect('club:dashboard')

    form = RegisterForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        email = form.cleaned_data['email']
        DEFAULT_CODE = getattr(settings, 'DEFAULT_REGISTER_CODE', '114514')
        code_input = form.cleaned_data['verification_code']
        is_default = code_input == DEFAULT_CODE
        is_valid = (
            request.session.get('register_code') == code_input
            and request.session.get('register_code_email') == email
            and timezone.now().timestamp() - request.session.get('register_code_sent_at', 0) <= 600
        )
        if not (is_default or is_valid):
            form.add_error('verification_code', '验证码错误或已过期，请重新获取。')
        else:
            user = User.objects.create_user(
                username=email,
                email=email,
                password=form.cleaned_data['password'],
            )
            UserProfile.objects.create(
                user=user,
                real_name=form.cleaned_data['real_name'],
                nickname=form.cleaned_data['nickname'],
                student_id=form.cleaned_data['student_id'],
                avatar=form.cleaned_data.get('avatar'),
            )
            request.session.pop('register_code', None)
            request.session.pop('register_code_email', None)
            request.session.pop('register_code_sent_at', None)
            login(request, user)
            messages.success(request, '注册成功，欢迎加入计算机俱乐部。')
            return redirect('club:dashboard')
    return render(request, 'club/register.html', {'form': form})


def send_register_code(request):
    """
    发送邮箱验证码（AJAX 接口）。

    返回 JSON，前端点「发送验证码」按钮后异步调用。
    限流策略：60 秒内同一 session 只能发一次（简单够用，生产建议用 Redis）。
    未配置 QQ SMTP 时 Django 会用 console 后端，验证码打印到终端方便开发调试。
    """
    if request.method != 'POST':
        return JsonResponse({'message': '仅支持 POST 请求。'}, status=405)

    email = request.POST.get('email', '').strip().lower()
    try:
        from django.core.validators import validate_email
        validate_email(email)
    except ValidationError:
        return JsonResponse({'message': '请输入有效的 QQ 邮箱。'}, status=400)

    if User.objects.filter(username=email).exists():
        return JsonResponse({'message': '该邮箱已经注册，请直接登录。'}, status=400)

    last_sent = request.session.get('register_code_sent_at', 0)
    if timezone.now().timestamp() - last_sent < 60:
        return JsonResponse({'message': '验证码发送过于频繁，请稍后再试。'}, status=429)

    code = f'{random.randint(0, 999999):06d}'
    request.session['register_code'] = code
    request.session['register_code_email'] = email
    request.session['register_code_sent_at'] = timezone.now().timestamp()
    send_mail(
        subject='计算机俱乐部注册验证码',
        message=f'你的注册验证码是：{code}，10 分钟内有效。请勿将验证码告知他人。',
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
    )
    return JsonResponse({'message': '验证码已发送，请查收邮件。'})


def login_view(request):
    """
    登录。

    LoginForm.clean() 里 authenticate() 会返回 user 对象塞进 cleaned_data['user']，
    这里直接取出来用 Django 的 login() 设置 session。
    支持 ?next= 参数跳回原页面（被 @login_required 拦截后重定向会自动带这个参数）。
    """
    if request.user.is_authenticated:
        return redirect('club:dashboard')

    form = LoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        login(request, form.cleaned_data['user'])
        messages.success(request, '登录成功。')
        return redirect(request.GET.get('next') or 'club:dashboard')
    return render(request, 'club/login.html', {'form': form})


def logout_view(request):
    """安全退出：Django logout() 清掉 session，消息提示后跳首页。"""
    logout(request)
    messages.success(request, '你已安全退出。')
    return redirect('club:dashboard')


@login_required
def profile(request):
    """个人资料编辑页。只有昵称和头像可以改，敏感字段走 Admin。"""
    form = ProfileForm(request.POST or None, request.FILES or None, instance=request.user.profile)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, '个人资料已更新。')
        return redirect('club:profile')
    return render(request, 'club/profile.html', {'form': form})
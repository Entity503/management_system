"""
认证表单
========
RegisterForm：注册（纯 Form，非 ModelForm，跨 User + UserProfile 两张表）。
LoginForm：登录，clean() 里 authenticate() 后塞 user 到 cleaned_data。
"""

from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core.validators import validate_email

from club.models import UserProfile


class RegisterForm(forms.Form):
    """
    注册表单（纯 Form，非 ModelForm，因为 User + UserProfile 跨两张表）。

    校验要点：
    - QQ 邮箱：格式合法 + 未被注册（clean_email）
    - 学号：未被占用（clean_student_id）
    - 两次密码一致（clean 整体校验）
    - 验证码校验放在 views.register 中（因为需要 session 里的 code 对比）
    """
    email = forms.EmailField(label='QQ 邮箱', validators=[validate_email])
    real_name = forms.CharField(label='真实姓名', max_length=50)
    student_id = forms.CharField(label='学号', max_length=30)
    nickname = forms.CharField(label='昵称', max_length=50)
    avatar = forms.ImageField(label='头像', required=False)
    verification_code = forms.CharField(label='邮箱验证码', max_length=6, min_length=6)
    password = forms.CharField(label='密码', min_length=8, widget=forms.PasswordInput)
    password_confirm = forms.CharField(label='确认密码', widget=forms.PasswordInput)

    def clean_email(self):
        """小写化 + 去空格 + 检查是否已被注册为 username。"""
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(username=email).exists():
            raise forms.ValidationError('该邮箱已经注册，请直接登录。')
        return email

    def clean_student_id(self):
        """检查学号是否被其他用户占用。"""
        sid = self.cleaned_data['student_id'].strip()
        if UserProfile.objects.filter(student_id=sid).exists():
            raise forms.ValidationError('该学号已被注册。')
        return sid

    def clean(self):
        """整体校验：两次密码输入必须完全一致。"""
        cleaned_data = super().clean()
        if cleaned_data.get('password') != cleaned_data.get('password_confirm'):
            self.add_error('password_confirm', '两次输入的密码不一致。')
        return cleaned_data


class LoginForm(forms.Form):
    """
    登录表单。

    clean() 中 authenticate() 会验证邮箱密码是否匹配，
    校验通过后把 user 对象塞进 cleaned_data['user']，views.login_view 直接取出来 login()。
    """
    email = forms.EmailField(label='QQ 邮箱')
    password = forms.CharField(label='密码', widget=forms.PasswordInput)

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email', '').strip().lower()
        password = cleaned_data.get('password')
        if email and password:
            user = authenticate(username=email, password=password)
            if user is None:
                raise forms.ValidationError('邮箱或密码错误。')
            if not user.is_active:
                raise forms.ValidationError('该账号已被禁用。')
            cleaned_data['user'] = user
        return cleaned_data
"""
个人资料表单
==========
ProfileForm：仅允许修改昵称和头像，敏感字段（真实姓名、学号）通过 Admin 修改。
"""

from django import forms

from club.models import UserProfile


class ProfileForm(forms.ModelForm):
    """个人资料编辑（只允许修改昵称和头像，真实姓名等敏感字段通过 Admin 修改）。"""
    class Meta:
        model = UserProfile
        fields = ('nickname', 'avatar')
        labels = {'nickname': '昵称', 'avatar': '头像'}

    def clean_nickname(self):
        nickname = self.cleaned_data['nickname'].strip()
        if not nickname:
            raise forms.ValidationError('请输入昵称。')
        return nickname
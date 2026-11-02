"""
AI 相关表单
===========
公告草稿没有 ModelForm（公告视图本身是手写 POST），
这里补一个纯 Form，供「草稿编辑后发布」复用。
"""

from django import forms

from ..models import Announcement


class AnnouncementDraftForm(forms.Form):
    """编辑公告草稿用的表单（字段与公告模型一致）。"""
    title = forms.CharField(label='标题', max_length=200)
    content = forms.CharField(label='正文', widget=forms.Textarea(attrs={'rows': 10}))
    category = forms.ChoiceField(label='分类', choices=Announcement.CATEGORY_CHOICES)
    is_pinned = forms.BooleanField(label='置顶', required=False)

    def clean_title(self):
        title = self.cleaned_data['title'].strip()
        if not title:
            raise forms.ValidationError('标题不能为空。')
        return title

    def clean_content(self):
        content = self.cleaned_data['content'].strip()
        if not content:
            raise forms.ValidationError('正文不能为空。')
        return content

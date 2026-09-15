"""
学习资料表单
==========
ResourceForm：资料上传。clean_file() 强校验 1GB 上限，后端兜底不能省。
"""

from django import forms
from django.conf import settings

from club.models import Resource


class ResourceForm(forms.ModelForm):
    """
    学习资料上传表单。

    content 字段带 id='editor-content'，供模板里的 EasyMDE 富文本编辑器挂载。
    clean_file() 强校验 1GB 上限，前端 input 的 accept 属性只是辅助，后端必须兜底。
    """
    class Meta:
        model = Resource
        fields = ('title', 'description', 'content', 'category', 'file', 'visibility')
        labels = {
            'title': '资料名称',
            'description': '资料简介',
            'content': '详细内容',
            'category': '资料分类',
            'file': '上传文件',
            'visibility': '可见范围',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'content': forms.Textarea(attrs={'id': 'editor-content', 'rows': 12}),
        }

    def clean_file(self):
        uploaded_file = self.cleaned_data.get('file')
        if not uploaded_file:
            raise forms.ValidationError('请选择要上传的文件。')
        if uploaded_file.size > settings.RESOURCE_MAX_FILE_SIZE:
            raise forms.ValidationError('单个文件大小不能超过 1 GB。')
        return uploaded_file
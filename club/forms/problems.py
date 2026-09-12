"""
题库表单
========
ProblemForm：题目创建/编辑，两个 Markdown 编辑区挂载 EasyMDE。
ProblemOptionForm：题目选项，用于内联编辑。
"""

from django import forms

from club.models import Problem, ProblemOption


class ProblemOptionForm(forms.ModelForm):
    """题目选项编辑表单，用于题目创建时内联编辑多个选项。"""
    class Meta:
        model = ProblemOption
        fields = ('label', 'content', 'is_correct')
        labels = {'label': '标签', 'content': '选项内容', 'is_correct': '正确答案'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['label'].widget.attrs['placeholder'] = '如 A'
        self.fields['content'].widget.attrs['placeholder'] = '选项文本'


class ProblemForm(forms.ModelForm):
    """
    题目创建 / 编辑表单。

    两个 Markdown 编辑区（content / explanation）分别挂载 EasyMDE，
    题型和难度都用 Model ChoiceField 自动渲染下拉框。
    answer 字段在 placeholder 里写清楚不同题型的填写规范。
    """
    class Meta:
        model = Problem
        fields = ('title', 'content', 'problem_type', 'difficulty', 'category', 'answer', 'explanation')
        labels = {
            'title': '题目标题',
            'content': '题目内容',
            'problem_type': '题型',
            'difficulty': '难度',
            'category': '所属模块',
            'answer': '参考答案',
            'explanation': '答案解析',
        }
        widgets = {
            'content': forms.Textarea(attrs={'id': 'editor-content', 'rows': 10}),
            'explanation': forms.Textarea(attrs={'id': 'editor-explanation', 'rows': 8}),
            'answer': forms.TextInput(attrs={'placeholder': '单选填 A，多选填 A,C（逗号分隔），判断填 T 或 F，填空直接写答案'}),
        }
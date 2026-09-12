"""
活动表单
========
ActivityForm：活动创建/编辑。clean() 整体校验时间逻辑：
结束 > 开始；报名截止 ≤ 开始。
DateTimeInput 统一用 datetime-local 让浏览器渲染原生日期选择器。
"""

from django import forms

from club.models import Activity


class ActivityForm(forms.ModelForm):
    """
    活动创建 / 编辑表单。

    clean() 整体校验时间逻辑：结束时间必须晚于开始时间、报名截止不能晚于开始。
    DateTimeInput 统一用 datetime-local 让浏览器渲染原生日期选择器。
    """
    class Meta:
        model = Activity
        fields = ('title', 'content', 'location', 'start_time', 'end_time', 'signup_deadline', 'capacity', 'status', 'cover')
        labels = {
            'title': '活动名称',
            'content': '活动详情',
            'location': '活动地点',
            'start_time': '开始时间',
            'end_time': '结束时间',
            'signup_deadline': '报名截止时间',
            'capacity': '人数上限',
            'status': '发布状态',
            'cover': '活动封面',
        }
        widgets = {
            'content': forms.Textarea(attrs={'id': 'editor-content', 'rows': 12}),
            'start_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'end_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'signup_deadline': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['start_time'].input_formats = ['%Y-%m-%dT%H:%M']
        self.fields['end_time'].input_formats = ['%Y-%m-%dT%H:%M']
        self.fields['signup_deadline'].input_formats = ['%Y-%m-%dT%H:%M']

    def clean(self):
        """时间逻辑校验：结束 > 开始；报名截止 ≤ 开始。"""
        cleaned = super().clean()
        st = cleaned.get('start_time')
        et = cleaned.get('end_time')
        sd = cleaned.get('signup_deadline')
        if st and et and st >= et:
            self.add_error('end_time', '结束时间必须晚于开始时间。')
        if st and sd and sd > st:
            self.add_error('signup_deadline', '报名截止不能晚于开始时间。')
        return cleaned
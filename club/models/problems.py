"""
题库域模型
==========
Tag：标签，多对多关联 Problem。
ProblemOption：题目选项，多对一归属 Problem。
Problem：题目（核心），支持 7 种题型。
Submission：答题记录，用于错题本和正确率统计。

依赖 resources.ResourceCategory（Problem.category 外键），通过字符串延迟引用规避循环。
"""

from django.contrib.auth.models import User
from django.db import models

from .base import TimeStampedModel
from .resources import ResourceCategory


class Tag(models.Model):
    """题库标签，多对多关联到 Problem。"""
    name = models.CharField('标签', max_length=30, unique=True)

    def __str__(self):
        return self.name


def _default_category():
    """Problem.category 的动态默认值：优先取 slug=other 的分类，避免迁移循环依赖。"""
    cat = ResourceCategory.objects.filter(slug='other').first()
    return cat.pk if cat else None


class ProblemOption(TimeStampedModel):
    """题目选项，多对一归属 Problem。单选题/多选题/判断题均使用此模型。"""
    problem = models.ForeignKey('Problem', on_delete=models.CASCADE, related_name='options')
    label = models.CharField('选项标签', max_length=10, help_text='如 A / B / C / D')
    content = models.TextField('选项内容', help_text='支持 Markdown')
    is_correct = models.BooleanField('是否正确', default=False)

    class Meta:
        verbose_name = '题目选项'
        verbose_name_plural = verbose_name
        ordering = ['label']

    def __str__(self):
        return f'{self.problem.title} - {self.label}'


class Problem(TimeStampedModel):
    """
    题目（核心业务模型之一）。

    - 支持 7 种题型：单选 / 多选 / 判断 / 填空 / 简答 / 综合 / 代码
    - 简答、综合、代码题为开放题，不自动判分，由管理员评判
    - 用户提交的题目默认 is_published=False，需管理员在 Admin 里审核发布
    - answer 字段存参考答案：多选用逗号分隔（如 A,C），判断填 T/F
    """
    TYPE_CHOICES = [
        ('single', '单选题'),
        ('multiple', '多选题'),
        ('judge', '判断题'),
        ('fill', '填空题'),
        ('short_answer', '简答题'),
        ('comprehensive', '综合题'),
        ('code', '代码题'),
    ]
    DIFFICULTY_CHOICES = [('easy', '简单'), ('medium', '中等'), ('hard', '困难')]
    title = models.CharField('题目标题', max_length=200)
    content = models.TextField('题目内容', help_text='支持 Markdown，可嵌入代码块')
    problem_type = models.CharField('题型', max_length=20, choices=TYPE_CHOICES, default='single')
    difficulty = models.CharField('难度', max_length=20, choices=DIFFICULTY_CHOICES, default='easy')
    category = models.ForeignKey(ResourceCategory, on_delete=models.PROTECT, related_name='problems', default=_default_category)
    answer = models.CharField('参考答案', max_length=255, blank=True, help_text='多选题用逗号分隔，如 A,C')
    explanation = models.TextField('解析', blank=True, help_text='支持 Markdown')
    tags = models.ManyToManyField(Tag, blank=True, related_name='problems')
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='problems')
    is_published = models.BooleanField('已发布', default=False, help_text='未发布的题目不会出现在刷题列表')

    class Meta:
        ordering = ['-created_at']
        verbose_name = '题目'
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.title

    @property
    def correct_labels(self):
        """返回所有正确选项的 label 列表，用于前端高亮显示。"""
        return list(self.options.filter(is_correct=True).values_list('label', flat=True))


class Submission(TimeStampedModel):
    """答题记录。每次提交都会创建一条，用于错题本和正确率统计。"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='submissions')
    problem = models.ForeignKey(Problem, on_delete=models.CASCADE, related_name='submissions')
    answer = models.TextField('提交答案')
    is_correct = models.BooleanField('是否正确', default=False, help_text='开放题默认为 False，等管理员评判')

    class Meta:
        verbose_name = '答题记录'
        verbose_name_plural = verbose_name
"""
刷题模块
========
题目列表（三维筛选）、详情 + 在线判分、用户出题、编辑、删除。

判分逻辑分四种情况：
┌──────────────────────┬───────────────────────────────────┐
│ 开放题（简答/综合/代码）│ is_correct=None，留给管理员人工评判   │
│ 填空题                │ 精确字符串比较，忽略大小写            │
│ 多选题                │ 排序后比较（顺序不影响正确性）         │
│ 单选/判断题           │ 精确比较                             │
└──────────────────────┴───────────────────────────────────┘

每次提交都创建一条 Submission 记录，用于错题本和正确率统计。
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

import markdown as md

from ..forms import ProblemForm
from ..models import Problem, ResourceCategory, Submission
from .comments import _inject_comments


@login_required
def practice(request):
    """
    题目列表（刷题中心入口）。

    支持三维筛选：
    - category（10 个学习模块）
    - difficulty（简单 / 中等 / 困难）
    - type（7 种题型）
    annotate(submission_count) 顺带查出每题被提交过多少次，前端可以显示热度。
    """
    problems = Problem.objects.filter(is_published=True).select_related('category', 'created_by__profile').annotate(
        submission_count=Count('submissions')
    )
    category_slug = request.GET.get('category', '').strip()
    difficulty = request.GET.get('difficulty', '').strip()
    problem_type = request.GET.get('type', '').strip()
    if category_slug:
        problems = problems.filter(category__slug=category_slug)
    if difficulty:
        problems = problems.filter(difficulty=difficulty)
    if problem_type:
        problems = problems.filter(problem_type=problem_type)
    context = {
        'problems': problems,
        'categories': ResourceCategory.objects.all(),
        'active_category': category_slug,
        'active_difficulty': difficulty,
        'active_type': problem_type,
    }
    return render(request, 'club/practice.html', context)


@login_required
def problem_detail(request, pk):
    """
    题目详情 + 答题判分。

    判分逻辑见模块顶部文档。
    """
    problem = get_object_or_404(Problem, pk=pk, is_published=True)
    content_html = md.markdown(problem.content or '', extensions=['fenced_code', 'tables'], output_format='html5')
    explanation_html = md.markdown(problem.explanation or '', extensions=['fenced_code', 'tables'], output_format='html5')
    user_answer = None
    is_correct = None
    if request.method == 'POST':
        open_types = ('short_answer', 'comprehensive', 'code')
        if problem.problem_type in open_types:
            user_answer = request.POST.get('open_answer', '').strip()
            is_correct = None
        elif problem.problem_type == 'fill':
            user_answer = request.POST.get('fill_answer', '').strip()
            correct = problem.answer.strip()
            is_correct = user_answer.lower() == correct.lower()
        elif problem.problem_type == 'multiple':
            user_answer = ','.join(sorted(request.POST.getlist('choice')))
            correct = ','.join(sorted(x.strip() for x in problem.answer.split(',') if x.strip()))
            is_correct = user_answer == correct
        else:
            user_answer = request.POST.get('choice', '').strip()
            correct = problem.answer.strip()
            is_correct = user_answer.upper() == correct.upper()
        Submission.objects.create(user=request.user, problem=problem, answer=user_answer, is_correct=is_correct if is_correct is not None else False)
        if is_correct is None:
            messages.success(request, '答案已提交，由管理员评判。')
        else:
            messages.success(request, '提交成功！' if is_correct else '答错了，继续加油。')
    ctx = {
        'problem': problem,
        'content_html': content_html,
        'explanation_html': explanation_html,
        'user_answer': user_answer,
        'is_correct': is_correct,
    }
    _inject_comments(request, ctx, problem)
    return render(request, 'club/problem_detail.html', ctx)


@login_required
def problem_create(request):
    """用户出题。创建者自动记为当前用户，is_published=True（直接发布）。"""
    form = ProblemForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        problem = form.save(commit=False)
        problem.created_by = request.user
        problem.is_published = True
        problem.save()
        messages.success(request, f'题目「{problem.title}」已发布。')
        return redirect('club:problem-detail', pk=problem.pk)
    return render(request, 'club/problem_create.html', {'form': form})


@login_required
def problem_edit(request, pk):
    """题目编辑。权限：Staff 或 创建者本人。"""
    problem = get_object_or_404(Problem, pk=pk)
    can_edit = request.user.is_staff or request.user == problem.created_by
    if not can_edit:
        raise Http404()
    form = ProblemForm(request.POST or None, instance=problem)
    if request.method == 'POST' and form.is_valid():
        problem = form.save()
        messages.success(request, f'题目「{problem.title}」已更新。')
        return redirect('club:problem-detail', pk=problem.pk)
    return render(request, 'club/problem_create.html', {
        'form': form,
        'problem': problem,
        'is_edit': True,
    })


@login_required
def problem_delete(request, pk):
    """题目删除。权限：Staff 或 创建者本人。POST 才真正执行。"""
    problem = get_object_or_404(Problem, pk=pk)
    can_delete = request.user.is_staff or request.user == problem.created_by
    if not can_delete:
        raise Http404()
    if request.method == 'POST':
        title = problem.title
        problem.delete()
        messages.success(request, f'题目「{title}」已删除。')
        return redirect('club:practice')
    return render(request, 'club/problem_confirm_delete.html', {'problem': problem})
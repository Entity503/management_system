"""
首页工作台
========
数据快照：最近公告、即将开始的活动、三个统计数字。
"""

from django.contrib.auth.models import User
from django.shortcuts import render
from django.utils import timezone

from ..models import Activity, Announcement, Problem, Resource


def dashboard(request):
    """
    首页工作台。

    数据快照：
    - 最近 5 条已发布公告（置顶排前）
    - 即将开始的 4 个活动（status=published 且开始时间还没到）
    - 三个统计数字：资料总数、已发布题目数、活跃成员数
    """
    context = {
        'announcements': Announcement.objects.filter(is_published=True)[:5],
        'activities': Activity.objects.filter(
            status='published', start_time__gte=timezone.now()
        ).order_by('start_time')[:4],
        'resource_count': Resource.objects.count(),
        'problem_count': Problem.objects.filter(is_published=True).count(),
        'member_count': User.objects.filter(is_active=True).count(),
    }
    return render(request, 'club/dashboard.html', context)
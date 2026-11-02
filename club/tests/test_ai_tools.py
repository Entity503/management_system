"""
AI 工具与多轮执行器测试
=======================
覆盖：只读查询、建稿权限、参数容错、3 轮上限、tool 消息回填。
"""

import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from club.models import AIDraft, Activity, Problem, ResourceCategory
from club.services.agent_runner import MAX_TOOL_ROUNDS, run_with_tools
from club.services.ai_tools import TOOL_SCHEMAS, execute_tool

from .test_ai_views import text_reply, tool_call_reply


class ToolExecutionTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user('s@example.com', 's@example.com', 'pass12345', is_staff=True)
        self.member = User.objects.create_user('m@example.com', 'm@example.com', 'pass12345')
        self.category = ResourceCategory.objects.get_or_create(
            name='计算机网络', slug='computer-networks',
        )[0]
        ResourceCategory.objects.get_or_create(name='其它', slug='other')

    def test_unknown_tool_is_rejected(self):
        result = execute_tool('rm_rf', '{}', self.staff)
        self.assertFalse(result['ok'])
        self.assertIn('不支持', result['summary'])

    def test_search_activities_excludes_drafts(self):
        now = timezone.now()
        Activity.objects.create(
            title='公开活动', content='x', start_time=now + timedelta(days=1),
            end_time=now + timedelta(days=1, hours=2), signup_deadline=now + timedelta(hours=12),
            capacity=10, status='published', organizer=self.staff,
        )
        Activity.objects.create(
            title='草稿活动', content='x', start_time=now + timedelta(days=3),
            end_time=now + timedelta(days=3, hours=2), signup_deadline=now + timedelta(days=2),
            capacity=10, status='draft', organizer=self.staff,
        )
        result = execute_tool('search_activities', {'time_range': 'upcoming'}, self.member)
        self.assertTrue(result['ok'])
        self.assertEqual(result['data']['total'], 1)
        self.assertEqual(result['data']['items'][0]['title'], '公开活动')

    def test_search_problems_filters_by_keyword_and_category(self):
        Problem.objects.create(
            title='TCP 握手', content='x', problem_type='single', difficulty='easy',
            category=self.category, answer='A', created_by=self.staff, is_published=True,
        )
        Problem.objects.create(
            title='未发布题', content='x', problem_type='single', difficulty='easy',
            category=self.category, answer='A', created_by=self.staff, is_published=False,
        )
        result = execute_tool('search_problems', {'keyword': 'TCP', 'category': '计算机网络'}, self.member)
        self.assertTrue(result['ok'])
        self.assertEqual(len(result['data']['items']), 1)
        self.assertEqual(result['data']['items'][0]['title'], 'TCP 握手')

    def test_platform_stats(self):
        result = execute_tool('platform_stats', {}, self.member)
        self.assertTrue(result['ok'])
        self.assertIn('members', result['data'])

    def test_draft_problem_creates_pending(self):
        result = execute_tool('draft_problem', {
            'title': '题目', 'content': '题干', 'problem_type': 'single',
            'difficulty': 'easy', 'category': '计算机网络', 'answer': 'B',
        }, self.member)
        self.assertTrue(result['ok'])
        draft = result['draft']
        self.assertEqual(draft.status, 'pending')
        self.assertEqual(draft.payload['answer'], 'B')
        self.assertEqual(Problem.objects.count(), 0)

    def test_draft_announcement_requires_staff(self):
        result = execute_tool('draft_announcement', {'title': '公告', 'content': '正文'}, self.member)
        self.assertFalse(result['ok'])
        self.assertIn('只有管理员', result['summary'])
        self.assertEqual(AIDraft.objects.count(), 0)

    def test_malformed_arguments_are_reported(self):
        result = execute_tool('draft_problem', 'not-json', self.member)
        self.assertFalse(result['ok'])
        self.assertIn('校验', result['summary'])
        self.assertEqual(Problem.objects.count(), 0)

    def test_for_model_payload_is_json_string(self):
        result = execute_tool('platform_stats', {}, self.member)
        payload = json.loads(result['for_model'])
        self.assertTrue(payload['ok'])


class AgentRunnerTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user('s@example.com', 's@example.com', 'pass12345', is_staff=True)
        ResourceCategory.objects.get_or_create(name='计算机网络', slug='computer-networks')
        ResourceCategory.objects.get_or_create(name='其它', slug='other')

    def test_tool_round_then_text(self):
        rounds = [
            tool_call_reply('draft_announcement', {'title': '公告 A', 'content': '正文'}),
            text_reply('已生成公告草稿。'),
        ]
        with patch('club.services.agent_runner.ai_service.chat_messages', side_effect=rounds) as mocked:
            result = run_with_tools('ops_assistant', [], '发个公告', '上下文', self.staff)

        self.assertEqual(len(result['tool_trace']), 1)
        self.assertEqual(result['tool_trace'][0]['name'], 'draft_announcement')
        self.assertIsNotNone(result['draft'])
        self.assertEqual(result['content'], '已生成公告草稿。')

        # 第二次调用必须带上 tool 结果消息
        second_messages = mocked.call_args_list[1][0][0]
        tool_messages = [m for m in second_messages if m['role'] == 'tool']
        self.assertEqual(len(tool_messages), 1)
        self.assertEqual(tool_messages[0]['tool_call_id'], 'call_1')

    def test_round_limit_forces_text(self):
        rounds = [tool_call_reply('platform_stats', {}) for _ in range(MAX_TOOL_ROUNDS)]
        rounds.append(text_reply('统计完成。'))
        with patch('club.services.agent_runner.ai_service.chat_messages', side_effect=rounds) as mocked:
            result = run_with_tools('ops_assistant', [], '统计一下', '', self.staff)

        self.assertEqual(len(result['tool_trace']), MAX_TOOL_ROUNDS)
        self.assertEqual(result['content'], '统计完成。')
        # 最后一轮不再传工具
        final_kwargs = mocked.call_args_list[-1][1]
        self.assertNotIn('tools', final_kwargs)

    def test_error_tool_does_not_break_loop(self):
        rounds = [
            tool_call_reply('draft_announcement', {'title': '公告', 'content': '正文'}),
            text_reply('需要管理员权限。'),
        ]
        with patch('club.services.agent_runner.ai_service.chat_messages', side_effect=rounds):
            result = run_with_tools('ops_assistant', [], '发公告', '', self.staff)
        self.assertIsNotNone(result['draft'])

    def test_tool_schemas_are_valid(self):
        for schema in TOOL_SCHEMAS:
            self.assertEqual(schema['type'], 'function')
            function = schema['function']
            self.assertTrue(function['name'])
            self.assertEqual(function['parameters']['type'], 'object')

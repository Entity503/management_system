"""
五个原有智能体的升级测试
========================
覆盖：工具白名单、题目/错题工具、个人产出物、模拟面试全流程。
"""

import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from club.agents import agent_tools
from club.models import (
    AIConversation,
    AIMessage,
    Activity,
    AgentArtifact,
    InterviewSession,
    InterviewTurn,
    Problem,
    ResourceCategory,
    Submission,
)
from club.services.agent_runner import run_with_tools
from club.services.ai_tools import execute_tool

from .test_ai_views import text_reply


class ToolWhitelistTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('u@example.com', 'u@example.com', 'pass12345')

    def test_agent_tools_configuration(self):
        self.assertIn('search_problems', agent_tools('problem_tutor'))
        self.assertIn('draft_problem', agent_tools('problem_tutor'))
        self.assertEqual(agent_tools('code_review'), ())
        self.assertEqual(agent_tools('interview'), ())

    def test_runner_receives_only_allowed_schemas(self):
        with patch(
            'club.services.agent_runner.ai_service.chat_messages',
            return_value=text_reply('好的'),
        ) as mocked:
            run_with_tools(
                'problem_tutor', [], '帮我找道题', '', self.user,
                tool_names=agent_tools('problem_tutor'),
            )

        tools = mocked.call_args.kwargs['tools']
        names = {schema['function']['name'] for schema in tools}
        self.assertEqual(names, {'search_problems', 'get_problem', 'list_my_wrong', 'draft_problem'})


class ProblemToolsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('u@example.com', 'u@example.com', 'pass12345')
        self.category = ResourceCategory.objects.get_or_create(
            name='计算机网络', slug='computer-networks',
        )[0]
        self.problem = Problem.objects.create(
            title='TCP 三次握手', content='为什么要三次握手？', problem_type='single',
            difficulty='medium', category=self.category, answer='A',
            explanation='同步序列号。', created_by=self.user, is_published=True,
        )

    def test_get_problem_detail(self):
        result = execute_tool('get_problem', {'problem_id': self.problem.pk}, self.user)
        self.assertTrue(result['ok'])
        self.assertEqual(result['data']['title'], 'TCP 三次握手')
        self.assertEqual(result['data']['answer'], 'A')

    def test_get_problem_rejects_missing(self):
        result = execute_tool('get_problem', {'problem_id': 99999}, self.user)
        self.assertFalse(result['ok'])

    def test_list_my_wrong(self):
        Submission.objects.create(
            user=self.user, problem=self.problem, answer='B', is_correct=False,
        )
        result = execute_tool('list_my_wrong', {}, self.user)
        self.assertTrue(result['ok'])
        self.assertEqual(result['data']['items'][0]['id'], self.problem.pk)

    def test_wrong_list_is_user_scoped(self):
        other = User.objects.create_user('o@example.com', 'o@example.com', 'pass12345')
        Submission.objects.create(
            user=other, problem=self.problem, answer='B', is_correct=False,
        )
        result = execute_tool('list_my_wrong', {}, self.user)
        self.assertEqual(result['data']['items'], [])


class ClubAssistantToolsTests(TestCase):
    def test_chat_agent_runs_with_tools(self):
        cache.clear()
        user = User.objects.create_user('u@example.com', 'u@example.com', 'pass12345')
        conversation = AIConversation.objects.create(user=user, agent_type='club_assistant')
        self.client.force_login(user)

        with patch(
            'club.services.agent_runner.ai_service.chat_messages',
            return_value=text_reply('这周没有活动。'),
        ) as mocked:
            response = self.client.post(reverse('club:ai-api-send'), {
                'conversation_id': conversation.pk,
                'message': '这周有什么活动？',
            })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        names = {schema['function']['name'] for schema in mocked.call_args.kwargs['tools']}
        self.assertIn('search_activities', names)


class ArtifactTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('u@example.com', 'u@example.com', 'pass12345')
        self.other = User.objects.create_user('o@example.com', 'o@example.com', 'pass12345')
        self.conversation = AIConversation.objects.create(
            user=self.user, agent_type='study_coach', title='学习计划',
        )
        self.message = AIMessage.objects.create(
            conversation=self.conversation,
            role='assistant',
            content='# 八周学习计划\n\n第一周：数据结构基础。',
        )
        self.client.force_login(self.user)

    def test_save_message_creates_artifact(self):
        response = self.client.post(
            reverse('club:ai-message-save', kwargs={'pk': self.message.pk}),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])

        artifact = AgentArtifact.objects.get()
        self.assertEqual(artifact.kind, 'study_plan')
        self.assertEqual(artifact.user, self.user)
        self.assertEqual(artifact.title, '八周学习计划')
        self.assertIn('第一周', artifact.content)

    def test_saving_twice_is_deduplicated(self):
        url = reverse('club:ai-message-save', kwargs={'pk': self.message.pk})
        self.client.post(url)
        response = self.client.post(url)

        self.assertTrue(response.json().get('duplicated'))
        self.assertEqual(AgentArtifact.objects.count(), 1)

    def test_unsupported_agent_rejected(self):
        conversation = AIConversation.objects.create(user=self.user, agent_type='ops_assistant')
        message = AIMessage.objects.create(
            conversation=conversation, role='assistant', content='草稿',
        )
        response = self.client.post(
            reverse('club:ai-message-save', kwargs={'pk': message.pk}),
        )
        self.assertEqual(response.status_code, 400)

    def test_other_user_cannot_save(self):
        self.client.force_login(self.other)
        response = self.client.post(
            reverse('club:ai-message-save', kwargs={'pk': self.message.pk}),
        )
        self.assertEqual(response.status_code, 404)

    def test_artifact_pages(self):
        artifact = AgentArtifact.objects.create(
            user=self.user, agent_type='study_coach', kind='study_plan',
            title='计划', content='# 标题',
        )
        self.assertEqual(self.client.get(reverse('club:ai-artifacts')).status_code, 200)
        self.assertEqual(
            self.client.get(reverse('club:ai-artifact-detail', kwargs={'pk': artifact.pk})).status_code,
            200,
        )


class InterviewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('u@example.com', 'u@example.com', 'pass12345')
        self.other = User.objects.create_user('o@example.com', 'o@example.com', 'pass12345')
        self.client.force_login(self.user)

    def _make_session(self):
        conversation = AIConversation.objects.create(user=self.user, agent_type='interview')
        AIMessage.objects.create(conversation=conversation, role='user', content='我想面试后端')
        AIMessage.objects.create(conversation=conversation, role='assistant', content='请介绍 TCP 三次握手')
        AIMessage.objects.create(conversation=conversation, role='user', content='用于同步序列号')
        return InterviewSession.objects.create(
            user=self.user, conversation=conversation, topic='后端开发', difficulty='medium',
        )

    def test_start_creates_session_and_conversation(self):
        response = self.client.post(reverse('club:ai-interview-start'), {
            'topic': '后端开发', 'difficulty': 'hard',
        })
        self.assertEqual(response.status_code, 302)

        session = InterviewSession.objects.get()
        self.assertEqual(session.topic, '后端开发')
        self.assertEqual(session.difficulty, 'hard')
        self.assertEqual(session.conversation.agent_type, 'interview')
        self.assertIn('模拟面试', session.conversation.context_note)

    def test_finish_saves_report(self):
        session = self._make_session()
        report = {
            'score': 82,
            'summary': '整体不错，基础扎实。',
            'turns': [
                {'question': 'TCP 三次握手？', 'answer': '同步序列号', 'score': 8, 'feedback': '基本正确'},
            ],
        }
        with patch(
            'club.views.ai.ai_service.chat_messages',
            return_value=text_reply(json.dumps(report, ensure_ascii=False)),
        ):
            response = self.client.post(
                reverse('club:ai-interview-finish', kwargs={'pk': session.pk}),
            )

        self.assertEqual(response.status_code, 302)
        session.refresh_from_db()
        self.assertEqual(session.status, 'finished')
        self.assertEqual(session.score, 82)
        self.assertEqual(session.turns.count(), 1)
        self.assertEqual(InterviewTurn.objects.get().score, 8)

        detail = self.client.get(reverse('club:ai-interview-detail', kwargs={'pk': session.pk}))
        self.assertContains(detail, '82')

    def test_finish_with_bad_report_keeps_session_active(self):
        session = self._make_session()
        with patch(
            'club.views.ai.ai_service.chat_messages',
            return_value=text_reply('这不是 JSON'),
        ):
            self.client.post(reverse('club:ai-interview-finish', kwargs={'pk': session.pk}))

        session.refresh_from_db()
        self.assertEqual(session.status, 'active')
        self.assertEqual(session.turns.count(), 0)

    def test_other_user_cannot_view(self):
        session = self._make_session()
        self.client.force_login(self.other)
        response = self.client.get(
            reverse('club:ai-interview-detail', kwargs={'pk': session.pk}),
        )
        self.assertEqual(response.status_code, 404)

    def test_pages_render(self):
        self.assertEqual(self.client.get(reverse('club:ai-interviews')).status_code, 200)
        session = self._make_session()
        self.assertEqual(
            self.client.get(reverse('club:ai-interview-detail', kwargs={'pk': session.pk})).status_code,
            200,
        )

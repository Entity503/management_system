"""
AI 增强功能测试
================
覆盖：详情页带上下文建会话、草稿编辑、重新生成、重命名、反馈、按智能体温度。
"""

import json
import re
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import RequestFactory, TestCase
from django.urls import reverse

from club import ai_service
from club.models import (
    AIConversation,
    AIDraft,
    AIMessage,
    Activity,
    Problem,
    Resource,
    ResourceCategory,
)
from club.services.ai_actions import create_draft

from .test_ai_views import parse_sse, text_reply


class BaseAITestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.staff = User.objects.create_user('s@example.com', 's@example.com', 'pass12345', is_staff=True)
        self.category = ResourceCategory.objects.get_or_create(
            name='计算机网络', slug='computer-networks',
        )[0]
        ResourceCategory.objects.get_or_create(name='其它', slug='other')

    def problem(self):
        return Problem.objects.create(
            title='TCP 三次握手', content='为什么需要三次握手？', problem_type='single',
            difficulty='medium', category=self.category, answer='A',
            explanation='同步序列号。', created_by=self.staff, is_published=True,
        )


class ExplainContextTests(BaseAITestCase):
    def test_problem_explain_creates_context_conversation(self):
        problem = self.problem()
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse('club:ai-explain', kwargs={'kind': 'problem', 'pk': problem.pk}),
        )
        self.assertEqual(response.status_code, 302)
        conversation = AIConversation.objects.get()
        self.assertEqual(conversation.agent_type, 'problem_tutor')
        self.assertIn(problem.title, conversation.context_label)
        self.assertIn('为什么需要三次握手', conversation.context_note)
        self.assertIn('参考答案', conversation.context_note)
        self.assertIn('先给一级提示', conversation.context_note)

    def test_resource_explain(self):
        resource = Resource.objects.create(
            title='TCP 入门', description='基础', content='三次握手与四次挥手',
            category=self.category, uploader=self.staff,
        )
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse('club:ai-explain', kwargs={'kind': 'resource', 'pk': resource.pk}),
        )
        self.assertEqual(response.status_code, 302)
        conversation = AIConversation.objects.get()
        self.assertEqual(conversation.agent_type, 'study_coach')
        self.assertIn('三次握手与四次挥手', conversation.context_note)

    def test_unknown_kind_404(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse('club:ai-explain', kwargs={'kind': 'activity', 'pk': 1}),
        )
        self.assertEqual(response.status_code, 404)

    def test_context_shows_in_chat_page(self):
        problem = self.problem()
        self.client.force_login(self.staff)
        self.client.post(reverse('club:ai-explain', kwargs={'kind': 'problem', 'pk': problem.pk}))
        conversation = AIConversation.objects.get()
        response = self.client.get(
            reverse('club:ai-chat-id', kwargs={'conversation_id': conversation.pk}),
        )
        self.assertContains(response, 'chat-context')
        self.assertContains(response, '题目：TCP 三次握手')


class DraftEditTests(BaseAITestCase):
    def _problem_draft(self):
        return create_draft(self.staff, 'problem', {
            'title': '原题目', 'content': '题干', 'problem_type': 'single',
            'difficulty': 'easy', 'category': '计算机网络', 'answer': 'A',
        })

    def test_edit_updates_payload_but_not_published(self):
        draft = self._problem_draft()
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse('club:ai-draft-edit', kwargs={'pk': draft.pk}),
            {
                'title': '改过的题目',
                'content': '新题干',
                'problem_type': 'single',
                'difficulty': 'hard',
                'category': self.category.pk,
                'answer': 'B',
                'explanation': '新解析',
            },
        )
        self.assertEqual(response.status_code, 302)
        draft.refresh_from_db()
        self.assertEqual(draft.payload['title'], '改过的题目')
        self.assertEqual(draft.payload['difficulty'], 'hard')
        self.assertEqual(draft.payload['answer'], 'B')
        self.assertEqual(draft.status, 'pending')
        self.assertEqual(Problem.objects.count(), 0)

    def test_invalid_edit_keeps_original(self):
        draft = self._problem_draft()
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse('club:ai-draft-edit', kwargs={'pk': draft.pk}),
            {
                'title': '', 'content': '题干', 'problem_type': 'single',
                'difficulty': 'easy', 'category': self.category.pk, 'answer': 'A',
            },
        )
        self.assertEqual(response.status_code, 200)
        draft.refresh_from_db()
        self.assertEqual(draft.payload['title'], '原题目')

    def test_activity_edit_validates_time(self):
        draft = create_draft(self.staff, 'activity', {
            'title': '活动', 'content': '内容',
            'start_time': '2026-11-07T19:00', 'end_time': '2026-11-07T21:00',
            'signup_deadline': '2026-11-06T18:00', 'capacity': 30, 'status': 'draft',
        })
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse('club:ai-draft-edit', kwargs={'pk': draft.pk}),
            {
                'title': '活动', 'content': '内容', 'location': '',
                'start_time': '2026-11-07T21:00', 'end_time': '2026-11-07T19:00',
                'signup_deadline': '2026-11-06T18:00', 'capacity': 30, 'status': 'draft',
            },
        )
        self.assertEqual(response.status_code, 200)
        draft.refresh_from_db()
        self.assertEqual(draft.payload['start_time'], '2026-11-07T19:00')

    def test_other_user_cannot_edit(self):
        draft = self._problem_draft()
        other = User.objects.create_user('o@example.com', 'o@example.com', 'pass12345')
        self.client.force_login(other)
        response = self.client.get(reverse('club:ai-draft-edit', kwargs={'pk': draft.pk}))
        self.assertEqual(response.status_code, 404)

    def test_applied_draft_cannot_be_edited(self):
        draft = self._problem_draft()
        draft.status = 'applied'
        draft.save(update_fields=['status'])
        self.client.force_login(self.staff)
        response = self.client.get(reverse('club:ai-draft-edit', kwargs={'pk': draft.pk}))
        self.assertEqual(response.status_code, 302)


class ConversationOpsTests(BaseAITestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.staff)
        self.conversation = AIConversation.objects.create(user=self.staff, agent_type='club_assistant')

    def test_rename(self):
        response = self.client.post(
            reverse('club:ai-rename', kwargs={'pk': self.conversation.pk}),
            {'title': '新标题'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.title, '新标题')

    def test_rename_rejects_empty(self):
        response = self.client.post(
            reverse('club:ai-rename', kwargs={'pk': self.conversation.pk}), {'title': '   '},
        )
        self.assertEqual(response.status_code, 400)

    def test_regenerate_replaces_last_pair(self):
        AIMessage.objects.create(conversation=self.conversation, role='user', content='旧问题')
        AIMessage.objects.create(conversation=self.conversation, role='assistant', content='旧回答')

        with patch('club.views.ai.ai_service.chat', return_value=text_reply('新回答')):
            response = self.client.post(
                reverse('club:ai-api-regenerate'),
                {'conversation_id': self.conversation.pk},
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertTrue(data.get('regenerated'))
        contents = list(
            self.conversation.messages.order_by('created_at').values_list('role', 'content')
        )
        self.assertNotIn(('assistant', '旧回答'), contents)
        self.assertIn(('assistant', '新回答'), contents)
        self.assertIn(('user', '旧问题'), contents)

    def test_regenerate_without_question_fails(self):
        response = self.client.post(
            reverse('club:ai-api-regenerate'), {'conversation_id': self.conversation.pk},
        )
        self.assertEqual(response.status_code, 400)

    def test_feedback_toggle(self):
        message = AIMessage.objects.create(
            conversation=self.conversation, role='assistant', content='回答',
        )
        url = reverse('club:ai-message-feedback', kwargs={'pk': message.pk})
        first = self.client.post(url, {'value': 'up'})
        self.assertEqual(first.json()['feedback'], 'up')
        message.refresh_from_db()
        self.assertEqual(message.feedback, 'up')

        second = self.client.post(url, {'value': 'up'})
        self.assertEqual(second.json()['feedback'], '')
        message.refresh_from_db()
        self.assertEqual(message.feedback, '')

    def test_cannot_feedback_others_message(self):
        other = User.objects.create_user('x@example.com', 'x@example.com', 'pass12345')
        conversation = AIConversation.objects.create(user=other, agent_type='club_assistant')
        message = AIMessage.objects.create(conversation=conversation, role='assistant', content='回答')
        response = self.client.post(
            reverse('club:ai-message-feedback', kwargs={'pk': message.pk}), {'value': 'up'},
        )
        self.assertEqual(response.status_code, 404)


class TemperatureTests(TestCase):
    def test_each_agent_has_its_own_temperature(self):
        with patch('club.ai_service.chat_messages', return_value=text_reply('ok')) as mocked:
            ai_service.chat('code_review', [], '看看代码')
            self.assertEqual(mocked.call_args.kwargs['temperature'], 0.2)

        with patch('club.ai_service.chat_messages', return_value=text_reply('ok')) as mocked:
            ai_service.chat('study_coach', [], '帮我规划')
            self.assertEqual(mocked.call_args.kwargs['temperature'], 0.7)

    def test_tool_agent_temperature(self):
        from club.agents import agent_temperature

        self.assertEqual(agent_temperature('ops_assistant'), 0.3)
        self.assertEqual(agent_temperature('unknown'), 0.7)

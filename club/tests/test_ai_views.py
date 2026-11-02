"""
AI 视图层测试
==============
覆盖：工具型建稿链路、只读工具、流式输出、权限、冷却、页面渲染。
所有 AI 调用都 mock，不会真的请求 DeepSeek / 百炼。
"""

import json
import re
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from club.models import AIDraft, Activity, Announcement, Problem, ResourceCategory


def tool_call_reply(name, arguments, call_id='call_1'):
    return {
        'content': '',
        'tool_calls': [{
            'id': call_id,
            'type': 'function',
            'function': {'name': name, 'arguments': json.dumps(arguments, ensure_ascii=False)},
        }],
        'model': 'deepseek-chat',
        'tokens': 12,
        'provider': 'deepseek',
    }


def text_reply(text, tokens=8):
    return {
        'content': text,
        'tool_calls': [],
        'model': 'deepseek-chat',
        'tokens': tokens,
        'provider': 'deepseek',
    }


def parse_sse(response):
    """把 StreamingHttpResponse 解析成事件列表。"""
    body = b''.join(response.streaming_content).decode('utf-8')
    events = []
    for block in body.split('\n\n'):
        block = block.strip()
        if block.startswith('data: '):
            events.append(json.loads(block[len('data: '):]))
    return events


class OpsDraftFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.staff = User.objects.create_user(
            'staff@example.com', 'staff@example.com', 'pass12345', is_staff=True,
        )
        self.member = User.objects.create_user('member@example.com', 'member@example.com', 'pass12345')
        self.other = User.objects.create_user('other@example.com', 'other@example.com', 'pass12345')
        ResourceCategory.objects.get_or_create(name='计算机网络', slug='computer-networks')
        ResourceCategory.objects.get_or_create(name='其它', slug='other')

    def _new_conversation(self, agent='ops_assistant'):
        response = self.client.post(reverse('club:ai-new'), {'agent_type': agent})
        self.assertEqual(response.status_code, 302)
        match = re.search(r'/ai/(\d+)/', response.url)
        self.assertIsNotNone(match, response.url)
        return int(match.group(1))

    def _send(self, conversation_id, message='帮我发个公告'):
        return self.client.post(reverse('club:ai-api-send'), {
            'conversation_id': conversation_id,
            'message': message,
        })

    def test_staff_creates_announcement_draft_via_tool(self):
        self.client.force_login(self.staff)
        conversation_id = self._new_conversation()

        rounds = [
            tool_call_reply('draft_announcement', {
                'title': '测试公告', 'content': '正文', 'category': 'general',
            }),
            text_reply('已生成公告草稿，请确认后发布。'),
        ]
        with patch('club.services.agent_runner.ai_service.chat_messages', side_effect=rounds):
            response = self._send(conversation_id)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['tools'][0]['name'], 'draft_announcement')
        self.assertTrue(data['tools'][0]['ok'])
        self.assertIn('draft', data)
        self.assertEqual(Announcement.objects.count(), 0)  # 确认前不落库

        draft = AIDraft.objects.get(pk=data['draft']['id'])
        self.assertEqual(draft.status, 'pending')
        self.assertEqual(draft.user, self.staff)

    def test_tool_draft_applies_after_confirm(self):
        self.client.force_login(self.staff)
        conversation_id = self._new_conversation()
        rounds = [
            tool_call_reply('draft_announcement', {'title': '待确认', 'content': '正文'}),
            text_reply('请确认。'),
        ]
        with patch('club.services.agent_runner.ai_service.chat_messages', side_effect=rounds):
            draft_id = self._send(conversation_id).json()['draft']['id']

        response = self.client.post(
            reverse('club:ai-draft-apply', kwargs={'pk': draft_id}),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Announcement.objects.filter(title='待确认', is_published=True).exists())

    def test_member_cannot_create_announcement_draft(self):
        self.client.force_login(self.member)
        conversation_id = self._new_conversation()

        rounds = [
            tool_call_reply('draft_announcement', {'title': '公告', 'content': '正文'}),
            text_reply('只有管理员可以发布公告。'),
        ]
        with patch('club.services.agent_runner.ai_service.chat_messages', side_effect=rounds):
            response = self._send(conversation_id, '帮我发个公告')

        data = response.json()
        self.assertTrue(data['ok'])
        self.assertNotIn('draft', data)
        self.assertFalse(data['tools'][0]['ok'])
        self.assertIn('只有管理员', data['tools'][0]['summary'])
        self.assertEqual(AIDraft.objects.count(), 0)

    def test_member_can_create_problem_draft(self):
        self.client.force_login(self.member)
        conversation_id = self._new_conversation()
        rounds = [
            tool_call_reply('draft_problem', {
                'title': 'TCP 三次握手', 'content': '题干', 'problem_type': 'single',
                'difficulty': 'medium', 'category': '计算机网络', 'answer': 'A',
            }),
            text_reply('已生成题目草稿。'),
        ]
        with patch('club.services.agent_runner.ai_service.chat_messages', side_effect=rounds):
            response = self._send(conversation_id, '帮我出个题')

        self.assertIn('draft', response.json())
        draft = AIDraft.objects.get()
        self.assertEqual(draft.kind, 'problem')

        self.client.post(
            reverse('club:ai-draft-apply', kwargs={'pk': draft.pk}),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertTrue(Problem.objects.get().is_published)

    def test_read_tool_returns_activities(self):
        self.client.force_login(self.staff)
        Activity.objects.create(
            title='周末分享会', content='内容', start_time=timezone.now() + timedelta(days=2),
            end_time=timezone.now() + timedelta(days=2, hours=2),
            signup_deadline=timezone.now() + timedelta(days=1),
            capacity=30, status='published', organizer=self.staff,
        )
        conversation_id = self._new_conversation()
        rounds = [
            tool_call_reply('search_activities', {'time_range': 'upcoming'}),
            text_reply('这周有一场：周末分享会。'),
        ]
        with patch('club.services.agent_runner.ai_service.chat_messages', side_effect=rounds) as mocked:
            response = self._send(conversation_id, '这周有什么活动？')

        data = response.json()
        self.assertEqual(data['tools'][0]['name'], 'search_activities')
        self.assertIn('查到', data['tools'][0]['summary'])
        self.assertIn('周末分享会', data['content'])
        # 最后一次请求里应包含 tool 结果消息
        last_messages = mocked.call_args_list[-1][0][0]
        self.assertTrue(any(m['role'] == 'tool' for m in last_messages))

    def test_json_fallback_when_model_ignores_tools(self):
        """模型不支持 function calling 时，仍能按旧 JSON 协议建稿。"""
        self.client.force_login(self.staff)
        conversation_id = self._new_conversation()
        raw = json.dumps({
            'kind': 'announcement',
            'payload': {'title': '兜底公告', 'content': '正文', 'category': 'general'},
        }, ensure_ascii=False)
        with patch('club.services.agent_runner.ai_service.chat_messages',
                   return_value=text_reply(f'```json\n{raw}\n```')):
            response = self._send(conversation_id)

        data = response.json()
        self.assertIn('draft', data)
        self.assertEqual(AIDraft.objects.get().status, 'pending')

    def test_other_user_cannot_apply(self):
        self.client.force_login(self.staff)
        conversation_id = self._new_conversation()
        rounds = [
            tool_call_reply('draft_announcement', {'title': '测试', 'content': '正文'}),
            text_reply('请确认。'),
        ]
        with patch('club.services.agent_runner.ai_service.chat_messages', side_effect=rounds):
            draft_id = self._send(conversation_id).json()['draft']['id']

        self.client.force_login(self.other)
        response = self.client.post(
            reverse('club:ai-draft-apply', kwargs={'pk': draft_id}),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Announcement.objects.count(), 0)

    def test_cooldown_blocks_rapid_requests(self):
        self.client.force_login(self.staff)
        conversation_id = self._new_conversation()
        with patch('club.services.agent_runner.ai_service.chat_messages',
                   return_value=text_reply('好的。')):
            first = self._send(conversation_id, '第一条')
            second = self._send(conversation_id, '第二条')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)

    def test_ai_failure_returns_friendly_error(self):
        self.client.force_login(self.staff)
        conversation_id = self._new_conversation()
        with patch('club.services.agent_runner.ai_service.chat_messages',
                   side_effect=RuntimeError('boom')):
            response = self._send(conversation_id)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['ok'])
        self.assertNotIn('boom', data['error'])


class StreamTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('stream@example.com', 'stream@example.com', 'pass12345')

    def _new_conversation(self, agent='code_review'):
        response = self.client.post(reverse('club:ai-new'), {'agent_type': agent})
        match = re.search(r'/ai/(\d+)/', response.url)
        return int(match.group(1))

    def test_stream_deltas_and_done(self):
        self.client.force_login(self.user)
        conversation_id = self._new_conversation()

        def fake_stream(messages):
            yield 'delta', '你好'
            yield 'delta', '，世界'
            yield 'done', {'model': 'deepseek-chat', 'tokens': 5}

        with patch('club.views.ai.ai_service.stream_messages', side_effect=fake_stream):
            response = self.client.post(reverse('club:ai-api-stream'), {
                'conversation_id': conversation_id, 'message': '你好',
            })
            # 流式响应是惰性的：必须在 patch 生效期间消费
            events = parse_sse(response)

        self.assertEqual(response.status_code, 200)
        types = [event['type'] for event in events]
        self.assertEqual(types[0], 'start')
        self.assertEqual(types[-1], 'done')
        text = ''.join(event['text'] for event in events if event['type'] == 'delta')
        self.assertEqual(text, '你好，世界')

        from club.models import AIMessage
        assistant = AIMessage.objects.filter(conversation_id=conversation_id, role='assistant').get()
        self.assertEqual(assistant.content, '你好，世界')

    def test_stream_tool_agent_emits_tool_and_draft(self):
        self.client.force_login(self.user)
        self.user.is_staff = True
        self.user.save(update_fields=['is_staff'])
        conversation_id = self._new_conversation(agent='ops_assistant')

        rounds = [
            tool_call_reply('draft_announcement', {'title': '流式公告', 'content': '正文'}),
            text_reply('已生成公告草稿。'),
        ]
        with patch('club.services.agent_runner.ai_service.chat_messages', side_effect=rounds):
            response = self.client.post(reverse('club:ai-api-stream'), {
                'conversation_id': conversation_id, 'message': '发个公告',
            })
            events = parse_sse(response)

        types = [event['type'] for event in events]
        self.assertIn('tool', types)
        self.assertIn('delta', types)
        done = events[-1]
        self.assertEqual(done['type'], 'done')
        self.assertIn('draft', done)
        self.assertEqual(AIDraft.objects.get().status, 'pending')

    def test_stream_requires_post(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('club:ai-api-stream'))
        self.assertEqual(response.status_code, 405)


class DraftPagesTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('u@example.com', 'u@example.com', 'pass12345')
        self.client.force_login(self.user)

    def test_chat_page_renders(self):
        response = self.client.get(reverse('club:ai-chat'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '运营助手')

    def test_drafts_page_renders(self):
        response = self.client.get(reverse('club:ai-drafts'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'AI 草稿箱')
        self.assertContains(response, 'csrfmiddlewaretoken')

    def test_conversation_page_renders_with_pending_draft(self):
        from club.models import AIConversation, AIMessage

        conversation = AIConversation.objects.create(user=self.user, agent_type='ops_assistant')
        AIDraft.objects.create(
            user=self.user, conversation=conversation, kind='announcement',
            payload={'title': '待确认公告', 'content': '正文', 'category': 'general', 'is_pinned': False},
        )
        AIMessage.objects.create(
            conversation=conversation, role='assistant', content='已查询',
            tool_calls=[{'name': 'search_activities', 'label': '查询活动', 'ok': True, 'summary': '查到 2 场活动'}],
        )
        response = self.client.get(reverse('club:ai-chat-id', kwargs={'conversation_id': conversation.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '待确认公告')
        self.assertContains(response, '确认发布')
        self.assertContains(response, '查询活动')

    def test_api_send_rejects_get(self):
        response = self.client.get(reverse('club:ai-api-send'))
        self.assertEqual(response.status_code, 405)

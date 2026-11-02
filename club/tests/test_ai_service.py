"""AI 服务层纯函数测试：消息组装与 SSE 解析。"""

from django.test import SimpleTestCase

from club.ai_service import _iter_stream_chunks, build_messages


class FakeStreamResponse:
    def __init__(self, lines):
        self._lines = lines

    def iter_lines(self):
        return iter(self._lines)


class BuildMessagesTests(SimpleTestCase):
    class FakeMessage:
        def __init__(self, role, content):
            self.role = role
            self.content = content

    def test_system_prompt_and_context(self):
        messages = build_messages(
            'club_assistant', [], '你好', context='【平台当前状态】测试上下文',
        )
        self.assertEqual(messages[0]['role'], 'system')
        self.assertIn('社团助手', messages[0]['content'])
        self.assertIn('【平台当前状态】', messages[0]['content'])
        self.assertEqual(messages[-1], {'role': 'user', 'content': '你好'})

    def test_history_is_appended_in_order(self):
        history = [
            self.FakeMessage('user', '第一句'),
            self.FakeMessage('assistant', '第一答'),
        ]
        messages = build_messages('study_coach', history, '第二句')
        self.assertEqual([m['role'] for m in messages], ['system', 'user', 'assistant', 'user'])
        self.assertEqual(messages[1]['content'], '第一句')
        self.assertEqual(messages[2]['content'], '第一答')

    def test_unknown_agent_falls_back(self):
        messages = build_messages('not_an_agent', [], 'hi')
        self.assertIn('社团助手', messages[0]['content'])


class StreamParserTests(SimpleTestCase):
    def test_decodes_utf8_bytes(self):
        lines = [
            b'',
            b'data: {"model":"deepseek-chat","choices":[{"delta":{"content":"\xe4\xbd\xa0"}}]}',
            b'data: {"choices":[{"delta":{"content":"\xe5\xa5\xbd"}}]}',
            b'data: [DONE]',
        ]
        events = list(_iter_stream_chunks(FakeStreamResponse(lines), 'deepseek-chat'))
        self.assertEqual(events[0], ('delta', '你'))
        self.assertEqual(events[1], ('delta', '好'))
        self.assertEqual(events[-1][0], 'done')
        self.assertEqual(events[-1][1]['model'], 'deepseek-chat')

    def test_skips_invalid_lines(self):
        lines = [b': keep-alive', b'data: not-json', b'data: {"choices":[]}']
        events = list(_iter_stream_chunks(FakeStreamResponse(lines), 'x'))
        self.assertEqual(events, [('done', {'model': 'x', 'tokens': 0})])

    def test_usage_is_captured(self):
        lines = [
            b'data: {"choices":[{"delta":{"content":"a"}}]}',
            b'data: {"choices":[],"usage":{"total_tokens":42}}',
            b'data: [DONE]',
        ]
        events = list(_iter_stream_chunks(FakeStreamResponse(lines), 'x'))
        self.assertEqual(events[-1][1]['tokens'], 42)

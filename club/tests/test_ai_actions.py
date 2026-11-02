"""
AI 草稿服务层测试
=================
覆盖：JSON 提取、三类草稿的校验/归一化、权限、确认落库、重复操作。
全部使用 Django TestCase（SQLite 内存库），不会碰本地/线上数据。
"""

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from club.models import (
    AIActionLog,
    AIDraft,
    Activity,
    Announcement,
    Problem,
    ResourceCategory,
)
from club.services.ai_actions import (
    DraftError,
    apply_draft,
    can_publish,
    create_draft,
    discard_draft,
    extract_json,
)


class ExtractJsonTests(TestCase):
    def test_plain_json(self):
        data = extract_json('{"kind": "problem", "payload": {"title": "x"}}')
        self.assertEqual(data['kind'], 'problem')

    def test_fenced_json(self):
        text = '好的\n```json\n{"kind": "announcement", "payload": {}}\n```\n'
        self.assertEqual(extract_json(text)['kind'], 'announcement')

    def test_noise_around_json(self):
        text = '我来帮你生成：{"kind":"activity","payload":{"a":1}} 请确认'
        self.assertEqual(extract_json(text)['kind'], 'activity')

    def test_braces_inside_strings(self):
        text = '{"kind":"announcement","payload":{"content":"集合 {A, B} 见"}}'
        self.assertEqual(extract_json(text)['payload']['content'], '集合 {A, B} 见')

    def test_invalid_returns_none(self):
        self.assertIsNone(extract_json('我需要更多信息'))
        self.assertIsNone(extract_json('{"kind": oops}'))
        self.assertIsNone(extract_json(''))


class DraftTestCase(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user('staff@example.com', 'staff@example.com', 'pass12345', is_staff=True)
        self.member = User.objects.create_user('member@example.com', 'member@example.com', 'pass12345')
        self.other = User.objects.create_user('other@example.com', 'other@example.com', 'pass12345')
        self.category, _ = ResourceCategory.objects.get_or_create(
            name='计算机网络', slug='computer-networks',
        )
        # 迁移 0003 已经种入 10 个分类，这里只保证要用的两个存在
        # create_draft 的每日上限按当天草稿数计算，测试里用不到 20 条
        AIActionLog.objects.all().delete()

    def _problem_payload(self, **overrides):
        payload = {
            'title': 'TCP 为什么需要三次握手',
            'content': '请选择正确答案：\n\nA. 为了建立可靠连接\nB. 为了同步序列号',
            'problem_type': '单选',
            'difficulty': '中等',
            'category': '计算机网络',
            'answer': 'b',
            'explanation': '三次握手用于同步双方的初始序列号。',
        }
        payload.update(overrides)
        return payload


class ProblemDraftTests(DraftTestCase):
    def test_normalizes_fields(self):
        draft = create_draft(self.member, 'problem', self._problem_payload())
        self.assertEqual(draft.status, 'pending')
        self.assertEqual(draft.payload['problem_type'], 'single')
        self.assertEqual(draft.payload['difficulty'], 'medium')
        self.assertEqual(draft.payload['answer'], 'B')
        self.assertEqual(draft.payload['category_name'], '计算机网络')
        # 只建草稿，不建题目
        self.assertEqual(Problem.objects.count(), 0)

    def test_multiple_choice_answer_sorted(self):
        draft = create_draft(self.member, 'problem', self._problem_payload(
            problem_type='多选', answer='c, a',
        ))
        self.assertEqual(draft.status, 'pending')
        self.assertEqual(draft.payload['answer'], 'A,C')

    def test_judge_answer_variants(self):
        draft = create_draft(self.member, 'problem', self._problem_payload(
            problem_type='判断', answer='正确',
        ))
        self.assertEqual(draft.payload['answer'], 'T')

    def test_missing_answer_marks_failed(self):
        draft = create_draft(self.member, 'problem', self._problem_payload(answer=''))
        self.assertEqual(draft.status, 'failed')
        self.assertIn('单选题缺少参考答案', draft.error)
        self.assertEqual(Problem.objects.count(), 0)

    def test_unknown_category_falls_back_to_other(self):
        ResourceCategory.objects.get_or_create(name='其它', slug='other')
        draft = create_draft(self.member, 'problem', self._problem_payload(category='不存在的分类'))
        self.assertEqual(draft.payload['category_name'], '其它')

    def test_apply_publishes_problem(self):
        draft = create_draft(self.member, 'problem', self._problem_payload())
        problem = apply_draft(draft, self.member)
        self.assertIsInstance(problem, Problem)
        self.assertTrue(problem.is_published)
        self.assertEqual(problem.created_by, self.member)
        draft.refresh_from_db()
        self.assertEqual(draft.status, 'applied')
        self.assertEqual(draft.applied_pk, problem.pk)

    def test_apply_twice_rejected(self):
        draft = create_draft(self.member, 'problem', self._problem_payload())
        apply_draft(draft, self.member)
        draft.refresh_from_db()
        with self.assertRaises(DraftError):
            apply_draft(draft, self.member)

    def test_other_user_cannot_apply(self):
        draft = create_draft(self.member, 'problem', self._problem_payload())
        with self.assertRaises(DraftError):
            apply_draft(draft, self.other)

    def test_discard(self):
        draft = create_draft(self.member, 'problem', self._problem_payload())
        discard_draft(draft, self.member)
        draft.refresh_from_db()
        self.assertEqual(draft.status, 'discarded')
        self.assertEqual(Problem.objects.count(), 0)


class AnnouncementDraftTests(DraftTestCase):
    def payload(self, **overrides):
        data = {
            'title': '本周六算法分享会',
            'content': '时间：周六 19:00\n地点：A301',
            'category': '活动通知',
            'is_pinned': 'false',
        }
        data.update(overrides)
        return data

    def test_apply_creates_published_announcement(self):
        draft = create_draft(self.staff, 'announcement', self.payload())
        self.assertEqual(draft.status, 'pending')
        self.assertEqual(draft.payload['category'], 'event')
        self.assertFalse(draft.payload['is_pinned'])

        announcement = apply_draft(draft, self.staff)
        self.assertIsInstance(announcement, Announcement)
        self.assertTrue(announcement.is_published)
        self.assertIsNotNone(announcement.published_at)
        self.assertEqual(announcement.author, self.staff)

    def test_member_cannot_publish(self):
        self.assertTrue(can_publish(self.staff, 'announcement'))
        self.assertFalse(can_publish(self.member, 'announcement'))
        draft = create_draft(self.member, 'announcement', self.payload())
        with self.assertRaises(DraftError):
            apply_draft(draft, self.member)
        self.assertEqual(Announcement.objects.count(), 0)

    def test_missing_content_fails(self):
        draft = create_draft(self.staff, 'announcement', self.payload(content=''))
        self.assertEqual(draft.status, 'failed')
        self.assertIn('缺少公告正文', draft.error)


class ActivityDraftTests(DraftTestCase):
    def payload(self, **overrides):
        data = {
            'title': '算法分享会',
            'content': '现场讲解常见算法题',
            'location': 'A301',
            'start_time': '2026-11-07T19:00',
            'end_time': '2026-11-07T21:00',
            'signup_deadline': '2026-11-06T18:00',
            'capacity': '50',
            'status': 'published',
        }
        data.update(overrides)
        return data

    def test_apply_creates_activity(self):
        draft = create_draft(self.staff, 'activity', self.payload())
        self.assertEqual(draft.status, 'pending')
        self.assertEqual(draft.payload['capacity'], 50)

        activity = apply_draft(draft, self.staff)
        self.assertIsInstance(activity, Activity)
        self.assertEqual(activity.status, 'published')
        self.assertEqual(activity.organizer, self.staff)
        self.assertEqual(activity.capacity, 50)
        self.assertEqual(
            timezone.localtime(activity.start_time).strftime('%Y-%m-%d %H:%M'),
            '2026-11-07 19:00',
        )

    def test_end_before_start_fails(self):
        draft = create_draft(self.staff, 'activity', self.payload(
            start_time='2026-11-07T19:00', end_time='2026-11-07T18:00',
        ))
        self.assertEqual(draft.status, 'failed')
        self.assertIn('结束时间', draft.error)

    def test_bad_time_format_fails(self):
        draft = create_draft(self.staff, 'activity', self.payload(start_time='本周六晚上'))
        self.assertEqual(draft.status, 'failed')
        self.assertIn('开始时间', draft.error)

    def test_capacity_clamped(self):
        draft = create_draft(self.staff, 'activity', self.payload(capacity='99999'))
        self.assertEqual(draft.payload['capacity'], 10000)


class AuditTests(DraftTestCase):
    def test_actions_are_logged(self):
        draft = create_draft(self.member, 'problem', self._problem_payload())
        apply_draft(draft, self.member)
        actions = list(AIActionLog.objects.order_by('created_at').values_list('action', 'ok'))
        self.assertIn(('draft.create', True), actions)
        self.assertIn(('draft.apply', True), actions)

    def test_failed_draft_is_logged_and_kept(self):
        draft = create_draft(self.member, 'problem', self._problem_payload(answer=''))
        self.assertTrue(AIDraft.objects.filter(pk=draft.pk, status='failed').exists())
        self.assertTrue(AIActionLog.objects.filter(action='draft.create', ok=False).exists())

"""
主动巡检 Agent 测试
====================
覆盖：触发条件、去重、归属回退、LLM 润色与回退、dry-run、管理命令。
"""

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from club.models import AIActionLog, AIDraft, Activity
from club.services import proactive


class ProactiveAgentTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            'staff@example.com', 'staff@example.com', 'pass12345', is_staff=True,
        )
        now = timezone.now()
        self.activity = Activity.objects.create(
            title='周末算法分享会',
            content='现场讲解常见算法题',
            location='A301',
            start_time=now + timedelta(hours=12),
            end_time=now + timedelta(hours=14),
            signup_deadline=now + timedelta(hours=6),
            capacity=30,
            status='published',
            organizer=self.staff,
        )

    def test_creates_pending_draft(self):
        report = proactive.run(use_llm=False)

        self.assertEqual(len(report['created']), 1)
        draft = AIDraft.objects.get()
        self.assertEqual(draft.kind, 'announcement')
        self.assertEqual(draft.source, 'proactive')
        self.assertEqual(draft.source_key, f'activity-start:{self.activity.pk}')
        self.assertEqual(draft.status, 'pending')
        self.assertEqual(draft.user, self.staff)
        self.assertIn(self.activity.title, draft.payload['title'])
        self.assertEqual(AIActionLog.objects.filter(action='agent.proactive').count(), 1)

    def test_dedup_within_window(self):
        proactive.run(use_llm=False)
        report = proactive.run(use_llm=False)

        self.assertEqual(AIDraft.objects.count(), 1)
        self.assertTrue(any('已提醒' in item['reason'] for item in report['skipped']))

    def test_activity_outside_window_is_ignored(self):
        now = timezone.now()
        self.activity.start_time = now + timedelta(days=3)
        self.activity.end_time = now + timedelta(days=3, hours=2)
        self.activity.signup_deadline = now + timedelta(days=2)
        self.activity.save()

        proactive.run(use_llm=False)
        self.assertEqual(AIDraft.objects.count(), 0)

    def test_deadline_rule(self):
        now = timezone.now()
        self.activity.start_time = now + timedelta(days=3)
        self.activity.end_time = now + timedelta(days=3, hours=2)
        self.activity.signup_deadline = now + timedelta(hours=10)
        self.activity.save()

        proactive.run(use_llm=False)

        draft = AIDraft.objects.get()
        self.assertEqual(draft.source_key, f'activity-deadline:{self.activity.pk}')
        self.assertIn('截止', draft.payload['title'])

    def test_non_staff_organizer_is_skipped(self):
        member = User.objects.create_user('member@example.com', 'member@example.com', 'pass12345')
        self.activity.organizer = member
        self.activity.save(update_fields=['organizer'])

        report = proactive.run(use_llm=False)

        self.assertEqual(AIDraft.objects.count(), 0)
        self.assertTrue(any('管理员' in item['reason'] for item in report['skipped']))

    def test_dry_run_creates_nothing(self):
        report = proactive.run(use_llm=False, dry_run=True)

        self.assertEqual(AIDraft.objects.count(), 0)
        self.assertTrue(report['created'][0]['dry_run'])

    def test_llm_copy_is_used(self):
        with patch.object(proactive, '_llm_available', return_value=True), \
                patch.object(proactive, '_llm_payload', return_value={
                    'title': 'LLM 标题', 'content': 'LLM 正文',
                }):
            proactive.run(use_llm=True)

        draft = AIDraft.objects.get()
        self.assertEqual(draft.payload['title'], 'LLM 标题')
        self.assertEqual(draft.payload['content'], 'LLM 正文')

    def test_llm_failure_falls_back_to_template(self):
        with patch.object(proactive, '_llm_available', return_value=True), \
                patch.object(proactive, '_llm_payload', side_effect=RuntimeError('boom')):
            proactive.run(use_llm=True)

        draft = AIDraft.objects.get()
        self.assertIn(self.activity.title, draft.payload['title'])

    def test_command_runs(self):
        out = StringIO()
        call_command('proactive_agent', '--no-llm', stdout=out)

        self.assertIn('巡检完成', out.getvalue())
        self.assertEqual(AIDraft.objects.count(), 1)

    def test_command_dry_run(self):
        out = StringIO()
        call_command('proactive_agent', '--no-llm', '--dry-run', stdout=out)

        self.assertIn('dry-run', out.getvalue())
        self.assertEqual(AIDraft.objects.count(), 0)

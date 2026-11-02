"""主动巡检 Agent 的管理命令：可手动执行，也可挂到定时任务。"""

from django.core.management.base import BaseCommand

from club.services.proactive import run


class Command(BaseCommand):
    help = '主动巡检：为即将开始 / 即将截止报名的活动生成提醒公告草稿'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='只打印计划，不创建草稿')
        parser.add_argument('--no-llm', action='store_true', help='不使用大模型润色，纯模板生成')
        parser.add_argument('--limit', type=int, default=10, help='单次最多处理几个活动（默认 10）')

    def handle(self, *args, **options):
        report = run(
            dry_run=options['dry_run'],
            use_llm=not options['no_llm'],
            limit=max(1, options['limit']),
        )

        self.stdout.write(f"巡检完成：候选活动 {report['candidates']} 个")

        for item in report['created']:
            suffix = '  [dry-run，未写入]' if item.get('dry_run') else f"  → 草稿 #{item['draft_id']}"
            self.stdout.write(f"  + {item['title']}（{item['activity']}，归属 {item['owner']}）{suffix}")

        for item in report['skipped']:
            self.stdout.write(f"  - 跳过 {item['activity']}：{item['reason']}")

        if not report['created'] and not report['skipped']:
            self.stdout.write('  没有需要提醒的活动')

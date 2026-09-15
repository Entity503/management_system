from django.db import migrations


def set_daily_ai_request_limit(apps, schema_editor):
    AIQuota = apps.get_model('club', 'AIQuota')
    AIQuota.objects.all().update(max_requests_per_day=5)


class Migration(migrations.Migration):
    dependencies = [
        ('club', '0010_aiquota_daily_limits'),
    ]

    operations = [
        migrations.RunPython(set_daily_ai_request_limit, migrations.RunPython.noop),
    ]
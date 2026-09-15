from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('club', '0009_comment'),
    ]

    operations = [
        migrations.AddField(
            model_name='aiquota',
            name='daily_requests',
            field=models.PositiveIntegerField(default=0, verbose_name='今日请求数'),
        ),
        migrations.AddField(
            model_name='aiquota',
            name='daily_requests_date',
            field=models.DateField(blank=True, null=True, verbose_name='请求统计日期'),
        ),
        migrations.AddField(
            model_name='aiquota',
            name='max_requests_per_day',
            field=models.PositiveIntegerField(default=5, verbose_name='每日 AI 请求上限'),
        ),
    ]
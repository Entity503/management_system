from django.db import migrations


RESOURCE_CATEGORIES = [
    ('数据结构', 'data-structures'),
    ('计算机组成原理', 'computer-organization'),
    ('计算机网络', 'computer-networks'),
    ('操作系统', 'operating-systems'),
    ('C/C++', 'c-cpp'),
    ('Java', 'java'),
    ('Python', 'python'),
    ('MySQL', 'mysql'),
    ('离散数学', 'discrete-mathematics'),
    ('其它', 'other'),
]


def create_categories(apps, schema_editor):
    # 使用迁移历史中的模型，避免未来模型变化影响旧迁移回放。
    ResourceCategory = apps.get_model('club', 'ResourceCategory')
    for name, slug in RESOURCE_CATEGORIES:
        ResourceCategory.objects.get_or_create(name=name, defaults={'slug': slug})


def remove_categories(apps, schema_editor):
    ResourceCategory = apps.get_model('club', 'ResourceCategory')
    ResourceCategory.objects.filter(slug__in=[slug for _, slug in RESOURCE_CATEGORIES]).delete()


class Migration(migrations.Migration):
    dependencies = [('club', '0002_userprofile_avatar_userprofile_real_name')]
    operations = [migrations.RunPython(create_categories, remove_categories)]

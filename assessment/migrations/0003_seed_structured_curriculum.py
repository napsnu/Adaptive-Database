from django.core.management import call_command
from django.db import migrations


def seed_structured_curriculum(apps, schema_editor):
    call_command('seed_cefr_curriculum')


def noop_reverse(apps, schema_editor):
    # Keep seeded curriculum data on reverse migration.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('assessment', '0002_topic_suggested_unit_order_answersample_cefrsublevel_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_structured_curriculum, reverse_code=noop_reverse),
    ]

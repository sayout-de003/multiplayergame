# Generated by Django 5.1.3 on 2024-12-03 04:39

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0002_gameroom_is_active"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="playerstatus",
            name="is_ready",
        ),
    ]
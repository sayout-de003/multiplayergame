# Generated by Django 5.1.3 on 2025-03-13 11:54

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0006_footballroom_footballplayer_footballmatchscore_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="game",
            name="playcanvas_project_id",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]

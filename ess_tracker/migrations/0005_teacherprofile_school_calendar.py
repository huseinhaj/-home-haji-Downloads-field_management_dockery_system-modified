from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ess_tracker', '0004_alter_essfillrun_kind'),
    ]

    operations = [
        migrations.AddField(
            model_name='teacherprofile',
            name='school_open',
            field=models.DateField(blank=True, help_text='Tarehe shule inavyofunguliwa mwaka huu (mf. 2026-01-12)', null=True),
        ),
        migrations.AddField(
            model_name='teacherprofile',
            name='school_close',
            field=models.DateField(blank=True, help_text='Tarehe shule inavyofungwa mwaka huu (mf. 2026-12-04)', null=True),
        ),
        migrations.AddField(
            model_name='teacherprofile',
            name='entries_per_week',
            field=models.PositiveSmallIntegerField(default=3, help_text='Mara ngapi kwa wiki mfumo ujaze maendeleo yako (2 au 3)'),
        ),
    ]
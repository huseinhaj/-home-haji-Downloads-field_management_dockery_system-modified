from django.db import migrations, models
from django.utils import timezone


def start_leases(apps, schema_editor):
    """Anzisha kipindi (lease) kwa waamiri waliokuwa wameseta muda.

    Mwenye 'Kila siku' (0) → hakuna mwisho (inaendelea). Mwenye wiki → lease
    ya wiki hiyo kuanzia sasa hivi karibuni.
    """
    TeacherProfile = apps.get_model('ess_tracker', 'TeacherProfile')
    now = timezone.now()
    for profile in TeacherProfile.objects.filter(approver_enabled=True):
        weeks = profile.auto_approve_weeks or 0
        profile.auto_lease_set_at = now
        profile.auto_lease_until = now + timezone.timedelta(weeks=weeks) if weeks else None
        profile.save(update_fields=['auto_lease_set_at', 'auto_lease_until'])


def stop_leases(apps, schema_editor):
    TeacherProfile = apps.get_model('ess_tracker', 'TeacherProfile')
    TeacherProfile.objects.update(auto_lease_until=None, auto_lease_set_at=None)


class Migration(migrations.Migration):

    dependencies = [
        ('ess_tracker', '0023_teacherprofile_auto_approve_daily'),
    ]

    operations = [
        migrations.AddField(
            model_name='teacherprofile',
            name='auto_lease_set_at',
            field=models.DateTimeField(
                blank=True,
                help_text='Wakati ambapo kipindi kiliposhwa kwa mara ya mwisho.',
                null=True),
        ),
        migrations.AddField(
            model_name='teacherprofile',
            name='auto_lease_until',
            field=models.DateTimeField(
                blank=True,
                help_text='Mwisho wa kipindi cha mchakato wa moja kwa moja (lease). '
                          'Mfungulwe kuweka muda (wiki) upya.',
                null=True),
        ),
        migrations.AlterField(
            model_name='teacherprofile',
            name='auto_approve_weeks',
            field=models.PositiveSmallIntegerField(
                choices=[(0, 'Kila siku (hazui mwisho)'), (1, 'Kwa wiki 1'),
                         (2, 'Kwa wiki mbili'), (4, 'Kwa wiki 4'), (12, 'Kwa miezi 3')],
                default=0,
                help_text='Mkuu/kiongozi: muda (kwa wiki) ambao mfumo wa moja kwa moja '
                          'unaweza kuendelea kwaweka kila siku (kujaza na kuidhinisha). '
                          'Mwisho wa muda: mfumo husimama hadi uweke upya.'),
        ),
        migrations.RunPython(start_leases, stop_leases),
    ]

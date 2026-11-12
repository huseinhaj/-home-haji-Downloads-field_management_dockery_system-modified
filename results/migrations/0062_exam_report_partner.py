from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('results', '0061_school_headmaster_stamp'),
    ]

    operations = [
        migrations.AddField(
            model_name='exam',
            name='report_partner',
            field=models.ForeignKey(
                blank=True,
                help_text='Mtihani wa pili unaounganishwa na huu kwenye report card (wastani wa alama). Akiwekwa, huchukua nafasi ya mchanganyiko wa kiotomatiki wa miezi.',
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name='report_partner_for',
                to='results.exam',
            ),
        ),
    ]

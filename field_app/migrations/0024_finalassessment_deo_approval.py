from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('field_app', '0023_finalassessment_deo_signature'),
    ]

    operations = [
        migrations.AddField(
            model_name='finalassessment',
            name='deo_approved',
            field=models.BooleanField(default=False, help_text='DEO ameidhibiti — cheti kinapatikana'),
        ),
        migrations.AddField(
            model_name='finalassessment',
            name='deo_approved_at',
            field=models.DateTimeField(blank=True, null=True, help_text='Tarehe DEO alipoidhibiti'),
        ),
        migrations.AddField(
            model_name='finalassessment',
            name='deo_approved_by',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='deo_approved_assessments',
                to='field_app.boardmember',
                help_text='DEO aliyeidhibiti',
            ),
        ),
        migrations.AlterField(
            model_name='finalassessment',
            name='is_final',
            field=models.BooleanField(default=False, help_text='Mkuu wa Shule amekamilisha tathmini'),
        ),
    ]

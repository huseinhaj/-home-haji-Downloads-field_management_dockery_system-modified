from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ess_tracker', '0003_essfillrun_kind'),
    ]

    operations = [
        migrations.AlterField(
            model_name='essfillrun',
            name='kind',
            field=models.CharField(
                choices=[('fill', 'Kujaza ESS'), ('sync', 'Sawazisha majina na ESS'),
                         ('push', 'Tuma majina kwenye ESS')],
                default='fill', max_length=10),
        ),
    ]

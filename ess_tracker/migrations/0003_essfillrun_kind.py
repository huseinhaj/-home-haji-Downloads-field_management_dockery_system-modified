from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ess_tracker', '0002_alter_weekentry_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='essfillrun',
            name='kind',
            field=models.CharField(
                choices=[('fill', 'Kujaza ESS'), ('sync', 'Sawazisha majina na ESS')],
                default='fill', max_length=10),
        ),
    ]

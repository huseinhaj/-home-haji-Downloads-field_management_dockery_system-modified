from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('results', '0022_migrate_logos_to_base64'),
    ]

    operations = [
        migrations.AddField(
            model_name='school',
            name='coat_of_arms',
            field=models.ImageField(blank=True, null=True, upload_to='coat_of_arms/',
                help_text='Nembo ya Coat of Arms — inaonekana katikati ya header'),
        ),
        migrations.AddField(
            model_name='school',
            name='coat_of_arms_b64',
            field=models.TextField(blank=True, default='',
                help_text='Coat of arms stored as base64 — persists on Railway'),
        ),
    ]

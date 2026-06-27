from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('field_app', '0027_multi_visit_assessment'),
    ]

    operations = [
        migrations.AddField(
            model_name='school',
            name='special_needs_education',
            field=models.BooleanField(
                default=False,
                help_text='Shule hii inatoa mafunzo ya elimu maalumu (viziwi, wasioona, n.k.)'
            ),
        ),
        migrations.AddField(
            model_name='school',
            name='is_inclusive',
            field=models.BooleanField(
                default=True,
                help_text='Shule hii inafuata mtaala wa elimu jumuishi (Tanzania 2021–2026)'
            ),
        ),
    ]

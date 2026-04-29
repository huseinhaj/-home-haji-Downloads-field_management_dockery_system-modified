from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('field_app', '0002_schoolassessment_supervisor_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='schoolassessment',
            name='academic_year',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to='field_app.academicyear',
            ),
        ),
    ]

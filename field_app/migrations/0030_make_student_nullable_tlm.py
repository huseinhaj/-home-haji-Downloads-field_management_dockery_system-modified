# Generated manually — only AlterField for student nullable (AddField already existed in earlier migrations)

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('field_app', '0029_seed_special_needs_schools'),
    ]

    operations = [
        migrations.AlterField(
            model_name='lessonplan',
            name='student',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='lesson_plans', to='field_app.studentteacher'),
        ),
        migrations.AlterField(
            model_name='schemeofwork',
            name='student',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='schemes', to='field_app.studentteacher'),
        ),
    ]

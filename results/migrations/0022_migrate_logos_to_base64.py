"""
Data migration: Migrate existing school logos from ImageField to base64 TextField.
After this, logos persist on Railway even when the ephemeral filesystem resets.
"""
import base64
import os
from django.db import migrations


def forwards(apps, schema_editor):
    School = apps.get_model('results', 'School')
    for school in School.objects.all():
        updated = False

        # School logo
        if school.school_logo and not school.school_logo_b64:
            try:
                field = school.school_logo
                storage = field.storage
                if storage.exists(field.name):
                    field.open('rb')
                    data = field.read()
                    field.close()
                    if data:
                        ext = os.path.splitext(str(field.name))[1].lower()
                        mime_map = {'.png': 'image/png', '.jpg': 'image/jpeg',
                                    '.jpeg': 'image/jpeg', '.gif': 'image/gif',
                                    '.svg': 'image/svg+xml'}
                        mime = mime_map.get(ext, 'image/png')
                        b64 = base64.b64encode(data).decode('ascii')
                        school.school_logo_b64 = f'data:{mime};base64,{b64}'
                        updated = True
            except Exception:
                pass

        # District logo
        if school.district_logo and not school.district_logo_b64:
            try:
                field = school.district_logo
                storage = field.storage
                if storage.exists(field.name):
                    field.open('rb')
                    data = field.read()
                    field.close()
                    if data:
                        ext = os.path.splitext(str(field.name))[1].lower()
                        mime_map = {'.png': 'image/png', '.jpg': 'image/jpeg',
                                    '.jpeg': 'image/jpeg', '.gif': 'image/gif',
                                    '.svg': 'image/svg+xml'}
                        mime = mime_map.get(ext, 'image/png')
                        b64 = base64.b64encode(data).decode('ascii')
                        school.district_logo_b64 = f'data:{mime};base64,{b64}'
                        updated = True
            except Exception:
                pass

        if updated:
            fields = []
            if school.school_logo_b64:
                fields.append('school_logo_b64')
            if school.district_logo_b64:
                fields.append('district_logo_b64')
            if fields:
                school.save(update_fields=fields)


class Migration(migrations.Migration):

    dependencies = [
        ('results', '0021_add_logo_b64_fields'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]

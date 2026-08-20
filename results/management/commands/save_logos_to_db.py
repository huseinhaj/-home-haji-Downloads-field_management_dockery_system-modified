"""
Management command: Save all existing school logos as base64 in the database.

Usage:
    python manage.py save_logos_to_db

This fixes the issue where Railway's ephemeral filesystem deletes logo files.
After running this, logos persist in the database forever.
"""
import base64
import os

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Save all existing school logos as base64 in the database'

    def handle(self, *args, **options):
        from results.models import School

        schools = School.objects.all()
        saved = 0
        skipped = 0

        for school in schools:
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
                            self.stdout.write(f'  ✅ School logo saved for: {school.name}')
                except Exception as e:
                    self.stdout.write(f'  ⚠️  Error reading school logo for {school.name}: {e}')

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
                            self.stdout.write(f'  ✅ District logo saved for: {school.name}')
                except Exception as e:
                    self.stdout.write(f'  ⚠️  Error reading district logo for {school.name}: {e}')

            if updated:
                fields = []
                if school.school_logo_b64:
                    fields.append('school_logo_b64')
                if school.district_logo_b64:
                    fields.append('district_logo_b64')
                if fields:
                    school.save(update_fields=fields)
                    saved += 1
            else:
                skipped += 1

        self.stdout.write(self.style.SUCCESS(
            f'\nDone! Saved: {saved} schools, Skipped: {skipped} (already saved or no logos)'
        ))

from django.db import migrations


def remove_arusha_district(apps, schema_editor):
    District = apps.get_model('field_app', 'District')
    School = apps.get_model('field_app', 'School')
    Region = apps.get_model('field_app', 'Region')

    # Use icontains to catch "Arusha", "Arusha Region", "ARUSHA", etc.
    arusha_region = Region.objects.filter(name__icontains='Arusha').first()
    if not arusha_region:
        return

    # Delete district named exactly "Arusha" (not "Arusha DC", "Arusha CC", etc.)
    # Guard: only if it has at most 1 school to avoid bulk data loss.
    for district in District.objects.filter(region=arusha_region):
        name_clean = district.name.strip().lower()
        if name_clean == 'arusha':
            school_count = School.objects.filter(district=district).count()
            if school_count <= 1:
                School.objects.filter(district=district).delete()
                district.delete()
            break


class Migration(migrations.Migration):

    dependencies = [
        ('field_app', '0024_finalassessment_deo_approval'),
    ]

    operations = [
        migrations.RunPython(remove_arusha_district, migrations.RunPython.noop),
    ]

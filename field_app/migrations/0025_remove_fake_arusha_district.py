from django.db import migrations


def remove_arusha_district(apps, schema_editor):
    District = apps.get_model('field_app', 'District')
    School = apps.get_model('field_app', 'School')
    Region = apps.get_model('field_app', 'Region')

    arusha_region = Region.objects.filter(name__iexact='Arusha').first()
    if not arusha_region:
        return

    # Only delete the district if it is named exactly "Arusha" and has at most 1 school,
    # to avoid accidentally removing a legitimate district.
    district = District.objects.filter(
        name__iexact='Arusha', region=arusha_region
    ).first()
    if district:
        school_count = School.objects.filter(district=district).count()
        if school_count <= 1:
            School.objects.filter(district=district).delete()
            district.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('field_app', '0024_finalassessment_deo_approval'),
    ]

    operations = [
        migrations.RunPython(remove_arusha_district, migrations.RunPython.noop),
    ]

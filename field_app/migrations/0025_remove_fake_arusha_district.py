from django.db import migrations


def remove_arusha_district(apps, schema_editor):
    District = apps.get_model('field_app', 'District')
    School = apps.get_model('field_app', 'School')
    Region = apps.get_model('field_app', 'Region')

    arusha_region = Region.objects.filter(name__icontains='Arusha').first()
    if not arusha_region:
        return

    district = None
    for d in District.objects.filter(region=arusha_region):
        if d.name.strip().lower() == 'arusha':
            district = d
            break

    if not district:
        return

    school_count = School.objects.filter(district=district).count()
    if school_count > 2:
        # Safety guard: don't delete if suspiciously many schools
        return

    schools = School.objects.filter(district=district)
    school_ids = list(schools.values_list('id', flat=True))

    if school_ids:
        # Null out FK references from StudentTeacher.selected_school
        try:
            StudentTeacher = apps.get_model('field_app', 'StudentTeacher')
            StudentTeacher.objects.filter(selected_school_id__in=school_ids).update(selected_school=None)
        except Exception:
            pass

        # Null out FK references from SchoolAssignment
        try:
            SchoolAssignment = apps.get_model('field_app', 'SchoolAssignment')
            SchoolAssignment.objects.filter(school_id__in=school_ids).delete()
        except Exception:
            pass

        # Null out FK references from StudentApplication
        try:
            StudentApplication = apps.get_model('field_app', 'StudentApplication')
            StudentApplication.objects.filter(school_id__in=school_ids).delete()
        except Exception:
            pass

        # Null out FK references from SchoolHeadRequest
        try:
            SchoolHeadRequest = apps.get_model('field_app', 'SchoolHeadRequest')
            SchoolHeadRequest.objects.filter(school_id__in=school_ids).update(school=None)
        except Exception:
            pass

        # Null out BoardMember.school
        try:
            BoardMember = apps.get_model('field_app', 'BoardMember')
            BoardMember.objects.filter(school_id__in=school_ids).update(school=None)
        except Exception:
            pass

        schools.delete()

    district.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('field_app', '0024_finalassessment_deo_approval'),
    ]

    operations = [
        migrations.RunPython(remove_arusha_district, migrations.RunPython.noop),
    ]

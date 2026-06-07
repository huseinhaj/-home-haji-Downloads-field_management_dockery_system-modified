"""
Deletes the duplicate 'Arusha' district (pk=185) from the database.
Any school linked to it is moved to 'Arusha Cc' (pk=1) first.

Run: python fix_arusha_district.py
"""
import os, sys, django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'field_management.settings')
sys.path.insert(0, os.path.dirname(__file__))
django.setup()

from field_app.models import District, School

BAD_PK  = 185
GOOD_PK = 1   # Arusha Cc

try:
    bad  = District.objects.get(pk=BAD_PK)
    good = District.objects.get(pk=GOOD_PK)
except District.DoesNotExist as e:
    print(f"District not found: {e}")
    sys.exit(1)

print(f"Bad district:  pk={bad.pk} name='{bad.name}'")
print(f"Good district: pk={good.pk} name='{good.name}'")

# Move any linked schools
schools = School.objects.filter(district=bad)
count = schools.count()
if count:
    print(f"Moving {count} school(s) to '{good.name}'...")
    for s in schools:
        print(f"  - {s.name} ({s.level})")
    schools.update(district=good)
else:
    print("No schools linked to bad district.")

# Delete the bad district
bad.delete()
print(f"Deleted district pk={BAD_PK} '{bad.name}' successfully.")

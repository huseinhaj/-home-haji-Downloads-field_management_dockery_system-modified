# create_import_script.py
import csv
import os
import django
import random
import string

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'field_management.settings')
django.setup()

from django.contrib.auth import get_user_model
from field_app.models import Assessor, School

User = get_user_model()

def import_assessors():
    csv_file = 'assessors.csv'
    
    with open(csv_file, 'r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            try:
                full_name = row['full_name']
                phone_number = row['phone_number']
                email = row['email']
                school_name = row['school_name']
                
                print(f"Processing: {full_name} - {email}")
                
                # Check if school exists
                try:
                    school = School.objects.get(name__icontains=school_name)
                    print(f"✅ Found school: {school.name}")
                except School.DoesNotExist:
                    print(f"❌ School '{school_name}' not found for {full_name}")
                    # Create school if it doesn't exist (optional)
                    # school = School.objects.create(name=school_name, level='Secondary', district=some_district)
                    continue
                except School.MultipleObjectsReturned:
                    schools = School.objects.filter(name__icontains=school_name)
                    school = schools.first()
                    print(f"⚠️  Multiple schools found, using: {school.name}")
                
                # Check if assessor already exists
                if Assessor.objects.filter(email=email).exists():
                    print(f"⚠️  Assessor with email {email} already exists")
                    continue
                
                # Create assessor - user will be auto-created in save() method
                assessor = Assessor(
                    full_name=full_name,
                    phone_number=phone_number,
                    email=email
                )
                assessor.save()
                
                print(f"✅ Successfully created assessor: {full_name}")
                print(f"   📧 Email: {email}")
                print(f"   📞 Phone: {phone_number}")
                print(f"   🏫 School: {school.name}")
                print("-" * 50)
                
            except Exception as e:
                print(f"❌ Error creating {row['full_name']}: {e}")
                import traceback
                traceback.print_exc()
    
    print("🎉 Import completed!")
    print(f"Total assessors in database: {Assessor.objects.count()}")

if __name__ == "__main__":
    import_assessors()

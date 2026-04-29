#!/usr/bin/env python
import os
import sys

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'field_management.settings')
sys.path.append(os.getcwd())

import django
django.setup()

from django.core.management import call_command
from django.db import connections

print("=" * 50)
print("🚀 Loading data to Render PostgreSQL...")
print("=" * 50)

# Use Render database directly
from django.conf import settings

# Set Render database connection
RENDER_DB = {
    'ENGINE': 'django.db.backends.postgresql',
    'NAME': 'field_db',
    'USER': 'field_user',
    'PASSWORD': 'ukRDqwwIGn9OwMizhEcDhzJHgUVHNLan',
    'HOST': 'dpg-d7ltilugvqtc73c8mr50-a.oregon-postgres.render.com',
    'PORT': '5432',
}

# Temporarily change database settings
original_db = settings.DATABASES['default']
settings.DATABASES['default'] = RENDER_DB

try:
    # Connect to Render and load data
    print("\n📥 Loading regions...")
    call_command('loaddata', 'regions.json', verbosity=1)
    
    print("\n📥 Loading districts...")
    call_command('loaddata', 'districts.json', verbosity=1)
    
    print("\n📥 Loading subjects...")
    call_command('loaddata', 'subjects.json', verbosity=1)
    
    print("\n📥 Loading schools (this will take 2-3 minutes)...")
    call_command('loaddata', 'schools.json', verbosity=1)
    
    print("\n✅ All data loaded successfully!")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    print("\nTrying alternative method...")
    
    # Alternative: Load each file separately with error handling
    for fixture in ['regions', 'districts', 'subjects', 'schools']:
        try:
            print(f"\n📥 Loading {fixture}...")
            call_command('loaddata', f'{fixture}.json', verbosity=0)
            print(f"  ✅ {fixture} loaded")
        except Exception as ex:
            print(f"  ❌ Failed to load {fixture}: {ex}")

finally:
    # Restore original settings
    settings.DATABASES['default'] = original_db

print("\n" + "=" * 50)
print("🎉 Migration process completed!")
print("=" * 50)

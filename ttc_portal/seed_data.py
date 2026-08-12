"""
seed_data.py — Jaza data za mwanzo (seed) kwa TTC Student Portal.

Inajumuisha:
  • Vyuo vyote vya ualimu (TTCs) vinavyotoa Diploma in Education
  • Programu 2 kwa kila chuo (Arts & Science)
  • Ada ya Mwaka + Mchango wa Chuo kwa kila chuo
  • Super admin kwa njia ya env vars (TTC_SUPERUSER_EMAIL / TTC_SUPERUSER_PASSWORD)

Hakuna akaunti za demo zinazoundwa — production huunda super admin yake kupitia
env vars au `python manage.py createsuperuser`.
"""

import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ttc_portal.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from django.contrib.auth import get_user_model
from colleges.models import College, Program
from fees.models import FeeItem
from fees.services import academic_year_now

User = get_user_model()

# ── Vyuo vya ualimu Tanzania (Teacher Training Colleges) ──
# (name, short_name, code, region, district, established)
TTCS = [
    ("Kasulu Teachers College", "Kasulu TC", "KAS", "Kigoma", "Kasulu", 1979),
    ("Butimba Teachers College", "Butimba TC", "BUT", "Mwanza", "Nyamagana", 1928),
    ("Morogoro Teachers College", "Morogoro TC", "MOR", "Morogoro", "Morogoro MC", 1954),
    ("Korogwe Teachers College", "Korogwe TC", "KOR", "Tanga", "Korogwe", 1949),
    ("Monduli Teachers College", "Monduli TC", "MON", "Arusha", "Monduli", 1967),
    ("Mpwapwa Teachers College", "Mpwapwa TC", "MPW", "Dodoma", "Mpwapwa", 1947),
    ("Marangu Teachers College", "Marangu TC", "MAR", "Kilimanjaro", "Moshi DC", 1928),
    ("Kleruu Teachers College", "Kleruu TC", "KLE", "Iringa", "Iringa MC", 1972),
    ("Tabora Teachers College", "Tabora TC", "TAB", "Tabora", "Tabora MC", 1960),
    ("Songea Teachers College", "Songea TC", "SON", "Ruvuma", "Songea MC", 1971),
    ("Nachingwea Teachers College", "Nachingwea TC", "NAC", "Lindi", "Nachingwea", 1974),
    ("Mtwara Teachers College", "Mtwara TC", "MTW", "Mtwara", "Mtwara MC", 1968),
    ("Mpanda Teachers College", "Mpanda TC", "MPA", "Katavi", "Mpanda", 1978),
    ("Sumbawanga Teachers College", "Sumbawanga TC", "SUM", "Rukwa", "Sumbawanga", 1975),
    ("Dar es Salaam Teachers College", "Dar es Salaam TC", "DAR", "Dar es Salaam", "Temeke", 1973),
    ("Tanga Teachers College", "Tanga TC", "TAN", "Tanga", "Tanga CC", 1976),
    ("Kigoma Teachers College", "Kigoma TC", "KIG", "Kigoma", "Kigoma Ujiji", 1977),
    ("Shinyanga Teachers College", "Shinyanga TC", "SHI", "Shinyanga", "Shinyanga MC", 1976),
    ("Singida Teachers College", "Singida TC", "SIN", "Singida", "Singida MC", 1978),
    ("Dodoma Teachers College", "Dodoma TC", "DOD", "Dodoma", "Dodoma CC", 1975),
    ("Makambako Teachers College", "Makambako TC", "MAK", "Njombe", "Makambako", 2008),
    ("Ilonga Teachers College", "Ilonga TC", "ILO", "Morogoro", "Kilosa", 1963),
    ("Kibaha Teachers College", "Kibaha TC", "KIB", "Pwani", "Kibaha", 2003),
    ("Muleba Teachers College", "Muleba TC", "MUL", "Kagera", "Muleba", 2004),
    ("Katoke Teachers College", "Katoke TC", "KAT", "Kagera", "Muleba", 1979),
    ("Nkasi Teachers College", "Nkasi TC", "NKA", "Rukwa", "Nkasi", 2005),
    ("Lushoto Teachers College", "Lushoto TC", "LUS", "Tanga", "Lushoto", 1960),
    ("Tunduru Teachers College", "Tunduru TC", "TUN", "Ruvuma", "Tunduru", 2007),
    ("Iringa Teachers College", "Iringa TC", "IRI", "Iringa", "Iringa DC", 1985),
    ("Mwanza Teachers College", "Mwanza TC", "MZA", "Mwanza", "Nyamagana", 2002),
    ("Kyela Teachers College", "Kyela TC", "KYE", "Mbeya", "Kyela", 2006),
    ("Mbinga Teachers College", "Mbinga TC", "MBI", "Ruvuma", "Mbinga", 2009),
    ("Kibondo Teachers College", "Kibondo TC", "KBO", "Kigoma", "Kibondo", 2005),
]

PROGRAMS = [
    ("Diploma in Education (Arts)", "DEA"),
    ("Diploma in Education (Science)", "DES"),
]

FEE_ITEMS = [
    ("Ada ya Mwaka (Tuition)", "ada", 300000),
    ("Mchango wa Chuo", "mchango", 150000),
]


def create_superuser_from_env():
    """Create the super admin from TTC_SUPERUSER_EMAIL / TTC_SUPERUSER_PASSWORD.

    Ukizitaka, weka pia TTC_SUPERUSER_USERNAME (default: 'admin'). Hakuna
    akaunti inayoundwa kama env vars hazipo — tumia createsuperuser baadaye.
    """
    email = os.environ.get('TTC_SUPERUSER_EMAIL', '').strip()
    password = os.environ.get('TTC_SUPERUSER_PASSWORD', '')
    username = os.environ.get('TTC_SUPERUSER_USERNAME', 'admin').strip()
    if not (email and password):
        print("   ⚠️  Hakuna TTC_SUPERUSER_EMAIL / TTC_SUPERUSER_PASSWORD — hakuna super admin.")
        print("       Unda baada ya deploy:  python manage.py createsuperuser")
        return
    user, created = User.objects.get_or_create(
        username=username,
        defaults={'email': email, 'role': 'super_admin', 'is_staff': True,
                  'is_superuser': True, 'first_name': 'Super', 'last_name': 'Admin'},
    )
    user.email = email
    user.is_staff = True
    user.is_superuser = True
    user.role = 'super_admin'
    user.set_password(password)
    user.save()
    print(f"   {'✓' if created else '='} Super Admin: {username} ({email})")


def run():
    print("⚙️  TTC Student Portal — seed data...")

    # 1. Vyuo
    colleges = []
    for name, short, code, region, district, est in TTCS:
        college, created = College.objects.get_or_create(
            code=code,
            defaults=dict(
                name=name, short_name=short, region=region,
                district=district, established=est, is_active=True,
            ),
        )
        colleges.append(college)
        print(f"  {'✓' if created else '='} {short} ({region})")

    # 2. Programu
    for college in colleges:
        for prog_name, prog_code in PROGRAMS:
            Program.objects.get_or_create(
                college=college, name=prog_name,
                defaults={'code': prog_code, 'duration_years': 2},
            )

    # 3. Ada na Michango
    for college in colleges:
        for item_name, category, amount in FEE_ITEMS:
            FeeItem.objects.get_or_create(
                college=college, name=item_name,
                defaults={'category': category, 'amount': amount, 'is_active': True},
            )

    # 4. Super admin (kutoka env vars — hakuna demo accounts!)
    create_superuser_from_env()

    print("\n✅ Seed imekamilika!")
    print("   ─────────────────────────────────────────────")
    print("   Hakuna akaunti za demo zilizoundwa.")
    print("   Tengeneza super admin: python manage.py createsuperuser")
    print("   Mwaka wa masomo: ", academic_year_now())


if __name__ == '__main__':
    run()

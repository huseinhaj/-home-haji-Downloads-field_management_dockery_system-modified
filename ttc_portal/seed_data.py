"""
seed_data.py — Jaza data za mwanzo (seed) kwa TTC Student Portal.

Inajumuisha:
  • Vyuo vyote vya ualimu (TTCs) vinavyotoa Diploma in Education
  • Programu 2 kwa kila chuo (Arts & Science)
  • Ada ya Mwaka + Mchango wa Chuo kwa kila chuo
  • Super admin, msimamizi wa chuo (Kasulu) na wanafunzi wa mfano

Endeleza:  python seed_data.py
"""

import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ttc_portal.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from colleges.models import College, Program, CollegeAdmin
from fees.models import FeeItem
from students.models import Student
from fees.services import create_bills_for_student, academic_year_now

User = get_user_model()

# Demo accounts (super admin / college admin / wanafunzi wa mfano) huundwa TU
# wakati TTC_SEED_DEMO=true au DEBUG=true. Production haipaswi kuwa na
# admin/admin123 wazi! Vyuo, programu na ada huundwa siku zote (data halisi).
DEMO_ENABLED = (
    os.environ.get('TTC_SEED_DEMO', '').lower() == 'true'
    or getattr(settings, 'DEBUG', False)
)

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

    # 4. Super admin / msimamizi wa chuo / wanafunzi wa mfano
    #    (DEMO tu — production hujenga akaunti zake kwa createsuperuser)
    year = academic_year_now()
    if not DEMO_ENABLED:
        print("\n   ⚠️  Demo accounts ZIMERUKWA (production mode).")
        print("       Tengeneza super admin: python manage.py createsuperuser")
        print("       au weka TTC_SEED_DEMO=true kwenye uanzishaji wa kwanza tu.")
    else:
        # Super admin
        super_admin, _ = User.objects.get_or_create(
            username='admin',
            defaults={'email': 'admin@ttc.ac.tz', 'role': 'super_admin', 'is_staff': True,
                      'is_superuser': True, 'first_name': 'Super', 'last_name': 'Admin'},
        )
        super_admin.set_password('admin123')
        super_admin.is_staff = True
        super_admin.is_superuser = True
        super_admin.role = 'super_admin'
        super_admin.save()

        # Msimamizi wa chuo (Kasulu TC)
        kasulu = College.objects.get(code='KAS')
        admin_user, _ = User.objects.get_or_create(
            username='kasulu_admin',
            defaults={'email': 'kasulu@ttc.ac.tz', 'role': 'college_admin',
                      'first_name': 'Mkuu', 'last_name': 'Kasulu'},
        )
        admin_user.set_password('admin123')
        admin_user.role = 'college_admin'
        admin_user.save()
        CollegeAdmin.objects.get_or_create(
            user=admin_user,
            defaults={'college': kasulu, 'full_name': 'Mtumishi wa Mahesabu — Kasulu TC',
                      'title': 'Mtumishi wa Mahesabu'},
        )

        # Wanafunzi wa mfano
        demo_students = [
            ("KAS", "Juma Hassan Mussa", "KAS/2026/014", 1, "M", "0712 345 678", "juma@gmail.com", "juma2026"),
            ("BUT", "Neema Joseph Kileo", "BUT/2026/007", 1, "F", "0755 123 456", "neema@gmail.com", "neema2026"),
            ("MOR", "Baraka Emmanuel John", "MOR/2026/021", 2, "M", "0768 234 567", "baraka@gmail.com", "baraka2026"),
        ]
        for code, name, reg, yr, gender, phone, email, pw in demo_students:
            college = College.objects.get(code=code)
            username = reg
            user, created = User.objects.get_or_create(
                username=username,
                defaults={'email': email, 'role': 'student', 'phone_number': phone},
            )
            if created:
                user.set_password(pw)
                user.save()
            student, created = Student.objects.get_or_create(
                registration_number=reg,
                defaults=dict(
                    user=user, college=college,
                    full_name=name, admission_year=2026, year_of_study=yr,
                    gender=gender, phone_number=phone, email=email,
                ),
            )
            if created:
                program = college.programs.first()
                if program:
                    student.program = program
                    student.save()
                create_bills_for_student(student, year)
            print(f"  {'✓' if created else '='} Mwanafunzi: {name} ({reg}) @ {college.short_name}")

        print("\n✅ Seed imekamilika!")
        print("   ─────────────────────────────────────────────")
        print("   Super Admin    : admin / admin123")
        print("   Kasulu Admin   : kasulu_admin / admin123")
        for _, _, reg, _, _, _, _, pw in demo_students:
            print(f"   Mwanafunzi     : {reg} / {pw}")
        print("   ─────────────────────────────────────────────")
        print("   Mwaka wa masomo: ", year)


if __name__ == '__main__':
    run()

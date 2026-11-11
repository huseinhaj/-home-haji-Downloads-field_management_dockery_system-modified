from django.core.management.base import BaseCommand

from field_app.models import MaterialSource

SOURCES = [
    {
        'name': 'Wazaelimu',
        'site_url': 'https://wazaelimu.com',
        'listing_urls': [
            'https://wazaelimu.com/category/notes-zote/',
            'https://wazaelimu.com/full-notes-for-secondary-education-all-subjects/',
            'https://wazaelimu.com/full-notes-advanced-level-form-5-6-all-subjects/',
            'https://wazaelimu.com/tie-books-download-pdf-form-1-6/',
        ],
        'default_type': 'notes',
        'max_articles_per_run': 15,
    },
    {
        'name': 'Lusa Elimu',
        'site_url': 'https://app.lusaelimu.com',
        'listing_urls': [
            'https://app.lusaelimu.com/category/notes/',
            'https://lusaelimu.co.tz/',
        ],
        'default_type': 'notes',
        'max_articles_per_run': 15,
    },
    {
        'name': 'Mitihani.co.tz',
        'site_url': 'https://mitihani.co.tz',
        'listing_urls': [
            'https://mitihani.co.tz/',
            'https://mitihani.co.tz/category/form-two-notes/',
        ],
        'default_type': 'exam',
        'max_articles_per_run': 15,
    },
    {
        'name': 'Elimu Zone',
        'site_url': 'https://elimuzone.com',
        'listing_urls': [
            'https://elimuzone.com/',
        ],
        'default_type': 'mixed',
        'max_articles_per_run': 10,
    },
    {
        # Teacher.ac — notes za TZ Form 1-6 (PDFs zimefichwa kwenye viewer.html?file=...)
        # url_filter inazuia kurasa za Uganda/Kenya zilizo mbele kwenye listing ileile
        'name': 'Teacher.ac',
        'site_url': 'https://teacher.ac',
        'listing_urls': [
            'https://teacher.ac/tanzania-school-resources/',
        ],
        'default_type': 'notes',
        'max_articles_per_run': 40,
        'url_filter': r'notes-tanzania',
    },
    {
        # Shule Direct — NECTA past papers (PDF za moja kwa moja kutoka S3)
        'name': 'Shule Direct',
        'site_url': 'https://notes.shuledirect.co.tz',
        'listing_urls': [
            'https://notes.shuledirect.co.tz/past-papers',
        ],
        'default_type': 'exam',
        'max_articles_per_run': 10,
    },
    {
        # Maktaba TETEA — past papers 5000+ (NECTA PSLE/FTNA/CSEE/ACSEE),
        # marking schemes, syllabi na study aids (Shika na Mikono) — PDF za
        # moja kwa moja kwenye kurasa za resources, hakuna JS-gating.
        'name': 'Maktaba TETEA',
        'site_url': 'https://maktaba.tetea.org',
        'listing_urls': [
            'https://maktaba.tetea.org/resources/standard-1-4/',
            'https://maktaba.tetea.org/resources/standard-5-7/',
            'https://maktaba.tetea.org/resources/form-1-2/',
            'https://maktaba.tetea.org/resources/form-3-4/',
            'https://maktaba.tetea.org/resources/form-5-6/',
        ],
        'default_type': 'exam',
        'max_articles_per_run': 60,
    },
]


class Command(BaseCommand):
    help = ('Weka/refresh vyanzo vya Maktaba (Wazaelimu, Lusa Elimu, Mitihani, '
            'Elimu Zone, Teacher.ac, Shule Direct, Maktaba TETEA).')

    def handle(self, *args, **opts):
        created_count = 0
        for src in SOURCES:
            obj, created = MaterialSource.objects.update_or_create(
                name=src['name'],
                defaults={
                    'site_url': src['site_url'],
                    'listing_urls': src['listing_urls'],
                    'default_type': src['default_type'],
                    'max_articles_per_run': src['max_articles_per_run'],
                    'url_filter': src.get('url_filter', ''),
                    'enabled': True,
                },
            )
            if created:
                created_count += 1
            self.stdout.write(f"{'✚' if created else '↻'} {obj.name} — {len(obj.listing_urls)} listings")
        self.stdout.write(self.style.SUCCESS(
            f'Vyanzo {len(SOURCES)} vimewekwa ({created_count} mpya).'))

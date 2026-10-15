"""Onyesha kitufe cha Fernet kinachotumika sasa kusimba password za ESS.

Matumizi:
    python manage.py ess_enc_key

Kama `ESS_ENC_KEY` haipo, kitufe hutokana na `DJANGO_SECRET_KEY`. Unaweza
kuweka matokeo ya amri hii kwenye env `ESS_ENC_KEY` ili kitufe kibaki kile
kile (inaendana na password zilizohifadhiwa awali).
"""
from django.core.management.base import BaseCommand

from ess_tracker.crypto import effective_key


class Command(BaseCommand):
    help = 'Onyesha kitufe cha Fernet (base64) kinachotumika kusimba password za ESS.'

    def add_arguments(self, parser):
        parser.add_argument('--show-source', action='store_true',
                            help='Onyesha kitufe kinatoka wapi (env au SECRET_KEY)')

    def handle(self, *args, **opts):
        import os
        src = 'ESS_ENC_KEY (env)' if (os.environ.get('ESS_ENC_KEY') or '').strip() \
            else 'SECRET_KEY (derived)'
        if opts['show_source']:
            self.stdout.write(f'Chanzo: {src}')
        self.stdout.write(f'ESS_ENC_KEY={effective_key().decode()}')
        self.stdout.write(self.style.WARNING(
            'Hii ni siri — usiishirikishe hadharani. Weka kama env ya kudumu.'))

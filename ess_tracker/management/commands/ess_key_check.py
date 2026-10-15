"""Tambua kitufe cha Fernet kilichotumika kusimba password za ESS zilizopo.

Hutumika pale password zinaonekana 'hazisomiki' (kitufe kimebadilika):
unajaribu SECRET_KEY mbalimbali (za awali) ili kupata kitufe kinachofungua
token zilizohifadhiwa — bila kubadilisha password yoyote.

Matumizi:
    python manage.py ess_key_check <username>
    python manage.py ess_key_check <username> --default-secret
    python manage.py ess_key_check <username> --secret "<DJANGO_SECRET_KEY ya awali>"
    python manage.py ess_key_check <username> --fernet "<BASE64_FERNET_KEY>"

Ikifanikiwa, amri itaonyesha 'ESS_ENC_KEY=<base64>' — iweke kama env ya
kudumu, kisha usibadilishe tena.
"""
import base64
import hashlib

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ess_tracker.crypto import effective_key
from ess_tracker.models import TeacherProfile

DEFAULT_SECRET = 'dev-only-insecure-key-change-in-production'


def _derive(secret: str) -> bytes:
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode('utf-8')).digest())


class Command(BaseCommand):
    help = 'Tambua kitufe cha Fernet kinachofungua password za ESS zilizohifadhiwa.'

    def add_arguments(self, parser):
        parser.add_argument('username', nargs='?', default=None,
                            help='ESS username (tupu = chukua sampuli yoyote)')
        parser.add_argument('--secret', action='append', default=[],
                            help='Jaribu DJANGO_SECRET_KEY hii (inaweza kurudiwa)')
        parser.add_argument('--default-secret', action='store_true',
                            help='Jaribu pia SECRET_KEY ya default ya Django')
        parser.add_argument('--fernet', action='append', default=[],
                            help='Jaribu Fernet key (base64) hii moja kwa moja')
        parser.add_argument('--show-current', action='store_true',
                            help='Onyesha kitufe cha sasa (kama --secret ya sasa)')

    def handle(self, *args, **opts):
        qs = TeacherProfile.objects.exclude(ess_password='')
        if opts['username']:
            qs = qs.filter(ess_username__iexact=opts['username'])
        profile = qs.order_by('-created_at').first()
        if profile is None:
            raise CommandError('Hakuna wasifu wenye password iliyohifadhiwa kwenye DB hii.')

        token = profile.ess_password.encode('ascii')
        self.stdout.write(f'Sampuli: ess_username={profile.ess_username!r} '
                          f'id={profile.id} token_len={len(token)}')

        candidates = [('kitufe cha sasa (env/SECRET_KEY)', effective_key())]
        if opts['show_current']:
            self.stdout.write(f'  kitufe cha sasa = {effective_key().decode()} (siri!)')
        if opts['default_secret']:
            candidates.append(('SECRET_KEY ya default ya Django', _derive(DEFAULT_SECRET)))
        for s in opts['secret']:
            candidates.append((f'--secret {s[:6]}…', _derive(s)))
        for f in opts['fernet']:
            candidates.append((f'--fernet {f[:6]}…', f.strip().encode('ascii')))

        winner = None
        for label, key in candidates:
            try:
                Fernet(key).decrypt(token)
                self.stdout.write(self.style.SUCCESS(f'✅ {label}: INAFUNGA'))
                winner = key
            except Exception as e:
                self.stdout.write(f'❌ {label}: {type(e).__name__}')

        if winner is None:
            self.stdout.write(self.style.WARNING(
                'Hakuna kitufe kilichofungua. Jaribu --secret "<DJANGO_SECRET_KEY ya awali>" '
                'au --default-secret.'))
            return
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Kitufe sahihi (weka kama env ESS_ENC_KEY, kisha usibadilishe):'))
        self.stdout.write(f'ESS_ENC_KEY={winner.decode()}')

"""Weka password ya ESS (na hiari washa/zima kuidhinisha) kwa wasifu wa mkuu/mwalimu.

Matumizi:
    python manage.py ess_set_password <ess_username> <password> [--approver|--no-approver]
    python manage.py ess_set_password <ess_username> --list
"""
from django.core.management.base import BaseCommand, CommandError

from ess_tracker.models import TeacherProfile


class Command(BaseCommand):
    help = ('Weka password mpya ya ESS (kwa usimbaji sahihi) na hiari washa '
            'au zima uwezo wa kuidhinisha (approver_enabled).')

    def add_arguments(self, parser):
        parser.add_argument('username', help='ESS username ya wasifu')
        parser.add_argument('password', nargs='?', default=None,
                            help='password mpya ya ESS (acha tupu ukitumia --list)')
        parser.add_argument('--approver', action='store_true',
                            help='Washa approver_enabled (role ya mkuu)')
        parser.add_argument('--no-approver', action='store_true',
                            help='Zima approver_enabled')
        parser.add_argument('--list', action='store_true',
                            help='Onyesha hali ya wasifu bila kubadilisha kitu')

    def _state(self, profile) -> str:
        if not profile.ess_password:
            return 'HAIPO (tupu)'
        return 'inasomika' if profile.ess_password_plain else 'HAISOMIKI (kitufe kimebadilika)'

    def handle(self, *args, **opts):
        qs = TeacherProfile.objects.filter(ess_username__iexact=opts['username'])
        if not qs.exists():
            raise CommandError(f'Wasifu wa ESS "{opts["username"]}" haupo kwenye DB hii.')
        if qs.count() > 1:
            self.stderr.write(self.style.WARNING(
                f'ONYO: kuna wasifu {qs.count()} wenye username hii — '
                f'nitarekebisha wa karibuni zaidi.'))
        profile = qs.order_by('-created_at').first()

        self.stdout.write(
            f'Wasifu id={profile.id} jina={profile.full_name!r} '
            f'ess_ready={profile.ess_ready} approver={profile.approver_enabled} '
            f'password={self._state(profile)}')

        if opts['list']:
            return

        changed = False
        if opts['password']:
            profile.set_ess_password(opts['password'])
            changed = True
        if opts['approver']:
            profile.approver_enabled = True
            changed = True
        elif opts['no_approver']:
            profile.approver_enabled = False
            changed = True

        if not changed:
            raise CommandError('Hakuna kilichobadilika. Toa password na/au --approver/--no-approver.')

        profile.save()
        self.stdout.write(self.style.SUCCESS(
            f'SAVED id={profile.id} ess_ready={profile.ess_ready} '
            f'approver={profile.approver_enabled} password={self._state(profile)}'))

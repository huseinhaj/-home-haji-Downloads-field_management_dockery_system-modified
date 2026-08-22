import logging

from django.contrib.auth.backends import BaseBackend

from .models import TeacherAccount

logger = logging.getLogger('results.auth')


class ResultsAuthBackend(BaseBackend):
    """Authenticates results-app teacher/academic accounts, kept entirely
    separate from field_app.CustomUser (own model, own database).

    Uses an explicit database to bypass any router misconfiguration."""

    DB = 'results'

    def authenticate(self, request, email=None, password=None, **kwargs):
        if not email or not password:
            return None
        email = email.strip()
        try:
            account = TeacherAccount.objects.using(self.DB).get(email__iexact=email)
        except TeacherAccount.DoesNotExist:
            # Logged so a "wrong password" report can be told apart from a
            # genuinely mistyped password vs. the account/email not
            # existing on the 'results' DB at all — without this, both
            # look identical to the user and undiagnosable from outside.
            logger.warning("login failed: no TeacherAccount for email=%r", email)
            return None
        if not account.is_active:
            logger.warning("login failed: account inactive, email=%r id=%s", email, account.pk)
            return None
        if not account.check_password(password):
            logger.warning(
                "login failed: password mismatch, email=%r id=%s has_usable_password=%s",
                email, account.pk, account.has_usable_password(),
            )
            return None
        return account

    def get_user(self, user_id):
        try:
            return TeacherAccount.objects.using(self.DB).get(pk=user_id)
        except TeacherAccount.DoesNotExist:
            return None

from django.contrib.auth.backends import BaseBackend

from .models import TeacherAccount


class ResultsAuthBackend(BaseBackend):
    """Authenticates results-app teacher/academic accounts, kept entirely
    separate from field_app.CustomUser (own model, own database)."""

    def authenticate(self, request, email=None, password=None, **kwargs):
        if not email or not password:
            return None
        try:
            account = TeacherAccount.objects.get(email__iexact=email)
        except TeacherAccount.DoesNotExist:
            return None
        if account.is_active and account.check_password(password):
            return account
        return None

    def get_user(self, user_id):
        try:
            return TeacherAccount.objects.get(pk=user_id)
        except TeacherAccount.DoesNotExist:
            return None

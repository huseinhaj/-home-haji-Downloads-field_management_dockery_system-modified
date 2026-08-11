from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()


class IdentifierBackend(ModelBackend):
    """Allow login with EITHER the registration number (username)
    OR the email address — exactly like the UDOM SR2 student portal."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        if username is None or password is None:
            return None

        identifier = username.strip()
        user = (
            User.objects
            .filter(Q(username__iexact=identifier) | Q(email__iexact=identifier))
            .first()
        )
        if user is None:
            # Fall back to the default backend behaviour (superuser via admin)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

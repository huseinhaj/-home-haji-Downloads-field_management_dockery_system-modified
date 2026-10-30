from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from .models import TeacherAccount


def results_login_required(view_func):
    """Kurasa za /shule/ ni za akaunti za shule (TeacherAccount) tu.

    CustomUser wa mfumo mkuu/ESS anaweza kuwa ameingia kwenye session
    hiyo hiyo; hana `school`, hivyo tumpeleke kwenye login ya matokeo
    badala ya kusababisha AttributeError kwenye views.
    """
    @wraps(view_func)
    @login_required(login_url='results_login')
    def _wrapped(request, *args, **kwargs):
        if not isinstance(request.user, TeacherAccount):
            return redirect('results_login')
        return view_func(request, *args, **kwargs)
    return _wrapped


def _role_required(is_role_fn, message):
    def decorator(view_func):
        @wraps(view_func)
        @results_login_required
        def _wrapped(request, *args, **kwargs):
            if not is_role_fn(request.user):
                raise PermissionDenied(message)
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


academic_required = _role_required(lambda user: getattr(user, 'is_academic', False), "Academic access required.")
teacher_required = _role_required(lambda user: getattr(user, 'is_teacher', False), "Teacher access required.")
# Academic Officers often teach a subject themselves — anything a subject
# teacher can do (marks entry, above all) should be open to them too.
teacher_or_academic_required = _role_required(
    lambda user: getattr(user, 'is_teacher', False) or getattr(user, 'is_academic', False),
    "Teacher or Academic access required.",
)
printing_secretary_required = _role_required(
    lambda user: getattr(user, 'is_printing_secretary', False),
    "Printing Secretary access required.",
)

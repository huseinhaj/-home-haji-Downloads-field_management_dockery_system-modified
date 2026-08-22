from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

results_login_required = login_required(login_url='results_login')


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

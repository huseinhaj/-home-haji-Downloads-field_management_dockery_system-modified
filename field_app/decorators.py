from functools import wraps
from django.shortcuts import redirect


def board_login_required(view_func):
    """Redirect to main login if not authenticated."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return wrapper


def assessor_login_required(view_func):
    """Redirect to assessor login if not authenticated."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('assessor_login')
        return view_func(request, *args, **kwargs)
    return wrapper

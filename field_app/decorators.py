from functools import wraps
from django.shortcuts import redirect


def board_login_required(view_func):
    """Require authenticated board member; add no-cache headers."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('board_login')
        try:
            bm = request.user.board_member
        except Exception:
            bm = None
        if bm is None:
            return redirect('board_login')
        response = view_func(request, *args, **kwargs)
        response['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
        response['Pragma'] = 'no-cache'
        return response
    return wrapper


def assessor_login_required(view_func):
    """Redirect to assessor login if not authenticated; add no-cache headers."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('assessor_login')
        try:
            from field_app.models import Assessor
            if not Assessor.objects.filter(user=request.user).exists():
                return redirect('assessor_login')
        except Exception:
            pass
        response = view_func(request, *args, **kwargs)
        response['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
        response['Pragma'] = 'no-cache'
        return response
    return wrapper

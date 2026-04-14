from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

from .utils import get_role_redirect_url, get_user_role


TEACHER_ROLE = "teacher"
STUDENT_ROLE = "student"


def teacher_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("accounts:login")

        if get_user_role(request.user) != TEACHER_ROLE:
            messages.warning(request, "当前账号不是教师账号，已为你跳转到对应端口。")
            return redirect(get_role_redirect_url(request.user))

        return view_func(request, *args, **kwargs)

    return _wrapped_view



def student_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("accounts:login")

        if get_user_role(request.user) != STUDENT_ROLE:
            messages.warning(request, "当前账号不是学生账号，已为你跳转到对应端口。")
            return redirect(get_role_redirect_url(request.user))

        return view_func(request, *args, **kwargs)

    return _wrapped_view

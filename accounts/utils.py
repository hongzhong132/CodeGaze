from django.urls import reverse

from .models import UserProfile


DEFAULT_ROLE = "student"
TEACHER_ROLE = "teacher"


def get_user_profile(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def get_user_role(user):
    if not user.is_authenticated:
        return DEFAULT_ROLE

    profile = get_user_profile(user)
    role = getattr(profile, "role", DEFAULT_ROLE) or DEFAULT_ROLE
    return TEACHER_ROLE if role == TEACHER_ROLE else DEFAULT_ROLE


def is_teacher(user):
    return get_user_role(user) == TEACHER_ROLE


def get_role_redirect_url(user):
    if is_teacher(user):
        return reverse("teacher:dashboard")
    return reverse("programming:problem_zones")


def get_profile_base_template(user):
    return "teacher_base.html" if is_teacher(user) else "student_base.html"


def get_profile_back_url(user):
    if is_teacher(user):
        return reverse("teacher:dashboard")
    return reverse("programming:problem_list")


def get_profile_back_label(user):
    return "返回教师首页" if is_teacher(user) else "返回题目列表"

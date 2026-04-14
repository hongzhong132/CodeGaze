from django.contrib import messages
from django.contrib.auth import get_user_model, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse

from .forms import CustomPasswordChangeForm, ProfileUpdateForm, RegisterForm
from .models import UserProfile
from .utils import (
    get_profile_back_label,
    get_profile_back_url,
    get_role_redirect_url,
    get_user_profile,
    get_user_role,
)
from programming.models import ProblemFavorite

User = get_user_model()


class CustomLoginView(LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        return self.get_redirect_url() or get_role_redirect_url(self.request.user)

    def form_valid(self, form):
        messages.success(self.request, "登录成功，欢迎回来。")
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "用户名或密码错误，请重试。")
        return super().form_invalid(form)


def register_view(request):
    if request.user.is_authenticated:
        return redirect(get_role_redirect_url(request.user))

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            username = form.cleaned_data["username"]
            password = form.cleaned_data["password1"]

            with transaction.atomic():
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                )
                UserProfile.objects.get_or_create(
                    user=user,
                    defaults={"role": "student"},
                )

            messages.success(request, "注册成功，请使用新账号登录。")
            return redirect("accounts:login")
        else:
            messages.error(request, "注册失败，请检查填写内容。")
    else:
        form = RegisterForm()

    return render(request, "accounts/register.html", {"form": form})


@login_required(login_url="accounts:login")
def role_redirect_view(request):
    return redirect(get_role_redirect_url(request.user))


@login_required(login_url="accounts:login")
def profile_view(request):
    profile = get_user_profile(request.user)
    user_role = get_user_role(request.user)

    favorite_count = 0
    recent_favorites = []
    if user_role == "student":
        favorite_qs = (
            ProblemFavorite.objects.filter(user=request.user)
            .select_related("problem")
            .order_by("-created_at")
        )
        favorite_count = favorite_qs.count()
        recent_favorites = favorite_qs[:6]

    if request.method == "POST":
        form_type = request.POST.get("form_type")

        if form_type == "profile":
            profile_form = ProfileUpdateForm(
                request.POST,
                request.FILES,
                instance=profile,
                user=request.user,
            )
            password_form = CustomPasswordChangeForm(request.user)

            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "个人资料已更新。")
                return redirect("accounts:profile")
            else:
                messages.error(request, "资料保存失败，请检查填写内容。")

        elif form_type == "password":
            profile_form = ProfileUpdateForm(instance=profile, user=request.user)
            password_form = CustomPasswordChangeForm(request.user, request.POST)

            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, "密码修改成功。")
                return redirect("accounts:profile")
            else:
                messages.error(request, "密码修改失败，请检查输入内容。")

        else:
            profile_form = ProfileUpdateForm(instance=profile, user=request.user)
            password_form = CustomPasswordChangeForm(request.user)
    else:
        profile_form = ProfileUpdateForm(instance=profile, user=request.user)
        password_form = CustomPasswordChangeForm(request.user)

    context = {
        "profile": profile,
        "profile_form": profile_form,
        "password_form": password_form,
        "favorite_count": favorite_count,
        "recent_favorites": recent_favorites,
        "user_role": user_role,
        "base_template": "teacher_base.html" if user_role == "teacher" else "student_base.html",
        "back_url": get_profile_back_url(request.user),
        "back_label": get_profile_back_label(request.user),
        "primary_url": reverse("teacher:dashboard") if user_role == "teacher" else "/admin/",
        "primary_label": "教师端首页" if user_role == "teacher" else "管理后台",
        "sidebar_avatar_url": profile.avatar.url if getattr(profile, "avatar", None) else "",
    }
    return render(request, "accounts/profile.html", context)


@login_required(login_url="accounts:login")
def switch_account_view(request):
    logout(request)
    messages.info(request, "请使用其他账号登录。")
    return redirect("accounts:login")


@login_required(login_url="accounts:login")
def logout_view(request):
    logout(request)
    messages.success(request, "你已退出登录。")
    return redirect("accounts:login")
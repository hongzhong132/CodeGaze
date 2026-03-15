from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.urls import reverse_lazy

from .forms import ProfileUpdateForm, CustomPasswordChangeForm
from .models import Profile
from programming.models import ProblemFavorite


class CustomLoginView(LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        return self.get_redirect_url() or str(reverse_lazy("programming:problem_list"))

    def form_valid(self, form):
        messages.success(self.request, "登录成功，欢迎回来。")
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "用户名或密码错误，请重试。")
        return super().form_invalid(form)


@login_required(login_url="accounts:login")
def profile_view(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)

    # ===== 收藏题目数据 =====
    favorite_qs = ProblemFavorite.objects.filter(
        user=request.user
    ).select_related("problem").order_by("-created_at")

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

        elif form_type == "password":
            profile_form = ProfileUpdateForm(
                instance=profile,
                user=request.user,
            )
            password_form = CustomPasswordChangeForm(
                request.user,
                request.POST,
            )

            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, "密码修改成功。")
                return redirect("accounts:profile")

        else:
            profile_form = ProfileUpdateForm(
                instance=profile,
                user=request.user,
            )
            password_form = CustomPasswordChangeForm(request.user)

    else:
        profile_form = ProfileUpdateForm(
            instance=profile,
            user=request.user,
        )
        password_form = CustomPasswordChangeForm(request.user)

    return render(
        request,
        "accounts/profile.html",
        {
            "profile": profile,
            "profile_form": profile_form,
            "password_form": password_form,
            "favorite_count": favorite_count,
            "recent_favorites": recent_favorites,
        },
    )


def switch_account_view(request):
    if request.user.is_authenticated:
        logout(request)
        messages.info(request, "请使用其他账号登录。")
    return redirect("accounts:login")


def logout_view(request):
    if request.user.is_authenticated:
        logout(request)
        messages.success(request, "你已退出登录。")
    return redirect("accounts:login")
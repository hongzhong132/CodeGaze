from django.shortcuts import redirect
from django.urls import reverse


def home_redirect(request):
    if request.user.is_authenticated:
        return redirect(reverse("programming:problem_list"))
    return redirect(reverse("accounts:login"))
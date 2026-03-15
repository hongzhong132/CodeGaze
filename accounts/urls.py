from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.CustomLoginView.as_view(), name="login"),
    path("profile/", views.profile_view, name="profile"),
    path("switch/", views.switch_account_view, name="switch_account"),
    path("logout/", views.logout_view, name="logout"),
]
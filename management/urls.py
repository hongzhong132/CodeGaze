from django.urls import path

from . import views

app_name = "management"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("problems/", views.problem_list, name="problem_list"),
    path("problems/create/", views.problem_create, name="problem_create"),
    path("problems/<int:pk>/edit/", views.problem_edit, name="problem_edit"),
    path("problems/<int:pk>/delete/", views.problem_delete, name="problem_delete"),
    path("users/", views.user_list, name="user_list"),
    path("submissions/", views.submission_list, name="submission_list"),
]

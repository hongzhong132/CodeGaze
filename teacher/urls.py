from django.urls import path

from . import views

app_name = "teacher"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("students/", views.student_list, name="student_list"),
    path("students/<int:user_id>/", views.student_detail, name="student_detail"),
    path("problems/", views.problem_analysis, name="problem_analysis"),
    path("recommendations/", views.recommendation_overview, name="recommendation_overview"),
]

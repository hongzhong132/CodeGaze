from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, render

from accounts.decorators import teacher_required
from .services import (
    get_dashboard_stats,
    get_problem_analysis_data,
    get_recommendation_data,
    get_student_detail_data,
    get_student_summary_list,
)


@login_required(login_url="accounts:login")
@teacher_required
def dashboard(request):
    context = get_dashboard_stats()
    return render(request, "teacher/dashboard.html", context)


@login_required(login_url="accounts:login")
@teacher_required
def student_list(request):
    context = {"students": get_student_summary_list()}
    return render(request, "teacher/student_list.html", context)


@login_required(login_url="accounts:login")
@teacher_required
def student_detail(request, user_id):
    student = get_object_or_404(User, id=user_id)
    context = get_student_detail_data(student)
    return render(request, "teacher/student_detail.html", context)


@login_required(login_url="accounts:login")
@teacher_required
def problem_analysis(request):
    context = get_problem_analysis_data(request)
    return render(request, "teacher/problem_analysis.html", context)


@login_required(login_url="accounts:login")
@teacher_required
def recommendation_overview(request):
    context = get_recommendation_data(request)
    return render(request, "teacher/recommendation.html", context)
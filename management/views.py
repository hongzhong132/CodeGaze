from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import UserProfile
from programming.models import CodeProblem, CodeSubmission, ProblemDiscussion, ProblemFavorite

from .forms import ProblemManageForm

User = get_user_model()

QUESTION_TYPE_CARDS = [
    {
        "value": "function",
        "label": "函数补全",
        "icon": "bi-braces-asterisk",
        "headline": "更适合算法训练 / 面试风格题",
        "description": "学生只需补全函数主体，平台负责参数注入与返回值判定。",
        "tips": [
            "一定要填写函数名与参数名，方便前端自动展示函数签名。",
            "输入 / 输出示例尽量写成结构化 JSON，便于教师端分析。",
            "测试用例推荐使用 input + expected 的标准结构。",
        ],
    },
    {
        "value": "acm",
        "label": "标准输入输出",
        "icon": "bi-terminal",
        "headline": "更适合竞赛 / OJ 真题风格",
        "description": "学生自己处理 stdin / stdout，更贴近 ACM、蓝桥杯、洛谷等场景。",
        "tips": [
            "要把输入格式、输出格式、样例输入、样例输出写清楚。",
            "数据范围尽量完整，避免学生无法判断算法复杂度。",
            "测试用例也建议覆盖边界值、空输入、最大规模输入。",
        ],
    },
]


def management_access_allowed(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True

    profile = getattr(user, "profile", None)
    return bool(profile and profile.role == "teacher")


def management_required(view_func):
    return login_required(user_passes_test(management_access_allowed)(view_func))


def paginate_queryset(queryset, request, per_page=10):
    paginator = Paginator(queryset, per_page)
    return paginator.get_page(request.GET.get("page"))


def split_csv(value):
    if not value:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


@management_required
def dashboard(request):
    now = timezone.now()
    recent_days = now - timezone.timedelta(days=7)

    total_users = User.objects.count()
    total_students = UserProfile.objects.filter(role="student").count()
    total_teachers = UserProfile.objects.filter(role="teacher").count()
    total_problems = CodeProblem.objects.count()
    total_submissions = CodeSubmission.objects.count()
    total_discussions = ProblemDiscussion.objects.count()
    total_favorites = ProblemFavorite.objects.count()

    new_users_7d = User.objects.filter(date_joined__gte=recent_days).count()
    new_submissions_7d = CodeSubmission.objects.filter(submitted_at__gte=recent_days).count()

    difficulty_stats = list(
        CodeProblem.objects.values("difficulty").annotate(total=Count("id")).order_by("difficulty")
    )
    category_stats = list(
        CodeProblem.objects.values("category").annotate(total=Count("id")).order_by("-total", "category")[:8]
    )
    recent_problems = CodeProblem.objects.order_by("-created_at")[:6]
    recent_submissions = (
        CodeSubmission.objects.select_related("user", "problem")
        .order_by("-submitted_at")[:8]
    )

    high_risk_problems = (
        CodeProblem.objects.filter(submission_count__gt=0)
        .annotate(
            wrong_count=Count("submissions", filter=~Q(submissions__status="AC")),
            ac_count=Count("submissions", filter=Q(submissions__status="AC")),
        )
        .order_by("-wrong_count", "id")[:6]
    )

    context = {
        "page_title": "后台首页",
        "total_users": total_users,
        "total_students": total_students,
        "total_teachers": total_teachers,
        "total_problems": total_problems,
        "total_submissions": total_submissions,
        "total_discussions": total_discussions,
        "total_favorites": total_favorites,
        "new_users_7d": new_users_7d,
        "new_submissions_7d": new_submissions_7d,
        "difficulty_stats": difficulty_stats,
        "category_stats": category_stats,
        "recent_problems": recent_problems,
        "recent_submissions": recent_submissions,
        "high_risk_problems": high_risk_problems,
    }
    return render(request, "management/dashboard.html", context)


@management_required
def problem_list(request):
    keyword = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    difficulty = request.GET.get("difficulty", "").strip()
    stage = request.GET.get("stage", "").strip()

    queryset = CodeProblem.objects.all().order_by("-updated_at", "-id")

    if keyword:
        queryset = queryset.filter(
            Q(title__icontains=keyword)
            | Q(tags__icontains=keyword)
            | Q(knowledge_points__icontains=keyword)
        )

    if category:
        queryset = queryset.filter(category=category)

    if difficulty:
        queryset = queryset.filter(difficulty=difficulty)

    if stage:
        queryset = queryset.filter(recommend_stage=stage)

    page_obj = paginate_queryset(queryset, request, per_page=10)

    context = {
        "page_title": "题库管理",
        "page_obj": page_obj,
        "keyword": keyword,
        "category": category,
        "difficulty": difficulty,
        "stage": stage,
        "category_choices": CodeProblem.CATEGORY_CHOICES,
        "difficulty_choices": CodeProblem.DIFFICULTY_CHOICES,
        "stage_choices": CodeProblem.STAGE_CHOICES,
        "question_total": queryset.count(),
    }
    return render(request, "management/problems/list.html", context)


def _build_problem_editor_context(form, is_create=False, problem=None):
    instance = problem or getattr(form, "instance", None)
    current_type = None
    if form.is_bound:
        current_type = form.data.get("question_type")
    if not current_type:
        current_type = form.initial.get("question_type") or getattr(instance, "question_type", "function") or "function"

    choice_maps = {
        "category": dict(CodeProblem.CATEGORY_CHOICES),
        "difficulty": dict(CodeProblem.DIFFICULTY_CHOICES),
        "stage": dict(CodeProblem.STAGE_CHOICES),
        "question_type": dict(CodeProblem.QUESTION_TYPE_CHOICES),
    }

    category_value = form["category"].value() or getattr(instance, "category", "")
    difficulty_value = form["difficulty"].value() or getattr(instance, "difficulty", "")
    stage_value = form["recommend_stage"].value() or getattr(instance, "recommend_stage", "")
    source_value = form["source"].value() or getattr(instance, "source", "") or "未填写"

    knowledge_points = split_csv(form["knowledge_points"].value() or getattr(instance, "knowledge_points", ""))
    tags = split_csv(form["tags"].value() or getattr(instance, "tags", ""))
    languages = split_csv(form["supported_languages"].value() or getattr(instance, "supported_languages", ""))

    current_type_card = next((item for item in QUESTION_TYPE_CARDS if item["value"] == current_type), QUESTION_TYPE_CARDS[0])

    return {
        "question_type_cards": QUESTION_TYPE_CARDS,
        "current_question_type": current_type,
        "current_type_card": current_type_card,
        "editor_overview": {
            "category_label": choice_maps["category"].get(category_value, category_value or "未设置"),
            "difficulty_label": choice_maps["difficulty"].get(difficulty_value, difficulty_value or "未设置"),
            "stage_label": choice_maps["stage"].get(stage_value, stage_value or "未设置"),
            "source_label": source_value,
            "knowledge_points": knowledge_points,
            "tags": tags,
            "languages": languages,
            "knowledge_points_count": len(knowledge_points),
            "tags_count": len(tags),
            "languages_count": len(languages),
        },
        "problem_metrics": {
            "submission_count": getattr(instance, "submission_count", 0) or 0,
            "accepted_count": getattr(instance, "accepted_count", 0) or 0,
            "acceptance_rate": getattr(instance, "acceptance_rate", 0) if instance and getattr(instance, "pk", None) else 0,
        },
        "is_editing": bool(instance and getattr(instance, "pk", None)),
        "problem": instance if instance and getattr(instance, "pk", None) else None,
        "json_examples": {
            "function_input": '{\n  "nums": [2, 7, 11, 15],\n  "target": 9\n}',
            "function_output": '[0, 1]',
            "test_cases": '[\n  {"input": [[2,7,11,15], 9], "expected": [0,1]},\n  {"input": [[3,2,4], 6], "expected": [1,2]}\n]',
            "acm_test_cases": '[\n  {"input": "5\\n1 2 3 4 5", "expected": "15"},\n  {"input": "3\\n10 20 30", "expected": "60"}\n]',
        },
    }


@management_required
def problem_create(request):
    if request.method == "POST":
        form = ProblemManageForm(request.POST)
        if form.is_valid():
            problem = form.save()
            messages.success(request, f"题目《{problem.title}》新增成功。")
            return redirect("management:problem_edit", pk=problem.pk)
        messages.error(request, "提交失败，请检查表单内容。")
    else:
        form = ProblemManageForm(initial={"question_type": "function"})

    context = {
        "page_title": "新增题目",
        "form": form,
        "is_create": True,
    }
    context.update(_build_problem_editor_context(form=form, is_create=True))
    return render(request, "management/problems/form.html", context)


@management_required
def problem_edit(request, pk):
    problem = get_object_or_404(CodeProblem, pk=pk)

    if request.method == "POST":
        form = ProblemManageForm(request.POST, instance=problem)
        if form.is_valid():
            problem = form.save()
            messages.success(request, f"题目《{problem.title}》已更新。")
            return redirect("management:problem_edit", pk=problem.pk)
        messages.error(request, "更新失败，请检查表单内容。")
    else:
        form = ProblemManageForm(instance=problem)

    context = {
        "page_title": "编辑题目",
        "form": form,
        "problem": problem,
        "is_create": False,
    }
    context.update(_build_problem_editor_context(form=form, problem=problem))
    return render(request, "management/problems/form.html", context)


@management_required
def problem_delete(request, pk):
    problem = get_object_or_404(CodeProblem, pk=pk)

    if request.method == "POST":
        title = problem.title
        problem.delete()
        messages.success(request, f"题目《{title}》已删除。")
        return redirect("management:problem_list")

    return render(
        request,
        "management/problems/delete.html",
        {
            "page_title": "删除题目",
            "problem": problem,
        },
    )


@management_required
def user_list(request):
    keyword = request.GET.get("q", "").strip()
    role = request.GET.get("role", "").strip()
    is_active = request.GET.get("is_active", "").strip()

    queryset = User.objects.select_related("profile").annotate(
        submission_total=Count("codesubmission", distinct=True)
    ).order_by("-date_joined", "-id")

    if keyword:
        queryset = queryset.filter(
            Q(username__icontains=keyword)
            | Q(email__icontains=keyword)
            | Q(profile__real_name__icontains=keyword)
            | Q(profile__student_no__icontains=keyword)
            | Q(profile__teacher_no__icontains=keyword)
        )

    if role:
        queryset = queryset.filter(profile__role=role)

    if is_active == "1":
        queryset = queryset.filter(is_active=True)
    elif is_active == "0":
        queryset = queryset.filter(is_active=False)

    page_obj = paginate_queryset(queryset, request, per_page=10)

    for obj in page_obj:
        obj.safe_profile = getattr(obj, "profile", None)

    context = {
        "page_title": "用户管理",
        "page_obj": page_obj,
        "keyword": keyword,
        "role": role,
        "is_active": is_active,
        "user_total": queryset.count(),
        "student_total": queryset.filter(profile__role="student").count(),
        "teacher_total": queryset.filter(profile__role="teacher").count(),
    }
    return render(request, "management/users/list.html", context)


@management_required
def submission_list(request):
    keyword = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    language = request.GET.get("language", "").strip()
    mode = request.GET.get("mode", "").strip()

    queryset = CodeSubmission.objects.select_related("user", "problem").order_by("-submitted_at")

    if keyword:
        queryset = queryset.filter(
            Q(problem__title__icontains=keyword)
            | Q(user__username__icontains=keyword)
            | Q(code__icontains=keyword)
        )

    if status:
        queryset = queryset.filter(status=status)

    if language:
        queryset = queryset.filter(language=language)

    if mode:
        queryset = queryset.filter(mode=mode)

    page_obj = paginate_queryset(queryset, request, per_page=12)

    context = {
        "page_title": "提交记录",
        "page_obj": page_obj,
        "keyword": keyword,
        "status": status,
        "language": language,
        "mode": mode,
        "submission_total": queryset.count(),
        "status_choices": CodeSubmission.STATUS_CHOICES,
        "language_choices": CodeSubmission.LANGUAGE_CHOICES,
        "mode_choices": CodeSubmission.MODE_CHOICES,
    }
    return render(request, "management/submissions/list.html", context)

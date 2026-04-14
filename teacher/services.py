from collections import Counter

from django.contrib.auth.models import User
from django.core.exceptions import FieldError
from django.db.models import Count, Q

from programming.models import CodeProblem, CodeSubmission, UserProblemStatus


ACCEPTED_STATUS = "accepted"
DEFAULT_CATEGORY = "未分类"
ROLE_LOOKUPS = (
    "profile__role",
    "userprofile__role",
    "accountprofile__role",
    "memberprofile__role",
)


def _safe_category(value):
    return value or DEFAULT_CATEGORY


def _clamp(value, low=0, high=100):
    return max(low, min(high, value))


def _truncate_text(text, limit=14):
    text = str(text or "")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _get_student_queryset():
    """
    优先按 role=student 获取学生。
    如果当前项目里没有显式的 profile role 关系，就退化为：
    1) 非超管、非 staff 用户；
    2) 如果仍然没有，再退到“至少提交过代码的用户”。
    """
    base_qs = User.objects.filter(is_active=True)

    for lookup in ROLE_LOOKUPS:
        try:
            qs = base_qs.filter(**{lookup: "student"}).distinct()
            qs.exists()
            if qs.exists():
                return qs
        except FieldError:
            continue

    fallback_qs = base_qs.filter(is_superuser=False, is_staff=False).distinct()
    if fallback_qs.exists():
        return fallback_qs

    active_submitter_ids = (
        CodeSubmission.objects.filter(user__isnull=False)
        .values_list("user_id", flat=True)
        .distinct()
    )
    return User.objects.filter(id__in=active_submitter_ids, is_superuser=False).distinct()


def _get_student_submissions(student):
    return (
        CodeSubmission.objects.filter(user=student)
        .select_related("problem")
        .order_by("-submitted_at")
    )


def _get_student_statuses(student):
    return (
        UserProblemStatus.objects.filter(user=student)
        .select_related("problem")
        .order_by("-updated_at")
    )


def _build_student_snapshot(student):
    submissions = list(_get_student_submissions(student))
    statuses = list(_get_student_statuses(student))

    problem_stats = {}

    for submission in submissions:
        if not submission.problem_id:
            continue

        item = problem_stats.setdefault(
            submission.problem_id,
            {
                "problem": submission.problem,
                "problem_id": submission.problem_id,
                "title": submission.problem.title,
                "category": _safe_category(getattr(submission.problem, "category", None)),
                "attempts": 0,
                "accepted_count": 0,
                "wrong_count": 0,
                "status": None,
                "is_favorite": False,
            },
        )

        item["attempts"] += 1
        if submission.status == ACCEPTED_STATUS:
            item["accepted_count"] += 1
        else:
            item["wrong_count"] += 1

    for status in statuses:
        if not status.problem_id:
            continue

        item = problem_stats.setdefault(
            status.problem_id,
            {
                "problem": status.problem,
                "problem_id": status.problem_id,
                "title": status.problem.title,
                "category": _safe_category(getattr(status.problem, "category", None)),
                "attempts": 0,
                "accepted_count": 0,
                "wrong_count": 0,
                "status": None,
                "is_favorite": False,
            },
        )

        item["attempts"] = max(item["attempts"], status.attempt_count or 0)
        item["wrong_count"] = max(item["wrong_count"], status.wrong_count or 0)
        item["is_favorite"] = item["is_favorite"] or bool(status.is_favorite)

        if status.status == "passed":
            item["status"] = "passed"
            item["accepted_count"] = max(item["accepted_count"], 1)
        elif status.status == "needs_work" and item["status"] != "passed":
            item["status"] = "needs_work"
        elif status.status == "tried" and item["status"] not in ("passed", "needs_work"):
            item["status"] = "tried"

    for item in problem_stats.values():
        if item["status"]:
            continue

        if item["accepted_count"] > 0:
            item["status"] = "passed"
        elif item["wrong_count"] >= 2:
            item["status"] = "needs_work"
        elif item["attempts"] > 0:
            item["status"] = "tried"
        else:
            item["status"] = "unseen"

    category_stats = {}
    for item in problem_stats.values():
        category = item["category"]
        stats = category_stats.setdefault(
            category,
            {
                "category": category,
                "problems": 0,
                "total": 0,  # 兼容旧模板字段
                "attempts": 0,
                "passed": 0,
                "tried": 0,
                "needs_work": 0,
                "wrong_count": 0,
                "focus_score": 0,
                "accept_rate": 0,
            },
        )

        stats["problems"] += 1
        stats["total"] += 1
        stats["attempts"] += item["attempts"]
        stats["wrong_count"] += item["wrong_count"]

        if item["status"] == "passed":
            stats["passed"] += 1
        elif item["status"] == "needs_work":
            stats["needs_work"] += 1
        elif item["status"] == "tried":
            stats["tried"] += 1

    for stats in category_stats.values():
        stats["focus_score"] = (
            stats["wrong_count"]
            + stats["needs_work"] * 3
            + stats["attempts"]
            - stats["passed"]
        )
        if stats["attempts"] > 0:
            stats["accept_rate"] = round(stats["passed"] / stats["attempts"] * 100, 2)

    category_stats_list = sorted(
        category_stats.values(),
        key=lambda x: (-x["focus_score"], -x["wrong_count"], x["category"]),
    )

    total_submissions = len(submissions)
    accepted_submissions = sum(1 for item in submissions if item.status == ACCEPTED_STATUS)
    passed_problems = sum(1 for item in problem_stats.values() if item["status"] == "passed")
    tried_count = sum(1 for item in problem_stats.values() if item["status"] == "tried")
    needs_work_count = sum(1 for item in problem_stats.values() if item["status"] == "needs_work")
    favorite_count = sum(1 for item in problem_stats.values() if item["is_favorite"])
    wrong_submissions = sum(item["wrong_count"] for item in problem_stats.values())
    accept_rate = round(accepted_submissions / total_submissions * 100, 2) if total_submissions else 0

    weak_problem_list = sorted(
        [
            item
            for item in problem_stats.values()
            if item["status"] == "needs_work" or item["wrong_count"] > 0
        ],
        key=lambda x: (-x["wrong_count"], -x["attempts"], x["title"]),
    )

    recent_submission_time = submissions[0].submitted_at if submissions else None

    return {
        "student": student,
        "submissions": submissions,
        "statuses": statuses,
        "recent_submissions": submissions[:20],
        "total_submissions": total_submissions,
        "accepted_submissions": accepted_submissions,
        "accept_rate": accept_rate,
        "passed_problems": passed_problems,
        "tried_count": tried_count,
        "needs_work_count": needs_work_count,
        "favorite_count": favorite_count,
        "wrong_submissions": wrong_submissions,
        "category_stats_list": category_stats_list,
        "problem_stats": sorted(problem_stats.values(), key=lambda x: x["title"]),
        "weak_problem_list": weak_problem_list,
        "recent_submission_time": recent_submission_time,
        "focus_score": (
            needs_work_count * 5
            + wrong_submissions
            + max(total_submissions - accepted_submissions, 0)
        ),
    }


def _build_student_ability_profile(snapshot):
    """
    按分类生成能力画像。
    这里不依赖复杂算法，完全基于现有提交 / 通过 / 错误数据做规则评分。
    """
    profile = []

    for item in snapshot.get("category_stats_list", []):
        problems = int(item.get("problems", 0))
        attempts = int(item.get("attempts", 0))
        passed = int(item.get("passed", 0))
        needs_work = int(item.get("needs_work", 0))
        wrong_count = int(item.get("wrong_count", 0))
        accept_rate = float(item.get("accept_rate", 0))

        coverage_score = (passed / problems * 100) if problems else 0
        practice_score = min((attempts / max(problems, 1)) * 18, 18)
        penalty_score = min(needs_work * 10 + wrong_count * 1.8, 38)

        ability_score = (
            coverage_score * 0.45
            + accept_rate * 0.37
            + practice_score
            - penalty_score
        )
        ability_score = round(_clamp(ability_score, 5, 98), 1)

        risk_index = round(
            _clamp(
                wrong_count * 6 + needs_work * 18 + max(attempts - passed, 0) * 2,
                0,
                100,
            ),
            1,
        )

        if ability_score >= 80:
            mastery_label = "稳定掌握"
            mastery_badge_class = "bg-success-subtle text-success-emphasis"
        elif ability_score >= 60:
            mastery_label = "持续提升"
            mastery_badge_class = "bg-primary-subtle text-primary-emphasis"
        elif ability_score >= 40:
            mastery_label = "需要强化"
            mastery_badge_class = "bg-warning-subtle text-warning-emphasis"
        else:
            mastery_label = "重点关注"
            mastery_badge_class = "bg-danger-subtle text-danger-emphasis"

        profile.append(
            {
                "category": item["category"],
                "problems": problems,
                "attempts": attempts,
                "passed": passed,
                "needs_work": needs_work,
                "wrong_count": wrong_count,
                "accept_rate": round(accept_rate, 2),
                "focus_score": item.get("focus_score", 0),
                "ability_score": ability_score,
                "risk_index": risk_index,
                "mastery_label": mastery_label,
                "mastery_badge_class": mastery_badge_class,
            }
        )

    profile.sort(
        key=lambda x: (-x["risk_index"], x["ability_score"], x["category"])
    )
    return profile


def _build_student_radar_data(ability_profile):
    radar_items = sorted(
        ability_profile,
        key=lambda x: (-x["attempts"], -x["focus_score"], x["category"]),
    )[:6]

    return {
        "indicators": [
            {"name": _truncate_text(item["category"], 8), "max": 100}
            for item in radar_items
        ],
        "values": [round(item["ability_score"], 1) for item in radar_items],
        "full_labels": [item["category"] for item in radar_items],
    }


def _build_student_graph_data(snapshot, ability_profile):
    student = snapshot["student"]

    nodes = [
        {
            "id": f"student_{student.id}",
            "name": student.username,
            "category": 0,
            "symbolSize": 68,
            "value": snapshot.get("accept_rate", 0),
        }
    ]
    links = []
    categories = [
        {"name": "学生"},
        {"name": "能力维度"},
        {"name": "待攻克题目"},
    ]

    profile_for_graph = sorted(
        ability_profile,
        key=lambda x: (-x["risk_index"], -x["attempts"], x["category"]),
    )[:6]

    category_node_map = {}

    for index, item in enumerate(profile_for_graph):
        node_id = f"category_{index}_{item['category']}"
        category_node_map[item["category"]] = node_id

        nodes.append(
            {
                "id": node_id,
                "name": f"{item['category']}\n{int(item['ability_score'])}分",
                "category": 1,
                "symbolSize": int(_clamp(32 + item["risk_index"] * 0.35, 34, 72)),
                "value": item["ability_score"],
            }
        )
        links.append(
            {
                "source": f"student_{student.id}",
                "target": node_id,
                "value": item["risk_index"],
            }
        )

    for weak_problem in snapshot.get("weak_problem_list", [])[:8]:
        category = weak_problem.get("category")
        if category not in category_node_map:
            continue

        problem_id = weak_problem.get("problem_id")
        node_id = f"problem_{problem_id}"

        nodes.append(
            {
                "id": node_id,
                "name": _truncate_text(weak_problem.get("title", "未命名题目"), 12),
                "category": 2,
                "symbolSize": int(
                    _clamp(20 + weak_problem.get("wrong_count", 0) * 4, 22, 54)
                ),
                "value": weak_problem.get("wrong_count", 0),
            }
        )
        links.append(
            {
                "source": category_node_map[category],
                "target": node_id,
                "value": weak_problem.get("wrong_count", 0),
            }
        )

    return {
        "nodes": nodes,
        "links": links,
        "categories": categories,
    }


def _build_student_ability_summary(snapshot, ability_profile):
    if not ability_profile:
        return {
            "stage_label": "暂无训练数据",
            "stage_badge_class": "bg-secondary-subtle text-secondary-emphasis",
            "stage_description": "该学生当前还没有足够的数据形成稳定能力画像。",
            "strong_categories": [],
            "weak_categories": [],
            "strong_text": "暂无明显强项",
            "weak_text": "暂无明显薄弱项",
            "focus_problem_count": 0,
            "summary_text": "建议先引导学生完成基础题训练，逐步积累可分析数据。",
        }

    strong_categories = sorted(
        ability_profile,
        key=lambda x: (-x["ability_score"], x["risk_index"], x["category"]),
    )[:2]

    weak_categories = sorted(
        ability_profile,
        key=lambda x: (-x["risk_index"], x["ability_score"], x["category"]),
    )[:2]

    total_submissions = snapshot.get("total_submissions", 0)
    accept_rate = snapshot.get("accept_rate", 0)
    needs_work_count = snapshot.get("needs_work_count", 0)

    if total_submissions == 0:
        stage_label = "暂无训练数据"
        stage_badge_class = "bg-secondary-subtle text-secondary-emphasis"
        stage_description = "当前尚未检测到有效提交记录。"
    elif accept_rate >= 70 and needs_work_count <= 2:
        stage_label = "稳定提升阶段"
        stage_badge_class = "bg-success-subtle text-success-emphasis"
        stage_description = "通过率较高，待攻克题较少，整体处于较稳定的提升状态。"
    elif accept_rate >= 45:
        stage_label = "持续训练阶段"
        stage_badge_class = "bg-primary-subtle text-primary-emphasis"
        stage_description = "已有一定训练积累，但部分分类仍存在波动，需要持续巩固。"
    else:
        stage_label = "重点干预阶段"
        stage_badge_class = "bg-danger-subtle text-danger-emphasis"
        stage_description = "当前错误与待攻克题偏多，建议教师优先做专项干预。"

    strong_text = "、".join(item["category"] for item in strong_categories) if strong_categories else "暂无明显强项"
    weak_text = "、".join(item["category"] for item in weak_categories) if weak_categories else "暂无明显薄弱项"

    summary_text = (
        f"当前该学生的相对优势方向是 {strong_text}，"
        f"当前最需要补强的方向是 {weak_text}。"
        f"建议优先围绕薄弱分类安排 1～2 轮基础巩固训练，"
        f"再逐步加入同类变式题，帮助其稳定形成解题方法。"
    )

    return {
        "stage_label": stage_label,
        "stage_badge_class": stage_badge_class,
        "stage_description": stage_description,
        "strong_categories": strong_categories,
        "weak_categories": weak_categories,
        "strong_text": strong_text,
        "weak_text": weak_text,
        "focus_problem_count": len(snapshot.get("weak_problem_list", [])),
        "summary_text": summary_text,
    }


def get_dashboard_stats():
    students = list(_get_student_queryset().order_by("id"))
    student_ids = [student.id for student in students]

    submissions_qs = CodeSubmission.objects.filter(user_id__in=student_ids)
    students_count = len(students)
    submissions_count = submissions_qs.count()
    accepted_count = submissions_qs.filter(status=ACCEPTED_STATUS).count()
    overall_accept_rate = round(accepted_count / submissions_count * 100, 2) if submissions_count else 0

    hot_wrong_problems = (
        CodeProblem.objects.annotate(
            wrong_count=Count(
                "submissions",
                filter=Q(submissions__user_id__in=student_ids) & ~Q(submissions__status=ACCEPTED_STATUS),
            ),
            submit_count=Count(
                "submissions",
                filter=Q(submissions__user_id__in=student_ids),
            ),
        )
        .filter(submit_count__gt=0)
        .order_by("-wrong_count", "-submit_count", "title")[:8]
    )

    hard_students = []
    for snapshot in [_build_student_snapshot(student) for student in students]:
        if snapshot["total_submissions"] == 0 and snapshot["needs_work_count"] == 0:
            continue

        hard_students.append(
            {
                "student": snapshot["student"],
                "username": snapshot["student"].username,
                "needs_work_count": snapshot["needs_work_count"],
                "wrong_submissions": snapshot["wrong_submissions"],
                "accept_rate": snapshot["accept_rate"],
                "focus_score": snapshot["focus_score"],
            }
        )

    hard_students.sort(
        key=lambda x: (-x["focus_score"], -x["wrong_submissions"], x["username"])
    )

    active_students_count = submissions_qs.values("user_id").distinct().count()

    return {
        "students_count": students_count,
        "active_students_count": active_students_count,
        "submissions_count": submissions_count,
        "accepted_count": accepted_count,
        "overall_accept_rate": overall_accept_rate,
        "hot_wrong_problems": hot_wrong_problems,
        "hard_students": hard_students[:8],
    }


def get_student_summary_list():
    students = list(_get_student_queryset().order_by("id"))
    result = []

    for student in students:
        snapshot = _build_student_snapshot(student)
        result.append(
            {
                "student": snapshot["student"],
                "total_submissions": snapshot["total_submissions"],
                "accepted_submissions": snapshot["accepted_submissions"],
                "passed_problems": snapshot["passed_problems"],
                "tried_count": snapshot["tried_count"],
                "needs_work_count": snapshot["needs_work_count"],
                "favorite_count": snapshot["favorite_count"],
                "wrong_submissions": snapshot["wrong_submissions"],
                "accept_rate": snapshot["accept_rate"],
                "focus_score": snapshot["focus_score"],
                "recent_submission_time": snapshot["recent_submission_time"],
            }
        )

    result.sort(
        key=lambda x: (
            -x["focus_score"],
            -x["wrong_submissions"],
            x["student"].username,
        )
    )
    return result


def _build_student_recommendation_card(snapshot):
    category_stats = snapshot.get("category_stats_list", [])
    if not category_stats:
        return None

    best_category = category_stats[0]
    recommended_category = best_category.get("category") or DEFAULT_CATEGORY

    raw_score = best_category.get("focus_score")
    if raw_score is None:
        raw_score = (
            int(best_category.get("wrong_count", 0)) * 2
            + int(best_category.get("needs_work", 0)) * 3
            + int(best_category.get("attempts", 0))
        )
    score = int(raw_score)

    if score >= 120:
        focus_level = "高风险"
        focus_badge_class = "bg-danger-subtle text-danger-emphasis"
    elif score >= 40:
        focus_level = "中风险"
        focus_badge_class = "bg-warning-subtle text-warning-emphasis"
    else:
        focus_level = "低风险"
        focus_badge_class = "bg-success-subtle text-success-emphasis"

    passed_problem_ids = {
        item["problem_id"]
        for item in snapshot.get("problem_stats", [])
        if item.get("status") == "passed"
    }

    recommended_problem_qs = CodeProblem.objects.filter(category=recommended_category)
    if recommended_category == DEFAULT_CATEGORY:
        recommended_problem_qs = CodeProblem.objects.filter(
            Q(category__isnull=True) | Q(category="")
        )

    recommended_problem_list = list(
        recommended_problem_qs.exclude(id__in=passed_problem_ids).order_by("id")[:3]
    )

    if not recommended_problem_list:
        recommended_problem_list = list(
            CodeProblem.objects.exclude(id__in=passed_problem_ids).order_by("id")[:3]
        )

    problem_note_map = ["基础巩固", "边界训练", "变式提升"]
    recommended_problems = []
    for idx, problem in enumerate(recommended_problem_list):
        recommended_problems.append(
            {
                "id": problem.id,
                "title": problem.title,
                "category": getattr(problem, "category", "") or DEFAULT_CATEGORY,
                "note": problem_note_map[idx] if idx < len(problem_note_map) else "专项练习",
            }
        )

    diagnosis = (
        f"该学生在“{recommended_category}”方向累计尝试 {best_category.get('attempts', 0)} 次，"
        f"待攻克 {best_category.get('needs_work', 0)} 题，"
        f"累计错误 {best_category.get('wrong_count', 0)} 次，"
        f"当前通过率为 {snapshot.get('accept_rate', 0)}%。"
    )

    teacher_advice = (
        f"建议先进行“{recommended_category}”基础巩固训练，"
        f"优先解决高频错误题，再逐步加入同类变式题，帮助学生稳定掌握解题思路。"
    )

    return {
        "recommended_category": recommended_category,
        "score": score,
        "focus_level": focus_level,
        "focus_badge_class": focus_badge_class,
        "diagnosis": diagnosis,
        "teacher_advice": teacher_advice,
        "recommended_problems": recommended_problems,
    }


def get_student_detail_data(student):
    snapshot = _build_student_snapshot(student)
    statuses_qs = _get_student_statuses(student)
    submissions_qs = _get_student_submissions(student)

    passed_list = statuses_qs.filter(status="passed")
    needs_work_list = statuses_qs.filter(status="needs_work")
    tried_list = statuses_qs.filter(status="tried")
    favorites = statuses_qs.filter(is_favorite=True)

    recommendation_card = _build_student_recommendation_card(snapshot)

    ability_profile_list = _build_student_ability_profile(snapshot)
    radar_chart_data = _build_student_radar_data(ability_profile_list)
    student_graph_data = _build_student_graph_data(snapshot, ability_profile_list)
    ability_summary = _build_student_ability_summary(snapshot, ability_profile_list)

    return {
        "student": student,
        "statuses": statuses_qs,
        "recent_submissions": submissions_qs[:20],
        "passed_list": passed_list,
        "needs_work_list": needs_work_list,
        "tried_list": tried_list,
        "favorites": favorites,
        "total_submissions": snapshot["total_submissions"],
        "accepted_submissions": snapshot["accepted_submissions"],
        "accept_rate": snapshot["accept_rate"],
        "category_stats_list": snapshot["category_stats_list"],
        "weak_problem_list": snapshot["weak_problem_list"][:10],
        "recommendation_card": recommendation_card,

        # 新增：学生能力画像数据
        "ability_profile_list": ability_profile_list,
        "radar_chart_data": radar_chart_data,
        "student_graph_data": student_graph_data,
        "ability_summary": ability_summary,
        "passed_problems": snapshot["passed_problems"],
        "tried_count": snapshot["tried_count"],
        "needs_work_count": snapshot["needs_work_count"],
        "wrong_submissions": snapshot["wrong_submissions"],
        "favorite_count": snapshot["favorite_count"],
    }


def get_problem_analysis_data(request=None):
    keyword = ""
    category_filter = ""
    difficulty_filter = ""
    sort_filter = "wrong_desc"

    if request is not None:
        keyword = request.GET.get("keyword", "").strip()
        category_filter = request.GET.get("category", "").strip()
        difficulty_filter = request.GET.get("difficulty", "").strip()
        sort_filter = request.GET.get("sort", "wrong_desc").strip()

    student_ids = list(_get_student_queryset().values_list("id", flat=True))
    problems = CodeProblem.objects.all().order_by("id")

    all_rows = []
    category_choices = set()
    difficulty_choices = set()

    for problem in problems:
        category = getattr(problem, "category", None) or DEFAULT_CATEGORY
        difficulty = getattr(problem, "difficulty", None) or "未设置"

        category_choices.add(category)
        difficulty_choices.add(difficulty)

        submissions = CodeSubmission.objects.filter(problem=problem, user_id__in=student_ids)
        statuses = UserProblemStatus.objects.filter(problem=problem, user_id__in=student_ids)

        total_submissions = submissions.count()
        accepted_count = submissions.filter(status=ACCEPTED_STATUS).count()
        wrong_count = max(total_submissions - accepted_count, 0)
        passed_users = statuses.filter(status="passed").count()
        needs_work_users = statuses.filter(status="needs_work").count()
        accept_rate = round(accepted_count / total_submissions * 100, 2) if total_submissions else 0

        if total_submissions >= 100:
            heat_level = "高热度"
            heat_badge_class = "bg-danger-subtle text-danger-emphasis"
        elif total_submissions >= 20:
            heat_level = "中热度"
            heat_badge_class = "bg-warning-subtle text-warning-emphasis"
        else:
            heat_level = "低热度"
            heat_badge_class = "bg-success-subtle text-success-emphasis"

        if total_submissions == 0:
            risk_level = "暂无数据"
            risk_badge_class = "bg-secondary-subtle text-secondary-emphasis"
        elif wrong_count >= 20 or (total_submissions >= 10 and accept_rate < 20):
            risk_level = "高风险"
            risk_badge_class = "bg-danger-subtle text-danger-emphasis"
        elif wrong_count >= 5 or accept_rate < 40:
            risk_level = "中风险"
            risk_badge_class = "bg-warning-subtle text-warning-emphasis"
        else:
            risk_level = "低风险"
            risk_badge_class = "bg-success-subtle text-success-emphasis"

        all_rows.append(
            {
                "problem": problem,
                "category": category,
                "difficulty": difficulty,
                "total_submissions": total_submissions,
                "accepted_count": accepted_count,
                "wrong_count": wrong_count,
                "passed_users": passed_users,
                "needs_work_users": needs_work_users,
                "accept_rate": accept_rate,
                "heat_level": heat_level,
                "heat_badge_class": heat_badge_class,
                "risk_level": risk_level,
                "risk_badge_class": risk_badge_class,
            }
        )

    filtered_rows = []
    for item in all_rows:
        title = getattr(item["problem"], "title", "") or ""

        if keyword and keyword.lower() not in title.lower():
            continue
        if category_filter and item["category"] != category_filter:
            continue
        if difficulty_filter and item["difficulty"] != difficulty_filter:
            continue

        filtered_rows.append(item)

    if sort_filter == "accept_asc":
        filtered_rows.sort(
            key=lambda x: (x["accept_rate"] if x["total_submissions"] > 0 else 101, -x["wrong_count"], x["problem"].id)
        )
    elif sort_filter == "accept_desc":
        filtered_rows.sort(
            key=lambda x: (-x["accept_rate"], -x["total_submissions"], x["problem"].id)
        )
    elif sort_filter == "submit_desc":
        filtered_rows.sort(
            key=lambda x: (-x["total_submissions"], -x["wrong_count"], x["problem"].id)
        )
    elif sort_filter == "id_asc":
        filtered_rows.sort(key=lambda x: x["problem"].id)
    else:
        filtered_rows.sort(
            key=lambda x: (-x["wrong_count"], -x["total_submissions"], x["problem"].id)
        )

    problem_count = len(filtered_rows)
    active_problem_count = sum(1 for item in filtered_rows if item["total_submissions"] > 0)
    high_risk_problem_count = sum(1 for item in filtered_rows if item["risk_level"] == "高风险")

    average_accept_rate = 0
    active_rows = [item for item in filtered_rows if item["total_submissions"] > 0]
    if active_rows:
        average_accept_rate = round(
            sum(item["accept_rate"] for item in active_rows) / len(active_rows),
            1,
        )

    category_summary_map = {}
    for item in filtered_rows:
        category = item["category"]
        if category not in category_summary_map:
            category_summary_map[category] = {
                "category": category,
                "problem_count": 0,
                "active_problem_count": 0,
                "total_submissions": 0,
                "wrong_count": 0,
                "accepted_count": 0,
            }

        category_summary_map[category]["problem_count"] += 1
        if item["total_submissions"] > 0:
            category_summary_map[category]["active_problem_count"] += 1
        category_summary_map[category]["total_submissions"] += item["total_submissions"]
        category_summary_map[category]["wrong_count"] += item["wrong_count"]
        category_summary_map[category]["accepted_count"] += item["accepted_count"]

    category_summary = []
    for value in category_summary_map.values():
        total_submissions = value["total_submissions"]
        value["accept_rate"] = round(
            value["accepted_count"] / total_submissions * 100, 2
        ) if total_submissions else 0
        category_summary.append(value)

    category_summary.sort(key=lambda x: (-x["wrong_count"], -x["total_submissions"], x["category"]))

    top_categories = [
        {"category": item["category"], "count": item["problem_count"]}
        for item in category_summary[:5]
    ]

    if category_summary:
        summary_text = "当前问题主要集中在：" + "、".join(
            f"{item['category']}（错误 {item['wrong_count']} 次）"
            for item in category_summary[:3]
        )
    else:
        summary_text = "当前暂无可用的分类汇总数据。"

    return {
        "problems": filtered_rows,
        "problem_count": problem_count,
        "active_problem_count": active_problem_count,
        "average_accept_rate": average_accept_rate,
        "high_risk_problem_count": high_risk_problem_count,
        "category_summary": category_summary[:6],
        "top_categories": top_categories,
        "summary_text": summary_text,
        "category_choices": sorted(category_choices),
        "difficulty_choices": sorted(difficulty_choices),
        "current_filters": {
            "keyword": keyword,
            "category": category_filter,
            "difficulty": difficulty_filter,
            "sort": sort_filter,
        },
    }


def get_recommendation_data(request=None):
    keyword = ""
    focus_filter = ""
    category_filter = ""

    if request is not None:
        keyword = request.GET.get("keyword", "").strip()
        focus_filter = request.GET.get("focus", "").strip()
        category_filter = request.GET.get("category", "").strip()

    students = list(_get_student_queryset().order_by("id"))
    all_recommendations = []
    all_categories = set()

    def get_focus_meta(score):
        if score >= 120:
            return "高风险", "bg-danger-subtle text-danger-emphasis"
        if score >= 40:
            return "中风险", "bg-warning-subtle text-warning-emphasis"
        return "低风险", "bg-success-subtle text-success-emphasis"

    problem_note_map = ["基础巩固", "边界训练", "变式提升"]

    for student in students:
        snapshot = _build_student_snapshot(student)
        category_stats = snapshot.get("category_stats_list", [])

        if not category_stats:
            continue

        for stat in category_stats:
            category_name = stat.get("category") or DEFAULT_CATEGORY
            stat["category"] = category_name
            all_categories.add(category_name)

        best_category = category_stats[0]
        recommended_category = best_category.get("category") or DEFAULT_CATEGORY
        score = int(best_category.get("focus_score", 0))

        focus_level, focus_badge_class = get_focus_meta(score)

        passed_problem_ids = {
            item["problem_id"]
            for item in snapshot.get("problem_stats", [])
            if item.get("status") == "passed"
        }

        recommended_problem_qs = CodeProblem.objects.filter(category=recommended_category)
        if recommended_category == DEFAULT_CATEGORY:
            recommended_problem_qs = CodeProblem.objects.filter(
                Q(category__isnull=True) | Q(category="")
            )

        recommended_problem_list = list(
            recommended_problem_qs.exclude(id__in=passed_problem_ids).order_by("id")[:3]
        )

        if not recommended_problem_list:
            recommended_problem_list = list(
                CodeProblem.objects.exclude(id__in=passed_problem_ids).order_by("id")[:3]
            )

        recommended_problems = []
        for idx, problem in enumerate(recommended_problem_list):
            recommended_problems.append(
                {
                    "id": problem.id,
                    "title": problem.title,
                    "category": getattr(problem, "category", "") or DEFAULT_CATEGORY,
                    "note": problem_note_map[idx] if idx < len(problem_note_map) else "专项练习",
                }
            )

        diagnosis = (
            f"该学生在“{recommended_category}”方向累计尝试 {best_category.get('attempts', 0)} 次，"
            f"待攻克 {best_category.get('needs_work', 0)} 题，"
            f"累计错误 {best_category.get('wrong_count', 0)} 次，"
            f"当前通过率为 {snapshot.get('accept_rate', 0)}%。"
        )

        teacher_advice = (
            f"建议先进行“{recommended_category}”基础巩固训练，"
            f"优先解决高频错误题，再逐步加入同类变式题，帮助学生稳定掌握解题思路。"
        )

        all_recommendations.append(
            {
                "student": student,
                "recommended_category": recommended_category,
                "score": score,
                "focus_level": focus_level,
                "focus_badge_class": focus_badge_class,
                "diagnosis": diagnosis,
                "teacher_advice": teacher_advice,
                "accept_rate": snapshot.get("accept_rate", 0),
                "total_submissions": snapshot.get("total_submissions", 0),
                "needs_work_count": snapshot.get("needs_work_count", 0),
                "wrong_submissions": snapshot.get("wrong_submissions", 0),
                "category_stats": category_stats,
                "recommended_problems": recommended_problems,
            }
        )

    filtered_recommendations = []

    for item in all_recommendations:
        if keyword and keyword.lower() not in item["student"].username.lower():
            continue
        if focus_filter and item["focus_level"] != focus_filter:
            continue
        if category_filter and item["recommended_category"] != category_filter:
            continue
        filtered_recommendations.append(item)

    filtered_recommendations.sort(
        key=lambda x: (-x["score"], -x["wrong_submissions"], x["student"].username)
    )

    category_counter = Counter()
    priority_counter = Counter()

    for item in filtered_recommendations:
        category_counter[item["recommended_category"]] += 1
        priority_counter[item["focus_level"]] += 1

    top_categories = [
        {"category": category, "count": count}
        for category, count in category_counter.most_common(5)
    ]

    recommendation_count = len(filtered_recommendations)
    high_priority_count = priority_counter.get("高风险", 0)
    medium_priority_count = priority_counter.get("中风险", 0)
    low_priority_count = priority_counter.get("低风险", 0)

    avg_focus_score = 0
    if recommendation_count > 0:
        avg_focus_score = round(
            sum(item["score"] for item in filtered_recommendations) / recommendation_count, 1
        )

    if top_categories:
        summary_text = "当前推荐主要集中在：" + "、".join(
            f"{item['category']}（{item['count']}人）" for item in top_categories[:3]
        )
    else:
        summary_text = "当前暂无可用推荐方向统计。"

    focus_choices = ["高风险", "中风险", "低风险"]
    category_choices = sorted(all_categories)

    return {
        "recommendations": filtered_recommendations,
        "recommendation_count": recommendation_count,
        "students_with_recommendation": recommendation_count,
        "top_categories": top_categories,
        "high_priority_count": high_priority_count,
        "medium_priority_count": medium_priority_count,
        "low_priority_count": low_priority_count,
        "avg_focus_score": avg_focus_score,
        "summary_text": summary_text,
        "focus_choices": focus_choices,
        "category_choices": category_choices,
        "current_filters": {
            "keyword": keyword,
            "focus": focus_filter,
            "category": category_filter,
        },
    }
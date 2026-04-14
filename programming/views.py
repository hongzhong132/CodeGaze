import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections import Counter

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.decorators import student_required
from .forms import DiscussionForm
from .models import CodeProblem, CodeSubmission, ProblemFavorite, UserProblemStatus
from .services.ai_assistant import get_ai_reply
from .services.face_detector import detect_faces_from_base64, face_backend_available
from .services.monitor_analyzer import analyze_monitor_result, build_monitor_message
from .services.problem_zones import (
    ZONE_CONFIGS,
    build_hot_labels,
    build_zone_buckets,
    get_problem_zone,
    get_zone_by_slug,
    split_csv_field,
)
from .services.recommendation import build_recommendation_dashboard

User = get_user_model()
logger = logging.getLogger(__name__)


# ==============================
# 多语言配置映射表
# ==============================
LANG_CONFIG = {
    'python': {
        'compile_cmd': None,
        'run_cmd': ['python', '-u'],
        'extension': '.py',
        'needs_class_name': False,
    },
    'c': {
        'compile_cmd': ['gcc', '-o', '{exe_path}', '{src_path}', '-O2', '-Wall', '-std=c11'],
        'run_cmd': ['{exe_path}'],
        'extension': '.c',
        'needs_class_name': False,
    },
    'cpp': {
        'compile_cmd': ['g++', '-o', '{exe_path}', '{src_path}', '-O2', '-std=c++17', '-Wall'],
        'run_cmd': ['{exe_path}'],
        'extension': '.cpp',
        'needs_class_name': False,
    },
    'java': {
        'compile_cmd': ['javac', '*.java'],
        'run_cmd': ['java', '-cp', '{dir_name}', '-Xmx128m', '-Xss64m', '{class_name}'],
        'extension': '.java',
        'needs_class_name': True,
    },
}


# ==============================
# 通用辅助函数
# ==============================
def get_language_config(lang):
    return LANG_CONFIG.get(lang)


def is_ajax_request(request):
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


def get_problem_mode(request, problem_id):
    """从 session 中读取当前题目的模式。默认是 practice。"""
    return request.session.get(f'problem_mode_{problem_id}', 'practice')


def get_mode_display(mode):
    return '考试模式' if mode == 'exam' else '练习模式'


def extract_java_class_name(code):
    """提取用户代码中的类名，用于重命名。"""
    code_no_comments = re.sub(r'//.*', '', code)
    match = re.search(r'public\s+class\s+([a-zA-Z_][a-zA-Z0-9_]*)', code_no_comments)
    if match:
        return match.group(1)

    match_default = re.search(r'^\s*class\s+([a-zA-Z_][a-zA-Z0-9_]*)', code_no_comments, re.MULTILINE)
    if match_default:
        return match_default.group(1)

    return 'Solution'


def format_error_message(stderr, lang, stage='运行'):
    if not stderr:
        return f'❌ {stage}错误：未知错误（无详细输出）'

    is_compile = '编译' in stage
    header = f"❌ {'编译错误' if is_compile else '运行时错误'} ({lang.upper()})"

    suggestions = {
        'c': '💡 检查：分号、变量未定义、头文件缺失、数组越界。',
        'cpp': '💡 检查：命名空间 std、括号匹配、C++17 特性兼容性。',
        'java': '💡 检查：类名必须与文件名一致（系统已自动处理）、包声明（请勿使用 package）、imports。',
        'python': '💡 检查：缩进错误、NameError、语法错误、编码问题。',
    }

    max_len = 1000
    truncated_stderr = stderr.strip()[:max_len] + ('...' if len(stderr) > max_len else '')
    return f"{header}\n\n{truncated_stderr}\n\n{suggestions.get(lang, '')}"


def _sync_user_problem_status(user, problem):
    return UserProblemStatus.sync_for_user_problem(user, problem)


# ==============================
# 题库 / 分区页辅助函数
# ==============================
def _normalize_text(value):
    return str(value or '').strip().lower()


def _get_display_value(obj, field_name, default=''):
    method = getattr(obj, f'get_{field_name}_display', None)
    if callable(method):
        try:
            return method()
        except Exception:
            return getattr(obj, field_name, default)
    return getattr(obj, field_name, default)


def _build_problem_list_url(params):
    base = reverse('programming:problem_list')
    encoded = params.urlencode()
    return f'{base}?{encoded}' if encoded else base


def _build_zone_detail_url(zone_slug, params):
    base = reverse('programming:problem_zone_detail', kwargs={'zone_slug': zone_slug})
    encoded = params.urlencode()
    return f'{base}?{encoded}' if encoded else base


def _get_user_problem_state(user, problem_ids):
    attempted_ids = set()
    passed_ids = set()
    favorite_problem_ids = set()

    if user.is_authenticated and problem_ids:
        submission_rows = CodeSubmission.objects.filter(
            user=user,
            problem_id__in=problem_ids,
        ).values_list('problem_id', 'status')

        for problem_id, status in submission_rows:
            attempted_ids.add(problem_id)
            if status == 'AC':
                passed_ids.add(problem_id)

        favorite_problem_ids = set(
            ProblemFavorite.objects.filter(
                user=user,
                problem_id__in=problem_ids,
            ).values_list('problem_id', flat=True)
        )

    retrying_ids = attempted_ids - passed_ids

    return {
        'attempted_ids': attempted_ids,
        'passed_ids': passed_ids,
        'retrying_ids': retrying_ids,
        'favorite_problem_ids': favorite_problem_ids,
    }


def _build_progress_meta(problem_id, user_state):
    attempted_ids = user_state['attempted_ids']
    passed_ids = user_state['passed_ids']
    retrying_ids = user_state['retrying_ids']

    if problem_id in passed_ids:
        return 'passed', '已通过', 'passed'
    if problem_id in retrying_ids:
        return 'retrying', '待攻克', 'retrying'
    if problem_id in attempted_ids:
        return 'attempted', '已尝试', 'attempted'
    return 'undone', '未开始', 'undone'


def _decorate_problem_cards(problems, user_state, request=None):
    decorated = []

    for problem in problems:
        zone = get_problem_zone(problem)
        problem.zone_meta = zone
        problem.zone_slug = zone['slug']
        problem.zone_name = zone['name']

        problem.category_label = _get_display_value(problem, 'category', getattr(problem, 'category', '未分类'))
        problem.difficulty_label = _get_display_value(problem, 'difficulty', getattr(problem, 'difficulty', '未分级'))
        problem.stage_label = _get_display_value(problem, 'recommend_stage', getattr(problem, 'recommend_stage', '未分阶段'))
        problem.question_type_label = _get_display_value(problem, 'question_type', getattr(problem, 'question_type', '未知类型'))

        problem.tag_list = split_csv_field(getattr(problem, 'tags', ''))
        problem.knowledge_point_list = split_csv_field(getattr(problem, 'knowledge_points', ''))
        problem.language_list = split_csv_field(getattr(problem, 'supported_languages', ''))

        progress_key, progress_label, progress_class = _build_progress_meta(problem.id, user_state)
        problem.user_progress_key = progress_key
        problem.user_progress_label = progress_label
        problem.user_progress_class = progress_class

        problem.is_favorited = problem.id in user_state['favorite_problem_ids']

        current_mode = get_problem_mode(request, problem.id) if request is not None else 'practice'
        problem.current_mode = current_mode
        problem.current_mode_label = get_mode_display(current_mode)
        problem.select_mode_url = reverse('programming:select_problem_mode', kwargs={'pk': problem.id})

        decorated.append(problem)

    return decorated


def _matches_problem_query(problem, q):
    if not q:
        return True

    q_norm = _normalize_text(q)
    fields = [
        getattr(problem, 'title', ''),
        getattr(problem, 'description', ''),
        getattr(problem, 'source', ''),
        getattr(problem, 'category', ''),
        _get_display_value(problem, 'category', ''),
        getattr(problem, 'difficulty', ''),
        _get_display_value(problem, 'difficulty', ''),
        getattr(problem, 'recommend_stage', ''),
        _get_display_value(problem, 'recommend_stage', ''),
        getattr(problem, 'tags', ''),
        getattr(problem, 'knowledge_points', ''),
        getattr(problem, 'question_type', ''),
        _get_display_value(problem, 'question_type', ''),
    ]

    return any(q_norm in _normalize_text(value) for value in fields)


def _matches_csv_keyword(field_value, keyword):
    if not keyword:
        return True
    keyword_norm = _normalize_text(keyword)
    return keyword_norm in {_normalize_text(item) for item in split_csv_field(field_value)}


def _filter_problems(
    problems,
    q='',
    difficulty='',
    stage='',
    tag='',
    language='',
    zone_slug='',
    progress='',
    only_favorite=False,
    user_state=None,
):
    user_state = user_state or {
        'attempted_ids': set(),
        'passed_ids': set(),
        'retrying_ids': set(),
        'favorite_problem_ids': set(),
    }

    filtered = []
    for problem in problems:
        if zone_slug and get_problem_zone(problem)['slug'] != zone_slug:
            continue

        if q and not _matches_problem_query(problem, q):
            continue

        if difficulty and getattr(problem, 'difficulty', '') != difficulty:
            continue

        if stage and getattr(problem, 'recommend_stage', '') != stage:
            continue

        if tag and not _matches_csv_keyword(getattr(problem, 'tags', ''), tag) and not _matches_csv_keyword(getattr(problem, 'knowledge_points', ''), tag):
            continue

        if language and not _matches_csv_keyword(getattr(problem, 'supported_languages', ''), language):
            continue

        if only_favorite and problem.id not in user_state['favorite_problem_ids']:
            continue

        if progress:
            attempted_ids = user_state['attempted_ids']
            passed_ids = user_state['passed_ids']
            retrying_ids = user_state['retrying_ids']

            if progress == 'undone' and problem.id in attempted_ids:
                continue
            if progress == 'passed' and problem.id not in passed_ids:
                continue
            if progress == 'retrying' and problem.id not in retrying_ids:
                continue
            if progress == 'favorite' and problem.id not in user_state['favorite_problem_ids']:
                continue

        filtered.append(problem)

    return filtered


def _build_problem_filter_options_from_iterable(problems):
    category_counter = Counter()
    difficulty_counter = Counter()
    stage_counter = Counter()
    tag_counter = Counter()
    language_counter = Counter()
    zone_counter = Counter()

    category_label_map = {}
    difficulty_label_map = {}
    stage_label_map = {}

    for problem in problems:
        category_value = getattr(problem, 'category', '')
        if category_value:
            category_counter[category_value] += 1
            category_label_map[category_value] = _get_display_value(problem, 'category', category_value)

        difficulty_value = getattr(problem, 'difficulty', '')
        if difficulty_value:
            difficulty_counter[difficulty_value] += 1
            difficulty_label_map[difficulty_value] = _get_display_value(problem, 'difficulty', difficulty_value)

        stage_value = getattr(problem, 'recommend_stage', '')
        if stage_value:
            stage_counter[stage_value] += 1
            stage_label_map[stage_value] = _get_display_value(problem, 'recommend_stage', stage_value)

        for tag in split_csv_field(getattr(problem, 'tags', '')):
            tag_counter[tag] += 1
        for point in split_csv_field(getattr(problem, 'knowledge_points', '')):
            tag_counter[point] += 1
        for lang in split_csv_field(getattr(problem, 'supported_languages', '')):
            language_counter[lang] += 1

        zone_counter[get_problem_zone(problem)['slug']] += 1

    category_options = [
        {'value': value, 'label': category_label_map.get(value, value), 'count': count}
        for value, count in category_counter.most_common()
    ]
    difficulty_options = [
        {'value': value, 'label': difficulty_label_map.get(value, value), 'count': count}
        for value, count in difficulty_counter.most_common()
    ]
    stage_options = [
        {'value': value, 'label': stage_label_map.get(value, value), 'count': count}
        for value, count in stage_counter.most_common()
    ]
    tag_options = [
        {'value': value, 'label': value, 'count': count}
        for value, count in tag_counter.most_common(20)
    ]
    language_options = [
        {
            'value': value,
            'label': value.upper() if len(value) <= 3 else value.title(),
            'count': count,
        }
        for value, count in language_counter.most_common()
    ]
    zone_options = []
    for zone in ZONE_CONFIGS:
        count = zone_counter.get(zone['slug'], 0)
        if count:
            zone_options.append({
                'value': zone['slug'],
                'label': zone['name'],
                'count': count,
            })

    return {
        'category_options': category_options,
        'difficulty_options': difficulty_options,
        'stage_options': stage_options,
        'tag_options': tag_options,
        'language_options': language_options,
        'zone_options': zone_options,
    }


def _build_current_filters(
    q='',
    difficulty='',
    stage='',
    tag='',
    language='',
    zone_slug='',
    progress='',
    only_favorite=False,
):
    zone_name_map = {zone['slug']: zone['name'] for zone in ZONE_CONFIGS}
    progress_name_map = {
        'undone': '未开始',
        'passed': '已通过',
        'retrying': '待攻克',
        'favorite': '只看收藏',
    }

    current_filters = []
    if zone_slug:
        current_filters.append({'key': '分区', 'value': zone_name_map.get(zone_slug, zone_slug)})
    if difficulty:
        current_filters.append({'key': '难度', 'value': difficulty})
    if stage:
        current_filters.append({'key': '阶段', 'value': stage})
    if tag:
        current_filters.append({'key': '标签', 'value': tag})
    if language:
        current_filters.append({'key': '语言', 'value': language.upper() if len(language) <= 3 else language.title()})
    if progress:
        current_filters.append({'key': '状态', 'value': progress_name_map.get(progress, progress)})
    if q:
        current_filters.append({'key': '搜索', 'value': q})
    if only_favorite:
        current_filters.append({'key': '收藏', 'value': '只看收藏'})

    return current_filters


def _build_zone_summary(zone, problems, user_state):
    difficulty_counter = Counter(getattr(problem, 'difficulty', '') for problem in problems if getattr(problem, 'difficulty', ''))
    problem_ids = [problem.id for problem in problems]

    passed_count = len(set(problem_ids) & user_state['passed_ids'])
    attempted_count = len(set(problem_ids) & user_state['attempted_ids'])
    retrying_count = len(set(problem_ids) & user_state['retrying_ids'])
    hot_labels = build_hot_labels(problems, limit=6)
    preview_titles = [problem.title for problem in problems[:4]]

    return {
        'slug': zone['slug'],
        'name': zone['name'],
        'icon': zone['icon'],
        'accent': zone['accent'],
        'description': zone['description'],
        'subtitle': zone['subtitle'],
        'problem_count': len(problems),
        'easy_count': difficulty_counter.get('easy', 0) + difficulty_counter.get('简单', 0),
        'medium_count': difficulty_counter.get('medium', 0) + difficulty_counter.get('中等', 0),
        'hard_count': difficulty_counter.get('hard', 0) + difficulty_counter.get('困难', 0),
        'passed_count': passed_count,
        'attempted_count': attempted_count,
        'retrying_count': retrying_count,
        'hot_labels': hot_labels,
        'preview_titles': preview_titles,
    }


# ==============================
# 题库分区首页
# ==============================
@student_required
def problem_zones(request):
    all_problems = list(CodeProblem.objects.all().order_by('id'))
    problem_ids = [problem.id for problem in all_problems]
    user_state = _get_user_problem_state(request.user, problem_ids)

    zone_buckets = build_zone_buckets(all_problems)
    zone_cards = [
        _build_zone_summary(zone, zone_buckets.get(zone['slug'], []), user_state)
        for zone in ZONE_CONFIGS
    ]

    recommendation_dashboard = build_recommendation_dashboard(request.user, limit_each=4)
    total_passed = len(user_state['passed_ids'])
    total_attempted = len(user_state['attempted_ids'])

    return render(
        request,
        'programming/problem_zones.html',
        {
            'zone_cards': zone_cards,
            'total_problem_count': len(all_problems),
            'total_zone_count': len(ZONE_CONFIGS),
            'total_passed': total_passed,
            'total_attempted': total_attempted,
            'recommend_summary': recommendation_dashboard['summary'],
            'focus_zones': recommendation_dashboard['focus_zones'][:2],
            'today_recommendations': recommendation_dashboard['today_recommendations'][:3],
            'strongest_zone': recommendation_dashboard['strongest_zone'],
            'weakest_zone': recommendation_dashboard['weakest_zone'],
        },
    )


# ==============================
# 学习推荐页
# ==============================
@student_required
def recommendation_home(request):
    dashboard = build_recommendation_dashboard(request.user, limit_each=5)
    dashboard['knowledge_graph_json'] = json.dumps(
        dashboard.get('knowledge_graph', {}),
        ensure_ascii=False,
    )
    return render(request, 'programming/recommendation.html', dashboard)


# ==============================
# 分区详情页
# ==============================
@student_required
def problem_zone_detail(request, zone_slug):
    zone = get_zone_by_slug(zone_slug)
    if not zone:
        raise Http404('分区不存在')

    q = request.GET.get('q', '').strip()
    difficulty = request.GET.get('difficulty', '').strip()
    stage = request.GET.get('stage', '').strip()
    tag = request.GET.get('tag', '').strip()
    language = request.GET.get('language', '').strip().lower()
    progress = request.GET.get('progress', '').strip()
    only_favorite = request.GET.get('favorite') == '1'

    all_problems = list(CodeProblem.objects.all().order_by('id'))
    zone_buckets = build_zone_buckets(all_problems)
    zone_all_problems = zone_buckets.get(zone_slug, [])

    problem_ids = [problem.id for problem in zone_all_problems]
    user_state = _get_user_problem_state(request.user, problem_ids)

    filtered_problems = _filter_problems(
        zone_all_problems,
        q=q,
        difficulty=difficulty,
        stage=stage,
        tag=tag,
        language=language,
        progress=progress,
        only_favorite=only_favorite,
        user_state=user_state,
    )
    filtered_problems = _decorate_problem_cards(filtered_problems, user_state, request=request)

    filter_options = _build_problem_filter_options_from_iterable(zone_all_problems)
    current_filters = _build_current_filters(
        q=q,
        difficulty=difficulty,
        stage=stage,
        tag=tag,
        language=language,
        progress=progress,
        only_favorite=only_favorite,
    )

    current_params = request.GET.copy()
    favorite_on_params = current_params.copy()
    favorite_on_params['favorite'] = '1'

    favorite_off_params = current_params.copy()
    if 'favorite' in favorite_off_params:
        del favorite_off_params['favorite']

    clear_filter_params = request.GET.copy()
    for key in ['q', 'difficulty', 'stage', 'tag', 'language', 'progress', 'favorite']:
        if key in clear_filter_params:
            del clear_filter_params[key]

    zone_summary = _build_zone_summary(zone, zone_all_problems, user_state)
    side_zone_cards = [
        {
            'slug': item['slug'],
            'name': item['name'],
            'count': len(zone_buckets.get(item['slug'], [])),
            'is_active': item['slug'] == zone_slug,
        }
        for item in ZONE_CONFIGS
    ]

    return render(
        request,
        'programming/problem_zone_detail.html',
        {
            'zone': zone,
            'zone_summary': zone_summary,
            'problems': filtered_problems,
            'q': q,
            'selected_difficulty': difficulty,
            'selected_stage': stage,
            'selected_tag': tag,
            'selected_language': language,
            'selected_progress': progress,
            'only_favorite': only_favorite,
            'current_filters': current_filters,
            'has_active_filters': bool(current_filters),
            'favorite_on_url': _build_zone_detail_url(zone_slug, favorite_on_params),
            'favorite_off_url': _build_zone_detail_url(zone_slug, favorite_off_params),
            'clear_filters_url': _build_zone_detail_url(zone_slug, clear_filter_params),
            'side_zone_cards': side_zone_cards,
            **filter_options,
        },
    )


# ==============================
# 全部题目页（保留，作为辅助入口）
# ==============================
@student_required
def problem_list(request):
    q = request.GET.get('q', '').strip()
    difficulty = request.GET.get('difficulty', '').strip()
    stage = request.GET.get('stage', '').strip()
    tag = request.GET.get('tag', '').strip()
    language = request.GET.get('language', '').strip().lower()
    zone_slug = request.GET.get('zone', '').strip()
    progress = request.GET.get('progress', '').strip()
    only_favorite = request.GET.get('favorite') == '1'

    all_problems = list(CodeProblem.objects.all().order_by('id'))
    problem_ids = [problem.id for problem in all_problems]
    user_state = _get_user_problem_state(request.user, problem_ids)

    filtered_problems = _filter_problems(
        all_problems,
        q=q,
        difficulty=difficulty,
        stage=stage,
        tag=tag,
        language=language,
        zone_slug=zone_slug,
        progress=progress,
        only_favorite=only_favorite,
        user_state=user_state,
    )
    filtered_problems = _decorate_problem_cards(filtered_problems, user_state, request=request)

    zone_buckets = build_zone_buckets(all_problems)
    zone_cards = [
        _build_zone_summary(zone, zone_buckets.get(zone['slug'], []), user_state)
        for zone in ZONE_CONFIGS
    ]

    filter_options = _build_problem_filter_options_from_iterable(all_problems)
    current_filters = _build_current_filters(
        q=q,
        difficulty=difficulty,
        stage=stage,
        tag=tag,
        language=language,
        zone_slug=zone_slug,
        progress=progress,
        only_favorite=only_favorite,
    )

    current_params = request.GET.copy()
    favorite_on_params = current_params.copy()
    favorite_on_params['favorite'] = '1'

    favorite_off_params = current_params.copy()
    if 'favorite' in favorite_off_params:
        del favorite_off_params['favorite']

    clear_filter_params = request.GET.copy()
    for key in ['q', 'difficulty', 'stage', 'tag', 'language', 'zone', 'progress', 'favorite']:
        if key in clear_filter_params:
            del clear_filter_params[key]

    return render(
        request,
        'programming/problem_list.html',
        {
            'problems': filtered_problems,
            'zone_cards': zone_cards,
            'q': q,
            'selected_difficulty': difficulty,
            'selected_stage': stage,
            'selected_tag': tag,
            'selected_language': language,
            'selected_zone': zone_slug,
            'selected_progress': progress,
            'only_favorite': only_favorite,
            'current_filters': current_filters,
            'has_active_filters': bool(current_filters),
            'favorite_on_url': _build_problem_list_url(favorite_on_params),
            'favorite_off_url': _build_problem_list_url(favorite_off_params),
            'clear_filters_url': _build_problem_list_url(clear_filter_params),
            **filter_options,
        },
    )


# ==============================
# 核心辅助：代码包装与驱动生成（用于函数补全模式）
# ==============================
def wrap_code_for_execution(user_code, language, func_name, input_data):
    """
    LeetCode 风格包装器：用户只提交函数，系统生成测试驱动器。
    输入数据通过硬编码变量传入（适用于函数补全模式）。
    """
    args_list = []
    if isinstance(input_data, str):
        try:
            parsed = json.loads(input_data)
            if isinstance(parsed, list):
                args_list = parsed
            else:
                args_list = [parsed]
        except json.JSONDecodeError:
            parts = input_data.strip().split()
            args_list = [int(p) if p.lstrip('-').isdigit() else p for p in parts]
    elif isinstance(input_data, list):
        args_list = input_data
    elif isinstance(input_data, dict) and 'args' in input_data:
        args_list = input_data['args']
    else:
        args_list = [input_data]

    if language == 'python':
        declarations = []
        call_args = []
        for i, arg in enumerate(args_list):
            var_name = f'arg{i}'
            if isinstance(arg, bool):
                declarations.append(f"{var_name} = {str(arg)}")
                call_args.append(var_name)
            elif isinstance(arg, int) or (isinstance(arg, float) and arg.is_integer()):
                declarations.append(f'{var_name} = {int(arg)}')
                call_args.append(var_name)
            elif isinstance(arg, list):
                declarations.append(f'{var_name} = {arg}')
                call_args.append(var_name)
            elif isinstance(arg, str):
                safe_str = arg.replace('"', '\\"')
                declarations.append(f'{var_name} = "{safe_str}"')
                call_args.append(var_name)
            else:
                declarations.append(f'{var_name} = None')
                call_args.append(var_name)

        init_block = '\n    '.join(declarations)
        params_call = ', '.join(call_args)
        driver_code = f"""
import json

# 用户代码开始
{user_code}
# 用户代码结束

def _run_solution():
    {init_block}
    result = None
    if '{func_name}' in globals():
        result = globals()['{func_name}']({params_call})
    else:
        for name, obj in globals().items():
            if isinstance(obj, type) and name.lower() == 'solution':
                instance = obj()
                if hasattr(instance, '{func_name}'):
                    result = getattr(instance, '{func_name}')({params_call})
                    break
    if result is not None:
        if isinstance(result, bool):
            print('true' if result else 'false')
        elif isinstance(result, (list, dict)):
            print(json.dumps(result))
        else:
            print(result)

if __name__ == '__main__':
    _run_solution()
"""
        return driver_code, None

    if language == 'c':
        declarations = []
        call_args = []
        for i, arg in enumerate(args_list):
            var_name = f'arg{i}'
            if isinstance(arg, int) or (isinstance(arg, float) and arg.is_integer()):
                declarations.append(f'int {var_name} = {int(arg)};')
                call_args.append(var_name)
            elif isinstance(arg, list):
                try:
                    arr_vals = ','.join(str(int(x)) for x in arg)
                except (ValueError, TypeError):
                    arr_vals = ','.join(str(x) for x in arg)
                declarations.append(f'int {var_name}[] = {{{arr_vals}}};')
                declarations.append(f'int {var_name}_size = {len(arg)};')
                call_args.extend([var_name, f'{var_name}_size'])
            elif isinstance(arg, str):
                safe_str = arg.replace('\\', '\\\\').replace('"', '\\"')
                declarations.append(f'char {var_name}[] = "{safe_str}";')
                call_args.append(var_name)
            else:
                declarations.append(f'int {var_name} = 0;')
                call_args.append(var_name)

        init_block = '\n    '.join(declarations)
        params_call = ', '.join(call_args)
        driver_code = f"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// 用户代码开始
{user_code}
// 用户代码结束

int main() {{
    {init_block}
    int result = {func_name}({params_call});
    printf("%d", result);
    return 0;
}}
"""
        return driver_code, None

    if language == 'cpp':
        declarations = []
        call_args = []
        for i, arg in enumerate(args_list):
            var_name = f'arg{i}'
            if isinstance(arg, int) or (isinstance(arg, float) and arg.is_integer()):
                declarations.append(f'int {var_name} = {int(arg)};')
                call_args.append(var_name)
            elif isinstance(arg, list):
                try:
                    arr_vals = ','.join(str(int(x)) for x in arg)
                except (ValueError, TypeError):
                    arr_vals = ','.join(str(x) for x in arg)
                declarations.append(f'vector<int> {var_name} = {{{arr_vals}}};')
                call_args.append(var_name)
            elif isinstance(arg, str):
                safe_str = arg.replace('\\', '\\\\').replace('"', '\\"')
                declarations.append(f'string {var_name} = "{safe_str}";')
                call_args.append(var_name)
            else:
                declarations.append(f'int {var_name} = 0;')
                call_args.append(var_name)

        init_block = '\n    '.join(declarations)
        params_call = ', '.join(call_args)
        driver_code = f"""
#include <iostream>
#include <vector>
#include <string>
using namespace std;

// 用户代码开始
{user_code}
// 用户代码结束

template<typename T>
void printResult(const T& res) {{
    cout << res;
}}

template<>
void printResult(const vector<int>& res) {{
    cout << '[';
    for (size_t i = 0; i < res.size(); ++i) {{
        cout << res[i];
        if (i < res.size() - 1) cout << ", ";
    }}
    cout << ']';
}}

template<>
void printResult(const bool& res) {{
    cout << (res ? "true" : "false");
}}

int main() {{
    {init_block}
    Solution solver;
    auto result = solver.{func_name}({params_call});
    printResult(result);
    return 0;
}}
"""
        return driver_code, None

    if language == 'java':
        original_class_name = extract_java_class_name(user_code)
        clean_code = re.sub(
            r'public\s+class\s+' + re.escape(original_class_name),
            f'class {original_class_name}',
            user_code,
        )

        init_lines = []
        call_args = []
        for i, arg in enumerate(args_list):
            var_name = f'arg{i}'
            if isinstance(arg, bool):
                init_lines.append(f'boolean {var_name} = {'true' if arg else 'false'};')
                call_args.append(var_name)
            elif isinstance(arg, (int, float)) and (isinstance(arg, int) or arg.is_integer()):
                init_lines.append(f'int {var_name} = {int(arg)};')
                call_args.append(var_name)
            elif isinstance(arg, list):
                try:
                    arr_vals = ','.join(str(int(x)) for x in arg)
                except (ValueError, TypeError):
                    arr_vals = ','.join(str(x) for x in arg)
                init_lines.append(f'int[] {var_name} = {{{arr_vals}}};')
                call_args.append(var_name)
            elif isinstance(arg, str):
                safe_str = arg.replace('\\', '\\\\').replace('"', '\\"')
                init_lines.append(f'String {var_name} = "{safe_str}";')
                call_args.append(var_name)
            else:
                init_lines.append(f'Object {var_name} = null;')
                call_args.append(var_name)

        init_block = '\n        '.join(init_lines)
        args_block = ', '.join(call_args)
        main_class_code = f"""
public class Main {{
    public static void main(String[] args) {{
        {init_block}
        {original_class_name} solver = new {original_class_name}();
        try {{
            Object result = solver.{func_name}({args_block});
            if (result == null) {{
                System.out.print("null");
            }} else if (result instanceof int[]) {{
                int[] arr = (int[]) result;
                System.out.print('[');
                for (int i = 0; i < arr.length; i++) {{
                    System.out.print(arr[i]);
                    if (i < arr.length - 1) System.out.print(", ");
                }}
                System.out.print(']');
            }} else if (result instanceof java.util.List) {{
                java.util.List<?> list = (java.util.List<?>) result;
                System.out.print('[');
                for (int i = 0; i < list.size(); i++) {{
                    System.out.print(list.get(i));
                    if (i < list.size() - 1) System.out.print(", ");
                }}
                System.out.print(']');
            }} else if (result instanceof Boolean) {{
                System.out.print(((Boolean) result) ? "true" : "false");
            }} else {{
                System.out.println(result);
            }}
        }} catch (Exception e) {{
            System.err.println("RUNTIME_ERROR: " + e.getMessage());
            e.printStackTrace();
            System.exit(1);
        }}
    }}
}}
"""
        return f'{clean_code}\n{main_class_code}', 'Main'

    return user_code, None


# ==============================
# 将输入数据序列化为 stdin 字符串（用于完整程序模式）
# ==============================
def serialize_input_for_stdin(input_data, language):
    if isinstance(input_data, (list, tuple)):
        return ' '.join(str(x) for x in input_data) + '\n'
    if isinstance(input_data, (int, float, bool)):
        return str(input_data).lower() + '\n'
    if isinstance(input_data, str):
        return input_data if input_data.endswith('\n') else input_data + '\n'
    return json.dumps(input_data) + '\n'


# ==============================
# 模式选择接口
# ==============================
@student_required
@require_POST
def select_problem_mode(request, pk):
    problem = get_object_or_404(CodeProblem, pk=pk)
    mode = request.POST.get('mode', '').strip()

    if mode not in ['practice', 'exam']:
        if is_ajax_request(request):
            return JsonResponse({'success': False, 'message': '无效的模式参数'}, status=400)
        messages.error(request, '❌ 模式参数错误')
        return redirect('programming:problem_detail', pk=problem.pk)

    request.session[f'problem_mode_{problem.pk}'] = mode
    mode_text = get_mode_display(mode)

    if is_ajax_request(request):
        return JsonResponse({
            'success': True,
            'mode': mode,
            'mode_display': mode_text,
            'message': f'已切换为{mode_text}',
        })

    messages.success(request, f'✅ 已切换为{mode_text}')
    next_url = request.POST.get('next')
    if next_url:
        return redirect(next_url)
    return redirect('programming:problem_detail', pk=problem.pk)


# ==============================
# 收藏 / 取消收藏接口
# ==============================
@student_required
@require_POST
def toggle_problem_favorite(request, pk):
    problem = get_object_or_404(CodeProblem, pk=pk)

    favorite, created = ProblemFavorite.objects.get_or_create(user=request.user, problem=problem)
    if created:
        is_favorited = True
        message_text = '✅ 收藏成功'
    else:
        favorite.delete()
        is_favorited = False
        message_text = '✅ 已取消收藏'

    _sync_user_problem_status(request.user, problem)
    favorite_count = ProblemFavorite.objects.filter(problem=problem).count()

    if is_ajax_request(request):
        return JsonResponse(
            {
                'success': True,
                'is_favorited': is_favorited,
                'favorite_count': favorite_count,
                'message': message_text,
            }
        )

    messages.success(request, message_text)
    next_url = request.POST.get('next')
    if next_url:
        return redirect(next_url)
    return redirect('programming:problem_detail', pk=problem.pk)


# ==============================
# 题目详情页
# ==============================
@student_required
def problem_detail(request, pk):
    problem = get_object_or_404(CodeProblem, pk=pk)
    current_mode = get_problem_mode(request, problem.pk)

    is_favorited = ProblemFavorite.objects.filter(user=request.user, problem=problem).exists()

    if request.method == 'POST' and 'discussion_form' in request.POST:
        form = DiscussionForm(request.POST)
        if form.is_valid():
            discussion = form.save(commit=False)
            discussion.problem = problem
            discussion.user = request.user
            discussion.save()
            messages.success(request, '✅ 讨论发布成功！')
            return redirect('programming:problem_detail', pk=pk)
        messages.error(request, '❌ 表单填写有误，请检查。')
    else:
        form = DiscussionForm()

    discussions = problem.discussions.all().select_related('user').order_by('-created_at')[:50]
    context = {
        'problem': problem,
        'form': form,
        'discussions': discussions,
        'current_mode': current_mode,
        'current_mode_label': get_mode_display(current_mode),
        'is_favorited': is_favorited,
        'favorite_count': problem.favorited_users.count(),
    }
    return render(request, 'programming/problem_detail.html', context)


# ==============================
# AI 监测上下文
# ==============================
def get_ai_monitor_context():
    available, reason = face_backend_available()
    return {
        'opencv_available': available,
        'backend_error': '' if available else reason,
    }


# ==============================
# 核心判题逻辑（Submit）
# ==============================
@student_required
def submit_code(request, pk):
    problem = get_object_or_404(CodeProblem, pk=pk)
    current_mode = get_problem_mode(request, problem.pk)

    if request.method != 'POST':
        context = {
            'problem': problem,
            'current_mode': current_mode,
            'current_mode_label': get_mode_display(current_mode),
            'show_monitor': current_mode == 'exam',
            **get_ai_monitor_context(),
        }
        return render(request, 'programming/submit_code.html', context)

    code = request.POST.get('code', '').strip()
    language = request.POST.get('language', '').strip()

    if not language or language not in LANG_CONFIG:
        return JsonResponse({'is_correct': False, 'feedback': f'❌ 不支持的语言：{language}'})
    if not code:
        return JsonResponse({'is_correct': False, 'feedback': '❌ 代码不能为空'})
    if len(code) > 65536:
        return JsonResponse({'is_correct': False, 'feedback': '❌ 代码长度超过限制（64KB）'})

    config = get_language_config(language)
    current_user = request.user
    test_cases = problem.test_cases if problem.test_cases else [{'input': [1, 1], 'expected': 2}]

    function_mode = False
    target_func_name = None
    if getattr(problem, 'function_name', ''):
        function_mode = True
        target_func_name = problem.function_name
    elif '二分' in problem.title:
        function_mode = True
        target_func_name = 'search'
    elif '两数' in problem.title:
        function_mode = True
        target_func_name = 'twoSum'

    if problem.title == '二分查找':
        function_mode = True
        target_func_name = 'search'

    temp_dir = None
    final_status = 'PD'
    final_feedback = ''
    exec_time = 0
    exec_memory = 0

    try:
        temp_dir = tempfile.mkdtemp(prefix=f'judge_{pk}_')
        all_passed = True
        creation_flag = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

        for i, case in enumerate(test_cases):
            input_data_obj = case.get('input')
            expected_raw = case.get('expected', case.get('output', ''))
            if isinstance(expected_raw, bool):
                expected_output = 'true' if expected_raw else 'false'
            elif isinstance(expected_raw, (list, dict)):
                expected_output = json.dumps(expected_raw, separators=(',', ':'))
            else:
                expected_output = str(expected_raw).strip()

            if function_mode:
                try:
                    final_code, class_name = wrap_code_for_execution(code, language, target_func_name, input_data_obj)
                except Exception as e:
                    final_status = 'RE'
                    final_feedback = f'❌ 代码包装失败：{str(e)}'
                    logger.error('Wrap Code Error: %s', e, exc_info=True)
                    all_passed = False
                    break

                file_name = f'{class_name}.java' if language == 'java' and class_name else f'main{config["extension"]}'
                src_path = os.path.join(temp_dir, file_name)
                with open(src_path, 'w', encoding='utf-8') as f:
                    f.write(final_code)

                if config['compile_cmd']:
                    exe_filename = 'a.out.exe' if os.name == 'nt' else 'a.out'
                    exe_path = os.path.join(temp_dir, exe_filename)
                    compile_args = [
                        arg.format(exe_path=exe_path, src_path=src_path, dir_name=temp_dir, class_name=class_name or '')
                        for arg in config['compile_cmd']
                    ]
                    proc_comp = subprocess.run(
                        compile_args,
                        capture_output=True,
                        text=True,
                        timeout=10,
                        creationflags=creation_flag,
                        cwd=temp_dir,
                    )
                    if proc_comp.returncode != 0:
                        final_status = 'CE'
                        final_feedback = format_error_message(proc_comp.stderr, language, '编译')
                        all_passed = False
                        break

                if language == 'java':
                    run_args = [arg.format(dir_name=temp_dir, class_name=class_name) for arg in config['run_cmd']]
                elif language == 'python':
                    run_args = ['python', '-u', src_path]
                else:
                    exe_filename = 'a.out.exe' if os.name == 'nt' else 'a.out'
                    exe_path = os.path.join(temp_dir, exe_filename)
                    run_args = [arg.format(exe_path=exe_path) for arg in config['run_cmd']]
                stdin_input = ''
            else:
                final_code = code
                if language == 'java':
                    class_name = extract_java_class_name(code)
                    file_name = f'{class_name}.java'
                else:
                    file_name = f'main{config["extension"]}'
                    class_name = None

                src_path = os.path.join(temp_dir, file_name)
                with open(src_path, 'w', encoding='utf-8') as f:
                    f.write(final_code)

                if config['compile_cmd']:
                    exe_filename = 'a.out.exe' if os.name == 'nt' else 'a.out'
                    exe_path = os.path.join(temp_dir, exe_filename)
                    compile_args = [
                        arg.format(exe_path=exe_path, src_path=src_path, dir_name=temp_dir, class_name=class_name or '')
                        for arg in config['compile_cmd']
                    ]
                    proc_comp = subprocess.run(
                        compile_args,
                        capture_output=True,
                        text=True,
                        timeout=10,
                        creationflags=creation_flag,
                        cwd=temp_dir,
                    )
                    if proc_comp.returncode != 0:
                        final_status = 'CE'
                        final_feedback = format_error_message(proc_comp.stderr, language, '编译')
                        all_passed = False
                        break

                if language == 'java':
                    run_args = [arg.format(dir_name=temp_dir, class_name=class_name) for arg in config['run_cmd']]
                elif language == 'python':
                    run_args = ['python', '-u', src_path]
                else:
                    exe_filename = 'a.out.exe' if os.name == 'nt' else 'a.out'
                    exe_path = os.path.join(temp_dir, exe_filename)
                    run_args = [arg.format(exe_path=exe_path) for arg in config['run_cmd']]
                stdin_input = serialize_input_for_stdin(input_data_obj, language)

            start_time = time.time()
            try:
                proc_run = subprocess.run(
                    run_args,
                    input=stdin_input,
                    capture_output=True,
                    text=True,
                    timeout=(getattr(problem, 'time_limit', 5)) + 1,
                    creationflags=creation_flag,
                    cwd=temp_dir,
                )

                end_time = time.time()
                case_time = (end_time - start_time) * 1000
                exec_time = max(exec_time, case_time)

                base_mem = {'python': 15000, 'java': 35000, 'c': 2000, 'cpp': 2000}
                exec_memory = max(exec_memory, base_mem.get(language, 5000))

                stdout = proc_run.stdout.strip()
                stderr = proc_run.stderr.strip()
                if proc_run.returncode != 0:
                    if 'timed out' in stderr.lower() or proc_run.returncode == -9:
                        final_status = 'TLE'
                        final_feedback = f'⏱️ 测试点 {i + 1}: 时间超限'
                    else:
                        final_status = 'RE'
                        error_msg = stderr if stderr else stdout
                        final_feedback = format_error_message(error_msg, language, '运行')
                    all_passed = False
                    break

                actual_output = stdout.strip()
                if actual_output == expected_output:
                    continue
                else:
                    try:
                        if json.loads(actual_output) == json.loads(expected_output):
                            continue
                    except Exception:
                        pass

                    final_status = 'WA'
                    diff_preview = f'期望:\n{expected_output[:200]}\n实际:\n{actual_output[:200]}'
                    final_feedback = f'❌ 测试点 {i + 1}: 答案错误\n{diff_preview}'
                    all_passed = False
                    break

            except subprocess.TimeoutExpired:
                final_status = 'TLE'
                final_feedback = f'⏱️ 测试点 {i + 1}: 时间超限'
                all_passed = False
                break
            except Exception as e:
                final_status = 'RE'
                final_feedback = f'⚠️ 运行异常：{str(e)}'
                all_passed = False
                break

        if all_passed:
            final_status = 'AC'
            final_feedback = f'🎉 Accepted!\n耗时：{exec_time:.2f}ms\n内存：~{exec_memory}KB'

    except Exception as e:
        final_status = 'RE'
        final_feedback = f'⚠️ 系统内部错误：{str(e)}'
        logger.error('Judge System Error: %s', e, exc_info=True)
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass

    submission = CodeSubmission.objects.create(
        problem=problem,
        user=current_user,
        code=code,
        language=language,
        mode=current_mode,
        status=final_status,
        feedback=final_feedback,
        execution_time=int(exec_time),
        execution_memory=exec_memory,
    )
    _sync_user_problem_status(current_user, problem)

    return JsonResponse({
        'is_correct': (final_status == 'AC'),
        'status': final_status,
        'feedback': final_feedback,
        'time': f'{exec_time:.2f}ms',
        'memory': f'{exec_memory}KB',
        'submission_id': submission.id,
        'mode': current_mode,
        'mode_display': submission.get_mode_display(),
    })


# ==============================
# 自定义测试运行（Run）
# ==============================
@student_required
def run_test(request, pk):
    problem = get_object_or_404(CodeProblem, pk=pk)

    if request.method != 'POST':
        return JsonResponse({'error': 'Method Not Allowed'}, status=405)

    code = request.POST.get('code', '').strip()
    test_input = request.POST.get('test_input', '').strip()
    language = request.POST.get('language', '').strip()

    if not language or language not in LANG_CONFIG:
        return JsonResponse({'success': False, 'output': '', 'error': '无效的语言'})
    if not code:
        return JsonResponse({'success': False, 'output': '', 'error': '代码为空'})
    if not test_input:
        return JsonResponse({'success': False, 'output': '', 'error': '请输入测试数据'})

    config = get_language_config(language)
    temp_dir = None

    function_mode = False
    target_func_name = None
    if hasattr(problem, 'function_name') and problem.function_name:
        function_mode = True
        target_func_name = problem.function_name
    elif '二分' in problem.title:
        function_mode = True
        target_func_name = 'search'
    elif '两数' in problem.title:
        function_mode = True
        target_func_name = 'twoSum'

    try:
        temp_dir = tempfile.mkdtemp()

        if function_mode:
            final_code, class_name = wrap_code_for_execution(code, language, target_func_name, test_input)
        else:
            final_code = code
            if language == 'java':
                class_name = extract_java_class_name(code)
            else:
                class_name = None

        if language == 'java' and class_name:
            file_name = f'{class_name}.java'
        else:
            file_name = f'main{config["extension"]}'

        src_path = os.path.join(temp_dir, file_name)
        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(final_code)

        creation_flag = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

        if config['compile_cmd']:
            exe_path = os.path.join(temp_dir, 'a.out.exe' if os.name == 'nt' else 'a.out')
            args = [
                arg.format(exe_path=exe_path, src_path=src_path, dir_name=temp_dir, class_name=class_name or '')
                for arg in config['compile_cmd']
            ]
            res = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=creation_flag,
                cwd=temp_dir,
            )
            if res.returncode != 0:
                return JsonResponse({'success': False, 'output': '', 'error': format_error_message(res.stderr, language, '编译')})

        if language == 'java':
            run_args = [arg.format(dir_name=temp_dir, class_name=class_name) for arg in config['run_cmd']]
        elif language == 'python':
            run_args = ['python', '-u', src_path]
        else:
            exe_path = os.path.join(temp_dir, 'a.out.exe' if os.name == 'nt' else 'a.out')
            run_args = [arg.format(exe_path=exe_path) for arg in config['run_cmd']]

        stdin_input = '' if function_mode else serialize_input_for_stdin(test_input, language)

        res_run = subprocess.run(
            run_args,
            input=stdin_input,
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=creation_flag,
            cwd=temp_dir,
        )

        if res_run.returncode != 0:
            return JsonResponse({'success': False, 'output': res_run.stdout, 'error': format_error_message(res_run.stderr, language, '运行')})

        return JsonResponse({'success': True, 'output': res_run.stdout, 'error': ''})

    except subprocess.TimeoutExpired:
        return JsonResponse({'success': False, 'output': '', 'error': '⏱️ 时间超限'})
    except Exception as e:
        return JsonResponse({'success': False, 'output': '', 'error': str(e)})
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


# ==============================
# 提交记录相关
# ==============================
@student_required
def submission_list(request):
    submissions = CodeSubmission.objects.filter(user=request.user).select_related('problem').order_by('-submitted_at')[:50]
    show_login_hint = False

    return render(
        request,
        'programming/submission_list.html',
        {'submissions': submissions, 'show_login_hint': show_login_hint},
    )


@student_required
def submission_detail(request, pk):
    submission = get_object_or_404(CodeSubmission, pk=pk)

    if submission.user and request.user != submission.user and not request.user.is_superuser:
        if is_ajax_request(request):
            return JsonResponse({'error': 'Forbidden'}, status=403)
        raise PermissionDenied('你只能查看自己的提交记录。')

    if is_ajax_request(request):
        data = {
            'id': submission.id,
            'problem_title': submission.problem.title,
            'status': submission.status,
            'status_display': submission.get_status_display(),
            'language': submission.get_language_display(),
            'mode': submission.mode,
            'mode_display': submission.get_mode_display(),
            'time': submission.execution_time,
            'memory': submission.execution_memory,
            'code': submission.code,
            'feedback': submission.feedback,
            'timestamp': submission.submitted_at.strftime('%Y-%m-%d %H:%M:%S'),
        }
        return JsonResponse(data)

    return render(request, 'programming/submission_detail.html', {'submission': submission})


# ==============================
# 摄像头与人脸检测功能
# ==============================
@student_required
def camera_view(request):
    available, reason = face_backend_available()

    if not available:
        messages.error(request, f'⚠️ AI 监测不可用：{reason}')
        return render(
            request,
            'programming/camera.html',
            {
                'opencv_available': False,
                'backend_error': reason,
            },
        )

    return render(
        request,
        'programming/camera.html',
        {
            'opencv_available': True,
            'backend_error': '',
        },
    )


@csrf_exempt
@student_required
def detect_face_api(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Only POST allowed'}, status=405)

    available, reason = face_backend_available()
    if not available:
        return JsonResponse({'success': False, 'error': f'AI 监测不可用: {reason}'}, status=503)

    try:
        max_body_size = min(getattr(settings, 'DATA_UPLOAD_MAX_MEMORY_SIZE', 5 * 1024 * 1024), 5 * 1024 * 1024)
        if len(request.body) > max_body_size:
            return JsonResponse({'success': False, 'error': 'Image too large'}, status=413)

        data = json.loads(request.body)
        image_data = data.get('image', '')
        if not image_data:
            return JsonResponse({'success': False, 'error': 'No image data'}, status=400)

        det_result = detect_faces_from_base64(image_data)
        analyze_result = analyze_monitor_result(det_result['image_shape'], det_result['faces'])
        message = build_monitor_message(analyze_result['status'], det_result['count'], analyze_result['warnings'])

        return JsonResponse({
            'success': True,
            'faces': det_result['faces'],
            'count': det_result['count'],
            'detector': det_result['detector'],
            'latency_ms': det_result['latency_ms'],
            'status': analyze_result['status'],
            'warnings': analyze_result['warnings'],
            'message': message,
        })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except ValueError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    except Exception as e:
        logger.error('Face Detection Error: %s', e, exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ==============================
# AI 助手接口
# ==============================
@require_POST
@student_required
def ai_assistant_api(request, pk):
    problem = get_object_or_404(CodeProblem, pk=pk)
    current_mode = get_problem_mode(request, problem.pk)

    if current_mode == 'exam':
        return JsonResponse({'success': False, 'error': '考试模式下不可使用 AI 助手。'}, status=403)

    message = request.POST.get('message', '').strip()
    code = request.POST.get('code', '')
    language = request.POST.get('language', 'python').strip()

    if not message:
        return JsonResponse({'success': False, 'error': '请输入你想问 AI 的问题。'}, status=400)

    try:
        reply = get_ai_reply(
            problem=problem,
            message=message,
            code=code,
            language=language,
            mode=current_mode,
        )
        return JsonResponse({'success': True, 'reply': reply, 'mode': current_mode})
    except Exception as e:
        logger.error('AI Assistant Error: %s', e, exc_info=True)
        return JsonResponse({'success': False, 'error': f'AI 助手暂时不可用：{str(e)}'}, status=500)

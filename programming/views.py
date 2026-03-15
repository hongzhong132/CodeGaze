import os
import re
import json
import time
import shutil
import tempfile
import subprocess
import logging

from .services.ai_assistant import get_ai_reply
from django.conf import settings
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib import messages
from django.db.models import Q
from django.views.decorators.csrf import csrf_exempt
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.urls import reverse

from .models import CodeProblem, CodeSubmission, ProblemDiscussion, ProblemFavorite
from .forms import DiscussionForm
from .services.face_detector import face_backend_available, detect_faces_from_base64
from .services.monitor_analyzer import analyze_monitor_result, build_monitor_message

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
    }
}


# ==============================
# 通用辅助函数
# ==============================
def get_language_config(lang):
    return LANG_CONFIG.get(lang)


def is_ajax_request(request):
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


def get_problem_mode(request, problem_id):
    """
    从 session 中读取当前题目的模式。
    默认是 practice。
    """
    return request.session.get(f'problem_mode_{problem_id}', 'practice')


def extract_java_class_name(code):
    """提取用户代码中的类名，用于重命名"""
    code_no_comments = re.sub(r'//.*', '', code)
    match = re.search(r'public\s+class\s+([a-zA-Z_][a-zA-Z0-9_]*)', code_no_comments)
    if match:
        return match.group(1)

    match_default = re.search(r'^\s*class\s+([a-zA-Z_][a-zA-Z0-9_]*)', code_no_comments, re.MULTILINE)
    if match_default:
        return match_default.group(1)

    return "Solution"


def format_error_message(stderr, lang, stage="运行"):
    if not stderr:
        return f"❌ {stage}错误：未知错误（无详细输出）"

    is_compile = "编译" in stage
    header = f"❌ {'编译错误' if is_compile else '运行时错误'} ({lang.upper()})"

    suggestions = {
        'c': "💡 检查：分号、变量未定义、头文件缺失、数组越界。",
        'cpp': "💡 检查：命名空间 std、括号匹配、C++17 特性兼容性。",
        'java': "💡 检查：类名必须与文件名一致（系统已自动处理）、包声明（请勿使用 package）、imports。",
        'python': "💡 检查：缩进错误、NameError、语法错误、编码问题。"
    }

    max_len = 1000
    truncated_stderr = stderr.strip()[:max_len] + ("..." if len(stderr) > max_len else "")
    return f"{header}\n\n{truncated_stderr}\n\n{suggestions.get(lang, '')}"


# ==============================
# 核心辅助：代码包装与驱动生成（用于函数补全模式）
# ==============================
def wrap_code_for_execution(user_code, language, func_name, input_data):
    """
    LeetCode 风格包装器：用户只提交函数，系统生成测试驱动器
    输入数据通过硬编码变量传入（适用于函数补全模式）
    """

    # 1. 标准化输入数据为列表 args_list
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

    # 2. 根据语言生成包装代码
    if language == 'python':
        declarations = []
        call_args = []
        for i, arg in enumerate(args_list):
            var_name = f"arg{i}"
            if isinstance(arg, bool):
                declarations.append(f"{var_name} = {str(arg)}")
                call_args.append(var_name)
            elif isinstance(arg, int) or (isinstance(arg, float) and arg.is_integer()):
                declarations.append(f"{var_name} = {int(arg)}")
                call_args.append(var_name)
            elif isinstance(arg, list):
                declarations.append(f"{var_name} = {arg}")
                call_args.append(var_name)
            elif isinstance(arg, str):
                safe_str = arg.replace('"', '\\"')
                declarations.append(f'{var_name} = "{safe_str}"')
                call_args.append(var_name)
            else:
                declarations.append(f"{var_name} = None")
                call_args.append(var_name)

        init_block = "\n    ".join(declarations)
        params_call = ", ".join(call_args)

        driver_code = f"""
import sys
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
            print("true" if result else "false")
        elif isinstance(result, (list, dict)):
            print(json.dumps(result))
        else:
            print(result)

if __name__ == "__main__":
    _run_solution()
"""
        return driver_code, None

    elif language == 'c':
        declarations = []
        call_args = []
        for i, arg in enumerate(args_list):
            var_name = f"arg{i}"
            if isinstance(arg, int) or (isinstance(arg, float) and arg.is_integer()):
                declarations.append(f"int {var_name} = {int(arg)};")
                call_args.append(var_name)
            elif isinstance(arg, list):
                try:
                    arr_vals = ",".join(str(int(x)) for x in arg)
                except (ValueError, TypeError):
                    arr_vals = ",".join(str(x) for x in arg)
                declarations.append(f"int {var_name}[] = {{{arr_vals}}};")
                declarations.append(f"int {var_name}_size = {len(arg)};")
                call_args.append(var_name)
                call_args.append(f"{var_name}_size")
            elif isinstance(arg, str):
                safe_str = arg.replace('\\', '\\\\').replace('"', '\\"')
                declarations.append(f'char {var_name}[] = "{safe_str}";')
                call_args.append(var_name)
            else:
                declarations.append(f"int {var_name} = 0;")
                call_args.append(var_name)

        init_block = "\n    ".join(declarations)
        params_call = ", ".join(call_args)

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

    elif language == 'cpp':
        declarations = []
        call_args = []
        for i, arg in enumerate(args_list):
            var_name = f"arg{i}"
            if isinstance(arg, int) or (isinstance(arg, float) and arg.is_integer()):
                declarations.append(f"int {var_name} = {int(arg)};")
                call_args.append(var_name)
            elif isinstance(arg, list):
                try:
                    arr_vals = ",".join(str(int(x)) for x in arg)
                except (ValueError, TypeError):
                    arr_vals = ",".join(str(x) for x in arg)
                declarations.append(f"vector<int> {var_name} = {{{arr_vals}}};")
                call_args.append(var_name)
            elif isinstance(arg, str):
                safe_str = arg.replace('\\', '\\\\').replace('"', '\\"')
                declarations.append(f'string {var_name} = "{safe_str}";')
                call_args.append(var_name)
            else:
                declarations.append(f"int {var_name} = 0;")
                call_args.append(var_name)

        init_block = "\n    ".join(declarations)
        params_call = ", ".join(call_args)

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
    cout << "[";
    for (size_t i = 0; i < res.size(); ++i) {{
        cout << res[i];
        if (i < res.size() - 1) cout << ", ";
    }}
    cout << "]";
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

    elif language == 'java':
        original_class_name = extract_java_class_name(user_code)
        clean_code = re.sub(
            r'public\s+class\s+' + re.escape(original_class_name),
            f'class {original_class_name}',
            user_code
        )

        init_lines = []
        call_args = []
        for i, arg in enumerate(args_list):
            var_name = f"arg{i}"
            if isinstance(arg, bool):
                val_str = "true" if arg else "false"
                init_lines.append(f"boolean {var_name} = {val_str};")
                call_args.append(var_name)
            elif isinstance(arg, (int, float)) and (isinstance(arg, int) or arg.is_integer()):
                val = int(arg)
                init_lines.append(f"int {var_name} = {val};")
                call_args.append(var_name)
            elif isinstance(arg, list):
                try:
                    arr_vals = ",".join(str(int(x)) for x in arg)
                except (ValueError, TypeError):
                    arr_vals = ",".join(str(x) for x in arg)
                init_lines.append(f"int[] {var_name} = {{{arr_vals}}};")
                call_args.append(var_name)
            elif isinstance(arg, str):
                safe_str = arg.replace('\\', '\\\\').replace('"', '\\"')
                init_lines.append(f'String {var_name} = "{safe_str}";')
                call_args.append(var_name)
            else:
                init_lines.append(f"Object {var_name} = null;")
                call_args.append(var_name)
                logger.warning(f"Unsupported argument type at index {i}: {type(arg)}")

        init_block = "\n        ".join(init_lines)
        args_block = ", ".join(call_args)

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
                System.out.print("[");
                for (int i = 0; i < arr.length; i++) {{
                    System.out.print(arr[i]);
                    if (i < arr.length - 1) System.out.print(", ");
                }}
                System.out.print("]");
            }} else if (result instanceof java.util.List) {{
                java.util.List<?> list = (java.util.List<?>) result;
                System.out.print("[");
                for (int i = 0; i < list.size(); i++) {{
                    System.out.print(list.get(i));
                    if (i < list.size() - 1) System.out.print(", ");
                }}
                System.out.print("]");
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
        return f"{clean_code}\n{main_class_code}", "Main"

    return user_code, None


# ==============================
# 将输入数据序列化为 stdin 字符串（用于完整程序模式）
# ==============================
def serialize_input_for_stdin(input_data, language):
    if isinstance(input_data, (list, tuple)):
        return ' '.join(str(x) for x in input_data) + '\n'
    elif isinstance(input_data, (int, float, bool)):
        return str(input_data).lower() + '\n'
    elif isinstance(input_data, str):
        return input_data if input_data.endswith('\n') else input_data + '\n'
    else:
        return json.dumps(input_data) + '\n'


# ==============================
# 题目列表页
# ==============================
def problem_list(request):
    q = request.GET.get('q', '').strip()
    only_favorite = request.GET.get('favorite') == '1'

    problems = CodeProblem.objects.all().order_by('id')
    favorite_problem_ids = set()

    if q:
        problems = problems.filter(
            Q(title__icontains=q) |
            Q(description__icontains=q)
        )

    if request.user.is_authenticated:
        favorite_problem_ids = set(
            ProblemFavorite.objects.filter(
                user=request.user
            ).values_list('problem_id', flat=True)
        )

    if only_favorite:
        if request.user.is_authenticated:
            problems = problems.filter(id__in=favorite_problem_ids)
        else:
            problems = CodeProblem.objects.none()

    return render(request, 'programming/problem_list.html', {
        'problems': problems,
        'q': q,
        'only_favorite': only_favorite,
        'favorite_problem_ids': favorite_problem_ids,
    })

# ==============================
# 模式选择接口
# ==============================
@require_POST
def select_problem_mode(request, pk):
    problem = get_object_or_404(CodeProblem, pk=pk)
    mode = request.POST.get('mode', '').strip()

    if mode not in ['practice', 'exam']:
        if is_ajax_request(request):
            return JsonResponse({
                'success': False,
                'message': '无效的模式参数'
            }, status=400)

        messages.error(request, "❌ 模式参数错误")
        return redirect('programming:problem_detail', pk=problem.pk)

    request.session[f'problem_mode_{problem.pk}'] = mode

    mode_text = "考试模式" if mode == 'exam' else "练习模式"

    if is_ajax_request(request):
        return JsonResponse({
            'success': True,
            'mode': mode,
            'mode_display': mode_text,
            'message': f'已切换为{mode_text}'
        })

    messages.success(request, f"✅ 已切换为{mode_text}")
    next_url = request.POST.get('next')
    if next_url:
        return redirect(next_url)
    return redirect('programming:problem_detail', pk=problem.pk)


# ==============================
# 收藏 / 取消收藏接口
# ==============================
@login_required
@require_POST
def toggle_problem_favorite(request, pk):
    problem = get_object_or_404(CodeProblem, pk=pk)

    favorite, created = ProblemFavorite.objects.get_or_create(
        user=request.user,
        problem=problem
    )

    if created:
        is_favorited = True
        message_text = "✅ 收藏成功"
    else:
        favorite.delete()
        is_favorited = False
        message_text = "✅ 已取消收藏"

    favorite_count = ProblemFavorite.objects.filter(problem=problem).count()

    if is_ajax_request(request):
        return JsonResponse({
            'success': True,
            'is_favorited': is_favorited,
            'favorite_count': favorite_count,
            'message': message_text
        })

    messages.success(request, message_text)
    next_url = request.POST.get('next')
    if next_url:
        return redirect(next_url)
    return redirect('programming:problem_detail', pk=problem.pk)


# ==============================
# 题目详情页
# ==============================
def problem_detail(request, pk):
    problem = get_object_or_404(CodeProblem, pk=pk)
    current_mode = get_problem_mode(request, problem.pk)

    is_favorited = False
    if request.user.is_authenticated:
        is_favorited = ProblemFavorite.objects.filter(
            user=request.user,
            problem=problem
        ).exists()

    if request.method == 'POST' and 'discussion_form' in request.POST:
        if request.user.is_authenticated:
            form = DiscussionForm(request.POST)
            if form.is_valid():
                discussion = form.save(commit=False)
                discussion.problem = problem
                discussion.user = request.user
                discussion.save()
                messages.success(request, "✅ 讨论发布成功！")
                return redirect('programming:problem_detail', pk=pk)
            else:
                messages.error(request, "❌ 表单填写有误，请检查。")
        else:
            messages.warning(request, "⚠️ 请先登录后再发起讨论。")
            login_url = reverse('login')
            return redirect(f'{login_url}?next={request.path}')
    else:
        form = DiscussionForm()

    discussions = problem.discussions.all().select_related('user').order_by('-created_at')[:50]

    context = {
        'problem': problem,
        'form': form,
        'discussions': discussions,
        'current_mode': current_mode,
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
def submit_code(request, pk):
    problem = get_object_or_404(CodeProblem, pk=pk)
    current_mode = get_problem_mode(request, problem.pk)

    if request.method != 'POST':
        context = {
            'problem': problem,
            'current_mode': current_mode,
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
    current_user = request.user if request.user.is_authenticated else None

    test_cases = problem.test_cases if problem.test_cases else [{"input": [1, 1], "expected": 2}]

    function_mode = False
    target_func_name = None

    if hasattr(problem, 'function_name') and problem.function_name:
        function_mode = True
        target_func_name = problem.function_name
    elif "二分" in problem.title:
        function_mode = True
        target_func_name = "search"
    elif "两数" in problem.title:
        function_mode = True
        target_func_name = "twoSum"

    if problem.title == "二分查找":
        function_mode = True
        target_func_name = 'search'

    temp_dir = None
    final_status = 'PD'
    final_feedback = ""
    exec_time = 0
    exec_memory = 0

    try:
        temp_dir = tempfile.mkdtemp(prefix=f"judge_{pk}_")
        all_passed = True
        creation_flag = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

        for i, case in enumerate(test_cases):
            input_data_obj = case.get("input")

            expected_raw = case.get("expected", case.get("output", ""))
            if isinstance(expected_raw, bool):
                expected_output = "true" if expected_raw else "false"
            elif isinstance(expected_raw, (list, dict)):
                expected_output = json.dumps(expected_raw, separators=(',', ':'))
            else:
                expected_output = str(expected_raw).strip()

            if function_mode:
                try:
                    final_code, class_name = wrap_code_for_execution(code, language, target_func_name, input_data_obj)
                except Exception as e:
                    final_status = 'RE'
                    final_feedback = f"❌ 代码包装失败：{str(e)}"
                    logger.error(f"Wrap Code Error: {e}", exc_info=True)
                    all_passed = False
                    break

                if language == 'java' and class_name:
                    file_name = f"{class_name}.java"
                else:
                    file_name = f"main{config['extension']}"

                src_path = os.path.join(temp_dir, file_name)

                try:
                    with open(src_path, 'w', encoding='utf-8') as f:
                        f.write(final_code)
                except Exception as e:
                    final_status = 'RE'
                    final_feedback = f"❌ 文件写入失败：{str(e)}"
                    all_passed = False
                    break

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
                        cwd=temp_dir
                    )

                    if proc_comp.returncode != 0:
                        final_status = 'CE'
                        final_feedback = format_error_message(proc_comp.stderr, language, "编译")
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

                stdin_input = ""
            else:
                final_code = code
                if language == 'java':
                    class_name = extract_java_class_name(code)
                    file_name = f"{class_name}.java"
                else:
                    file_name = f"main{config['extension']}"
                    class_name = None

                src_path = os.path.join(temp_dir, file_name)

                try:
                    with open(src_path, 'w', encoding='utf-8') as f:
                        f.write(final_code)
                except Exception as e:
                    final_status = 'RE'
                    final_feedback = f"❌ 文件写入失败：{str(e)}"
                    all_passed = False
                    break

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
                        cwd=temp_dir
                    )

                    if proc_comp.returncode != 0:
                        final_status = 'CE'
                        final_feedback = format_error_message(proc_comp.stderr, language, "编译")
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
                    cwd=temp_dir
                )

                end_time = time.time()
                case_time = (end_time - start_time) * 1000

                if case_time > exec_time:
                    exec_time = case_time

                base_mem = {'python': 15000, 'java': 35000, 'c': 2000, 'cpp': 2000}
                case_memory = base_mem.get(language, 5000)
                if case_memory > exec_memory:
                    exec_memory = case_memory

                stdout = proc_run.stdout.strip()
                stderr = proc_run.stderr.strip()

                if proc_run.returncode != 0:
                    if "timed out" in stderr.lower() or proc_run.returncode == -9:
                        final_status = 'TLE'
                        final_feedback = f"⏱️ 测试点 {i + 1}: 时间超限"
                    else:
                        final_status = 'RE'
                        error_msg = stderr if stderr else stdout
                        final_feedback = format_error_message(error_msg, language, "运行")
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
                    diff_preview = f"期望:\n{expected_output[:200]}\n实际:\n{actual_output[:200]}"
                    final_feedback = f"❌ 测试点 {i + 1}: 答案错误\n{diff_preview}"
                    all_passed = False
                    break

            except subprocess.TimeoutExpired:
                final_status = 'TLE'
                final_feedback = f"⏱️ 测试点 {i + 1}: 时间超限"
                all_passed = False
                break
            except Exception as e:
                final_status = 'RE'
                final_feedback = f"⚠️ 运行异常：{str(e)}"
                all_passed = False
                break

        if all_passed:
            final_status = 'AC'
            final_feedback = f"🎉 Accepted!\n耗时：{exec_time:.2f}ms\n内存：~{exec_memory}KB"

    except Exception as e:
        final_status = 'RE'
        final_feedback = f"⚠️ 系统内部错误：{str(e)}"
        logger.error(f"Judge System Error: {e}", exc_info=True)
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
        execution_memory=exec_memory
    )

    # 不要再手动 update submission_count / accepted_count
    # 因为模型的 save() 里已经自动统计，手动加会重复累计

    return JsonResponse({
        'is_correct': (final_status == 'AC'),
        'status': final_status,
        'feedback': final_feedback,
        'time': f"{exec_time:.2f}ms",
        'memory': f"{exec_memory}KB",
        'submission_id': submission.id,
        'mode': current_mode,
        'mode_display': submission.get_mode_display(),
    })


# ==============================
# 自定义测试运行（Run）
# ==============================
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
    elif "二分" in problem.title:
        function_mode = True
        target_func_name = "search"
    elif "两数" in problem.title:
        function_mode = True
        target_func_name = "twoSum"

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
            file_name = f"{class_name}.java"
        else:
            file_name = f"main{config['extension']}"

        src_path = os.path.join(temp_dir, file_name)
        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(final_code)

        creation_flag = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

        if config['compile_cmd']:
            exe_path = os.path.join(temp_dir, 'a.out.exe' if os.name == 'nt' else 'a.out')
            args = [
                arg.format(
                    exe_path=exe_path,
                    src_path=src_path,
                    dir_name=temp_dir,
                    class_name=class_name or ''
                )
                for arg in config['compile_cmd']
            ]
            res = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=creation_flag,
                cwd=temp_dir
            )
            if res.returncode != 0:
                return JsonResponse({
                    'success': False,
                    'output': '',
                    'error': format_error_message(res.stderr, language, "编译")
                })

        if language == 'java':
            run_args = [arg.format(dir_name=temp_dir, class_name=class_name) for arg in config['run_cmd']]
        elif language == 'python':
            run_args = ['python', '-u', src_path]
        else:
            exe_path = os.path.join(temp_dir, 'a.out.exe' if os.name == 'nt' else 'a.out')
            run_args = [arg.format(exe_path=exe_path) for arg in config['run_cmd']]

        if function_mode:
            stdin_input = ""
        else:
            stdin_input = serialize_input_for_stdin(test_input, language)

        res_run = subprocess.run(
            run_args,
            input=stdin_input,
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=creation_flag,
            cwd=temp_dir
        )

        if res_run.returncode != 0:
            return JsonResponse({
                'success': False,
                'output': res_run.stdout,
                'error': format_error_message(res_run.stderr, language, "运行")
            })

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
def submission_list(request):
    if not request.user.is_authenticated:
        submissions = []
        show_login_hint = True
    else:
        submissions = CodeSubmission.objects.filter(
            user=request.user
        ).select_related('problem').order_by('-submitted_at')[:50]
        show_login_hint = False

    return render(request, 'programming/submission_list.html', {
        'submissions': submissions,
        'show_login_hint': show_login_hint
    })


def submission_detail(request, pk):
    submission = get_object_or_404(CodeSubmission, pk=pk)

    if submission.user and request.user != submission.user and not request.user.is_superuser:
        if is_ajax_request(request):
            return JsonResponse({'error': 'Forbidden'}, status=403)
        raise PermissionDenied("你只能查看自己的提交记录。")

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
            'timestamp': submission.submitted_at.strftime('%Y-%m-%d %H:%M:%S')
        }
        return JsonResponse(data)

    return render(request, 'programming/submission_detail.html', {'submission': submission})


# ==============================
# 摄像头与人脸检测功能
# ==============================
def camera_view(request):
    available, reason = face_backend_available()

    if not available:
        messages.error(request, f"⚠️ AI 监测不可用：{reason}")
        return render(request, 'programming/camera.html', {
            'opencv_available': False,
            'backend_error': reason,
        })

    return render(request, 'programming/camera.html', {
        'opencv_available': True,
        'backend_error': '',
    })


@csrf_exempt
def detect_face_api(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Only POST allowed'}, status=405)

    available, reason = face_backend_available()
    if not available:
        return JsonResponse({
            'success': False,
            'error': f'AI 监测不可用: {reason}'
        }, status=503)

    try:
        max_body_size = min(
            getattr(settings, 'DATA_UPLOAD_MAX_MEMORY_SIZE', 5 * 1024 * 1024),
            5 * 1024 * 1024
        )

        if len(request.body) > max_body_size:
            return JsonResponse({
                'success': False,
                'error': 'Image too large'
            }, status=413)

        data = json.loads(request.body)
        image_data = data.get('image', '')

        if not image_data:
            return JsonResponse({
                'success': False,
                'error': 'No image data'
            }, status=400)

        det_result = detect_faces_from_base64(image_data)
        analyze_result = analyze_monitor_result(
            det_result['image_shape'],
            det_result['faces']
        )

        message = build_monitor_message(
            analyze_result['status'],
            det_result['count'],
            analyze_result['warnings']
        )

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
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON'
        }, status=400)
    except ValueError as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)
    except Exception as e:
        logger.error(f"Face Detection Error: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
def build_ai_demo_reply(problem, message, code, language):
    message = (message or "").strip()
    code = (code or "").strip()

    if not message:
        return "你还没有输入问题。可以试试：解释题意、分析当前代码、帮我找 bug、给优化建议。"

    if "题意" in message or "解释" in message:
        return f"""这道题是：{problem.title}

核心目标：
{problem.description[:180]}...

建议先确认：
1. 输入是什么
2. 输出是什么
3. 是否有边界情况
4. 当前题目更适合哪种数据结构或算法思路"""

    if "bug" in message or "报错" in message or "错误" in message:
        if not code:
            return "你还没有填写代码，先把代码贴到编辑器里，我才能帮你分析 bug。"
        return f"""我已读取你当前的 {language} 代码。

第一步建议你优先检查：
1. 输入输出格式是否严格符合题意
2. 边界值是否处理完整
3. 变量是否未初始化或下标越界
4. 是否存在死循环、空数组、空字符串等情况

这是第一版测试回复。下一步你可以接入真实模型接口。"""

    if "优化" in message or "复杂度" in message:
        return """优化代码时，建议按这个顺序思考：
1. 先看当前解法时间复杂度
2. 再看是否有重复计算
3. 是否能用哈希、双指针、前缀和、二分等方法降复杂度
4. 最后再考虑代码结构是否更简洁"""

    if "分析代码" in message or "看看代码" in message:
        if not code:
            return "当前编辑器里还没有代码，先输入代码后再让我分析。"
        return f"""我已经拿到你当前的 {language} 代码。

我建议你下一步优先让我做这几类事情：
- 帮我找 bug
- 解释这段代码逻辑
- 给我优化建议
- 帮我检查边界情况"""

    return f"""我已经收到你的问题：{message}

当前题目：{problem.title}
当前语言：{language}

这是 AI 助手第一版占位回复。你现在已经把右侧助手的前后端链路打通了，下一步只需要把这里替换成真实模型调用即可。"""
@require_POST
@require_POST
def ai_assistant_api(request, pk):
    problem = get_object_or_404(CodeProblem, pk=pk)
    current_mode = get_problem_mode(request, problem.pk)

    if current_mode == 'exam':
        return JsonResponse({
            'success': False,
            'error': '考试模式下不可使用 AI 助手。'
        }, status=403)

    message = request.POST.get('message', '').strip()
    code = request.POST.get('code', '')
    language = request.POST.get('language', 'python').strip()

    if not message:
        return JsonResponse({
            'success': False,
            'error': '请输入你想问 AI 的问题。'
        }, status=400)

    try:
        reply = get_ai_reply(
            problem=problem,
            message=message,
            code=code,
            language=language,
            mode=current_mode,
        )
        return JsonResponse({
            'success': True,
            'reply': reply,
            'mode': current_mode,
        })
    except Exception as e:
        logger.error(f"AI Assistant Error: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f'AI 助手暂时不可用：{str(e)}'
        }, status=500)
import json
import os
import sys
from collections import Counter

import django

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = current_dir

if project_root not in sys.path:
    sys.path.insert(0, project_root)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'codegaze.settings')
django.setup()

from programming.models import CodeProblem


CATEGORY_MAP = {
    '基础输入输出': '基础',
    '基础入门': '基础',
    '基础': '基础',
    '数组': '数组',
    '字符串': '字符串',
    '哈希': '哈希',
    '哈希表': '哈希',
    '双指针': '双指针',
    '滑动窗口': '双指针',
    '栈': '栈',
    '栈与队列': '栈',
    '队列': '栈',
    '链表': '链表',
    '二分查找': '二分',
    '二分': '二分',
    '贪心': '贪心',
    '动态规划': '动态规划',
    '树': '树',
    '图': '图',
    '回溯': '回溯',
    '数学': '数学',
}

STAGE_MAP = {
    'easy': '入门',
    'medium': '提升',
    'hard': '进阶',
    '简单': '入门',
    '中等': '提升',
    '困难': '进阶',
    '入门': '入门',
    '提升': '提升',
    '进阶': '进阶',
    '冲刺': '冲刺',
}

DEFAULT_LANGUAGES = 'python,c,cpp,java'
DEFAULT_SOURCE = 'CodeGaze题库'


def normalize_difficulty(diff_str):
    if not diff_str:
        return 'medium'

    diff_lower = str(diff_str).lower().strip()
    zh_map = {
        '简单': 'easy',
        '中等': 'medium',
        '困难': 'hard',
        '入门': 'easy',
        '普通': 'medium',
    }
    if diff_lower in zh_map:
        return zh_map[diff_lower]

    en_map = {
        'easy': 'easy',
        'medium': 'medium',
        'hard': 'hard',
        'simple': 'easy',
    }
    return en_map.get(diff_lower, 'medium')


def normalize_category(category):
    if not category:
        return '基础'
    category = str(category).strip()
    valid_choices = dict(CodeProblem.CATEGORY_CHOICES)
    return CATEGORY_MAP.get(category, category if category in valid_choices else '基础')


def normalize_stage(stage, difficulty):
    if not stage:
        return STAGE_MAP.get(difficulty, '入门')
    stage = str(stage).strip()
    return STAGE_MAP.get(stage, '入门')


def normalize_question_type(question_type, function_name):
    value = str(question_type or '').strip().lower()
    if value in {'function', 'acm'}:
        return value
    return 'function' if function_name else 'acm'


def process_csv_text(value):
    if not value:
        return ''

    if isinstance(value, list):
        return ",".join([str(v).strip() for v in value if str(v).strip()])

    if isinstance(value, str):
        items = [item.strip() for item in value.split(',') if item.strip()]
        return ",".join(items)

    return str(value).strip()


def process_param_names(value):
    return process_csv_text(value)


def safe_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def validate_test_cases(test_cases_input):
    if not test_cases_input:
        return []

    if isinstance(test_cases_input, str):
        try:
            test_cases_input = json.loads(test_cases_input)
        except json.JSONDecodeError:
            print("⚠️  test_cases 不是合法 JSON，已重置为空列表。")
            return []

    if not isinstance(test_cases_input, list):
        print("⚠️  test_cases 不是列表，已重置为空列表。")
        return []

    normalized = []
    for idx, case in enumerate(test_cases_input, 1):
        if not isinstance(case, dict):
            print(f"⚠️  第 {idx} 个测试用例不是对象，已跳过。")
            continue

        if 'input' not in case:
            print(f"⚠️  第 {idx} 个测试用例缺少 input，已跳过。")
            continue

        if 'expected' not in case and 'output' not in case:
            print(f"⚠️  第 {idx} 个测试用例缺少 expected/output，已跳过。")
            continue

        normalized.append({
            'input': case.get('input'),
            'expected': case.get('expected', case.get('output')),
        })

    return normalized


def build_sample_input_from_case(case_input):
    if case_input is None:
        return ''

    if isinstance(case_input, list):
        return "\n".join(json.dumps(x, ensure_ascii=False) if isinstance(x, (list, dict, bool)) else str(x) for x in case_input)

    if isinstance(case_input, dict):
        return json.dumps(case_input, ensure_ascii=False)

    if isinstance(case_input, bool):
        return str(case_input).lower()

    return str(case_input)


def build_sample_output_from_expected(expected):
    if expected is None:
        return ''
    if isinstance(expected, (list, dict)):
        return json.dumps(expected, ensure_ascii=False)
    if isinstance(expected, bool):
        return str(expected).lower()
    return str(expected)


def fill_missing_examples(payload):
    test_cases = payload.get('test_cases') or []
    if not test_cases:
        return payload

    first_case = test_cases[0]
    if not payload.get('sample_input'):
        payload['sample_input'] = build_sample_input_from_case(first_case.get('input'))
    if not payload.get('sample_output'):
        payload['sample_output'] = build_sample_output_from_expected(first_case.get('expected'))
    if payload.get('input_example') in [None, '', {}]:
        payload['input_example'] = first_case.get('input')
    if payload.get('output_example') in [None, '', {}]:
        payload['output_example'] = first_case.get('expected')
    return payload


def merge_with_existing(existing, payload):
    """
    对已有题目做“补齐式更新”：
    - 新 payload 中是空值时，保留数据库原值
    - 新 payload 中有值时，覆盖数据库原值
    """
    merged = {}
    for key, value in payload.items():
        old_value = getattr(existing, key, None)
        if value in [None, '', [], {}]:
            merged[key] = old_value
        else:
            merged[key] = value
    return merged


def import_from_json(file_path):
    if not os.path.isabs(file_path):
        file_path = os.path.join(project_root, file_path)

    if not os.path.exists(file_path):
        print(f"❌ 错误：找不到文件 {file_path}")
        return

    print(f"📂 正在读取文件: {file_path}")

    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if not isinstance(data, list):
        data = [data]

    total = len(data)
    success_count = 0
    skip_count = 0
    update_count = 0
    error_count = 0
    category_counter = Counter()
    difficulty_counter = Counter()

    print(f"📝 检测到 {total} 条数据，开始处理...\n")

    for index, item in enumerate(data, 1):
        title = str(item.get('title', '')).strip()
        if not title:
            print(f"[{index}/{total}] ⚠️  跳过：缺少标题字段")
            skip_count += 1
            continue

        try:
            difficulty = normalize_difficulty(item.get('difficulty'))
            category = normalize_category(item.get('category'))
            function_name = str(item.get('function_name', '') or '').strip()
            recommend_stage = normalize_stage(item.get('recommend_stage'), difficulty)
            test_cases = validate_test_cases(item.get('test_cases'))

            payload = {
                'title': title,
                'description': item.get('description', ''),
                'category': category,
                'knowledge_points': process_csv_text(item.get('knowledge_points')),
                'supported_languages': process_csv_text(item.get('supported_languages')) or DEFAULT_LANGUAGES,
                'estimated_minutes': safe_int(item.get('estimated_minutes', 15), 15),
                'recommend_stage': recommend_stage,
                'question_type': normalize_question_type(item.get('question_type', 'function'), function_name),
                'function_name': function_name,
                'param_names': process_param_names(item.get('param_names')),
                'input_example': item.get('input_example'),
                'output_example': item.get('output_example'),
                'input_format': item.get('input_format', ''),
                'output_format': item.get('output_format', ''),
                'data_range': item.get('data_range', ''),
                'sample_input': item.get('sample_input', ''),
                'sample_output': item.get('sample_output', ''),
                'difficulty': difficulty,
                'time_limit': safe_int(item.get('time_limit', 1), 1),
                'memory_limit': safe_int(item.get('memory_limit', 128), 128),
                'source': item.get('source', DEFAULT_SOURCE) or DEFAULT_SOURCE,
                'tags': process_csv_text(item.get('tags')),
                'test_cases': test_cases,
                'solution_text': item.get('solution_text', ''),
                'video_url': item.get('video_url', ''),
            }

            payload = fill_missing_examples(payload)

            existing = CodeProblem.objects.filter(title=title).first()
            if existing:
                merged_payload = merge_with_existing(existing, payload)
                for key, value in merged_payload.items():
                    setattr(existing, key, value)
                existing.save()
                update_count += 1
                print(f"[{index}/{total}] ♻️  已更新: {title}")
            else:
                CodeProblem.objects.create(**payload)
                success_count += 1
                print(f"[{index}/{total}] ✅ 成功导入: {title}")

            category_counter[category] += 1
            difficulty_counter[difficulty] += 1

        except Exception as e:
            error_count += 1
            print(f"[{index}/{total}] ❌ 失败: {title} - 错误信息: {str(e)}")

    print("\n" + "=" * 56)
    print("🎉 导入完成！")
    print(f"   ✅ 新增导入: {success_count} 题")
    print(f"   ♻️  更新题目: {update_count} 题")
    print(f"   ⏭️  跳过无效: {skip_count} 题")
    print(f"   ❌ 导入失败: {error_count} 题")
    print("   📊 分类分布:", dict(category_counter))
    print("   📊 难度分布:", dict(difficulty_counter))
    print("=" * 56)


if __name__ == '__main__':
    target_file = sys.argv[1] if len(sys.argv) > 1 else 'problems_data_enhanced.json'
    import_from_json(target_file)
problems_data_enhanced
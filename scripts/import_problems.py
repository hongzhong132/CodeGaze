import os
import sys
import django
import json

# --- 1. 环境配置 ---
# 获取当前脚本所在目录
current_dir = os.path.dirname(os.path.abspath(__file__))
# 获取项目根目录 (假设脚本在 scripts/ 下，根目录在其上一级)
project_root = os.path.dirname(current_dir)

if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 设置 Django 环境变量
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'codegaze.settings')

# 初始化 Django
django.setup()

from django.db import transaction
from programming.models import CodeProblem

# --- 2. 辅助函数 ---

def normalize_difficulty(diff_str):
    """
    将各种格式的难度字符串标准化为数据库选择的 key (easy, medium, hard)
    """
    if not diff_str:
        return 'medium'
    
    diff_lower = str(diff_str).lower().strip()
    
    # 中文映射
    zh_map = {
        '简单': 'easy',
        '中等': 'medium',
        '困难': 'hard',
        '入门': 'easy',
        '普通': 'medium'
    }
    
    if diff_lower in zh_map:
        return zh_map[diff_lower]
    
    # 英文映射 (处理可能的大小写)
    en_map = {
        'easy': 'easy',
        'medium': 'medium',
        'hard': 'hard',
        'simple': 'easy'
    }
    
    return en_map.get(diff_lower, 'medium')

def process_tags(tags_input):
    """
    将标签输入统一处理为逗号分隔的字符串
    支持: ['A', 'B'], "A, B", "A,B"
    """
    if not tags_input:
        return ""
    
    if isinstance(tags_input, list):
        # 如果是列表，去空并连接
        return ",".join([str(t).strip() for t in tags_input if str(t).strip()])
    
    if isinstance(tags_input, str):
        # 如果是字符串，按逗号分割再去重连接（清洗多余空格）
        items = [t.strip() for t in tags_input.split(',') if t.strip()]
        return ",".join(items)
    
    return str(tags_input)

def validate_test_cases(test_cases_input):
    """
    验证测试用例是否为合法的列表格式
    """
    if not test_cases_input:
        return []
    
    if isinstance(test_cases_input, list):
        # 简单检查每个元素是否是字典
        for i, case in enumerate(test_cases_input):
            if not isinstance(case, dict):
                print(f"⚠️  警告：第 {i} 个测试用例不是对象格式，已跳过该用例。")
                continue
            if 'input' not in case or 'output' not in case:
                print(f"⚠️  警告：第 {i} 个测试用例缺少 'input' 或 'output' 字段。")
        return test_cases_input
    
    # 如果传入的是字符串形式的 JSON，尝试解析
    if isinstance(test_cases_input, str):
        try:
            parsed = json.loads(test_cases_input)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
            
    print("⚠️  警告：test_cases 格式不正确，已重置为空列表。")
    return []

# --- 3. 核心导入逻辑 ---

def import_from_json(file_path):
    """从 JSON 文件导入题目到数据库"""
    
    # --- 路径处理 ---
    if not os.path.isabs(file_path):
        # 尝试在当前脚本目录找
        local_path = os.path.join(current_dir, file_path)
        if os.path.exists(local_path):
            file_path = local_path
        else:
            # 尝试在项目根目录找
            root_path = os.path.join(project_root, file_path)
            if os.path.exists(root_path):
                file_path = root_path
            else:
                print(f"❌ 错误：找不到文件 '{file_path}'")
                print(f"   尝试查找位置:\n   1. {local_path}\n   2. {root_path}")
                return

    print(f"📂 正在读取文件: {file_path} ...")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"❌ 错误：文件不存在。")
        return
    except json.JSONDecodeError as e:
        print(f"❌ 错误：JSON 格式无效！详情: {e}")
        return

    if not isinstance(data, list):
        data = [data]

    total = len(data)
    success_count = 0
    skip_count = 0
    error_count = 0

    print(f"📝 检测到 {total} 条数据，开始处理...\n")

    for index, item in enumerate(data, 1):
        title = item.get('title')
        
        if not title:
            print(f"[{index}/{total}] ⚠️  跳过：缺少标题字段")
            skip_count += 1
            continue

        # 检查是否存在
        if CodeProblem.objects.filter(title=title).exists():
            print(f"[{index}/{total}] ⏭️  跳过：题目 '{title}' 已存在")
            skip_count += 1
            continue

        try:
            # 数据清洗与转换
            clean_tags = process_tags(item.get('tags'))
            clean_difficulty = normalize_difficulty(item.get('difficulty'))
            clean_test_cases = validate_test_cases(item.get('test_cases'))

            # 构建模型实例
            problem = CodeProblem(
                title=title,
                description=item.get('description', ''),
                input_format=item.get('input_format', ''),
                output_format=item.get('output_format', ''),
                data_range=item.get('data_range', ''),
                sample_input=item.get('sample_input', ''),
                sample_output=item.get('sample_output', ''),
                difficulty=clean_difficulty,
                time_limit=int(item.get('time_limit', 1)),
                memory_limit=int(item.get('memory_limit', 128)),
                source=item.get('source', 'Imported'),
                tags=clean_tags,
                test_cases=clean_test_cases,
                # 如果有题解和视频链接也导入
                solution_text=item.get('solution_text', ''),
                video_url=item.get('video_url', '')
            )
            
            # 保存
            problem.save()
            
            success_count += 1
            # 简单的进度反馈
            tags_preview = f" ({clean_tags})" if clean_tags else ""
            print(f"[{index}/{total}] ✅ 成功: {title}{tags_preview}")

        except Exception as e:
            error_count += 1
            print(f"[{index}/{total}] ❌ 失败: {title} - 错误信息: {str(e)}")

    # --- 总结报告 ---
    print("\n" + "="*40)
    print("🎉 导入完成！")
    print(f"   ✅ 成功导入: {success_count} 题")
    print(f"   ⏭️  跳过存在: {skip_count} 题")
    print(f"   ❌ 导入失败: {error_count} 题")
    print("="*40)

if __name__ == '__main__':
    # 获取命令行参数
    if len(sys.argv) > 1:
        target_file = sys.argv[1]
    else:
        # 默认查找项目根目录下的 problems_data.json
        target_file = 'problems_data.json'
        
    import_from_json(target_file)
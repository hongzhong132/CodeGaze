import os
import django
import json

# 1. 设置 Django 环境变量
# 注意：这里将 'your_project_name' 修改为了你实际的项目名 'codegaze'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'codegaze.settings')

# 2. 初始化 Django
django.setup()

from programming.models import CodeProblem

# 3. 定义你的题目数据 (可以直接粘贴你之前的 JSON 内容在这里)
# 为了方便，我将你之前提供的 JSON 数据直接硬编码在这里，避免文件路径问题
problems_data = [
    {
        "id": 1,
        "title": "A + B Problem",
        "description": "计算两个整数 A 和 B 的和。这是所有算法竞赛的入门第一题。",
        "difficulty": "简单",
        "tags": ["入门", "模拟"],
        "function_name": "add",
        "param_names": ["a", "b"],
        "input_example": {"a": 1, "b": 2},
        "output_example": 3,
        "test_cases": [
            {"input": [1, 2], "expected": 3},
            {"input": [-1, 1], "expected": 0},
            {"input": [0, 0], "expected": 0}
        ]
    },
    {
        "id": 2,
        "title": "两数之和",
        "description": "给定一个整数数组 nums 和一个整数目标值 target，请你在该数组中找出和为目标值的那两个整数，并返回它们的数组下标。",
        "difficulty": "简单",
        "tags": ["数组", "哈希表"],
        "function_name": "twoSum",
        "param_names": ["nums", "target"],
        "input_example": {"nums": [2, 7, 11, 15], "target": 9},
        "output_example": [0, 1],
        "test_cases": [
            {"input": [[2, 7, 11, 15], 9], "expected": [0, 1]},
            {"input": [[3, 2, 4], 6], "expected": [1, 2]},
            {"input": [[3, 3], 6], "expected": [0, 1]}
        ]
    },
    {
        "id": 20,
        "title": "有效的括号",
        "description": "给定一个只包括 '('，')'，'{'，'}'，'['，']' 的字符串 s ，判断字符串是否有效。",
        "difficulty": "简单",
        "tags": ["栈", "字符串"],
        "function_name": "isValid",
        "param_names": ["s"],
        "input_example": {"s": "()[]{}"},
        "output_example": True,
        "test_cases": [
            {"input": ["()[]{}"], "expected": True},
            {"input": ["(]"], "expected": False},
            {"input": ["([)]"], "expected": False},
            {"input": ["{[]}"], "expected": True}
        ]
    },
    {
        "id": 70,
        "title": "爬楼梯",
        "description": "假设你正在爬楼梯。需要 n 阶你才能到达楼顶。每次你可以爬 1 或 2 个台阶。你有多少种不同的方法可以爬到楼顶呢？",
        "difficulty": "简单",
        "tags": ["动态规划", "递归"],
        "function_name": "climbStairs",
        "param_names": ["n"],
        "input_example": {"n": 3},
        "output_example": 3,
        "test_cases": [
            {"input": [2], "expected": 2},
            {"input": [3], "expected": 3},
            {"input": [5], "expected": 8}
        ]
    },
    {
        "id": 704,
        "title": "二分查找",
        "description": "给定一个 n 个元素有序的（升序）整型数组 nums 和一个目标值 target ，写一个函数搜索 nums 中的 target，如果目标值存在返回下标，否则返回 -1。",
        "difficulty": "简单",
        "tags": ["数组", "二分查找"],
        "function_name": "search",
        "param_names": ["nums", "target"],
        "input_example": {"nums": [-1, 0, 3, 5, 9, 12], "target": 9},
        "output_example": 4,
        "test_cases": [
            {"input": [[-1, 0, 3, 5, 9, 12], 9], "expected": 4},
            {"input": [[-1, 0, 3, 5, 9, 12], 2], "expected": -1},
            {"input": [[5], 5], "expected": 0}
        ]
    },
    {
        "id": 3,
        "title": "无重复字符的最长子串",
        "description": "给定一个字符串 s ，请你找出其中不含有重复字符的最长子串的长度。",
        "difficulty": "中等",
        "tags": ["字符串", "滑动窗口", "哈希表"],
        "function_name": "lengthOfLongestSubstring",
        "param_names": ["s"],
        "input_example": {"s": "abcabcbb"},
        "output_example": 3,
        "test_cases": [
            {"input": ["abcabcbb"], "expected": 3},
            {"input": ["bbbbb"], "expected": 1},
            {"input": ["pwwkew"], "expected": 3},
            {"input": [""], "expected": 0}
        ]
    },
    {
        "id": 46,
        "title": "全排列",
        "description": "给定一个不含重复数字的数组 nums ，返回其所有可能的全排列。你可以按任意顺序返回答案。",
        "difficulty": "中等",
        "tags": ["回溯", "递归", "数组"],
        "function_name": "permute",
        "param_names": ["nums"],
        "input_example": {"nums": [1, 2, 3]},
        "output_example": [[1, 2, 3], [1, 3, 2], [2, 1, 3], [2, 3, 1], [3, 1, 2], [3, 2, 1]],
        "test_cases": [
            {"input": [[1, 2, 3]], "expected": [[1, 2, 3], [1, 3, 2], [2, 1, 3], [2, 3, 1], [3, 1, 2], [3, 2, 1]]},
            {"input": [[0, 1]], "expected": [[0, 1], [1, 0]]},
            {"input": [[1]], "expected": [[1]]}
        ]
    }
]

def import_problems():
    print("🚀 开始导入题目数据...")
    
    success_count = 0
    update_count = 0
    
    for problem in problems_data:
        # 处理 tags 和 param_names：如果是列表，转为逗号分隔的字符串
        # 如果你的模型字段是 ArrayField (PostgreSQL)，则不需要 join，直接赋值即可
        # 这里假设是 CharField 或 TextField，使用逗号分隔
        tags_str = ','.join(problem['tags']) if isinstance(problem['tags'], list) else problem['tags']
        params_str = ','.join(problem['param_names']) if isinstance(problem['param_names'], list) else problem['param_names']
        
        obj, created = CodeProblem.objects.update_or_create(
            id=problem['id'],
            defaults={
                'title': problem['title'],
                'description': problem['description'],
                'difficulty': problem['difficulty'],
                'tags': tags_str, 
                'function_name': problem['function_name'],
                'param_names': params_str,
                # 如果 input_example 和 output_example 是 JSONField，可以直接传字典
                # 如果是 TextField，可能需要 json.dumps()，这里尝试直接传，Django 通常能处理
                'input_example': problem['input_example'], 
                'output_example': problem['output_example'],
                'test_cases': problem['test_cases'], # 关键：保持列表结构
            }
        )
        
        if created:
            print(f"✅ [新建] ID: {problem['id']} - {problem['title']}")
            success_count += 1
        else:
            print(f"🔄 [更新] ID: {problem['id']} - {problem['title']}")
            update_count += 1
            
    print("-" * 30)
    print(f"🎉 导入完成！新建: {success_count} 条，更新: {update_count} 条")

if __name__ == '__main__':
    try:
        import_problems()
    except Exception as e:
        print(f"❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
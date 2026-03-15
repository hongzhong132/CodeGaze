# programming/utils/evaluate.py

import subprocess
import os
import time
import tempfile
from django.conf import settings

def evaluate_code(problem, code, language):
    """
    评测用户提交的代码
    :param problem: CodeProblem 对象
    :param code: 用户提交的代码
    :param language: 编程语言
    :return: (is_correct, feedback, execution_time)
    """
    # 创建临时文件
    with tempfile.NamedTemporaryFile(suffix='.' + language, delete=False) as temp_file:
        temp_file.write(code.encode())
        temp_file_path = temp_file.name
    
    # 准备输入/输出
    input_data = problem.input_example.strip() if problem.input_example else "1 2"
    expected_output = problem.output_example.strip() if problem.output_example else "3"
    
    # 根据语言执行代码
    start_time = time.time()
    try:
        if language == 'python':
            result = subprocess.run(
                ['python', temp_file_path],
                input=input_data,
                capture_output=True,
                text=True,
                timeout=5  # 5秒超时
            )
        elif language == 'java':
            # 编译Java
            compile_result = subprocess.run(
                ['javac', temp_file_path],
                capture_output=True,
                text=True
            )
            if compile_result.returncode != 0:
                return False, f"编译错误: {compile_result.stderr}", None
            
            # 执行Java
            class_name = os.path.splitext(os.path.basename(temp_file_path))[0]
            result = subprocess.run(
                ['java', class_name],
                input=input_data,
                capture_output=True,
                text=True,
                timeout=5
            )
        elif language in ['cpp', 'c']:
            # 编译C/C++
            compile_result = subprocess.run(
                ['g++', '-o', 'a.out', temp_file_path],
                capture_output=True,
                text=True
            )
            if compile_result.returncode != 0:
                return False, f"编译错误: {compile_result.stderr}", None
            
            # 执行
            result = subprocess.run(
                ['./a.out'],
                input=input_data,
                capture_output=True,
                text=True,
                timeout=5
            )
        else:
            return False, "不支持的语言", None
        
        # 计算执行时间
        execution_time = time.time() - start_time
        
        # 检查输出
        actual_output = result.stdout.strip()
        is_correct = (actual_output == expected_output)
        
        # 构建反馈
        feedback = (
            f"执行完成! 时间: {execution_time:.2f}秒\n"
            f"输入: {input_data}\n"
            f"输出: {actual_output}\n"
            f"预期: {expected_output}"
        )
        
        return is_correct, feedback, execution_time
    
    except subprocess.TimeoutExpired:
        return False, "代码执行超时 (5秒)", time.time() - start_time
    except Exception as e:
        return False, f"执行错误: {str(e)}", time.time() - start_time
    finally:
        # 清理临时文件
        os.unlink(temp_file_path)
        if language == 'java':
            if os.path.exists(os.path.splitext(temp_file_path)[0] + '.class'):
                os.unlink(os.path.splitext(temp_file_path)[0] + '.class')
        elif language in ['cpp', 'c'] and os.path.exists('a.out'):
            os.unlink('a.out')
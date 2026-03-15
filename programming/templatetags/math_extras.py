# programming/templatetags/math_extras.py

from django import template

register = template.Library()

@register.filter
def divide(value, arg):
    """
    将一个数除以另一个数
    用法: {{ value|divide:arg }}
    示例: {{ accepted_count|divide:submission_count }}
    """
    try:
        val = float(value)
        divisor = float(arg)
        if divisor == 0:
            return 0
        return val / divisor
    except (ValueError, TypeError, ZeroDivisionError):
        return 0

@register.filter
def multiply(value, arg):
    """
    将一个数乘以另一个数
    用法: {{ value|multiply:arg }}
    示例: {{ 0.85|multiply:100 }} -> 85.0
    """
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def percentage(value, arg=100):
    """
    将小数转换为百分比字符串
    用法: {{ value|percentage }} 或 {{ value|percentage:100 }}
    示例: {{ 0.85|percentage }} -> "85.0%"
    """
    try:
        result = float(value) * float(arg)
        return f"{result:.1f}%"
    except (ValueError, TypeError):
        return "0.0%"
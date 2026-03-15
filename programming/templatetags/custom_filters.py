from django import template

register = template.Library()

@register.filter
def split_str(value, arg):
    """
    用法: {{ value|split_str:"," }}
    将字符串按指定字符分割成列表
    """
    if not value:
        return []
    return value.split(arg)

@register.filter
def strip_str(value):
    """
    用法: {{ value|strip_str }}
    去除字符串首尾空格
    """
    if not value:
        return ""
    return value.strip()
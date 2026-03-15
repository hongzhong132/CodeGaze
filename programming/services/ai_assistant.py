import os
from typing import Any

from django.conf import settings
from openai import OpenAI


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _truncate_text(text: str, max_len: int) -> str:
    text = _safe_text(text)
    if len(text) <= max_len:
        return text
    return text[:max_len] + "\n...(内容已截断)"


def _normalize_language(language: str) -> str:
    language = _safe_text(language).lower()
    mapping = {
        "python": "Python",
        "cpp": "C++",
        "c": "C",
        "java": "Java",
    }
    return mapping.get(language, language or "未知语言")


def _get_provider() -> str:
    return (
        getattr(settings, "AI_ASSISTANT_PROVIDER", None)
        or os.getenv("AI_ASSISTANT_PROVIDER", "demo")
    ).strip().lower()


def _get_client() -> OpenAI:
    api_key = getattr(settings, "OPENAI_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
    base_url = getattr(settings, "OPENAI_BASE_URL", "") or os.getenv(
        "OPENAI_BASE_URL", "https://integrate.api.nvidia.com/v1"
    )

    if not api_key:
        raise RuntimeError("未配置 OPENAI_API_KEY")

    return OpenAI(
        base_url=base_url,
        api_key=api_key,
    )


def _get_model_name() -> str:
    model = getattr(settings, "AI_ASSISTANT_MODEL", "") or os.getenv(
        "AI_ASSISTANT_MODEL", "deepseek-ai/deepseek-r1"
    )
    if not model:
        raise RuntimeError("未配置 AI_ASSISTANT_MODEL")
    return model


def _build_system_prompt() -> str:
    return (
        "你是 CodeGaze 平台的编程练习 AI 助手。\n"
        "你的任务是帮助用户理解题意、分析代码、排查 bug、给出优化建议。\n\n"
        "要求：\n"
        "1. 必须使用中文回答。\n"
        "2. 优先讲思路，不要默认直接给完整标准答案。\n"
        "3. 如果用户明确要求完整代码，可以给参考实现，但先解释思路。\n"
        "4. 回答要结合题目、当前代码和编程语言。\n"
        "5. 如果用户没有提供代码，不要假装已经看过代码。\n"
        "6. 尽量结构化回答，优先分点说明。"
    )


def _build_user_prompt(problem, message: str, code: str, language: str) -> str:
    title = _safe_text(getattr(problem, "title", ""))
    description = _truncate_text(getattr(problem, "description", ""), 1800)
    input_format = _truncate_text(getattr(problem, "input_format", ""), 800)
    output_format = _truncate_text(getattr(problem, "output_format", ""), 800)
    data_range = _truncate_text(getattr(problem, "data_range", ""), 800)
    sample_input = _truncate_text(getattr(problem, "sample_input", ""), 500)
    sample_output = _truncate_text(getattr(problem, "sample_output", ""), 500)

    try:
        difficulty = _safe_text(problem.get_difficulty_display())
    except Exception:
        difficulty = _safe_text(getattr(problem, "difficulty", ""))

    code_text = _truncate_text(code, 5000)
    if not code_text:
        code_text = "（当前编辑器中没有代码）"

    return f"""
【题目信息】
题目名称：{title}
题目难度：{difficulty or "未标注"}

【题目描述】
{description or "无"}

【输入格式】
{input_format or "无"}

【输出格式】
{output_format or "无"}

【数据范围】
{data_range or "无"}

【样例输入】
{sample_input or "无"}

【样例输出】
{sample_output or "无"}

【用户当前语言】
{_normalize_language(language)}

【用户当前代码】
{code_text}

【用户问题】
{_safe_text(message)}
""".strip()


def _build_demo_reply(problem, message: str, code: str, language: str) -> str:
    title = _safe_text(getattr(problem, "title", "未命名题目"))
    return (
        f"当前处于 demo 模式。\n\n"
        f"题目：{title}\n"
        f"问题：{_safe_text(message)}\n\n"
        "如果你看到这段话，说明服务层正常，但还没切到真实模型。"
    )


def _extract_completion_text(completion) -> str:
    if not completion or not getattr(completion, "choices", None):
        return ""

    message = completion.choices[0].message

    # 普通回答
    content = getattr(message, "content", None)
    if content:
        return str(content).strip()

    return ""


def _call_nvidia_model(problem, message: str, code: str, language: str) -> str:
    client = _get_client()
    model = _get_model_name()

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _build_system_prompt()},
            {
                "role": "user",
                "content": _build_user_prompt(problem, message, code, language),
            },
        ],
        temperature=0.6,
        top_p=0.7,
        max_tokens=4096,
        stream=False,
    )

    text = _extract_completion_text(completion)
    if not text:
        raise RuntimeError("模型返回为空")
    return text


def get_ai_reply(problem, message: str, code: str, language: str, mode: str = "practice") -> str:
    message = _safe_text(message)
    code = _safe_text(code)
    language = _safe_text(language) or "python"
    mode = _safe_text(mode) or "practice"

    if not message:
        return "请输入你想问 AI 的问题。"

    if mode == "exam":
        return "当前为考试模式，AI 助手不可用。"

    provider = _get_provider()

    if provider == "demo":
        return _build_demo_reply(problem, message, code, language)

    if provider == "nvidia":
        return _call_nvidia_model(problem, message, code, language)

    raise RuntimeError(f"不支持的 AI_ASSISTANT_PROVIDER：{provider}")
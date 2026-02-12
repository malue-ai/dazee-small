"""
Prompt 管理模块

统一管理所有 LLM 提示词，从 .md 文件加载。

使用方式：
    from prompts import load_prompt

    prompt = load_prompt("agent/system")
    prompt_with_vars = load_prompt("agent/task_planning", max_steps=10)
"""

from pathlib import Path

from utils.app_paths import get_bundle_dir

PROMPTS_DIR = get_bundle_dir() / "prompts"


def load_prompt(name: str, **variables) -> str:
    """
    从 prompts/ 目录加载 .md 文件并注入变量

    Args:
        name: Prompt 路径（如 "agent/system"，不含 .md 后缀）
        **variables: 模板变量（对应 .md 文件中的 {variable_name} 占位符）

    Returns:
        渲染后的 Prompt 字符串

    Raises:
        FileNotFoundError: 如果 .md 文件不存在

    Example:
        prompt = load_prompt("agent/task_planning", max_steps=10)
    """
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt 文件不存在: {path}")

    template = path.read_text(encoding="utf-8")
    if variables:
        template = template.format(**variables)
    return template

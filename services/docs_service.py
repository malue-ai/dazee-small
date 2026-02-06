"""
文档服务 - 读取和解析 docs 目录中的文档
"""

import re
from pathlib import Path
from typing import Optional

from models.docs import DocCategory, DocContent, DocFile, DocsStructure

# 文档分类配置
DOCS_CATEGORIES = {
    "architecture": {
        "name": "架构设计",
        "icon": "🏗️",
        "description": "系统架构、设计模式和技术决策",
    },
    "api": {"name": "API 文档", "icon": "🔌", "description": "API 规范和接口说明"},
    "guides": {"name": "使用指南", "icon": "📖", "description": "功能使用和配置指南"},
    "deployment": {"name": "部署文档", "icon": "🚀", "description": "部署和运维相关文档"},
    "specs": {"name": "技术规范", "icon": "📋", "description": "技术规范和标准定义"},
    "reports": {"name": "分析报告", "icon": "📊", "description": "分析报告和优化建议"},
    "analysis": {"name": "流程分析", "icon": "🔍", "description": "系统流程分析和性能优化"},
    "troubleshooting": {"name": "故障排查", "icon": "🔧", "description": "常见问题和解决方案"},
    "internal": {"name": "内部文档", "icon": "🔒", "description": "内部开发文档"},
}


def _extract_title_from_markdown(content: str, filename: str) -> str:
    """
    从 Markdown 内容中提取标题

    Args:
        content: Markdown 文件内容
        filename: 文件名（用作后备标题）

    Returns:
        提取的标题
    """
    # 尝试匹配第一个 # 标题
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip()

    # 使用文件名作为后备
    name = filename.replace(".md", "").replace("_", " ").replace("-", " ")
    return name.title()


def _get_docs_root() -> Path:
    """获取 docs 目录路径"""
    return Path(__file__).parent.parent / "docs"


async def get_docs_structure() -> DocsStructure:
    """
    获取文档目录结构

    Returns:
        文档结构对象
    """
    docs_root = _get_docs_root()
    categories = []
    total_files = 0

    # 遍历配置的分类目录
    for category_id, config in DOCS_CATEGORIES.items():
        category_path = docs_root / category_id

        if not category_path.exists() or not category_path.is_dir():
            continue

        files = []
        # 获取目录中的所有 .md 文件
        for md_file in sorted(category_path.glob("*.md")):
            if md_file.name.startswith("."):
                continue

            # 读取文件提取标题
            try:
                content = md_file.read_text(encoding="utf-8")
                title = _extract_title_from_markdown(content, md_file.name)
            except Exception:
                title = md_file.stem.replace("_", " ").replace("-", " ").title()

            files.append(
                DocFile(name=md_file.name, path=f"{category_id}/{md_file.name}", title=title)
            )
            total_files += 1

        if files:
            categories.append(
                DocCategory(
                    id=category_id,
                    name=config["name"],
                    icon=config["icon"],
                    description=config["description"],
                    files=files,
                )
            )

    # 处理根目录的文件
    root_files = []
    for md_file in sorted(docs_root.glob("*.md")):
        if md_file.name.startswith("."):
            continue

        try:
            content = md_file.read_text(encoding="utf-8")
            title = _extract_title_from_markdown(content, md_file.name)
        except Exception:
            title = md_file.stem.replace("_", " ").replace("-", " ").title()

        root_files.append(DocFile(name=md_file.name, path=md_file.name, title=title))
        total_files += 1

    if root_files:
        categories.insert(
            0,
            DocCategory(
                id="root", name="概览", icon="📚", description="项目文档入口", files=root_files
            ),
        )

    return DocsStructure(categories=categories, total_files=total_files)


async def get_doc_content(doc_path: str) -> Optional[DocContent]:
    """
    获取文档内容

    Args:
        doc_path: 文档相对路径（如 "architecture/01-MEMORY-PROTOCOL.md"）

    Returns:
        文档内容对象，如果不存在返回 None
    """
    docs_root = _get_docs_root()

    # 安全检查：防止路径遍历攻击
    try:
        file_path = (docs_root / doc_path).resolve()
        if not str(file_path).startswith(str(docs_root.resolve())):
            return None
    except Exception:
        return None

    if not file_path.exists() or not file_path.is_file():
        return None

    if not file_path.suffix.lower() == ".md":
        return None

    try:
        content = file_path.read_text(encoding="utf-8")
        title = _extract_title_from_markdown(content, file_path.name)

        # 确定分类
        parts = doc_path.split("/")
        category = parts[0] if len(parts) > 1 else "root"

        return DocContent(path=doc_path, title=title, content=content, category=category)
    except Exception:
        return None

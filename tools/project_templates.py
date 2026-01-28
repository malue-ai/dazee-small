"""
项目模板管理器

从 templates/ 目录读取预置的项目脚手架，支持：
- node_fullstack: 简单的 Node.js Express 全栈模板
- react_fullstack: 现代化 Vite + React + TypeScript 模板

模板存放在项目根目录的 templates/ 文件夹中，方便维护和更新。
"""

import os
from pathlib import Path
from typing import Dict, Optional

# 模板根目录
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

# 可用模板列表
AVAILABLE_TEMPLATES = {
    "node_fullstack": "简单的 Node.js Express 全栈模板",
    "react_fullstack": "现代化 Vite + React + TypeScript 模板（推荐）",
    "static_html": "简单的静态 HTML 页面",
}


def list_templates() -> Dict[str, str]:
    """列出所有可用模板及其描述"""
    return AVAILABLE_TEMPLATES


def get_template_files(template_name: str) -> Dict[str, str]:
    """
    读取指定模板的所有文件内容
    
    Args:
        template_name: 模板名称 (node_fullstack, react_fullstack, static_html)
        
    Returns:
        Dict[相对路径, 文件内容]
        
    Example:
        files = get_template_files("react_fullstack")
        # { "client/package.json": "...", "server/src/index.ts": "...", ... }
    """
    template_dir = TEMPLATES_DIR / template_name
    
    if not template_dir.exists():
        return {}
    
    files: Dict[str, str] = {}
    
    # 遍历模板目录中的所有文件
    for file_path in template_dir.rglob("*"):
        # 跳过目录和隐藏文件（除了 .gitignore 等配置文件）
        if file_path.is_dir():
            continue
        
        # 跳过 node_modules 等不需要的目录
        relative_path = file_path.relative_to(template_dir)
        if any(part.startswith("node_modules") for part in relative_path.parts):
            continue
        
        try:
            # 读取文件内容
            content = file_path.read_text(encoding="utf-8")
            files[str(relative_path)] = content
        except Exception:
            # 跳过无法读取的文件（如二进制文件）
            pass
    
    return files


def get_template_startup_command(template_name: str) -> Optional[str]:
    """
    获取模板的启动命令提示
    
    Returns:
        启动命令字符串，用于 Agent 执行
    """
    commands = {
        "node_fullstack": "cd /home/user/project && npm install && npm start",
        "react_fullstack": (
            "cd /home/user/project && npm install && npm run dev"
        ),
        "static_html": "cd /home/user/project && python3 -m http.server 8000",
    }
    return commands.get(template_name)


def get_template_ports(template_name: str) -> Dict[str, int]:
    """
    获取模板使用的端口
    
    Returns:
        { "frontend": 5173, "backend": 3000 } 等
    """
    ports = {
        "node_fullstack": {"main": 3000},
        "react_fullstack": {"frontend": 5173, "backend": 3000},
        "static_html": {"main": 8000},
    }
    return ports.get(template_name, {"main": 3000})

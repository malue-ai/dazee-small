#!/usr/bin/env python3
"""
工具配置同步脚本

功能：
1. 从 capabilities.yaml 读取所有工具定义
2. 自动生成 enabled_capabilities 配置片段
3. 更新 instances/_template/config.yaml
4. 检查各实例配置与模板的差异

使用方法：
    # 预览变更（不实际修改）
    python scripts/sync_capabilities.py --dry-run
    
    # 同步到模板
    python scripts/sync_capabilities.py --sync
    
    # 检查实例配置差异
    python scripts/sync_capabilities.py --check-instances
    
    # 完整操作（同步 + 检查）
    python scripts/sync_capabilities.py --sync --check-instances
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import yaml
import re

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 配置文件路径
CAPABILITIES_PATH = PROJECT_ROOT / "config" / "capabilities.yaml"
TEMPLATE_CONFIG_PATH = PROJECT_ROOT / "instances" / "_template" / "config.yaml"
INSTANCES_DIR = PROJECT_ROOT / "instances"


# ==================== 工具分类映射 ====================
# 与 core/tool/loader.py 中的 TOOL_CATEGORIES 保持一致

TOOL_CATEGORIES = {
    "document_skills": {
        "tools": ["pptx", "xlsx", "docx", "pdf"],
        "description": "文档生成技能包 (Claude Skills)",
        "comment": "包含：pptx, xlsx, docx, pdf",
    },
    "sandbox_tools": {
        "tools": [
            "sandbox_write_file", "sandbox_run_command",
            "sandbox_create_project", "sandbox_run_project",
        ],
        "description": "代码沙盒核心工具 (E2B)",
        "comment": "4 个核心：写文件、执行命令、创建项目、运行项目",
    },
    "ppt_tools": {
        "tools": ["ppt_generator", "slidespeak_render"],
        "description": "PPT 生成工具",
        "comment": "闭环 PPT 生成",
    },
}

# 核心工具（不暴露给用户配置）
CORE_TOOLS = [
    "plan_todo",
    "api_calling", 
    "hitl",
    "file_read",
]

# 工具分组（用于生成配置时的注释分组）
TOOL_GROUPS = {
    "信息获取类": {
        "tools": ["web_search", "exa_search", "knowledge_search"],
        "defaults": {"web_search": 1, "exa_search": 0, "knowledge_search": 1},
        "comments": {
            "web_search": "互联网搜索（Tavily）",
            "exa_search": "Exa 语义搜索（需 API Key）",
            "knowledge_search": "个人知识库检索",
        }
    },
    "文档生成类（Claude Skills，整体启用）": {
        "tools": ["document_skills"],
        "defaults": {"document_skills": 0},
        "comments": {
            "document_skills": "包含：pptx, xlsx, docx, pdf",
        }
    },
    "PPT 生成类": {
        "tools": ["ppt_generator"],
        "defaults": {"ppt_generator": 0},
        "comments": {
            "ppt_generator": "闭环 PPT 生成（SlideSpeak）",
        }
    },
    "代码沙盒类（整体启用）": {
        "tools": ["sandbox_tools"],
        "defaults": {"sandbox_tools": 0},
        "comments": {
            "sandbox_tools": "包含：文件操作、代码执行、项目运行等全部沙盒工具",
        }
    },
    "动态代码执行": {
        "tools": ["code_execution"],
        "defaults": {"code_execution": 0},
        "comments": {
            "code_execution": "本地代码执行（谨慎启用）",
        }
    },
}


@dataclass
class CapabilityInfo:
    """工具能力信息"""
    name: str
    type: str
    subtype: str
    description: str
    level: int  # 1=核心工具, 2=动态工具
    categories: List[str]
    is_core: bool


class CapabilitiesSync:
    """工具配置同步器"""
    
    def __init__(self):
        self.capabilities: Dict[str, CapabilityInfo] = {}
        self._load_capabilities()
    
    def _load_capabilities(self):
        """从 capabilities.yaml 加载工具定义"""
        if not CAPABILITIES_PATH.exists():
            print(f"❌ 找不到 {CAPABILITIES_PATH}")
            sys.exit(1)
        
        with open(CAPABILITIES_PATH, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        for cap in data.get('capabilities', []):
            name = cap.get('name', '')
            if not name:
                continue
            
            self.capabilities[name] = CapabilityInfo(
                name=name,
                type=cap.get('type', 'TOOL'),
                subtype=cap.get('subtype', 'CUSTOM'),
                description=cap.get('metadata', {}).get('description', ''),
                level=cap.get('level', 2),
                categories=cap.get('capabilities', []),
                is_core=name in CORE_TOOLS,
            )
        
        print(f"✅ 已加载 {len(self.capabilities)} 个工具定义")
    
    def generate_enabled_capabilities_section(self) -> str:
        """生成 enabled_capabilities 配置段"""
        lines = []
        lines.append("# ==================== 工具能力配置 ====================")
        lines.append("#")
        lines.append("# 📌 配置原则：")
        lines.append("#   - 按功能类别启用/禁用工具（1=启用，0=禁用）")
        lines.append("#   - 核心工具（plan_todo, api_calling 等）自动启用，无需配置")
        lines.append("#   - 类别内的工具作为整体启用，避免关联配置失效")
        lines.append("#")
        lines.append(f"# 🔧 自动生成于：capabilities.yaml（共 {len(self.capabilities)} 个工具）")
        lines.append("#")
        lines.append("enabled_capabilities:")
        
        for group_name, group_info in TOOL_GROUPS.items():
            lines.append(f"  # --- {group_name} ---")
            
            for tool_name in group_info["tools"]:
                default_value = group_info["defaults"].get(tool_name, 0)
                comment = group_info["comments"].get(tool_name, "")
                
                # 检查工具是否存在于 capabilities.yaml
                exists = tool_name in self.capabilities or tool_name in TOOL_CATEGORIES
                marker = "" if exists else "⚠️ "
                
                line = f"  {tool_name}: {default_value}"
                if comment:
                    # 对齐注释
                    padding = 25 - len(tool_name) - len(str(default_value))
                    line += " " * max(1, padding) + f"# {marker}{comment}"
                
                lines.append(line)
            
            lines.append("")  # 空行分隔
        
        return "\n".join(lines)
    
    def update_template_config(self, dry_run: bool = True) -> bool:
        """更新模板配置文件"""
        if not TEMPLATE_CONFIG_PATH.exists():
            print(f"❌ 找不到模板配置 {TEMPLATE_CONFIG_PATH}")
            return False
        
        with open(TEMPLATE_CONFIG_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 生成新的 enabled_capabilities 段
        new_section = self.generate_enabled_capabilities_section()
        
        # 查找并替换 enabled_capabilities 段
        # 匹配从 "# ==================== 工具能力配置" 到下一个 "# ====================" 或文件结尾
        pattern = r'# ==================== 工具能力配置 =+.*?(?=# ==================== [^工]|$)'
        
        if re.search(pattern, content, re.DOTALL):
            new_content = re.sub(pattern, new_section + "\n\n", content, flags=re.DOTALL)
            changed = new_content != content
        else:
            # 如果没找到，在文件末尾添加
            new_content = content + "\n\n" + new_section
            changed = True
        
        if dry_run:
            print("\n" + "=" * 60)
            print("📋 预览：enabled_capabilities 配置")
            print("=" * 60)
            print(new_section)
            print("=" * 60)
            if changed:
                print("\n⚠️ 模板配置将被更新。使用 --sync 执行实际更新。")
            else:
                print("\n✅ 模板配置已是最新，无需更新。")
        else:
            if changed:
                with open(TEMPLATE_CONFIG_PATH, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"✅ 已更新模板配置：{TEMPLATE_CONFIG_PATH}")
            else:
                print("✅ 模板配置已是最新，无需更新。")
        
        return changed
    
    def check_instance_configs(self) -> Dict[str, Dict[str, Any]]:
        """检查各实例配置与模板的差异"""
        results = {}
        
        for instance_dir in INSTANCES_DIR.iterdir():
            if not instance_dir.is_dir():
                continue
            if instance_dir.name.startswith("_"):
                continue  # 跳过模板
            
            config_path = instance_dir / "config.yaml"
            if not config_path.exists():
                results[instance_dir.name] = {"status": "missing", "config_path": str(config_path)}
                continue
            
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                
                enabled_caps = config.get('enabled_capabilities', {})
                
                # 检查未知的工具配置
                unknown_tools = []
                for tool_name in enabled_caps.keys():
                    if tool_name not in self.capabilities and tool_name not in TOOL_CATEGORIES:
                        unknown_tools.append(tool_name)
                
                # 检查缺失的新工具
                missing_tools = []
                for tool_name in TOOL_GROUPS.keys():
                    for t in TOOL_GROUPS[tool_name]["tools"]:
                        if t not in enabled_caps:
                            missing_tools.append(t)
                
                results[instance_dir.name] = {
                    "status": "ok" if not unknown_tools and not missing_tools else "needs_update",
                    "enabled_capabilities": enabled_caps,
                    "unknown_tools": unknown_tools,
                    "missing_tools": missing_tools,
                    "config_path": str(config_path),
                }
                
            except Exception as e:
                results[instance_dir.name] = {
                    "status": "error",
                    "error": str(e),
                    "config_path": str(config_path),
                }
        
        return results
    
    def print_instance_report(self, results: Dict[str, Dict[str, Any]]):
        """打印实例检查报告"""
        print("\n" + "=" * 60)
        print("📊 实例配置检查报告")
        print("=" * 60)
        
        for instance_name, info in sorted(results.items()):
            status = info["status"]
            
            if status == "ok":
                print(f"✅ {instance_name}: 配置正常")
            elif status == "missing":
                print(f"⚠️ {instance_name}: 缺少 config.yaml")
            elif status == "error":
                print(f"❌ {instance_name}: 解析错误 - {info.get('error', 'unknown')}")
            elif status == "needs_update":
                print(f"🔄 {instance_name}: 需要更新")
                if info.get("unknown_tools"):
                    print(f"   ⚠️ 未知工具: {', '.join(info['unknown_tools'])}")
                if info.get("missing_tools"):
                    print(f"   📝 缺失工具: {', '.join(info['missing_tools'])}")
        
        print("=" * 60)
    
    def generate_tool_reference(self) -> str:
        """生成工具参考文档"""
        lines = []
        lines.append("# 可用工具参考")
        lines.append("")
        lines.append("## 核心工具（自动启用，无需配置）")
        lines.append("")
        
        for name in CORE_TOOLS:
            cap = self.capabilities.get(name)
            if cap:
                lines.append(f"- **{name}**: {cap.description[:50]}...")
            else:
                lines.append(f"- **{name}**: (未定义)")
        
        lines.append("")
        lines.append("## 可配置工具")
        lines.append("")
        
        # 按类别分组
        categorized = {}
        for name, cap in self.capabilities.items():
            if cap.is_core:
                continue
            
            # 使用第一个 capability 作为分类
            category = cap.categories[0] if cap.categories else "其他"
            if category not in categorized:
                categorized[category] = []
            categorized[category].append(cap)
        
        for category, caps in sorted(categorized.items()):
            lines.append(f"### {category}")
            lines.append("")
            for cap in caps:
                desc = cap.description[:60] + "..." if len(cap.description) > 60 else cap.description
                lines.append(f"- **{cap.name}** [{cap.type}]: {desc}")
            lines.append("")
        
        lines.append("")
        lines.append("## 工具类别（整体启用）")
        lines.append("")
        
        for cat_name, cat_info in TOOL_CATEGORIES.items():
            tools = ", ".join(cat_info["tools"])
            lines.append(f"- **{cat_name}**: {cat_info['description']}")
            lines.append(f"  - 包含: {tools}")
        
        return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="工具配置同步脚本 - 从 capabilities.yaml 同步到实例配置"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预览变更，不实际修改文件（默认）"
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="执行同步，更新模板配置"
    )
    parser.add_argument(
        "--check-instances",
        action="store_true",
        help="检查各实例配置与模板的差异"
    )
    parser.add_argument(
        "--generate-docs",
        action="store_true",
        help="生成工具参考文档"
    )
    
    args = parser.parse_args()
    
    # 默认 dry-run
    if not args.sync and not args.check_instances and not args.generate_docs:
        args.dry_run = True
    
    sync = CapabilitiesSync()
    
    # 更新模板
    if args.dry_run or args.sync:
        sync.update_template_config(dry_run=not args.sync)
    
    # 检查实例
    if args.check_instances:
        results = sync.check_instance_configs()
        sync.print_instance_report(results)
    
    # 生成文档
    if args.generate_docs:
        doc = sync.generate_tool_reference()
        doc_path = PROJECT_ROOT / "docs" / "tool_reference.md"
        doc_path.parent.mkdir(exist_ok=True)
        with open(doc_path, 'w', encoding='utf-8') as f:
            f.write(doc)
        print(f"✅ 已生成工具参考文档：{doc_path}")


if __name__ == "__main__":
    main()

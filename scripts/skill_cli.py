#!/usr/bin/env python3
"""
Claude Skills 管理 CLI 工具

管理范围：
- 仅管理 skills/custom_claude_skills/ 下的系统级 Claude Skills
- 实例级 Skills（instances/xxx/skills/）由 instance_loader.py 自动管理

概念区分：
- Claude Skills: 上传到 Anthropic 服务器执行，通过 container.skills 调用
- Skill 自定义接口: skills/library/ 本地执行，无需上传（不在此管理）

功能：
- register: 注册 Claude Skill 到 Anthropic 服务器，自动回写 skill_id 到 capabilities.yaml
- unregister: 注销 Claude Skill，自动从 capabilities.yaml 移除 skill_id
- list: 列出所有已注册的 Claude Skills
- update: 更新 Claude Skill 版本（本地修改后同步到 Anthropic）
- update-all: 批量更新所有已注册的 Claude Skills
- versions: 查看 Claude Skill 版本历史
- sync: 同步 capabilities.yaml 与 Anthropic 服务器

使用示例：
    # 注册新 Skill
    python scripts/skill_cli.py register --skill professional-ppt-generator
    
    # 本地修改后更新版本
    python scripts/skill_cli.py update --skill professional-ppt-generator
    
    # 批量更新所有
    python scripts/skill_cli.py update-all
    
    # 查看版本历史
    python scripts/skill_cli.py versions --skill professional-ppt-generator
    
    # 列出所有已注册的 Skills
    python scripts/skill_cli.py list

设计原则：
- 开发人员一次性操作，运行时不需要注册
- skill_id 自动回写到 capabilities.yaml
- capabilities.yaml 是唯一真相来源
"""

import argparse
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import yaml
from dotenv import load_dotenv
from anthropic import Anthropic
from anthropic.lib import files_from_dir

# 加载环境变量
load_dotenv(PROJECT_ROOT / ".env")

# 配置文件路径
CAPABILITIES_FILE = PROJECT_ROOT / "config" / "capabilities.yaml"
# Claude Skills 目录（需要上传到 Anthropic 服务器）
# 注意：skills/library/ 是 Skill 自定义接口（本地执行），不在此管理
CUSTOM_CLAUDE_SKILLS_PATH = PROJECT_ROOT / "skills" / "custom_claude_skills"


class SkillCLI:
    """
    Skill 管理 CLI
    
    职责：
    - 注册/注销 Skills 到 Claude 服务器
    - 自动回写 skill_id 到 capabilities.yaml
    - 维护 capabilities.yaml 与 Claude 服务器的一致性
    """
    
    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("❌ ANTHROPIC_API_KEY 未配置")
        
        # 创建带 Skills beta 的客户端
        self.client = Anthropic(
            api_key=api_key,
            default_headers={"anthropic-beta": "skills-2025-10-02"}
        )
        
        # 加载 capabilities.yaml
        self.capabilities = self._load_capabilities()
    
    def _load_capabilities(self) -> Dict[str, Any]:
        """加载 capabilities.yaml"""
        if not CAPABILITIES_FILE.exists():
            print(f"⚠️ 配置文件不存在: {CAPABILITIES_FILE}")
            return {"capabilities": []}
        
        with open(CAPABILITIES_FILE, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {"capabilities": []}
    
    def _save_capabilities(self):
        """保存 capabilities.yaml"""
        with open(CAPABILITIES_FILE, 'w', encoding='utf-8') as f:
            yaml.dump(
                self.capabilities, 
                f, 
                default_flow_style=False, 
                allow_unicode=True,
                sort_keys=False
            )
        print(f"✅ 配置已保存: {CAPABILITIES_FILE}")
    
    def _find_capability(self, skill_name: str) -> Optional[Dict[str, Any]]:
        """在 capabilities.yaml 中查找指定的能力"""
        for cap in self.capabilities.get("capabilities", []):
            if cap.get("name") == skill_name:
                return cap
        return None
    
    def _add_or_update_capability(self, skill_name: str, skill_id: str, skill_path: str):
        """添加或更新 capability 条目"""
        existing = self._find_capability(skill_name)
        
        if existing:
            # 更新已有条目
            existing["skill_id"] = skill_id
            existing["registered_at"] = datetime.now().isoformat()
            print(f"📝 更新 capability: {skill_name}")
        else:
            # 添加新条目
            new_cap = {
                "name": skill_name,
                "type": "SKILL",
                "subtype": "CUSTOM",
                "provider": "user",
                "skill_id": skill_id,
                "skill_path": str(skill_path),
                "registered_at": datetime.now().isoformat(),
                "capabilities": self._infer_capabilities(skill_name),
                "priority": 80,
                "cost": {"time": "medium", "money": "low"},
                "constraints": {
                    "requires_api": True,
                    "requires_claude_code_execution": True
                },
                "metadata": {
                    "description": f"Custom Skill: {skill_name}",
                    "note": "由 skill_cli.py 自动注册"
                }
            }
            self.capabilities.setdefault("capabilities", []).append(new_cap)
            print(f"➕ 添加 capability: {skill_name}")
    
    def _infer_capabilities(self, skill_name: str) -> List[str]:
        """根据 skill 名称推断能力标签"""
        name_lower = skill_name.lower()
        caps = []
        
        if "ppt" in name_lower or "presentation" in name_lower:
            caps.extend(["ppt_generation", "presentation_creation"])
        if "excel" in name_lower or "xlsx" in name_lower:
            caps.extend(["data_analysis", "spreadsheet_creation"])
        if "doc" in name_lower or "word" in name_lower:
            caps.extend(["document_creation", "text_editing"])
        if "pdf" in name_lower:
            caps.extend(["pdf_generation", "document_creation"])
        if "analysis" in name_lower or "data" in name_lower:
            caps.extend(["data_analysis"])
        
        # 默认能力
        if not caps:
            caps = ["custom_skill"]
        
        return caps
    
    def _remove_skill_id(self, skill_name: str):
        """从 capability 中移除 skill_id"""
        cap = self._find_capability(skill_name)
        if cap and "skill_id" in cap:
            del cap["skill_id"]
            if "registered_at" in cap:
                del cap["registered_at"]
            print(f"🗑️ 移除 skill_id: {skill_name}")
    
    # ==================== CLI 命令 ====================
    
    def register(self, skill_name: str) -> bool:
        """
        注册 Skill 到 Claude 服务器
        
        Args:
            skill_name: Skill 目录名称（在 skills/library/ 下）
            
        Returns:
            是否成功
        """
        print(f"\n📦 注册 Skill: {skill_name}")
        print("=" * 50)
        
        # 1. 验证 Skill 目录
        skill_path = CUSTOM_CLAUDE_SKILLS_PATH / skill_name
        if not skill_path.exists():
            print(f"❌ Skill 目录不存在: {skill_path}")
            return False
        
        skill_md = skill_path / "SKILL.md"
        if not skill_md.exists():
            print(f"❌ SKILL.md 不存在: {skill_md}")
            return False
        
        print(f"✅ Skill 目录验证通过: {skill_path}")
        
        # 2. 检查是否已注册
        existing = self._find_capability(skill_name)
        if existing and existing.get("skill_id"):
            print(f"⚠️ Skill 已注册: {existing['skill_id']}")
            confirm = input("是否重新注册? (y/N): ")
            if confirm.lower() != 'y':
                return False
            # 先注销旧的
            self.unregister(skill_name, skip_save=True)
        
        # 3. 注册到 Claude 服务器
        print(f"📤 正在注册到 Claude 服务器...")
        try:
            skill = self.client.beta.skills.create(
                display_title=skill_name,
                files=files_from_dir(str(skill_path))
            )
            skill_id = skill.id
            print(f"✅ 注册成功!")
            print(f"   Skill ID: {skill_id}")
            print(f"   Version: {skill.latest_version}")
        except Exception as e:
            print(f"❌ 注册失败: {e}")
            return False
        
        # 4. 回写到 capabilities.yaml
        self._add_or_update_capability(skill_name, skill_id, skill_path)
        self._save_capabilities()
        
        print(f"\n✨ Skill 注册完成!")
        print(f"   - skill_id 已自动写入 capabilities.yaml")
        print(f"   - 运行时将自动使用此 Skill")
        
        return True
    
    def unregister(self, skill_name: str, skip_save: bool = False) -> bool:
        """
        注销 Skill
        
        Args:
            skill_name: Skill 名称
            skip_save: 是否跳过保存（内部使用）
            
        Returns:
            是否成功
        """
        print(f"\n🗑️ 注销 Skill: {skill_name}")
        print("=" * 50)
        
        # 1. 获取 skill_id
        cap = self._find_capability(skill_name)
        skill_id = cap.get("skill_id") if cap else None
        
        if not skill_id:
            print(f"⚠️ Skill 未注册或无 skill_id: {skill_name}")
            return False
        
        # 2. 从 Claude 服务器删除
        print(f"📤 正在从 Claude 服务器删除...")
        try:
            # 先删除所有版本
            versions = self.client.beta.skills.versions.list(skill_id=skill_id)
            for version in versions.data:
                self.client.beta.skills.versions.delete(
                    skill_id=skill_id, 
                    version=version.version
                )
                print(f"   删除版本: {version.version}")
            
            # 再删除 Skill
            self.client.beta.skills.delete(skill_id)
            print(f"✅ 从服务器删除成功")
        except Exception as e:
            print(f"⚠️ 服务器删除失败（可能已不存在）: {e}")
        
        # 3. 从 capabilities.yaml 移除 skill_id
        self._remove_skill_id(skill_name)
        if not skip_save:
            self._save_capabilities()
        
        print(f"\n✨ Skill 注销完成!")
        return True
    
    def list_skills(self):
        """列出所有 Skills 状态"""
        print(f"\n📋 Skills 状态")
        print("=" * 70)
        
        # 1. 从 capabilities.yaml 读取
        local_skills = {}
        for cap in self.capabilities.get("capabilities", []):
            if cap.get("type") == "SKILL" and cap.get("subtype") == "CUSTOM":
                local_skills[cap["name"]] = {
                    "skill_id": cap.get("skill_id"),
                    "registered_at": cap.get("registered_at"),
                    "skill_path": cap.get("skill_path")
                }
        
        # 2. 从 Claude 服务器获取
        print("📡 正在从 Claude 服务器获取...")
        try:
            server_skills = self.client.beta.skills.list(source="custom")
            server_skill_ids = {s.id: s.display_title for s in server_skills.data}
        except Exception as e:
            print(f"⚠️ 无法连接服务器: {e}")
            server_skill_ids = {}
        
        # 3. 显示状态
        print(f"\n{'Skill 名称':<30} {'状态':<15} {'Skill ID':<25}")
        print("-" * 70)
        
        all_names = set(local_skills.keys())
        for name in sorted(all_names):
            info = local_skills.get(name, {})
            skill_id = info.get("skill_id")
            
            if skill_id:
                if skill_id in server_skill_ids:
                    status = "✅ 已注册"
                else:
                    status = "⚠️ 服务器不存在"
            else:
                status = "❌ 未注册"
            
            skill_id_display = skill_id[:20] + "..." if skill_id and len(skill_id) > 20 else (skill_id or "-")
            print(f"{name:<30} {status:<15} {skill_id_display:<25}")
        
        # 4. 显示本地 skills/custom_claude_skills/ 中未配置的 Skill
        print(f"\n📁 Claude Skills 目录 ({CUSTOM_CLAUDE_SKILLS_PATH}):")
        if CUSTOM_CLAUDE_SKILLS_PATH.exists():
            for skill_dir in CUSTOM_CLAUDE_SKILLS_PATH.iterdir():
                if skill_dir.is_dir() and not skill_dir.name.startswith('_'):
                    skill_md = skill_dir / "SKILL.md"
                    if skill_md.exists():
                        name = skill_dir.name
                        if name in local_skills:
                            if local_skills[name].get("skill_id"):
                                print(f"   ✅ {name} (已注册)")
                            else:
                                print(f"   ⚠️ {name} (未注册)")
                        else:
                            print(f"   ➕ {name} (可注册)")
    
    def sync(self):
        """同步 capabilities.yaml 与 Claude 服务器"""
        print(f"\n🔄 同步 capabilities.yaml")
        print("=" * 50)
        
        # 获取服务器状态
        try:
            server_skills = self.client.beta.skills.list(source="custom")
            server_map = {s.display_title: s.id for s in server_skills.data}
            print(f"📡 服务器上有 {len(server_map)} 个 Custom Skills")
        except Exception as e:
            print(f"❌ 无法连接服务器: {e}")
            return
        
        # 检查本地配置
        updated = False
        for cap in self.capabilities.get("capabilities", []):
            if cap.get("type") != "SKILL" or cap.get("subtype") != "CUSTOM":
                continue
            
            name = cap.get("name")
            local_skill_id = cap.get("skill_id")
            server_skill_id = server_map.get(name)
            
            if server_skill_id and not local_skill_id:
                # 服务器有但本地没有 → 同步到本地
                cap["skill_id"] = server_skill_id
                cap["registered_at"] = datetime.now().isoformat()
                print(f"   ➕ 同步 skill_id: {name} → {server_skill_id}")
                updated = True
            elif local_skill_id and local_skill_id not in [s.id for s in server_skills.data]:
                # 本地有但服务器没有 → 标记为失效
                print(f"   ⚠️ skill_id 已失效: {name} ({local_skill_id})")
        
        if updated:
            self._save_capabilities()
            print(f"\n✅ 同步完成")
        else:
            print(f"\n✅ 无需同步")
    
    def update(self, skill_name: str) -> bool:
        """
        更新 Claude Skill 版本（本地修改后同步到 Anthropic 服务器）
        
        注意：此命令仅管理 skills/custom_claude_skills/ 下的系统级 Claude Skills
              实例级 Skills 由 instance_loader.py 在实例启动时自动注册
        
        Args:
            skill_name: Skill 名称
            
        Returns:
            是否成功
        """
        print(f"\n🔄 更新 Claude Skill: {skill_name}")
        print("=" * 50)
        
        # 1. 获取 skill_id
        cap = self._find_capability(skill_name)
        skill_id = cap.get("skill_id") if cap else None
        
        if not skill_id:
            print(f"❌ Skill 未注册: {skill_name}")
            print(f"   请先运行: python scripts/skill_cli.py register --skill {skill_name}")
            return False
        
        # 2. 查找本地目录
        skill_path = self._find_skill_path(skill_name)
        if not skill_path:
            print(f"❌ Skill 目录不存在: skills/custom_claude_skills/{skill_name}")
            return False
        
        print(f"📂 本地目录: {skill_path}")
        
        # 3. 获取当前版本信息
        try:
            current_skill = self.client.beta.skills.retrieve(skill_id)
            print(f"📋 当前版本: {current_skill.latest_version}")
        except Exception as e:
            print(f"⚠️ 无法获取当前版本信息: {e}")
        
        # 4. 创建新版本
        print(f"📤 正在创建新版本...")
        try:
            version = self.client.beta.skills.versions.create(
                skill_id=skill_id,
                files=files_from_dir(str(skill_path))
            )
            print(f"✅ 更新成功!")
            print(f"   新版本: {version.version}")
            print(f"   提示: 使用 'latest' 版本会自动使用新版本")
        except Exception as e:
            print(f"❌ 更新失败: {e}")
            return False
        
        return True
    
    def _find_skill_path(self, skill_name: str) -> Optional[Path]:
        """
        查找 Claude Skill 本地目录
        
        搜索位置：skills/custom_claude_skills/{skill_name}
        
        注意：实例级 Skills 由 instance_loader.py 管理，不在此处理
        """
        skill_path = CUSTOM_CLAUDE_SKILLS_PATH / skill_name
        if skill_path.exists() and (skill_path / "SKILL.md").exists():
            return skill_path
        
        return None
    
    def update_all(self) -> int:
        """
        批量更新所有已注册的系统级 Claude Skills
        
        注意：此命令仅管理 skills/custom_claude_skills/ 下的系统级 Claude Skills
              实例级 Skills 由 instance_loader.py 管理
            
        Returns:
            成功更新的数量
        """
        print(f"\n🔄 批量更新所有系统级 Claude Skills")
        print("=" * 50)
        print(f"📂 目录: {CUSTOM_CLAUDE_SKILLS_PATH}")
        
        updated_count = 0
        failed_skills = []
        
        # 更新 capabilities.yaml 中的 Claude Skills
        for cap in self.capabilities.get("capabilities", []):
            if cap.get("type") == "SKILL" and cap.get("subtype") == "CUSTOM":
                skill_name = cap.get("name")
                skill_id = cap.get("skill_id")
                
                if not skill_id:
                    continue
                
                skill_path = self._find_skill_path(skill_name)
                if not skill_path:
                    print(f"   ⚠️ {skill_name}: 本地目录不存在，跳过")
                    continue
                
                print(f"\n   📦 更新: {skill_name}")
                try:
                    version = self.client.beta.skills.versions.create(
                        skill_id=skill_id,
                        files=files_from_dir(str(skill_path))
                    )
                    print(f"      ✅ 新版本: {version.version}")
                    updated_count += 1
                except Exception as e:
                    print(f"      ❌ 失败: {e}")
                    failed_skills.append(skill_name)
        
        # 汇总
        print(f"\n{'=' * 50}")
        print(f"✨ 批量更新完成!")
        print(f"   成功: {updated_count} 个")
        if failed_skills:
            print(f"   失败: {len(failed_skills)} 个 ({', '.join(failed_skills)})")
        
        print(f"\n💡 提示: 实例级 Skills 请使用 instance_loader.py 管理")
        
        return updated_count
    
    def versions(self, skill_name: str) -> bool:
        """
        查看 Skill 的版本历史
        
        Args:
            skill_name: Skill 名称
            
        Returns:
            是否成功
        """
        print(f"\n📜 Skill 版本历史: {skill_name}")
        print("=" * 50)
        
        # 1. 获取 skill_id
        cap = self._find_capability(skill_name)
        skill_id = cap.get("skill_id") if cap else None
        
        if not skill_id:
            print(f"❌ Skill 未注册: {skill_name}")
            return False
        
        # 2. 获取版本列表
        try:
            versions = self.client.beta.skills.versions.list(skill_id=skill_id)
            
            if not versions.data:
                print("   (无版本记录)")
                return True
            
            print(f"\n{'版本 ID':<25} {'创建时间':<25}")
            print("-" * 50)
            
            for v in versions.data:
                # 版本号是 epoch timestamp，转换为可读时间
                try:
                    from datetime import datetime
                    ts = int(v.version) / 1000000  # 微秒转秒
                    created = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    created = "未知"
                
                version_display = v.version[:20] + "..." if len(v.version) > 20 else v.version
                print(f"{version_display:<25} {created:<25}")
            
            print(f"\n总计: {len(versions.data)} 个版本")
            
        except Exception as e:
            print(f"❌ 获取版本失败: {e}")
            return False
        
        return True


def main():
    parser = argparse.ArgumentParser(
        description="Claude Skills 管理 CLI - 管理 skills/custom_claude_skills/ 下的系统级 Claude Skills",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
说明:
  此工具仅管理系统级 Claude Skills（skills/custom_claude_skills/）
  实例级 Skills（instances/xxx/skills/）由 instance_loader.py 自动管理

  注意区分：
  - Claude Skills: 上传到 Anthropic 服务器执行（本工具管理）
  - Skill 自定义接口: skills/library/ 本地执行（无需上传）

示例:
  # 注册 Skill（自动回写 skill_id 到 capabilities.yaml）
  python scripts/skill_cli.py register --skill professional-ppt-generator

  # 列出所有 Skills 状态
  python scripts/skill_cli.py list

  # 注销 Skill
  python scripts/skill_cli.py unregister --skill professional-ppt-generator

  # 更新单个 Skill 版本（本地修改后同步到服务器）
  python scripts/skill_cli.py update --skill professional-ppt-generator

  # 批量更新所有已注册的 Skills
  python scripts/skill_cli.py update-all

  # 查看 Skill 版本历史
  python scripts/skill_cli.py versions --skill professional-ppt-generator

  # 同步本地配置与服务器
  python scripts/skill_cli.py sync
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="命令")
    
    # register 命令
    register_parser = subparsers.add_parser("register", help="注册 Claude Skill 到 Anthropic 服务器")
    register_parser.add_argument("--skill", "-s", required=True, help="Skill 目录名称（在 skills/custom_claude_skills/ 下）")
    
    # unregister 命令
    unregister_parser = subparsers.add_parser("unregister", help="注销 Claude Skill")
    unregister_parser.add_argument("--skill", "-s", required=True, help="Skill 名称")
    
    # list 命令
    subparsers.add_parser("list", help="列出所有 Claude Skills 状态")
    
    # update 命令
    update_parser = subparsers.add_parser("update", help="更新 Claude Skill 版本（本地修改后同步到 Anthropic）")
    update_parser.add_argument("--skill", "-s", required=True, help="Skill 名称")
    
    # update-all 命令
    subparsers.add_parser("update-all", help="批量更新所有已注册的系统级 Claude Skills")
    
    # versions 命令
    versions_parser = subparsers.add_parser("versions", help="查看 Claude Skill 版本历史")
    versions_parser.add_argument("--skill", "-s", required=True, help="Skill 名称")
    
    # sync 命令
    subparsers.add_parser("sync", help="同步 capabilities.yaml 与 Anthropic 服务器")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        cli = SkillCLI()
        
        if args.command == "register":
            cli.register(args.skill)
        elif args.command == "unregister":
            cli.unregister(args.skill)
        elif args.command == "list":
            cli.list_skills()
        elif args.command == "update":
            cli.update(args.skill)
        elif args.command == "update-all":
            cli.update_all()
        elif args.command == "versions":
            cli.versions(args.skill)
        elif args.command == "sync":
            cli.sync()
            
    except Exception as e:
        print(f"❌ 错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()



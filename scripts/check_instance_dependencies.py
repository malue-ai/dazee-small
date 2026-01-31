#!/usr/bin/env python3
"""
实例依赖检查脚本 - check_instance_dependencies.py

🆕 V6.1: 借鉴 clawdbot 的部署检查机制

用途：
- 部署前检查实例所需的所有依赖
- 生成友好的安装提示
- 可选：交互式安装缺失的依赖

使用方式：
    # 检查依赖
    python scripts/check_instance_dependencies.py client_agent
    
    # 检查并生成安装脚本
    python scripts/check_instance_dependencies.py client_agent --generate-install
    
    # 交互式安装（引导用户）
    python scripts/check_instance_dependencies.py client_agent --interactive
"""

import os
import sys
import shutil
import argparse
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from logger import get_logger
from core.skill.dynamic_loader import DynamicSkillLoader

logger = get_logger("dependency_checker")


class DependencyChecker:
    """实例依赖检查器"""
    
    def __init__(self, instance_name: str):
        self.instance_name = instance_name
        self.instance_dir = PROJECT_ROOT / "instances" / instance_name
        self.skills_dir = self.instance_dir / "skills"
        
        if not self.instance_dir.exists():
            raise ValueError(f"实例不存在: {instance_name}")
        
        self.loader = DynamicSkillLoader(self.skills_dir)
    
    def check_all_skills(self) -> Dict[str, Dict]:
        """
        检查所有 skills 的依赖状态
        
        Returns:
            {
                "enabled": [...],  # 满足依赖的
                "missing": [...],  # 缺少依赖的
                "stats": {...}     # 统计信息
            }
        """
        all_skills = [
            d.name for d in self.skills_dir.iterdir() 
            if d.is_dir() and not d.name.startswith('_')
        ]
        
        enabled = []
        missing = []
        
        for skill_name in all_skills:
            try:
                if self.loader.is_skill_eligible(skill_name):
                    enabled.append(skill_name)
                else:
                    dep = self.loader.check_skill_dependency(skill_name)
                    missing.append({
                        "name": skill_name,
                        "missing_bins": dep.missing_bins,
                        "missing_env": dep.missing_env,
                        "install_options": dep.install_options,
                    })
            except Exception as e:
                logger.debug(f"检查 {skill_name} 失败: {e}")
        
        return {
            "enabled": enabled,
            "missing": missing,
            "stats": {
                "total": len(all_skills),
                "enabled": len(enabled),
                "missing": len(missing),
            }
        }
    
    def generate_report(self, results: Dict) -> str:
        """生成依赖检查报告"""
        lines = [
            "=" * 70,
            f"📋 {self.instance_name} 依赖检查报告",
            "=" * 70,
            "",
            f"总计: {results['stats']['total']} 个 Skills",
            f"✅ 可用: {results['stats']['enabled']} 个",
            f"❌ 缺少依赖: {results['stats']['missing']} 个",
            "",
        ]
        
        if results['missing']:
            lines.extend([
                "=" * 70,
                "❌ 缺少依赖的 Skills",
                "=" * 70,
                "",
            ])
            
            # 按依赖类型分组
            by_bins = []
            by_env = []
            
            for skill in results['missing']:
                if skill['missing_bins']:
                    by_bins.append(skill)
                if skill['missing_env']:
                    by_env.append(skill)
            
            if by_bins:
                lines.append("## 需要安装命令行工具的 Skills")
                lines.append("")
                for skill in by_bins:
                    lines.append(f"### {skill['name']}")
                    if skill['missing_bins']:
                        lines.append(f"   缺少: {', '.join(skill['missing_bins'])}")
                    if skill['install_options']:
                        for opt in skill['install_options']:
                            lines.append(f"   安装: {self._format_install_cmd(opt)}")
                    lines.append("")
            
            if by_env:
                lines.append("## 需要配置环境变量的 Skills")
                lines.append("")
                for skill in by_env:
                    if skill['missing_env']:
                        lines.append(f"### {skill['name']}")
                        for env_name in skill['missing_env']:
                            lines.append(f"   需要: {env_name}")
                        lines.append("")
        else:
            lines.extend([
                "🎉 所有 Skills 依赖已满足！",
                "",
            ])
        
        lines.extend([
            "=" * 70,
            "💡 提示",
            "=" * 70,
            "",
            "1. 安装缺少的命令行工具后重启实例即可启用对应 Skills",
            "2. 环境变量配置在: instances/{}/\\.env".format(self.instance_name),
            "3. 可选：运行 --generate-install 生成自动安装脚本",
            "",
        ])
        
        return "\n".join(lines)
    
    def generate_install_script(self, results: Dict) -> str:
        """生成自动安装脚本"""
        lines = [
            "#!/bin/bash",
            "#",
            f"# {self.instance_name} 依赖自动安装脚本",
            "# 自动生成，请根据需要修改",
            "#",
            "",
            "set -e",
            "",
            "echo '📦 开始安装 {} 依赖...'".format(self.instance_name),
            "echo ''",
            "",
        ]
        
        # 按安装方式分组
        brew_formulas = []
        npm_packages = []
        go_modules = []
        
        for skill in results['missing']:
            for opt in skill.get('install_options', []):
                kind = opt.get('kind')
                if kind == 'brew':
                    brew_formulas.append(opt.get('formula'))
                elif kind == 'node':
                    npm_packages.append(opt.get('package'))
                elif kind == 'go':
                    go_modules.append(opt.get('module'))
        
        if brew_formulas:
            lines.extend([
                "# Homebrew 安装",
                "if command -v brew &> /dev/null; then",
                "    echo '📦 安装 Homebrew 工具...'",
            ])
            for formula in set(brew_formulas):
                if formula:
                    lines.append(f"    brew install {formula} || true")
            lines.extend([
                "else",
                "    echo '⚠️ Homebrew 未安装，跳过'",
                "fi",
                "echo ''",
                "",
            ])
        
        if npm_packages:
            lines.extend([
                "# npm 安装",
                "if command -v npm &> /dev/null; then",
                "    echo '📦 安装 npm 包...'",
            ])
            for package in set(npm_packages):
                if package:
                    lines.append(f"    npm install -g {package} || true")
            lines.extend([
                "else",
                "    echo '⚠️ npm 未安装，跳过'",
                "fi",
                "echo ''",
                "",
            ])
        
        if go_modules:
            lines.extend([
                "# Go 安装",
                "if command -v go &> /dev/null; then",
                "    echo '📦 安装 Go 模块...'",
            ])
            for module in set(go_modules):
                if module:
                    lines.append(f"    go install {module} || true")
            lines.extend([
                "else",
                "    echo '⚠️ Go 未安装，跳过'",
                "fi",
                "echo ''",
                "",
            ])
        
        # 环境变量提示
        env_vars = []
        for skill in results['missing']:
            env_vars.extend(skill.get('missing_env', []))
        
        if env_vars:
            env_file = self.instance_dir / ".env"
            lines.extend([
                "# 环境变量配置",
                f"echo '📝 请在 {env_file} 中配置以下环境变量：'",
            ])
            for env_name in set(env_vars):
                lines.append(f"echo '   - {env_name}'")
            lines.append("echo ''")
            lines.append("")
        
        lines.extend([
            "echo '✅ 依赖安装完成'",
            "echo '💡 请重启实例以启用新的 Skills'",
            "",
        ])
        
        return "\n".join(lines)
    
    def _format_install_cmd(self, opt: Dict) -> str:
        """格式化安装命令"""
        kind = opt.get('kind')
        if kind == 'brew':
            return f"brew install {opt.get('formula')}"
        elif kind == 'node':
            return f"npm install -g {opt.get('package')}"
        elif kind == 'go':
            return f"go install {opt.get('module')}"
        else:
            return opt.get('label', 'Manual install')
    
    def run_interactive(self, results: Dict):
        """交互式引导安装"""
        print("\n" + "=" * 70)
        print(f"🚀 {self.instance_name} 交互式依赖配置")
        print("=" * 70 + "\n")
        
        if not results['missing']:
            print("✅ 所有依赖已满足，无需配置！\n")
            return
        
        print(f"发现 {len(results['missing'])} 个 Skills 缺少依赖。")
        print("是否要查看详细信息？[Y/n] ", end="")
        
        response = input().strip().lower()
        if response in ['', 'y', 'yes']:
            for skill in results['missing']:
                print(f"\n📦 {skill['name']}")
                if skill['missing_bins']:
                    print(f"   需要工具: {', '.join(skill['missing_bins'])}")
                if skill['missing_env']:
                    print(f"   需要配置: {', '.join(skill['missing_env'])}")
                if skill['install_options']:
                    print(f"   安装方式:")
                    for opt in skill['install_options']:
                        print(f"      {self._format_install_cmd(opt)}")
        
        print("\n" + "=" * 70)
        print("💡 下一步")
        print("=" * 70)
        print("1. 运行 --generate-install 生成自动安装脚本")
        print(f"2. 在 instances/{self.instance_name}/.env 中配置环境变量")
        print("3. 重启实例启用新的 Skills")
        print("")


def main():
    parser = argparse.ArgumentParser(
        description="检查实例 Skills 依赖",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "instance",
        help="实例名称（例如：client_agent）"
    )
    parser.add_argument(
        "--generate-install",
        action="store_true",
        help="生成自动安装脚本"
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="交互式引导配置"
    )
    parser.add_argument(
        "--output",
        help="输出文件路径（用于安装脚本）"
    )
    
    args = parser.parse_args()
    
    try:
        checker = DependencyChecker(args.instance)
        results = checker.check_all_skills()
        
        if args.interactive:
            checker.run_interactive(results)
        elif args.generate_install:
            script = checker.generate_install_script(results)
            
            if args.output:
                output_path = Path(args.output)
                output_path.write_text(script)
                output_path.chmod(0o755)
                print(f"✅ 安装脚本已生成: {output_path}")
            else:
                print(script)
        else:
            report = checker.generate_report(results)
            print(report)
            
            # 退出码：有缺失依赖时返回 1
            sys.exit(1 if results['missing'] else 0)
    
    except Exception as e:
        logger.error(f"检查失败: {e}", exc_info=True)
        sys.exit(2)


if __name__ == "__main__":
    main()

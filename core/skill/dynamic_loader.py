"""
动态 Skill 加载器 - DynamicSkillLoader

🆕 V6.1: 支持运行时动态检查和加载 Skills

设计理念（借鉴 clawdbot）：
1. 启动时静态过滤不满足依赖的 Skills（当前行为）
2. 运行时 Agent 可请求检查特定 Skill 的依赖
3. 如果依赖已安装，动态启用该 Skill
4. 可选：Agent 调用安装命令后重新检查

使用场景：
- 用户安装了新的 CLI 工具
- Agent 需要使用某个被过滤的 Skill
- 动态启用而无需重启实例
"""

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from logger import get_logger

logger = get_logger("dynamic_skill_loader")


@dataclass
class SkillDependency:
    """Skill 依赖信息"""

    skill_name: str
    skill_path: Path

    # 依赖要求
    required_bins: List[str]
    any_bins: List[str]
    required_env: List[str]
    supported_os: List[str]

    # 安装信息
    install_options: List[Dict]

    # 检查结果
    missing_bins: List[str] = None
    missing_env: List[str] = None
    os_compatible: bool = True


class DynamicSkillLoader:
    """
    动态 Skill 加载器

    支持运行时检查和启用 Skills。
    """

    def __init__(
        self,
        skills_dir: Path,
    ):
        """
        初始化

        Args:
            skills_dir: Skills 目录路径
        """
        self.skills_dir = Path(skills_dir)
        self._cache: Dict[str, SkillDependency] = {}

    def check_skill_dependency(self, skill_name: str) -> SkillDependency:
        """
        检查单个 Skill 的依赖状态

        Args:
            skill_name: Skill 名称

        Returns:
            SkillDependency 对象
        """
        skill_path = self.skills_dir / skill_name
        skill_md = skill_path / "SKILL.md"

        if not skill_md.exists():
            raise ValueError(f"Skill not found: {skill_name}")

        # 解析 frontmatter
        dep = self._parse_skill_metadata(skill_name, skill_path, skill_md)

        # 检查依赖
        dep.missing_bins = [b for b in dep.required_bins if shutil.which(b) is None]
        dep.missing_env = [e for e in dep.required_env if not os.getenv(e)]

        # 检查 anyBins
        if dep.any_bins:
            has_any = any(shutil.which(b) is not None for b in dep.any_bins)
            if not has_any:
                dep.missing_bins.extend([f"任一: {dep.any_bins}"])

        # 检查 OS
        if dep.supported_os:
            import platform

            current_os = platform.system().lower()
            dep.os_compatible = current_os in dep.supported_os or (
                current_os == "darwin" and "macos" in dep.supported_os
            )

        self._cache[skill_name] = dep
        return dep

    def is_skill_eligible(self, skill_name: str) -> bool:
        """
        检查 Skill 是否满足所有依赖

        Args:
            skill_name: Skill 名称

        Returns:
            是否满足依赖
        """
        try:
            dep = self.check_skill_dependency(skill_name)
            return not dep.missing_bins and not dep.missing_env and dep.os_compatible
        except Exception:
            return False

    def get_install_instructions(self, skill_name: str) -> str:
        """
        获取 Skill 的安装说明

        Args:
            skill_name: Skill 名称

        Returns:
            安装说明文本
        """
        dep = self._cache.get(skill_name) or self.check_skill_dependency(skill_name)

        if not dep.missing_bins and not dep.missing_env:
            return f"✅ {skill_name} 已满足所有依赖"

        lines = [f"## {skill_name} 依赖安装说明", ""]

        if dep.missing_bins:
            lines.append("### 缺少的命令行工具")
            for bin_name in dep.missing_bins:
                lines.append(f"- `{bin_name}`")
            lines.append("")

        if dep.missing_env:
            lines.append("### 缺少的环境变量")
            for env_name in dep.missing_env:
                lines.append(f"- `{env_name}`")
            lines.append("")

        if dep.install_options:
            lines.append("### 安装方式")
            for opt in dep.install_options:
                kind = opt.get("kind", "unknown")
                label = opt.get("label", f"Install via {kind}")

                if kind == "brew":
                    formula = opt.get("formula", "")
                    lines.append(f"- **{label}**: `brew install {formula}`")
                elif kind == "node":
                    package = opt.get("package", "")
                    lines.append(f"- **{label}**: `npm install -g {package}`")
                elif kind == "go":
                    module = opt.get("module", "")
                    lines.append(f"- **{label}**: `go install {module}`")
                else:
                    lines.append(f"- **{label}**")
            lines.append("")

        return "\n".join(lines)

    def get_eligible_skills(self) -> Tuple[List[str], List[str]]:
        """
        V11: 获取当前平台可用且满足依赖的 Skills

        扫描 skills_dir 下所有 Skill，逐个检查依赖。

        Returns:
            (可用 Skill 名称列表, 不可用 Skill 名称列表)
        """
        candidates = [
            d.name
            for d in self.skills_dir.iterdir()
            if d.is_dir() and (d / "SKILL.md").exists()
        ]

        eligible = []
        ineligible = []
        for name in candidates:
            if self.is_skill_eligible(name):
                eligible.append(name)
            else:
                ineligible.append(name)

        logger.info(
            f"Skills 筛选完成: {len(eligible)} 可用, {len(ineligible)} 不可用"
        )
        return eligible, ineligible

    def _parse_skill_metadata(
        self, skill_name: str, skill_path: Path, skill_md: Path
    ) -> SkillDependency:
        """解析 SKILL.md 的 metadata"""
        import json

        import yaml

        content = skill_md.read_text(encoding="utf-8")

        dep = SkillDependency(
            skill_name=skill_name,
            skill_path=skill_path,
            required_bins=[],
            any_bins=[],
            required_env=[],
            supported_os=[],
            install_options=[],
        )

        if not content.startswith("---"):
            return dep

        end_idx = content.find("---", 3)
        if end_idx <= 0:
            return dep

        try:
            frontmatter = yaml.safe_load(content[3:end_idx])
            metadata = frontmatter.get("metadata", {})

            if isinstance(metadata, str):
                metadata = json.loads(metadata)

            moltbot = metadata.get("moltbot", {})
            requires = moltbot.get("requires", {})

            dep.required_bins = requires.get("bins", [])
            dep.any_bins = requires.get("anyBins", [])
            dep.required_env = requires.get("env", [])
            dep.supported_os = moltbot.get("os", [])
            dep.install_options = moltbot.get("install", [])

        except Exception as e:
            logger.debug(f"解析 {skill_name} metadata 失败: {e}")

        return dep


# 便捷函数
def check_and_report_skills(
    skills_dir: Path, skill_names: List[str]
) -> Dict[str, Tuple[bool, str]]:
    """
    批量检查 Skills 依赖状态

    Args:
        skills_dir: Skills 目录
        skill_names: Skill 名称列表

    Returns:
        {skill_name: (eligible, message)}
    """
    loader = DynamicSkillLoader(skills_dir)
    results = {}

    for name in skill_names:
        try:
            eligible = loader.is_skill_eligible(name)
            if eligible:
                results[name] = (True, "✅ 满足依赖")
            else:
                instructions = loader.get_install_instructions(name)
                results[name] = (False, instructions)
        except Exception as e:
            results[name] = (False, f"❌ 检查失败: {e}")

    return results

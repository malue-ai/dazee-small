"""
Skills-First 统一加载器 - SkillsLoader

职责：
1. 解析 config.yaml 的 skills 二维分类配置
2. 按当前 OS 合并 common + {os} Skills
3. 检查每个 Skill 的运行时状态（依赖、授权、配置）
4. 加载 SKILL.md 内容（懒加载，供系统提示词注入）
5. 生成 enabled_capabilities 兼容旧 ToolLoader
6. 提供统一 Skill 列表给 Agent 和 UI

设计原则：
- Agent 只看到 SkillEntry 列表，不感知 backend_type
- 向后兼容：backend_type=tool 的 Skill 会映射到 enabled_capabilities
- 渐进式加载：SKILL.md 内容按需加载
- 异步优先：所有 I/O 操作异步执行
"""

import os
import platform
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiofiles

from logger import get_logger

from .models import BackendType, DependencyLevel, SkillEntry, SkillStatus

logger = get_logger("skills_loader")

# OS 键映射
_OS_KEY_MAP = {
    "darwin": "darwin",
    "windows": "win32",
    "linux": "linux",
}

# 依赖复杂度等级（配置中的键名）
_DEPENDENCY_LEVELS = ["builtin", "lightweight", "external", "cloud_api"]


def _current_os_key() -> str:
    """获取当前 OS 配置键"""
    return _OS_KEY_MAP.get(platform.system().lower(), "linux")


class SkillsLoader:
    """
    Skills-First 统一加载器

    使用示例：
        loader = SkillsLoader(
            skills_config=config["skills"],
            instance_skills_dir=Path("instances/xiaodazi/skills"),
            library_skills_dir=Path("skills/library"),
        )

        # 加载并合并当前 OS 的 Skills
        entries = await loader.load()

        # 获取可用 Skills（供 Agent 使用）
        available = loader.get_available_skills()

        # 获取 enabled_capabilities（兼容 ToolLoader）
        caps = loader.get_enabled_capabilities()

        # 获取 Skills 摘要（供系统提示词注入）
        prompt_section = await loader.build_skills_prompt()
    """

    def __init__(
        self,
        skills_config: Dict[str, Any],
        instance_skills_dir: Path,
        library_skills_dir: Path,
    ):
        """
        初始化

        Args:
            skills_config: config.yaml 中的 skills 配置段
            instance_skills_dir: 实例 Skills 目录（instances/{name}/skills/）
            library_skills_dir: 全局 Skills 库目录（skills/library/）
        """
        self._config = skills_config or {}
        self._instance_dir = Path(instance_skills_dir)
        self._library_dir = Path(library_skills_dir)
        self._os_key = _current_os_key()
        self._loading_mode = self._config.get("loading_mode", "lazy")

        # 加载结果缓存
        self._entries: List[SkillEntry] = []
        self._loaded = False

    # ================================================================
    # 公开 API
    # ================================================================

    async def load(self) -> List[SkillEntry]:
        """
        加载并合并当前 OS 的全部 Skills

        流程：
        1. 解析 common + 当前 OS 的配置
        2. 创建 SkillEntry 列表
        3. 解析 SKILL.md 路径
        4. 检查运行时状态
        5. 缓存结果

        Returns:
            合并后的 SkillEntry 列表
        """
        if self._loaded:
            return self._entries

        logger.info(f"开始加载 Skills（OS: {self._os_key}）")

        # 1. 解析 common 配置
        common_entries = self._parse_os_section("common")

        # 2. 解析当前 OS 配置
        os_entries = self._parse_os_section(self._os_key)

        # 3. 合并（去重，后者覆盖前者）
        merged = self._merge_entries(common_entries, os_entries)

        # 4. 解析 SKILL.md 路径
        for entry in merged:
            entry.skill_path = self._resolve_skill_path(entry)

        # 5. 检查运行时状态
        for entry in merged:
            self._check_status(entry)

        self._entries = merged
        self._loaded = True

        # 打印加载摘要
        self._log_summary()

        return self._entries

    def get_all_skills(self) -> List[SkillEntry]:
        """获取所有已加载的 Skills"""
        return list(self._entries)

    def get_available_skills(self) -> List[SkillEntry]:
        """获取所有可用的 Skills（enabled=True 且 status=ready）"""
        return [e for e in self._entries if e.is_available()]

    def get_enabled_skills(self) -> List[SkillEntry]:
        """获取所有已启用的 Skills（包含非 ready 状态）"""
        return [e for e in self._entries if e.enabled]

    def get_skills_by_backend(self, backend: BackendType) -> List[SkillEntry]:
        """按后端类型筛选 Skills"""
        return [e for e in self._entries if e.backend_type == backend]

    def get_skill(self, name: str) -> Optional[SkillEntry]:
        """按名称获取单个 Skill"""
        for entry in self._entries:
            if entry.name == name:
                return entry
        return None

    def get_enabled_capabilities(self) -> Dict[str, bool]:
        """
        生成 enabled_capabilities 字典（兼容 ToolLoader）

        将 backend_type=tool 的 Skill 映射回框架 Tool 名称。

        Returns:
            {"plan_todo": True, "hitl": True, ...}
        """
        caps = {}
        for entry in self._entries:
            if entry.backend_type == BackendType.TOOL and entry.enabled:
                tool_name = entry.tool_name or entry.name
                caps[tool_name] = True
        return caps

    def get_status_table(self) -> List[Dict[str, Any]]:
        """
        获取 Skills 状态表（供 UI 仪表板展示）

        Returns:
            [{"name": ..., "status": ..., "description": ..., ...}, ...]
        """
        return [
            {
                "name": e.name,
                "description": e.description,
                "backend_type": e.backend_type.value,
                "dependency_level": e.dependency_level.value,
                "os_category": e.os_category,
                "status": e.status.value,
                "status_message": e.status_message,
                "enabled": e.enabled,
            }
            for e in self._entries
        ]

    async def load_skill_content(self, name: str) -> Optional[str]:
        """
        加载指定 Skill 的 SKILL.md 内容（懒加载）

        Args:
            name: Skill 名称

        Returns:
            SKILL.md 完整内容，或 None
        """
        entry = self.get_skill(name)
        if not entry:
            return None

        # 已缓存
        if entry.skill_md_content is not None:
            return entry.skill_md_content

        # backend_type=tool 无 SKILL.md
        if entry.backend_type == BackendType.TOOL:
            return None

        if not entry.skill_path:
            return None

        skill_md = Path(entry.skill_path) / "SKILL.md"
        if not skill_md.exists():
            return None

        try:
            async with aiofiles.open(skill_md, "r", encoding="utf-8") as f:
                content = await f.read()
            entry.skill_md_content = content
            return content
        except Exception as e:
            logger.warning(f"加载 SKILL.md 失败: {name}, 错误: {e}")
            return None

    async def build_skills_prompt(self) -> str:
        """
        构建 Skills 列表提示词片段（注入到系统提示词）

        格式：
        - 可用 Skills 的名称和描述
        - 不可用 Skills 的说明（帮助 Agent 告知用户）

        Returns:
            Markdown 格式的 Skills 描述
        """
        available = self.get_available_skills()
        unavailable = [
            e for e in self._entries
            if e.enabled and e.status != SkillStatus.READY
        ]

        sections = ["# 当前可用的 Skills\n"]

        if available:
            for entry in available:
                if entry.backend_type == BackendType.TOOL:
                    # Tool 类型由框架管理，不在此展示
                    continue
                sections.append(f"- **{entry.name}**: {entry.description}")
            sections.append("")

        if unavailable:
            sections.append("# 尚未就绪的 Skills（可引导用户启用）\n")
            for entry in unavailable:
                hint = self._get_setup_hint(entry)
                sections.append(f"- **{entry.name}**: {entry.description}（{hint}）")
            sections.append("")

        return "\n".join(sections)

    # ================================================================
    # 内部方法：配置解析
    # ================================================================

    def _parse_os_section(self, os_key: str) -> List[SkillEntry]:
        """
        解析某个 OS 分类下的全部 Skills

        Args:
            os_key: common / darwin / win32 / linux

        Returns:
            SkillEntry 列表
        """
        os_config = self._config.get(os_key, {})
        if not isinstance(os_config, dict):
            return []

        entries = []
        for level_key in _DEPENDENCY_LEVELS:
            items = os_config.get(level_key, [])
            if not isinstance(items, list):
                continue

            for item in items:
                if not isinstance(item, dict):
                    continue

                entry = self._parse_skill_item(item, os_key, level_key)
                if entry:
                    entries.append(entry)

        return entries

    def _parse_skill_item(
        self, item: Dict[str, Any], os_key: str, level_key: str
    ) -> Optional[SkillEntry]:
        """
        解析单个 Skill 配置项

        Args:
            item: config.yaml 中的 Skill 字典
            os_key: 所属 OS 分类
            level_key: 依赖复杂度等级

        Returns:
            SkillEntry 或 None
        """
        name = item.get("name")
        if not name:
            logger.warning(f"跳过无 name 字段的 Skill 配置: {item}")
            return None

        # 解析 backend_type
        backend_str = item.get("backend_type", "local")
        try:
            backend_type = BackendType(backend_str)
        except ValueError:
            logger.warning(f"Skill {name}: 未知 backend_type '{backend_str}'，使用 local")
            backend_type = BackendType.LOCAL

        # 解析 dependency_level
        try:
            dep_level = DependencyLevel(level_key)
        except ValueError:
            dep_level = DependencyLevel.BUILTIN

        return SkillEntry(
            name=name,
            description=item.get("description", ""),
            backend_type=backend_type,
            dependency_level=dep_level,
            os_category=os_key,
            enabled=item.get("enabled", True),
            skill_source=item.get("skill_source", "instance"),
            tool_name=item.get("tool_name"),
            api_config=item.get("api_config"),
            mcp_config=item.get("mcp_config"),
            bins=item.get("bins", []),
            python_packages=item.get("python_packages", []),
            system_auth=item.get("system_auth"),
            requires_app=item.get("requires_app"),
            install_info=item.get("install"),
            raw_config=item,
        )

    # ================================================================
    # 内部方法：合并与路径解析
    # ================================================================

    def _merge_entries(
        self, common: List[SkillEntry], os_specific: List[SkillEntry]
    ) -> List[SkillEntry]:
        """
        合并 common + OS 特定 Skills（去重，OS 特定覆盖 common）

        Args:
            common: 跨平台 Skills
            os_specific: 当前 OS 专属 Skills

        Returns:
            合并后的列表
        """
        merged = {}
        for entry in common:
            merged[entry.name] = entry
        for entry in os_specific:
            merged[entry.name] = entry

        return list(merged.values())

    def _resolve_skill_path(self, entry: SkillEntry) -> Optional[str]:
        """
        解析 Skill 的 SKILL.md 目录路径

        优先级：
        1. instance skills 目录
        2. library skills 目录

        Args:
            entry: Skill 条目

        Returns:
            目录路径字符串，或 None
        """
        # backend_type=tool 不需要 SKILL.md
        if entry.backend_type == BackendType.TOOL:
            return None

        # 1. 优先查找 instance 目录
        instance_path = self._instance_dir / entry.name
        if instance_path.exists() and (instance_path / "SKILL.md").exists():
            return str(instance_path)

        # 2. 查找 library 目录
        library_path = self._library_dir / entry.name
        if library_path.exists() and (library_path / "SKILL.md").exists():
            return str(library_path)

        # 3. 未找到
        if entry.backend_type in (BackendType.LOCAL, BackendType.API):
            logger.debug(
                f"Skill {entry.name}: 未找到 SKILL.md "
                f"（instance: {instance_path}, library: {library_path}）"
            )

        return None

    # ================================================================
    # 内部方法：状态检查
    # ================================================================

    def _check_status(self, entry: SkillEntry) -> None:
        """
        检查 Skill 运行时状态，更新 entry.status 和 entry.status_message

        检查顺序：
        1. backend_type=tool → 信任框架注册，标记 ready
        2. bins 依赖 → 检查命令是否存在
        3. system_auth → 标记 need_auth（无法自动检测）
        4. requires_app → 检查应用是否安装
        5. api_config → 检查 API Key 是否配置
        6. python_packages → 检查 Python 包是否安装
        """
        # Tool 类型信任框架
        if entry.backend_type == BackendType.TOOL:
            entry.status = SkillStatus.READY
            entry.status_message = "框架内置工具"
            return

        # 检查命令行依赖
        if entry.bins:
            missing = [b for b in entry.bins if shutil.which(b) is None]
            if missing:
                entry.status = SkillStatus.UNAVAILABLE
                entry.status_message = f"缺少命令: {', '.join(missing)}"
                return

        # 检查系统授权
        if entry.system_auth:
            entry.status = SkillStatus.NEED_AUTH
            entry.status_message = f"需要系统授权: {entry.system_auth}"
            return

        # 检查外部应用
        if entry.requires_app:
            if not self._check_app_installed(entry.requires_app, entry.raw_config):
                entry.status = SkillStatus.UNAVAILABLE
                entry.status_message = f"需要安装应用: {entry.requires_app}"
                return

        # 检查 API 配置
        if entry.backend_type == BackendType.API and entry.api_config:
            auth_type = entry.api_config.get("auth_type", "none")
            if auth_type != "none":
                key_field = entry.api_config.get("auth_key_field", "")
                if key_field and not os.getenv(key_field):
                    entry.status = SkillStatus.NEED_SETUP
                    entry.status_message = f"需要配置 API Key: {key_field}"
                    return

        # 检查 Python 包（轻量检查，不 import）
        if entry.python_packages:
            missing_pkgs = self._check_python_packages(entry.python_packages)
            if missing_pkgs:
                if entry.raw_config.get("auto_install"):
                    # 标记为 ready，首次使用时自动安装
                    entry.status = SkillStatus.READY
                    entry.status_message = f"首次使用时自动安装: {', '.join(missing_pkgs)}"
                else:
                    entry.status = SkillStatus.NEED_SETUP
                    entry.status_message = f"需要安装 Python 包: {', '.join(missing_pkgs)}"
                return

        # 全部通过
        entry.status = SkillStatus.READY
        entry.status_message = "就绪"

    def _check_app_installed(self, app_name: str, config: Dict[str, Any]) -> bool:
        """
        检查外部应用是否安装

        Args:
            app_name: 应用名称
            config: Skill 原始配置（含 detect_path）

        Returns:
            是否安装
        """
        detect_paths = config.get("detect_path", {})
        path_template = detect_paths.get(self._os_key)
        if path_template:
            expanded = os.path.expandvars(os.path.expanduser(path_template))
            return Path(expanded).exists()

        # macOS: 检查 /Applications
        if self._os_key == "darwin":
            return Path(f"/Applications/{app_name}.app").exists()

        # 无法检测，保守返回 False
        return False

    def _check_python_packages(self, packages: List[str]) -> List[str]:
        """
        检查 Python 包是否已安装

        Args:
            packages: 包名列表

        Returns:
            缺失的包名列表
        """
        missing = []
        for pkg in packages:
            # 标准化包名（pip install name 和 import name 可能不同）
            import_name = pkg.replace("-", "_").lower()
            try:
                __import__(import_name)
            except ImportError:
                missing.append(pkg)
        return missing

    # ================================================================
    # 内部方法：辅助
    # ================================================================

    def _get_setup_hint(self, entry: SkillEntry) -> str:
        """获取设置提示（供提示词使用）"""
        if entry.status == SkillStatus.NEED_AUTH:
            return f"需要授权: {entry.system_auth}"
        if entry.status == SkillStatus.NEED_SETUP:
            return entry.status_message
        if entry.status == SkillStatus.UNAVAILABLE:
            return entry.status_message
        return ""

    def _log_summary(self) -> None:
        """打印加载摘要"""
        total = len(self._entries)
        ready = sum(1 for e in self._entries if e.status == SkillStatus.READY)
        need_auth = sum(1 for e in self._entries if e.status == SkillStatus.NEED_AUTH)
        need_setup = sum(1 for e in self._entries if e.status == SkillStatus.NEED_SETUP)
        unavailable = sum(1 for e in self._entries if e.status == SkillStatus.UNAVAILABLE)

        by_backend = {}
        for e in self._entries:
            key = e.backend_type.value
            by_backend[key] = by_backend.get(key, 0) + 1

        logger.info(
            f"Skills 加载完成: 共 {total} 个 "
            f"(ready={ready}, need_auth={need_auth}, "
            f"need_setup={need_setup}, unavailable={unavailable})"
        )
        logger.info(f"  按后端: {by_backend}")

        # 打印每个 Skill 状态
        for entry in self._entries:
            icon = {
                SkillStatus.READY: "✅",
                SkillStatus.NEED_AUTH: "🔐",
                SkillStatus.NEED_SETUP: "⚙️",
                SkillStatus.UNAVAILABLE: "❌",
            }.get(entry.status, "❓")
            logger.debug(
                f"  {icon} {entry.name} "
                f"[{entry.os_category}/{entry.dependency_level.value}] "
                f"backend={entry.backend_type.value} "
                f"status={entry.status.value}"
            )


# ================================================================
# 便捷工厂函数
# ================================================================


def create_skills_loader(
    skills_config: Dict[str, Any],
    instance_skills_dir: Path,
    library_skills_dir: Optional[Path] = None,
) -> SkillsLoader:
    """
    创建 SkillsLoader 实例

    Args:
        skills_config: config.yaml 中的 skills 配置段
        instance_skills_dir: 实例 Skills 目录
        library_skills_dir: 全局 Skills 库（默认项目根目录/skills/library）

    Returns:
        SkillsLoader 实例
    """
    if library_skills_dir is None:
        from utils.app_paths import get_bundle_dir
        library_skills_dir = get_bundle_dir() / "skills" / "library"

    return SkillsLoader(
        skills_config=skills_config,
        instance_skills_dir=instance_skills_dir,
        library_skills_dir=library_skills_dir,
    )

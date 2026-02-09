"""
Skills-First 数据模型

定义 SkillEntry 及相关类型，作为 Skills-First 架构的统一数据结构。

设计原则：
- SkillEntry 是 Agent 看到的唯一能力单元
- backend_type 是内部实现细节，Agent 不感知
- 与 config.yaml 的 skills 配置一一映射
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class BackendType(str, Enum):
    """
    Skill 执行后端类型

    Agent 不感知此字段，由 SkillsLoader 内部路由。
    """

    LOCAL = "local"  # 本地脚本/命令（SKILL.md 指导 Agent 执行）
    TOOL = "tool"  # 框架内置 Tool（通过 tool_use 调用）
    MCP = "mcp"  # MCP Server 协议
    API = "api"  # REST/HTTP API


class DependencyLevel(str, Enum):
    """
    依赖复杂度等级

    决定 Skill 的安装/配置门槛。
    """

    BUILTIN = "builtin"  # 内置，安装即用
    LIGHTWEIGHT = "lightweight"  # 轻量，Python 包或系统授权
    EXTERNAL = "external"  # 外部，需安装外部应用/工具
    CLOUD_API = "cloud_api"  # 云服务，需 API Key


class SkillStatus(str, Enum):
    """
    Skill 运行时状态

    供 UI 展示和 Agent 使用。
    """

    READY = "ready"  # 可直接使用
    NEED_AUTH = "need_auth"  # 需要系统授权（如 macOS 辅助功能权限）
    NEED_SETUP = "need_setup"  # 需要配置（如 API Key、安装 Python 包）
    UNAVAILABLE = "unavailable"  # 依赖不满足（缺少 CLI、应用未安装）


@dataclass
class SkillEntry:
    """
    统一 Skill 条目

    Agent 看到的唯一能力单元。无论底层是 Tool、MCP 还是 API，
    Agent 统一通过 SkillEntry 感知能力。

    Attributes:
        name: Skill 唯一标识（如 'macos-screenshot'）
        description: 一句话描述
        backend_type: 执行后端类型（local/tool/mcp/api）
        dependency_level: 依赖复杂度（builtin/lightweight/external/cloud_api）
        os_category: 所属 OS 分类（common/darwin/win32/linux）
        status: 运行时状态（ready/need_auth/need_setup/unavailable）
        enabled: 是否启用
        skill_source: 来源（library/instance）
        skill_path: SKILL.md 所在目录路径
        skill_md_content: SKILL.md 内容（懒加载）
        tool_name: backend_type=tool 时，对应的框架 Tool 名称
        api_config: backend_type=api 时，API 连接配置
        mcp_config: backend_type=mcp 时，MCP Server 配置
        bins: 依赖的命令行工具
        python_packages: 依赖的 Python 包
        system_auth: 需要的系统权限（如 macOS accessibility）
        requires_app: 依赖的外部应用名
        install_info: 安装说明
        status_message: 状态说明（人类可读）
        raw_config: 原始配置字典（从 config.yaml 解析）
    """

    name: str
    description: str = ""
    backend_type: BackendType = BackendType.LOCAL
    dependency_level: DependencyLevel = DependencyLevel.BUILTIN
    os_category: str = "common"
    status: SkillStatus = SkillStatus.READY
    enabled: bool = True

    # 来源
    skill_source: str = "instance"  # library / instance
    skill_path: Optional[str] = None
    skill_md_content: Optional[str] = None

    # backend_type=tool
    tool_name: Optional[str] = None

    # backend_type=api
    api_config: Optional[Dict[str, Any]] = None

    # backend_type=mcp
    mcp_config: Optional[Dict[str, Any]] = None

    # 依赖信息
    bins: List[str] = field(default_factory=list)
    python_packages: List[str] = field(default_factory=list)
    system_auth: Optional[str] = None
    requires_app: Optional[str] = None
    install_info: Optional[Dict[str, str]] = None

    # 运行时
    status_message: str = ""
    raw_config: Dict[str, Any] = field(default_factory=dict)

    def is_available(self) -> bool:
        """Skill 是否可用（启用且状态为 ready）"""
        return self.enabled and self.status == SkillStatus.READY

    def to_registry_dict(self) -> Dict[str, Any]:
        """转换为 skill_registry.yaml 格式"""
        result = {
            "name": self.name,
            "enabled": self.enabled,
            "description": self.description,
            "status": self.status.value,
        }
        if self.os_category != "common":
            result["os"] = self.os_category
        return result

    def to_summary(self) -> str:
        """生成简短摘要（供系统提示词使用）"""
        status_icon = {
            SkillStatus.READY: "✅",
            SkillStatus.NEED_AUTH: "🔐",
            SkillStatus.NEED_SETUP: "⚙️",
            SkillStatus.UNAVAILABLE: "❌",
        }.get(self.status, "❓")

        return f"{status_icon} {self.name}: {self.description}"

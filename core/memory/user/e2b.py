"""
E2B 沙箱记忆 - 用户级

职责：
- 管理用户的 E2B 沙箱会话生命周期
- 支持临时沙箱（会话结束销毁）和持久沙箱（跨会话保留）
- 存储代码执行历史
- 为 LLM 生成上下文

设计原则：
- 用户级隔离：每个用户有独立的沙箱空间
- 双模式支持：临时沙箱 + 持久沙箱
- Memory-First：沙箱状态持久化在 Memory
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from logger import get_logger

logger = get_logger("memory.user.e2b")


class E2BSandboxSession:
    """
    E2B 沙箱会话信息

    设计原则（Memory-First）：
    1. 沙箱信息持久化在 Memory，而不是工具内部变量
    2. 支持多轮对话（用户可以说"继续处理数据"）
    3. session 结束时自动清理资源
    """

    def __init__(
        self,
        sandbox_id: str,
        created_at: datetime,
        template: str = "base",
        status: str = "active",
        persistent: bool = False,
        name: Optional[str] = None,
    ):
        self.sandbox_id = sandbox_id
        self.template = template
        self.created_at = created_at
        self.last_used = created_at
        self.status = status  # "active" / "idle" / "terminated"
        self.persistent = persistent  # 是否跨会话保留
        self.name = name  # 沙箱名称（持久沙箱）
        self.execution_count = 0
        self.files: Dict[str, Any] = {}  # 文件记录
        self.installed_packages: List[str] = []
        self.env_vars: Dict[str, str] = {}

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "sandbox_id": self.sandbox_id,
            "template": self.template,
            "created_at": self.created_at.isoformat(),
            "last_used": self.last_used.isoformat(),
            "status": self.status,
            "persistent": self.persistent,
            "name": self.name,
            "execution_count": self.execution_count,
            "files": self.files,
            "installed_packages": self.installed_packages,
            "env_vars": self.env_vars,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "E2BSandboxSession":
        """从字典反序列化"""
        session = cls(
            sandbox_id=data["sandbox_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            template=data.get("template", "base"),
            status=data.get("status", "active"),
            persistent=data.get("persistent", False),
            name=data.get("name"),
        )
        session.last_used = datetime.fromisoformat(data["last_used"])
        session.execution_count = data.get("execution_count", 0)
        session.files = data.get("files", {})
        session.installed_packages = data.get("installed_packages", [])
        session.env_vars = data.get("env_vars", {})
        return session


class E2BMemory:
    """
    E2B 沙箱记忆管理 - 用户级

    特性：
    1. 临时沙箱：会话结束后自动销毁
    2. 持久沙箱：跨会话保留，用户的"云端工作空间"
    3. 执行历史：记录最近的代码执行

    使用示例：
    ```python
    e2b = E2BMemory(user_id="user_123")

    # 临时沙箱（默认）
    e2b.set_session(sandbox_session)

    # 持久沙箱
    e2b.add_persistent_sandbox(sandbox_session, name="数据分析环境")

    # 获取沙箱
    sandbox = e2b.get_active_sandbox()  # 临时或持久
    sandbox = e2b.get_persistent_sandbox("数据分析环境")
    ```
    """

    def __init__(self, user_id: Optional[str] = None) -> None:
        """
        初始化 E2B 记忆

        Args:
            user_id: 用户 ID（用于隔离）
        """
        self.user_id = user_id

        # 临时沙箱（会话级）
        self._temporary_session: Optional[E2BSandboxSession] = None

        # 持久沙箱（用户级，跨会话）
        self._persistent_sandboxes: Dict[str, E2BSandboxSession] = {}

        # 执行历史
        self.execution_history: List[Dict[str, Any]] = []

    # ==================== 临时沙箱（会话级） ====================

    def set_session(self, session: E2BSandboxSession) -> None:
        """设置临时 E2B 沙箱会话"""
        session.persistent = False
        self._temporary_session = session
        logger.debug(f"[E2BMemory] 临时会话已创建: {session.sandbox_id}")

    def get_session(self) -> Optional[E2BSandboxSession]:
        """获取当前临时 E2B 会话"""
        return self._temporary_session

    def has_active_session(self) -> bool:
        """检查是否有活跃的临时 E2B 会话"""
        return self._temporary_session is not None and self._temporary_session.status == "active"

    def update_session(self, **kwargs) -> None:
        """更新临时 E2B 会话信息"""
        if self._temporary_session:
            for key, value in kwargs.items():
                if hasattr(self._temporary_session, key):
                    setattr(self._temporary_session, key, value)
            self._temporary_session.last_used = datetime.now()

    def clear_session(self) -> None:
        """清除临时 E2B 会话（终止沙箱）"""
        if self._temporary_session:
            logger.info(f"[E2BMemory] 临时会话已清除: {self._temporary_session.sandbox_id}")
            self._temporary_session.status = "terminated"
            self._temporary_session = None

    # ==================== 持久沙箱（用户级） ====================

    def add_persistent_sandbox(self, session: E2BSandboxSession, name: str):
        """
        添加持久沙箱

        Args:
            session: 沙箱会话
            name: 沙箱名称（唯一标识）
        """
        session.persistent = True
        session.name = name
        self._persistent_sandboxes[name] = session
        logger.info(f"[E2BMemory] 持久沙箱已添加: {name} ({session.sandbox_id})")

    def get_persistent_sandbox(self, name: str) -> Optional[E2BSandboxSession]:
        """获取持久沙箱"""
        return self._persistent_sandboxes.get(name)

    def list_persistent_sandboxes(self) -> List[Dict[str, Any]]:
        """列出所有持久沙箱"""
        return [
            {
                "name": name,
                "sandbox_id": session.sandbox_id,
                "template": session.template,
                "status": session.status,
                "last_used": session.last_used.isoformat(),
                "execution_count": session.execution_count,
            }
            for name, session in self._persistent_sandboxes.items()
        ]

    def remove_persistent_sandbox(self, name: str) -> bool:
        """移除持久沙箱"""
        if name in self._persistent_sandboxes:
            session = self._persistent_sandboxes.pop(name)
            session.status = "terminated"
            logger.info(f"[E2BMemory] 持久沙箱已移除: {name}")
            return True
        return False

    # ==================== 统一接口 ====================

    def get_active_sandbox(self) -> Optional[E2BSandboxSession]:
        """
        获取活跃的沙箱（优先临时沙箱）

        查找顺序：
        1. 临时沙箱（如果活跃）
        2. 最近使用的持久沙箱
        """
        if self.has_active_session():
            return self._temporary_session

        # 查找最近使用的持久沙箱
        active_persistent = [s for s in self._persistent_sandboxes.values() if s.status == "active"]
        if active_persistent:
            return max(active_persistent, key=lambda s: s.last_used)

        return None

    # ==================== 执行历史 ====================

    def add_execution(self, code: str, result: Dict[str, Any], execution_time: float):
        """
        记录 E2B 代码执行历史

        Args:
            code: 执行的代码
            result: 执行结果
            execution_time: 执行时间（秒）
        """
        execution_record = {
            "timestamp": datetime.now().isoformat(),
            "code": code,
            "result": result,
            "execution_time": execution_time,
            "success": result.get("success", False),
        }
        self.execution_history.append(execution_record)

        # 限制历史记录数量（避免 Memory 过大）
        if len(self.execution_history) > 20:
            self.execution_history.pop(0)

        # 更新当前活跃沙箱的执行计数
        active = self.get_active_sandbox()
        if active:
            active.execution_count += 1
            active.last_used = datetime.now()

    def get_recent_executions(self, limit: int = 5) -> List[Dict[str, Any]]:
        """获取最近的执行历史"""
        return self.execution_history[-limit:]

    # ==================== LLM 上下文 ====================

    def get_context_for_llm(self, max_history: int = 3) -> str:
        """
        获取 E2B 上下文（给 LLM）

        精简版本，只包含关键信息：
        - 当前沙箱状态
        - 最近 N 次执行历史（摘要）
        - 已安装的包
        - 存在的文件
        """
        active = self.get_active_sandbox()
        if not active:
            return ""

        context_parts = [
            "## 📦 E2B沙箱状态",
            f"- Sandbox ID: {active.sandbox_id}",
            f"- 类型: {'持久' if active.persistent else '临时'}",
            f"- 执行次数: {active.execution_count}",
        ]

        if active.name:
            context_parts.append(f"- 名称: {active.name}")

        if active.installed_packages:
            context_parts.append(f"- 已安装包: {', '.join(active.installed_packages)}")

        if active.files:
            context_parts.append(f"- 文件: {', '.join(active.files.keys())}")

        # 最近的执行历史（摘要）
        recent = self.execution_history[-max_history:]
        if recent:
            context_parts.append("\n## 📝 最近执行历史")
            for i, exec_record in enumerate(recent, 1):
                status = "✅" if exec_record["success"] else "❌"
                context_parts.append(f"{i}. {status} {exec_record['timestamp'][:19]}")
                # 只显示代码的第一行（摘要）
                first_line = exec_record["code"].split("\n")[0][:50]
                context_parts.append(f"   代码: {first_line}...")

        # 列出持久沙箱
        if self._persistent_sandboxes:
            context_parts.append("\n## 💾 持久沙箱")
            for name, session in self._persistent_sandboxes.items():
                status_icon = "🟢" if session.status == "active" else "⚪"
                context_parts.append(f"- {status_icon} {name}")

        return "\n".join(context_parts)

    # ==================== 清理 ====================

    def clear_temporary(self) -> None:
        """清空临时沙箱和执行历史"""
        self.clear_session()
        self.execution_history.clear()
        logger.debug("[E2BMemory] 临时数据已清空")

    def clear_all(self) -> None:
        """清空所有 E2B 记忆（包括持久沙箱）"""
        self.clear_session()
        self._persistent_sandboxes.clear()
        self.execution_history.clear()
        logger.info("[E2BMemory] 所有数据已清空")

    # ==================== 序列化 ====================

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "user_id": self.user_id,
            "temporary_session": (
                self._temporary_session.to_dict() if self._temporary_session else None
            ),
            "persistent_sandboxes": {
                name: session.to_dict() for name, session in self._persistent_sandboxes.items()
            },
            "execution_history": self.execution_history,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "E2BMemory":
        """从字典反序列化"""
        memory = cls(user_id=data.get("user_id"))

        if data.get("temporary_session"):
            memory._temporary_session = E2BSandboxSession.from_dict(data["temporary_session"])

        for name, session_data in data.get("persistent_sandboxes", {}).items():
            memory._persistent_sandboxes[name] = E2BSandboxSession.from_dict(session_data)

        memory.execution_history = data.get("execution_history", [])

        return memory

    def summary(self) -> str:
        """获取摘要信息"""
        return (
            f"E2BMemory(user_id={self.user_id}, "
            f"temporary={'yes' if self._temporary_session else 'no'}, "
            f"persistent_count={len(self._persistent_sandboxes)}, "
            f"executions={len(self.execution_history)})"
        )


def create_e2b_memory(user_id: Optional[str] = None) -> E2BMemory:
    """创建 E2BMemory 实例"""
    return E2BMemory(user_id=user_id)

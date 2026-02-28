# -*- coding: utf-8 -*-
"""
Nodes 通信协议定义

定义节点间通信的数据结构。
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class NodeCommand(Enum):
    """
    节点命令类型

    节点命令定义：
    - system.run: 执行 shell 命令
    - system.which: 检查可执行文件是否存在
    - system.notify: 发送系统通知
    - system.execApprovals.get: 获取当前执行审批策略
    - system.execApprovals.set: 更新执行审批策略（全量替换）
    - system.execApprovals.addRule: 添加单条审批规则（HITL 授权后使用）
    - camera.snap: 摄像头拍照
    - camera.list: 枚举可用摄像头
    - camera.clip: 摄像头录制短视频
    - screen.capture: 屏幕截图（支持多显示器、格式、质量）
    - screen.list: 枚举所有显示器信息
    - screen.record: 屏幕录制视频
    - location.get: 获取设备位置信息
    - canvas.present: 展示 WebView 窗口
    - canvas.hide: 隐藏 WebView 窗口
    - canvas.navigate: WebView 导航到 URL
    - canvas.eval: 在 WebView 中执行 JavaScript
    - canvas.snapshot: 获取 WebView 窗口快照（base64 图像）
    - canvas.a2ui.push: 向 Canvas 推送 A2UI JSONL 内容
    - canvas.a2ui.reset: 重置 Canvas A2UI 内容
    """

    SYSTEM_RUN = "system.run"
    SYSTEM_WHICH = "system.which"
    SYSTEM_NOTIFY = "system.notify"
    SYSTEM_EXEC_APPROVALS_GET = "system.execApprovals.get"
    SYSTEM_EXEC_APPROVALS_SET = "system.execApprovals.set"
    SYSTEM_EXEC_APPROVALS_ADD_RULE = "system.execApprovals.addRule"
    CAMERA_SNAP = "camera.snap"
    CAMERA_LIST = "camera.list"
    CAMERA_CLIP = "camera.clip"
    SCREEN_CAPTURE = "screen.capture"
    SCREEN_LIST = "screen.list"
    SCREEN_RECORD = "screen.record"
    LOCATION_GET = "location.get"
    CANVAS_PRESENT = "canvas.present"
    CANVAS_HIDE = "canvas.hide"
    CANVAS_NAVIGATE = "canvas.navigate"
    CANVAS_EVAL = "canvas.eval"
    CANVAS_SNAPSHOT = "canvas.snapshot"
    CANVAS_A2UI_PUSH = "canvas.a2ui.push"
    CANVAS_A2UI_RESET = "canvas.a2ui.reset"
    BROWSER_PROXY = "browser.proxy"


class NodeStatus(Enum):
    """节点状态"""

    UNKNOWN = "unknown"
    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"
    ERROR = "error"


@dataclass
class NodeInfo:
    """节点信息"""

    node_id: str
    display_name: str
    platform: str  # darwin, win32, linux
    status: NodeStatus = NodeStatus.UNKNOWN
    capabilities: List[str] = field(default_factory=list)
    last_seen: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "display_name": self.display_name,
            "platform": self.platform,
            "status": self.status.value,
            "capabilities": self.capabilities,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
        }


@dataclass
class NodeInvokeRequest:
    """
    节点调用请求

    封装节点调用的请求参数
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    command: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    timeout_ms: int = 30000
    node_id: str = "local"  # 默认本地节点

    @classmethod
    def create(
        cls,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        timeout_ms: int = 30000,
        node_id: str = "local",
    ) -> "NodeInvokeRequest":
        """创建调用请求"""
        return cls(
            command=command,
            params=params or {},
            timeout_ms=timeout_ms,
            node_id=node_id,
        )


@dataclass
class NodeInvokeResponse:
    """
    节点调用响应

    封装节点调用的响应结果
    """

    id: str
    ok: bool
    payload: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    elapsed_ms: Optional[int] = None

    @classmethod
    def success(
        cls, request_id: str, payload: Dict[str, Any], elapsed_ms: int = 0
    ) -> "NodeInvokeResponse":
        """创建成功响应"""
        return cls(id=request_id, ok=True, payload=payload, elapsed_ms=elapsed_ms)

    @classmethod
    def failure(
        cls,
        request_id: str,
        error: str,
        elapsed_ms: int = 0,
        error_code: Optional[str] = None,
    ) -> "NodeInvokeResponse":
        """创建失败响应"""
        return cls(
            id=request_id, ok=False, error=error,
            error_code=error_code, elapsed_ms=elapsed_ms,
        )

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "id": self.id,
            "ok": self.ok,
        }
        if self.payload is not None:
            result["payload"] = self.payload
        if self.error is not None:
            result["error"] = self.error
        if self.error_code is not None:
            result["error_code"] = self.error_code
        if self.elapsed_ms is not None:
            result["elapsed_ms"] = self.elapsed_ms
        return result


@dataclass
class ShellResult:
    """
    Shell 命令执行结果

    Shell 命令执行的标准返回结构
    """

    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    timed_out: bool = False
    elapsed_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "elapsed_ms": self.elapsed_ms,
        }

    def to_payload(self) -> Dict[str, Any]:
        """转换为 NodeInvokeResponse 的 payload 格式"""
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
        }


@dataclass
class NotifyParams:
    """系统通知参数"""

    title: str
    message: str
    subtitle: Optional[str] = None
    sound: bool = True
    category: Optional[str] = None  # urgent/reminder/info/error/build 等，用于通知分类过滤


@dataclass
class SystemRunParams:
    """
    system.run 命令参数

    system.run 命令的标准参数结构
    """

    command: List[str]
    cwd: Optional[str] = None
    env: Optional[Dict[str, str]] = None
    timeout_ms: int = 30000

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SystemRunParams":
        return cls(
            command=data.get("command", []),
            cwd=data.get("cwd"),
            env=data.get("env"),
            timeout_ms=data.get("timeout_ms", 30000),
        )

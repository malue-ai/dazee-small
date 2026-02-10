# -*- coding: utf-8 -*-
"""
Open System Preferences tool — directly open macOS/Windows settings panels.

When the Agent detects a permission issue (screen recording, accessibility, etc.),
it calls this tool to directly open the system settings panel for the user.

No text instructions, no "please go to settings" — just opens it.
"""

import logging
import os
import platform
from typing import Any, Dict, Optional

from core.nodes.manager import get_node_manager
from core.tool.types import ToolContext
from tools.base import BaseTool

logger = logging.getLogger(__name__)

# macOS: System Preferences URL schemes
_MACOS_PREF_URLS = {
    "screen_recording": "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
    "accessibility": "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
    "camera": "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera",
    "location": "x-apple.systempreferences:com.apple.preference.security?Privacy_LocationServices",
    "full_disk_access": "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles",
    "automation": "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation",
    "notifications": "x-apple.systempreferences:com.apple.preference.security?Privacy_Notifications",
}

# Windows: Settings URI schemes
_WINDOWS_SETTINGS_URIS = {
    "screen_recording": "ms-settings:privacy-graphicscaptureprogrammatic",
    "camera": "ms-settings:privacy-webcam",
    "location": "ms-settings:privacy-location",
    "notifications": "ms-settings:notifications",
    "apps": "ms-settings:appsfeatures",
}


class OpenSystemPreferencesTool(BaseTool):
    """
    Directly open OS settings panel for a specific permission.

    macOS: opens System Preferences to the exact privacy pane.
    Windows: opens Settings to the relevant privacy page.
    """

    def __init__(self, node_manager=None):
        self._node_manager = node_manager
        self._initialized = False

    @property
    def _node_manager_ref(self):
        if self._node_manager is None:
            self._node_manager = get_node_manager()
        return self._node_manager

    @property
    def name(self) -> str:
        return "open_system_preferences"

    @property
    def description(self) -> str:
        return """直接打开系统设置面板（macOS/Windows），让用户授权指定权限。

不要用文字告诉用户怎么操作，直接调用这个工具帮用户打开对应设置页面。

支持的权限类型：
- screen_recording: 屏幕录制权限（截屏、UI 自动化需要）
- accessibility: 辅助功能权限（peekaboo、AppleScript 需要）
- camera: 摄像头权限
- location: 位置权限
- full_disk_access: 完全磁盘访问权限（macOS）
- automation: 自动化权限（macOS，控制其他应用需要）
- notifications: 通知权限"""

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "permission": {
                    "type": "string",
                    "enum": [
                        "screen_recording",
                        "accessibility",
                        "camera",
                        "location",
                        "full_disk_access",
                        "automation",
                        "notifications",
                    ],
                    "description": "要打开的权限设置类型",
                },
            },
            "required": ["permission"],
        }

    async def execute(
        self, params: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> Any:
        perm_type = params.get("permission", "")
        if not perm_type:
            return {"success": False, "error": "缺少 permission 参数"}

        if not self._initialized:
            await self._node_manager_ref.start()
            self._initialized = True

        system = platform.system()

        if system == "Darwin":
            return await self._open_macos(perm_type)
        elif system == "Windows":
            return await self._open_windows(perm_type)
        else:
            return {
                "success": False,
                "error": f"当前系统 ({system}) 暂不支持自动打开设置",
            }

    async def _open_macos(self, perm_type: str) -> Dict[str, Any]:
        """Open macOS System Preferences to the specified privacy pane."""
        url = _MACOS_PREF_URLS.get(perm_type)
        if not url:
            return {
                "success": False,
                "error": f"macOS 不支持 '{perm_type}' 类型的设置面板",
            }

        try:
            response = await self._node_manager_ref.run_command(
                command=["open", url],
                node_id="local",
                timeout_ms=5000,
            )
            if response.ok:
                logger.info(f"已打开 macOS 系统设置: {perm_type}")
                return {
                    "success": True,
                    "action": f"已打开「系统设置 → 隐私与安全性 → {_perm_display_name(perm_type)}」",
                }
            else:
                return {"success": False, "error": "打开系统设置失败"}
        except Exception as e:
            logger.error(f"打开 macOS 系统设置失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _open_windows(self, perm_type: str) -> Dict[str, Any]:
        """Open Windows Settings to the specified privacy page."""
        uri = _WINDOWS_SETTINGS_URIS.get(perm_type)
        if not uri:
            return {
                "success": False,
                "error": f"Windows 不支持 '{perm_type}' 类型的设置面板",
            }

        try:
            response = await self._node_manager_ref.run_command(
                command=["cmd", "/c", "start", uri],
                node_id="local",
                timeout_ms=5000,
            )
            if response.ok:
                logger.info(f"已打开 Windows 设置: {perm_type}")
                return {
                    "success": True,
                    "action": f"已打开 Windows 设置 → {_perm_display_name(perm_type)}",
                }
            else:
                return {"success": False, "error": "打开系统设置失败"}
        except Exception as e:
            logger.error(f"打开 Windows 设置失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}


def _perm_display_name(perm_type: str) -> str:
    """Human-readable permission name in Chinese."""
    names = {
        "screen_recording": "屏幕录制",
        "accessibility": "辅助功能",
        "camera": "摄像头",
        "location": "位置服务",
        "full_disk_access": "完全磁盘访问",
        "automation": "自动化",
        "notifications": "通知",
    }
    return names.get(perm_type, perm_type)

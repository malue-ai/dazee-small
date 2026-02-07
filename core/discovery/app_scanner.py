"""
应用扫描器 - AppScanner

三平台：darwin (/Applications + brew)、win32 (registry + winget)、linux (dpkg + flatpak)。
"""

import platform
from pathlib import Path
from typing import Any, Dict, List

from logger import get_logger

logger = get_logger(__name__)


class AppScanner:
    """
    应用扫描器

    扫描当前系统已安装应用，用于能力匹配与提示词注入。
    """

    def __init__(self) -> None:
        self._os = platform.system().lower()

    def scan(self) -> List[Dict[str, Any]]:
        """
        扫描已安装应用

        Returns:
            [{"name", "path", "source"}, ...]
        """
        if self._os == "darwin":
            return self._scan_darwin()
        if self._os == "windows":
            return self._scan_win32()
        return self._scan_linux()

    def _scan_darwin(self) -> List[Dict[str, Any]]:
        """macOS: /Applications + brew list"""
        apps = []
        app_dir = Path("/Applications")
        if app_dir.exists():
            for p in app_dir.iterdir():
                if p.suffix == ".app":
                    apps.append({"name": p.stem, "path": str(p), "source": "applications"})
        return apps

    def _scan_win32(self) -> List[Dict[str, Any]]:
        """Windows: 占位"""
        return []

    def _scan_linux(self) -> List[Dict[str, Any]]:
        """Linux: 占位"""
        return []

    def get_capabilities(self, app_name: str) -> List[str]:
        """应用能力映射（占位）"""
        return []

    def find_app_for_task(self, task: str) -> List[str]:
        """为任务匹配已安装应用（占位）"""
        return []

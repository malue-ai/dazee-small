"""
应用扫描器 - AppScanner

三平台：darwin (/Applications + brew)、win32 (registry + winget)、linux (dpkg + flatpak)。
"""

import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

from logger import get_logger

logger = get_logger(__name__)


class AppScanner:
    """
    应用扫描器

    扫描当前系统已安装应用，用于能力匹配与提示词注入。
    """

    # Windows 注册表路径（Uninstall 键）
    _WIN_UNINSTALL_KEYS = [
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    ]

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
        apps: List[Dict[str, Any]] = []
        app_dir = Path("/Applications")
        if app_dir.exists():
            for p in app_dir.iterdir():
                if p.suffix == ".app":
                    apps.append({"name": p.stem, "path": str(p), "source": "applications"})
        return apps

    def _scan_win32(self) -> List[Dict[str, Any]]:
        """
        Windows: registry scanning + winget fallback.

        Uses winreg (stdlib on Windows) to read HKLM and HKCU Uninstall keys.
        Falls back to 'winget list' when winreg is unavailable.
        """
        apps: List[Dict[str, Any]] = []
        seen_names: set = set()

        # 1. Registry scanning (primary)
        apps.extend(self._scan_win32_registry(seen_names))

        # 2. Start Menu shortcuts (supplementary)
        apps.extend(self._scan_win32_start_menu(seen_names))

        # 3. winget fallback (if registry returned few results)
        if len(apps) < 5:
            apps.extend(self._scan_win32_winget(seen_names))

        return apps

    def _scan_win32_registry(self, seen: set) -> List[Dict[str, Any]]:
        """Scan Windows registry for installed applications."""
        apps: List[Dict[str, Any]] = []

        if sys.platform != "win32":
            return apps

        try:
            import winreg
        except ImportError:
            logger.debug("winreg not available (non-Windows platform)")
            return apps

        for root_key in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
            for subkey_path in self._WIN_UNINSTALL_KEYS:
                try:
                    with winreg.OpenKey(root_key, subkey_path) as key:
                        count = winreg.QueryInfoKey(key)[0]
                        for i in range(count):
                            try:
                                subkey_name = winreg.EnumKey(key, i)
                                with winreg.OpenKey(key, subkey_name) as subkey:
                                    app_info = self._read_registry_app(subkey)
                                    if app_info and app_info["name"] not in seen:
                                        seen.add(app_info["name"])
                                        apps.append(app_info)
                            except OSError:
                                continue
                except OSError:
                    continue

        return apps

    @staticmethod
    def _read_registry_app(subkey: Any) -> Dict[str, Any] | None:
        """Read a single app entry from registry subkey."""
        if sys.platform != "win32":
            return None

        import winreg

        try:
            name, _ = winreg.QueryValueEx(subkey, "DisplayName")
        except OSError:
            return None

        if not name or not name.strip():
            return None

        # Skip Windows updates / hotfixes
        name_lower = name.lower()
        if any(
            skip in name_lower
            for skip in ["update for", "hotfix for", "security update", "kb"]
        ):
            return None

        path = ""
        try:
            path, _ = winreg.QueryValueEx(subkey, "InstallLocation")
        except OSError:
            try:
                path, _ = winreg.QueryValueEx(subkey, "DisplayIcon")
            except OSError:
                pass

        return {
            "name": name.strip(),
            "path": (path or "").strip(),
            "source": "registry",
        }

    @staticmethod
    def _scan_win32_start_menu(seen: set) -> List[Dict[str, Any]]:
        """Scan Windows Start Menu shortcuts for applications."""
        import os

        apps: List[Dict[str, Any]] = []
        start_menu_dirs = [
            Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
            Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        ]

        for menu_dir in start_menu_dirs:
            if not menu_dir.exists():
                continue
            try:
                for p in menu_dir.rglob("*.lnk"):
                    name = p.stem
                    if name not in seen and not name.startswith("Uninstall"):
                        seen.add(name)
                        apps.append({
                            "name": name,
                            "path": str(p),
                            "source": "start_menu",
                        })
            except OSError:
                continue

        return apps

    @staticmethod
    def _scan_win32_winget(seen: set) -> List[Dict[str, Any]]:
        """Fallback: scan using 'winget list' command."""
        apps: List[Dict[str, Any]] = []
        try:
            result = subprocess.run(
                ["winget", "list", "--accept-source-agreements"],
                capture_output=True,
                text=True,
                timeout=15,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode != 0:
                return apps

            lines = result.stdout.strip().splitlines()
            # Skip header lines (first 2-3 lines are decorators)
            data_started = False
            for line in lines:
                if "---" in line:
                    data_started = True
                    continue
                if not data_started or not line.strip():
                    continue
                # winget list output is column-based; extract the first column
                parts = line.split()
                if parts:
                    name = " ".join(parts[:-2]) if len(parts) > 2 else parts[0]
                    name = name.strip()
                    if name and name not in seen:
                        seen.add(name)
                        apps.append({
                            "name": name,
                            "path": "",
                            "source": "winget",
                        })
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            logger.debug(f"winget scan skipped: {e}")

        return apps

    def _scan_linux(self) -> List[Dict[str, Any]]:
        """Linux: /usr/share/applications .desktop files"""
        apps: List[Dict[str, Any]] = []
        desktop_dirs = [
            Path("/usr/share/applications"),
            Path.home() / ".local" / "share" / "applications",
        ]
        seen: set = set()

        for desktop_dir in desktop_dirs:
            if not desktop_dir.exists():
                continue
            try:
                for p in desktop_dir.iterdir():
                    if p.suffix == ".desktop":
                        name = p.stem
                        if name not in seen:
                            seen.add(name)
                            apps.append({
                                "name": name,
                                "path": str(p),
                                "source": "desktop_entry",
                            })
            except OSError:
                continue

        return apps

    def get_capabilities(self, app_name: str) -> List[str]:
        """应用能力映射（占位）"""
        return []

    def find_app_for_task(self, task: str) -> List[str]:
        """为任务匹配已安装应用（占位）"""
        return []

"""
Subprocess environment sanitizer.

Provides a single entry point for building clean environment dicts
that isolate child processes from PyInstaller bundling artifacts and
other potentially harmful inherited variables.

All code that spawns subprocesses (ShellExecutor, browser.py,
runtime_context_builder.py, etc.) should use ``make_clean_env()``
instead of raw ``os.environ.copy()``.
"""

from __future__ import annotations

import os
import sys
from typing import Dict, List, Optional, Set

from logger import get_logger

logger = get_logger("utils.subprocess_env")

_IS_WIN32 = sys.platform == "win32"

# ── Always-blocked keys ──────────────────────────────────────────────

BLOCKED_KEYS: Set[str] = {
    "NODE_OPTIONS",
    "PYTHONHOME",
    "PYTHONPATH",
    "LD_PRELOAD",
}

BLOCKED_KEYS_WIN32: Set[str] = {
    "PSModulePath",
    "__PSLockdownPolicy",
}

BLOCKED_PREFIXES: List[str] = [
    "DYLD_",
    "LD_",
]

# ── PyInstaller-specific keys (frozen mode only) ─────────────────────

_PYINSTALLER_KEYS: Set[str] = {
    "_MEIPASS", "_MEIPASS2", "_PYI_ARCHIVE_FILE", "_PYI_SPLASH_IPC",
    "VIRTUAL_ENV",
    "TCL_LIBRARY", "TK_LIBRARY",
    "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE",
}

_PYINSTALLER_PREFIXES: List[str] = ["_PYI_", "_MEI"]

# ── Fragments that identify PyInstaller paths inside PATH ────────────

_PYINSTALLER_PATH_FRAGMENTS = ("_internal", "_MEIPASS", "Contents/MacOS")


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def make_clean_env(
    extra_env: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Build a sanitized env dict for subprocess calls.

    Frozen mode (PyInstaller):
      - Removes all ``_MEI*`` / ``_PYI_*`` variables
      - Removes ``VIRTUAL_ENV``, ``TCL_LIBRARY``, ``SSL_CERT_FILE``, etc.
      - Strips PATH segments that reference ``_internal`` / ``_MEIPASS``
      - Injects ``PYTHONSAFEPATH=1`` and ``PYTHONDONTWRITEBYTECODE=1``

    Development mode (venv / system Python):
      - Prepends the interpreter's bin dir to PATH so child ``python3``
        resolves to the same Python running the backend.

    Both modes:
      - Removes ``PYTHONPATH``, ``PYTHONHOME``, ``LD_PRELOAD`` and
        platform-specific dangerous keys.
      - Merges caller-supplied *extra_env* (after filtering).
    """
    sanitized = dict(os.environ)

    if is_frozen():
        _clean_pyinstaller_vars(sanitized)
        _clean_path_segments(sanitized)
        sanitized["PYTHONSAFEPATH"] = "1"
        sanitized["PYTHONDONTWRITEBYTECODE"] = "1"
    else:
        _prepend_python_bin(sanitized)

    _remove_blocked(sanitized)

    if extra_env:
        _merge_extra(sanitized, extra_env)

    return sanitized


# ── Internals ────────────────────────────────────────────────────────


def _clean_pyinstaller_vars(env: Dict[str, str]) -> None:
    for key in list(env.keys()):
        if key in _PYINSTALLER_KEYS:
            del env[key]
            continue
        for prefix in _PYINSTALLER_PREFIXES:
            if key.startswith(prefix):
                del env[key]
                break


def _clean_path_segments(env: Dict[str, str]) -> None:
    """Remove PATH entries that point inside PyInstaller bundles."""
    raw_path = env.get("PATH", "")
    if not raw_path:
        return

    cleaned = []
    for segment in raw_path.split(os.pathsep):
        if any(frag in segment for frag in _PYINSTALLER_PATH_FRAGMENTS):
            continue
        cleaned.append(segment)

    env["PATH"] = os.pathsep.join(cleaned)


def _prepend_python_bin(env: Dict[str, str]) -> None:
    python_bin_dir = os.path.dirname(os.path.abspath(sys.executable))
    current_path = env.get("PATH", "")
    if python_bin_dir not in current_path.split(os.pathsep):
        env["PATH"] = python_bin_dir + os.pathsep + current_path


def _remove_blocked(env: Dict[str, str]) -> None:
    blocked = BLOCKED_KEYS | (BLOCKED_KEYS_WIN32 if _IS_WIN32 else set())

    for key in list(env.keys()):
        if key in blocked:
            del env[key]
            continue
        for prefix in BLOCKED_PREFIXES:
            if key.startswith(prefix):
                del env[key]
                break


def _merge_extra(env: Dict[str, str], extra: Dict[str, str]) -> None:
    blocked = BLOCKED_KEYS | (BLOCKED_KEYS_WIN32 if _IS_WIN32 else set())
    for key, value in extra.items():
        if key in blocked:
            logger.warning(f"跳过阻止的环境变量: {key}")
            continue
        skip = False
        for prefix in BLOCKED_PREFIXES:
            if key.startswith(prefix):
                logger.warning(f"跳过阻止的环境变量: {key}")
                skip = True
                break
        if not skip:
            env[key] = value


# ── Python capability detection ──────────────────────────────────────

async def detect_python_info(
    shell_execute=None,
) -> Dict[str, object]:
    """Detect the system Python available to subprocesses.

    Returns a dict like::

        {"available": True, "version": "3.12.1", "path": "/usr/bin/python3",
         "has_safe_path": True}

    Uses *shell_execute* (an async callable matching
    ``ShellExecutor.execute``) if provided; otherwise falls back to a
    lightweight subprocess call with a clean env.
    """
    result: Dict[str, object] = {
        "available": False,
        "version": "",
        "path": "",
        "has_safe_path": False,
    }

    try:
        if shell_execute:
            sr = await shell_execute(
                ["python3", "--version"],
                timeout=5.0,
            )
            stdout = getattr(sr, "stdout", "") or ""
            stderr = getattr(sr, "stderr", "") or ""
            exit_code = getattr(sr, "exit_code", -1)
        else:
            import asyncio

            clean = make_clean_env()
            proc = await asyncio.create_subprocess_exec(
                "python3", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=clean,
                cwd=os.path.expanduser("~"),
            )
            raw_out, raw_err = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            stdout = raw_out.decode(errors="replace").strip()
            stderr = raw_err.decode(errors="replace").strip()
            exit_code = proc.returncode

        version_line = stdout or stderr
        if exit_code == 0 and version_line:
            import re
            m = re.search(r"(\d+\.\d+\.\d+)", version_line)
            if m:
                ver = m.group(1)
                major, minor, _ = (int(x) for x in ver.split("."))
                result["available"] = True
                result["version"] = ver
                result["has_safe_path"] = (major, minor) >= (3, 11)

                if shell_execute:
                    wr = await shell_execute(
                        ["which", "python3"] if not _IS_WIN32 else ["where", "python3"],
                        timeout=3.0,
                    )
                    w_out = getattr(wr, "stdout", "") or ""
                    result["path"] = w_out.strip().split("\n")[0]
    except Exception as exc:
        logger.debug(f"Python 探测失败: {exc}")

    return result


def python_info_to_prompt(info: Dict[str, object]) -> str:
    """Convert detect_python_info() result to a short LLM-facing string."""
    if not info.get("available"):
        return (
            "[系统环境] 用户系统无 Python，禁止使用 python3/python 命令。"
            "数据处理请使用 awk、sed、sort、jq、find 等系统命令。"
        )

    ver = str(info.get("version", ""))

    parts = [f"[系统环境] 用户 Python {ver}"]

    major, minor = 0, 0
    try:
        major, minor = (int(x) for x in ver.split(".")[:2])
    except (ValueError, TypeError):
        pass

    if (major, minor) < (3, 10):
        parts.append(
            "（较旧，优先使用 shell 命令；若必须用 Python，避免 match/case 等 3.10+ 语法）"
        )
    else:
        parts.append("（可正常使用）")

    return "".join(parts)

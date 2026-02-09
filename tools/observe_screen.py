# -*- coding: utf-8 -*-
"""
Observe Screen tool - understand screen content via peekaboo + local OCR.

Architecture:
  1. peekaboo see (primary) → UI elements with IDs, window info (~1.5s, local)
  2. macOS Vision OCR (supplement) → text content not captured by peekaboo (~0.7s, local)
  Both run in parallel, results merged.

Design principles:
  1. Tool 只做本地工作，不调 LLM（调度是主 Agent 的职责）
  2. peekaboo 优先：行业级屏幕自动化工具，返回可操作的元素 ID
  3. 上下文工程：只放文字进上下文，零图片 token
  4. 中间结果不持久化：截图是临时文件

后续交互（由主 Agent 调度 skills 组合）：
  - peekaboo click --on <ID>  → 点击元素
  - peekaboo type "text" --app <app> → 输入文字
  - peekaboo see --analyze "问题" → peekaboo 内置 AI 分析（深度理解）
"""

import asyncio
import json
import logging
import os
import tempfile
from typing import Any, Dict, Optional

from core.nodes.manager import get_node_manager
from core.tool.types import ToolContext
from tools.base import BaseTool
from utils.file_handler import FileHandler

logger = logging.getLogger(__name__)


# ============================================================
# peekaboo see (primary: UI elements + window info)
# ============================================================

async def _check_peekaboo_available(node_manager) -> bool:
    """
    Check if peekaboo CLI is available on this system.

    Caches the result for the process lifetime.
    """
    if hasattr(_check_peekaboo_available, "_cached"):
        return _check_peekaboo_available._cached

    try:
        response = await node_manager.run_command(
            command=["which", "peekaboo"], node_id="local", timeout_ms=5000,
        )
        available = response.ok
    except Exception:
        available = False

    _check_peekaboo_available._cached = available
    if not available:
        logger.info("peekaboo 未安装，将使用 screencapture + OCR 降级模式")
    return available


async def _peekaboo_see(node_manager, app: str = "", window_title: str = "") -> Optional[Dict]:
    """
    Run peekaboo see to capture UI element map.

    Returns parsed data dict or None on failure.
    ~1.5s, local, returns element IDs for subsequent click/type.
    """
    if not await _check_peekaboo_available(node_manager):
        return None

    try:
        cmd = ["peekaboo", "see", "--json"]
        if app:
            cmd.extend(["--app", app])
        if window_title:
            cmd.extend(["--window-title", window_title])

        response = await node_manager.run_command(
            command=cmd, node_id="local", timeout_ms=15000,
        )

        if not response.ok:
            logger.debug(f"peekaboo see failed: {response.error}")
            return None

        payload = response.payload or {}
        stdout = payload.get("stdout", "")
        if not stdout:
            return None

        return json.loads(stdout).get("data", {})

    except Exception as e:
        logger.debug(f"peekaboo see error: {e}")
        return None


def _format_peekaboo_result(data: Dict) -> str:
    """
    Format peekaboo see output into concise text for the agent.

    Extracts window title and actionable UI elements with IDs.
    """
    lines = []

    window_title = data.get("window_title", "")
    if window_title:
        lines.append(f"窗口: {window_title}")

    elements = data.get("ui_elements", [])
    if not elements:
        return "\n".join(lines) if lines else ""

    # Group elements by role for readability
    USEFUL_ROLES = {
        "button", "textField", "link", "menuItem", "staticText",
        "cell", "checkBox", "radioButton", "popUpButton", "comboBox",
        "tab", "textArea", "image",
    }

    actionable = [
        e for e in elements
        if e.get("title") and e.get("role") in USEFUL_ROLES
    ]

    if actionable:
        lines.append(f"\nUI 元素 ({len(actionable)} 个可交互):")
        for e in actionable[:60]:
            eid = e.get("id", "")
            role = e.get("role", "")
            title = e.get("title", "")
            # Truncate long titles
            if len(title) > 80:
                title = title[:77] + "..."
            lines.append(f"  [{eid}] {role}: {title}")

        if len(actionable) > 60:
            lines.append(f"  ...还有 {len(actionable) - 60} 个元素")

    return "\n".join(lines)


# ============================================================
# macOS Vision OCR (supplement: text not in UI elements)
# ============================================================

async def _ocr_with_vision(image_path: str) -> Optional[str]:
    """
    macOS native Vision framework OCR.

    ~700ms, free, supports zh-Hans + en.
    Supplements peekaboo by capturing text in images/non-standard UI.
    """
    def _run_ocr() -> Optional[str]:
        try:
            import objc  # noqa: F401
            import Vision
            from Foundation import NSURL
            from Quartz import (
                CGImageSourceCreateImageAtIndex,
                CGImageSourceCreateWithURL,
            )

            img_url = NSURL.fileURLWithPath_(image_path)
            img_source = CGImageSourceCreateWithURL(img_url, None)
            if img_source is None:
                return None

            cg_image = CGImageSourceCreateImageAtIndex(img_source, 0, None)
            if cg_image is None:
                return None

            request = Vision.VNRecognizeTextRequest.alloc().init()
            request.setRecognitionLanguages_(["zh-Hans", "en"])
            request.setRecognitionLevel_(1)  # Accurate

            handler = (
                Vision.VNImageRequestHandler.alloc()
                .initWithCGImage_options_(cg_image, {})
            )
            success, error = handler.performRequests_error_([request], None)

            if not success:
                logger.warning(f"Vision OCR failed: {error}")
                return None

            lines = []
            for obs in request.results():
                top = obs.topCandidates_(1)
                if top:
                    lines.append(top[0].string())

            return "\n".join(lines) if lines else None

        except ImportError:
            logger.debug("pyobjc not available, Vision OCR skipped")
            return None
        except Exception as e:
            logger.warning(f"Vision OCR error: {e}")
            return None

    return await asyncio.to_thread(_run_ocr)


# ============================================================
# Tool
# ============================================================

class ObserveScreenTool(BaseTool):
    """
    Capture screen via peekaboo see + local OCR. No LLM calls.
    """

    def __init__(self, node_manager=None):
        self._node_manager = node_manager
        self._initialized = False
        self._file_handler = FileHandler(auto_compress=True)

    @property
    def _node_manager_ref(self):
        if self._node_manager is None:
            self._node_manager = get_node_manager()
        return self._node_manager

    @property
    def name(self) -> str:
        return "observe_screen"

    @property
    def description(self) -> str:
        return """截取屏幕/应用窗口，返回 UI 元素列表和 OCR 文字。

返回内容包括：
- 窗口标题
- 可交互 UI 元素（按钮、输入框、链接等）及其元素 ID
- 屏幕上的文字内容（OCR）

元素 ID 用于后续 peekaboo 操作（禁止 raw osascript）：
- peekaboo click --on <ID> --app <app> → 点击元素
- peekaboo type "text" --app <app> → 输入 ASCII
- peekaboo paste "中文" --app <app> → 输入中文/CJK（必须用 paste）
- peekaboo hotkey --keys cmd+k --app <app> → 快捷键

参数：
- app: 可选，应用名称（如 Lark、Safari）
- window_title: 可选，窗口标题关键词
- mode: screen / window / frontmost
- description: 可选，说明截屏目的

如需更深度的界面理解，可用 peekaboo see --analyze "问题"。"""

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "app": {
                    "type": "string",
                    "description": "应用名称（如 Lark、Safari）",
                },
                "window_title": {
                    "type": "string",
                    "description": "窗口标题关键词",
                },
                "mode": {
                    "type": "string",
                    "enum": ["screen", "window", "frontmost"],
                    "description": "截屏范围",
                    "default": "frontmost",
                },
                "description": {
                    "type": "string",
                    "description": "简短说明本次截屏目的",
                },
            },
            "required": [],
        }

    async def execute(
        self, params: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> Any:
        if os.name != "posix" or not hasattr(os, "uname"):
            return {"success": False, "error": "仅支持 macOS"}
        try:
            if os.uname().sysname != "Darwin":
                return {"success": False, "error": "仅支持 macOS"}
        except Exception:
            return {"success": False, "error": "仅支持 macOS"}

        if not self._initialized:
            await self._node_manager_ref.start()
            self._initialized = True

        app = (params.get("app") or "").strip()
        window_title = (params.get("window_title") or "").strip()
        description = (params.get("description") or "").strip()

        # === Parallel: peekaboo see + screenshot for OCR ===
        # peekaboo see handles its own screenshot internally
        # We take a separate screenshot for OCR (peekaboo doesn't expose OCR)
        fd, tmp_path = tempfile.mkstemp(suffix=".png", prefix="observe_screen_")
        os.close(fd)

        try:
            has_peekaboo = await _check_peekaboo_available(self._node_manager_ref)

            # Build screenshot command (for OCR only)
            screenshot_taken = False

            if has_peekaboo and (app or window_title):
                # peekaboo available: use it for window-specific capture
                peekaboo_mode = "window" if app else "frontmost"
                screenshot_cmd = [
                    "peekaboo", "image",
                    "--mode", peekaboo_mode,
                    "--path", tmp_path,
                    "--format", "png",
                ]
                if app:
                    screenshot_cmd.extend(["--app", app])
                if window_title:
                    screenshot_cmd.extend(["--window-title", window_title])

                resp = await self._node_manager_ref.run_command(
                    command=screenshot_cmd, node_id="local", timeout_ms=15000,
                )
                screenshot_taken = resp.ok and os.path.isfile(tmp_path) and os.path.getsize(tmp_path) > 0

            # Fallback: screencapture (always available on macOS)
            if not screenshot_taken:
                screenshot_cmd = ["screencapture", "-x", tmp_path]
                await self._node_manager_ref.run_command(
                    command=screenshot_cmd, node_id="local", timeout_ms=15000,
                )

            # Run peekaboo see + OCR in parallel
            see_task = _peekaboo_see(self._node_manager_ref, app, window_title)

            has_screenshot = os.path.isfile(tmp_path) and os.path.getsize(tmp_path) > 0
            ocr_task = _ocr_with_vision(tmp_path) if has_screenshot else asyncio.sleep(0)

            see_data, ocr_text = await asyncio.gather(see_task, ocr_task)

            # === Build result ===
            result: Dict[str, Any] = {"success": True}

            # peekaboo see result (primary)
            if see_data:
                formatted = _format_peekaboo_result(see_data)
                if formatted:
                    result["ui"] = formatted

            # OCR text (supplement → primary when peekaboo unavailable)
            if isinstance(ocr_text, str) and len(ocr_text.strip()) > 20:
                if len(ocr_text) > 3000:
                    ocr_text = ocr_text[:3000] + "\n...(已截断)"
                result["ocr_text"] = ocr_text

            # Hints when both sources are thin
            if "ui" not in result and "ocr_text" not in result:
                result["screen_text"] = "(未能获取界面信息)"
                if not has_peekaboo:
                    result["hint"] = (
                        "peekaboo 未安装，screencapture 已截取全屏但 OCR 未提取到文字。"
                        "建议安装 peekaboo: brew install nicklama/tap/peekaboo"
                    )
                else:
                    result["hint"] = (
                        "可尝试: peekaboo see --app <应用名> --analyze '描述你想了解的内容'"
                    )

            if description:
                result["purpose"] = description

            return result

        except Exception as e:
            logger.error(f"observe_screen failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except Exception:
                pass

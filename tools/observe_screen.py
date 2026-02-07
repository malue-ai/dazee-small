# -*- coding: utf-8 -*-
"""
Observe Screen tool - capture screenshot and return as multimodal content for LLM.

Returns a list of content blocks (text + image) so the agent can "see" the screen.
Used with the multimodal tool_result pipeline.
"""

import logging
import os
import tempfile
from typing import Any, Dict, List, Optional

from core.nodes.manager import get_node_manager
from tools.base import BaseTool
from core.tool.types import ToolContext
from utils.file_handler import FileHandler

logger = logging.getLogger(__name__)


class ObserveScreenTool(BaseTool):
    """
    Capture screen or app window and return screenshot as image content block.

    On success returns a list of content blocks (text + image) for multimodal
    tool_result; on failure returns a dict for JSON serialization.
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
        return """截取当前屏幕或指定应用窗口的截图，并将截图内容返回给模型以便理解屏幕内容。

适用场景：
- 查看桌面/某个应用当前界面（如飞书群聊、浏览器）
- 在群聊或窗口中查找消息、附件、联系人
- 根据用户描述定位屏幕上的信息

参数：
- app: 可选，应用名称（如 Lark、Safari）
- window_title: 可选，窗口标题关键词
- mode: screen（全屏）/ window（窗口）/ frontmost（当前前台窗口）
- description: 可选，简短说明本次截屏目的，便于模型理解上下文

成功时返回截图图像，模型可直接“看到”屏幕内容并据此决策下一步操作。"""

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "app": {
                    "type": "string",
                    "description": "应用名称（如 Lark、Safari），与 window_title 配合可精确定位窗口",
                },
                "window_title": {
                    "type": "string",
                    "description": "窗口标题关键词，用于匹配目标窗口",
                },
                "mode": {
                    "type": "string",
                    "enum": ["screen", "window", "frontmost"],
                    "description": "截屏范围：screen=全屏，window=指定窗口，frontmost=当前前台窗口",
                    "default": "screen",
                },
                "description": {
                    "type": "string",
                    "description": "简短说明本次截屏目的（如：查看飞书群聊中刘灵分享的简历），供模型理解上下文",
                },
            },
            "required": [],
        }

    async def execute(
        self, params: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> Any:
        """
        Execute screenshot and return multimodal content blocks or error dict.

        Returns:
            On success: list of content blocks [{"type":"text",...}, {"type":"image",...}]
            On failure: dict with success=False, error=...
        """
        if os.name != "posix" or not hasattr(os, "uname"):
            return {"success": False, "error": "observe_screen 仅支持 macOS/Linux"}
        try:
            uname = os.uname()
            if getattr(uname, "sysname", "") != "Darwin":
                return {"success": False, "error": "observe_screen 当前仅支持 macOS"}
        except Exception:
            return {"success": False, "error": "observe_screen 当前仅支持 macOS"}

        if not self._initialized:
            await self._node_manager_ref.start()
            self._initialized = True

        app = (params.get("app") or "").strip()
        window_title = (params.get("window_title") or "").strip()
        mode = params.get("mode") or "screen"
        description = (params.get("description") or "").strip()

        fd, path = tempfile.mkstemp(suffix=".png", prefix="observe_screen_")
        os.close(fd)
        try:
            use_peekaboo = bool(app or window_title or mode == "frontmost")
            if use_peekaboo:
                peekaboo_mode = "frontmost" if mode == "frontmost" else "window"
                cmd = [
                    "peekaboo",
                    "image",
                    "--mode", peekaboo_mode,
                    "--path", path,
                    "--format", "png",
                ]
                if app:
                    cmd.extend(["--app", app])
                if window_title:
                    cmd.extend(["--window-title", window_title])
            else:
                cmd = ["screencapture", path]
                if mode == "window":
                    cmd.insert(1, "-w")

            response = await self._node_manager_ref.run_command(
                command=cmd,
                node_id="local",
                timeout_ms=15000,
            )

            if not response.ok:
                return {"success": False, "error": response.error or "截屏命令执行失败"}

            if not os.path.isfile(path) or os.path.getsize(path) == 0:
                return {"success": False, "error": "截屏未生成有效文件"}

            encoded = await self._file_handler.encode_image_to_base64(path, use_cache=False)
            if not encoded:
                return {"success": False, "error": "截图编码失败（可能格式或大小不符合要求）"}

            image_data, media_type = encoded
            try:
                size_info = f"{os.path.getsize(path) // 1024}KB"
            except Exception:
                size_info = ""

            caption = "已截取"
            if app:
                caption += f" 应用 {app}"
            if window_title:
                caption += f" 窗口标题含「{window_title}」"
            caption += " 的屏幕截图"
            if size_info:
                caption += f" ({size_info})"
            if description:
                caption += f"。目的：{description}"

            blocks: List[Dict[str, Any]] = [
                {"type": "text", "text": caption},
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": image_data},
                },
            ]
            return blocks
        except Exception as e:
            logger.error(f"observe_screen 执行失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
        finally:
            try:
                if os.path.exists(path):
                    os.unlink(path)
            except Exception as e:
                logger.debug(f"清理临时文件失败: {e}")
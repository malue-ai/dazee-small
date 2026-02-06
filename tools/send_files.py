"""
send_files 工具 - 发送文件信息到前端

用于在 Agent 回复中包含文件时，通过 SSE 事件返回结构化的文件数据。
前端会根据 files 类型的 delta 事件渲染文件列表，支持预览和下载。

配置说明：
- input_schema 在 config/capabilities.yaml 中定义
- 运营可直接修改 YAML 调整参数，无需改代码
"""

from pathlib import Path
from typing import Any, Dict, List

from core.tool.types import BaseTool, ToolContext
from logger import get_logger

logger = get_logger(__name__)


class SendFilesTool(BaseTool):
    """
    发送文件信息工具（input_schema 由 capabilities.yaml 定义）

    将文件信息结构化后发送给前端，前端会渲染为可下载的文件列表。
    """

    name = "send_files"

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        """
        执行工具 - 返回文件信息

        Args:
            params: 工具输入参数
                - files: 文件列表，每个文件必须包含 name 和 url
            context: 工具执行上下文

        Returns:
            包含文件信息的结果
        """
        # 从 params 提取参数
        files = params.get("files", [])

        if not files:
            return {"success": False, "error": "文件列表不能为空"}

        # 验证并处理文件信息
        validated_files = []
        errors = []

        for file_info in files:
            # 必填字段检查
            if not file_info.get("name"):
                logger.warning("文件缺少 name 字段，跳过")
                continue

            if not file_info.get("url"):
                errors.append(f"文件 {file_info.get('name')} 缺少 url")
                continue

            file_name = file_info["name"]

            # 构建标准化的文件信息
            validated_file = {
                "name": file_name,
                "type": file_info.get("type") or self._extract_file_type(file_name),
                "url": file_info["url"],
            }

            # 可选字段
            if file_info.get("size"):
                validated_file["size"] = file_info["size"]
            if file_info.get("thumbnail"):
                validated_file["thumbnail"] = file_info["thumbnail"]
            if file_info.get("description"):
                validated_file["description"] = file_info["description"]

            validated_files.append(validated_file)

        if not validated_files:
            return {
                "success": False,
                "error": (
                    f"没有有效的文件信息。错误: {'; '.join(errors)}"
                    if errors
                    else "没有有效的文件信息"
                ),
            }

        logger.info(f"📁 send_files 工具: 发送 {len(validated_files)} 个文件")

        result = {"success": True, "files": validated_files}

        # 如果有部分文件处理失败，也返回警告
        if errors:
            result["warnings"] = errors

        return result

    def _extract_file_type(self, filename: str) -> str:
        """
        从文件名中提取文件类型

        Args:
            filename: 文件名

        Returns:
            文件扩展名（不含点号）
        """
        if "." in filename:
            return filename.rsplit(".", 1)[-1].lower()
        return "unknown"


# 工具实例（用于 ToolExecutor 加载）
send_files_tool = SendFilesTool()

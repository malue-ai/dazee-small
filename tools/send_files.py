"""
send_files 工具 - 发送文件信息到前端

用于在 Agent 回复中包含文件时，通过 SSE 事件返回结构化的文件数据。
前端会根据 files 类型的 delta 事件渲染文件列表，支持预览和下载。

使用场景：
- 工具调用返回了文件 URL（如 PPT、文档、图片等）
- 需要在回复中向用户展示可下载的文件
- 沙盒文件上传后返回的 URL

注意：
- 文件 URL 必须是可访问的链接
- 沙盒文件请先使用 sandbox_upload_file 工具上传到 S3 获取 URL
"""

from pathlib import Path
from typing import Dict, Any, List

from logger import get_logger

logger = get_logger(__name__)


class SendFilesTool:
    """
    发送文件信息工具
    
    将文件信息结构化后发送给前端，前端会渲染为可下载的文件列表。
    
    FilesData 格式：
    {
        "files": [
            {
                "name": "报告.pptx",
                "type": "pptx",
                "url": "https://...",
                "size": 1024000,        # 可选
                "thumbnail": "https://...",  # 可选
                "description": "AI技术分享"  # 可选
            }
        ]
    }
    """
    
    @property
    def name(self) -> str:
        return "send_files"
    
    @property
    def description(self) -> str:
        return """发送文件信息到前端，用于展示可下载的文件列表。

使用场景：
- 当工具调用返回了文件 URL（如 PPT、Word、Excel、图片等）
- 当 sandbox_upload_file 工具上传文件后返回了 URL
- 需要在回复中向用户展示可下载/可预览的文件

示例：
{
    "files": [
        {
            "name": "AI技术分享.pptx",
            "type": "pptx",
            "url": "https://example.com/files/ai_tech.pptx",
            "description": "AI 技术分享演示文稿"
        }
    ]
}

注意：
- url 必须是真实可访问的链接
- 沙盒中的文件请先使用 sandbox_upload_file 工具上传到 S3
- type 可选，会根据文件名自动推断"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "files": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "文件名（包含扩展名）"
                            },
                            "type": {
                                "type": "string",
                                "description": "文件类型/扩展名（如 pptx, docx, xlsx, pdf, png）"
                            },
                            "url": {
                                "type": "string",
                                "description": "文件下载链接（必填）"
                            },
                            "size": {
                                "type": "integer",
                                "description": "文件大小（字节，可选）"
                            },
                            "thumbnail": {
                                "type": "string",
                                "description": "文件预览缩略图URL（可选）"
                            },
                            "description": {
                                "type": "string",
                                "description": "文件描述（可选）"
                            }
                        },
                        "required": ["name", "url"]
                    },
                    "description": "文件列表"
                }
            },
            "required": ["files"]
        }
    
    async def execute(self, files: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        执行工具 - 返回文件信息
        
        Args:
            files: 文件列表，每个文件必须包含 name 和 url
            
        Returns:
            包含文件信息的结果
        """
        if not files:
            return {
                "success": False,
                "error": "文件列表不能为空"
            }
        
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
                "url": file_info["url"]
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
                "error": f"没有有效的文件信息。错误: {'; '.join(errors)}" if errors else "没有有效的文件信息"
            }
        
        logger.info(f"📁 send_files 工具: 发送 {len(validated_files)} 个文件")
        
        result = {
            "success": True,
            "files": validated_files
        }
        
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

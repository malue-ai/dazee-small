"""
send_files 工具 - 发送文件信息到前端

用于在 Agent 回复中包含文件时，通过 SSE 事件返回结构化的文件数据。
前端会根据 files 类型的 delta 事件渲染文件列表，支持预览和下载。

使用场景：
- 工具调用返回了文件 URL（如 PPT、文档、图片等）
- 需要在回复中向用户展示可下载的文件
- 【新增】沙盒中生成的文件（如清洗后的 Excel、生成的图片等）

支持两种模式：
1. URL 模式：直接发送已有的文件 URL
2. 沙盒模式：从沙盒读取文件 → 上传 S3 → 返回预签名 URL

注意：
- 沙盒文件会自动上传到 S3 持久化存储
- S3 预签名 URL 有效期 24 小时
"""

import hashlib
from datetime import datetime
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

支持两种模式：
1. URL 模式：直接发送已有的文件 URL
2. 沙盒模式：从沙盒读取文件，自动上传到 S3 后发送

使用场景：
- 当工具调用返回了文件 URL（如 PPT、Word、Excel、图片等）
- 当在沙盒中生成了文件（如清洗后的 Excel、生成的图片等）
- 需要在回复中向用户展示可下载/可预览的文件

示例1 - URL 模式：
{
    "files": [
        {
            "name": "AI技术分享.pptx",
            "type": "pptx",
            "url": "https://example.com/files/ai_tech.pptx"
        }
    ]
}

示例2 - 沙盒模式（自动上传 S3）：
{
    "files": [
        {
            "name": "清洗后的数据.xlsx",
            "sandbox_path": "/home/user/output.xlsx",
            "conversation_id": "conv_123",
            "description": "已清洗完成的数据文件"
        }
    ]
}

注意：
- URL 模式：url 必须是真实的可访问链接
- 沙盒模式：sandbox_path + conversation_id 必填，文件会自动上传到 S3
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
                                "description": "文件下载链接（与 sandbox_path 二选一）"
                            },
                            "sandbox_path": {
                                "type": "string",
                                "description": "沙盒中的文件路径（如 /home/user/output.xlsx），会自动上传到 S3"
                            },
                            "conversation_id": {
                                "type": "string",
                                "description": "对话 ID（使用 sandbox_path 时必填）"
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
                        "required": ["name"]
                    },
                    "description": "文件列表（每个文件需要 url 或 sandbox_path 其中之一）"
                }
            },
            "required": ["files"]
        }
    
    async def execute(self, files: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        执行工具 - 返回文件信息
        
        支持两种模式：
        1. URL 模式：直接返回文件 URL
        2. 沙盒模式：从沙盒读取文件 → 上传 S3 → 返回预签名 URL
        
        Args:
            files: 文件列表
            
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
            
            file_name = file_info["name"]
            sandbox_path = file_info.get("sandbox_path")
            url = file_info.get("url")
            conversation_id = file_info.get("conversation_id")
            
            # 检查是沙盒模式还是 URL 模式
            if sandbox_path:
                # 沙盒模式：需要 conversation_id
                if not conversation_id:
                    errors.append(f"文件 {file_name} 使用沙盒模式但缺少 conversation_id")
                    continue
                
                # 从沙盒读取并上传到 S3
                try:
                    upload_result = await self._upload_sandbox_file_to_s3(
                        conversation_id=conversation_id,
                        sandbox_path=sandbox_path,
                        file_name=file_name
                    )
                    url = upload_result["presigned_url"]
                    file_size = upload_result.get("file_size")
                    logger.info(f"✅ 沙盒文件已上传 S3: {file_name} → {upload_result['s3_key']}")
                except Exception as e:
                    errors.append(f"文件 {file_name} 上传失败: {str(e)}")
                    logger.error(f"❌ 沙盒文件上传失败: {file_name} - {e}", exc_info=True)
                    continue
            elif not url:
                errors.append(f"文件 {file_name} 缺少 url 或 sandbox_path")
                continue
            else:
                file_size = file_info.get("size")
            
            # 构建标准化的文件信息
            validated_file = {
                "name": file_name,
                "type": file_info.get("type") or self._extract_file_type(file_name),
                "url": url
            }
            
            # 可选字段
            if file_size:
                validated_file["size"] = file_size
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
    
    async def _upload_sandbox_file_to_s3(
        self,
        conversation_id: str,
        sandbox_path: str,
        file_name: str
    ) -> Dict[str, Any]:
        """
        从沙盒读取文件并上传到 S3
        
        Args:
            conversation_id: 对话 ID
            sandbox_path: 沙盒中的文件路径
            file_name: 文件名（用于 S3 存储）
            
        Returns:
            {
                "s3_key": str,
                "presigned_url": str,
                "file_size": int
            }
        """
        from services.sandbox_service import get_sandbox_service
        from utils.s3_uploader import get_s3_uploader
        
        # 1. 从沙盒读取文件
        sandbox_service = get_sandbox_service()
        file_content = await sandbox_service.read_file_bytes(conversation_id, sandbox_path)
        file_size = len(file_content)
        
        logger.info(f"📖 从沙盒读取文件: {sandbox_path} ({file_size} bytes)")
        
        # 2. 生成 S3 key
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_hash = hashlib.md5(f"{file_name}{timestamp}".encode()).hexdigest()[:8]
        file_ext = Path(file_name).suffix
        unique_filename = f"{Path(file_name).stem}_{file_hash}{file_ext}"
        s3_key = f"outputs/sandbox/{conversation_id}/{unique_filename}"
        
        # 3. 确定 Content-Type
        content_type = self._get_content_type(file_name)
        
        # 4. 上传到 S3
        s3_uploader = get_s3_uploader()
        await s3_uploader.initialize()
        
        await s3_uploader.upload_bytes(
            file_content=file_content,
            object_name=s3_key,
            content_type=content_type,
            metadata={
                "conversation_id": conversation_id,
                "original_filename": file_name,
                "sandbox_path": sandbox_path
            },
            acl="private"
        )
        
        # 5. 生成预签名 URL（24小时有效）
        presigned_url = s3_uploader.get_presigned_url(s3_key, expires_in=86400)
        
        return {
            "s3_key": s3_key,
            "presigned_url": presigned_url,
            "file_size": file_size
        }
    
    def _get_content_type(self, filename: str) -> str:
        """
        根据文件扩展名确定 Content-Type
        
        Args:
            filename: 文件名
            
        Returns:
            Content-Type
        """
        content_types = {
            '.pdf': 'application/pdf',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.ppt': 'application/vnd.ms-powerpoint',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            '.xls': 'application/vnd.ms-excel',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.txt': 'text/plain',
            '.md': 'text/markdown',
            '.json': 'application/json',
            '.csv': 'text/csv',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.mp3': 'audio/mpeg',
            '.mp4': 'video/mp4',
            '.wav': 'audio/wav',
            '.zip': 'application/zip',
            '.rar': 'application/x-rar-compressed',
        }
        
        ext = Path(filename).suffix.lower()
        return content_types.get(ext, 'application/octet-stream')
    
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

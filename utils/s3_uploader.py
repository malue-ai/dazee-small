"""
AWS S3 上传工具 - S3 Uploader

职责：
1. 文件上传到 S3
2. 生成预签名 URL
3. 文件删除
4. 批量操作

设计原则：
- 使用 boto3 SDK
- 支持多种文件类型
- 自动路径管理
- 错误处理和重试
"""

import os
import io
import boto3
import hashlib
import aiofiles
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from pathlib import Path
from urllib.parse import quote, unquote
from botocore.exceptions import ClientError, NoCredentialsError
import yaml

from logger import get_logger

logger = get_logger("s3_uploader")


class S3UploaderError(Exception):
    """S3 上传器异常基类"""
    pass


class S3ConfigError(S3UploaderError):
    """S3 配置错误"""
    pass


class S3UploadError(S3UploaderError):
    """S3 上传失败"""
    pass


def _sanitize_metadata(metadata: Dict[str, str]) -> Dict[str, str]:
    """
    清理 metadata，将非 ASCII 字符进行 URL 编码
    
    S3 metadata 只能包含 ASCII 字符，中文等 Unicode 字符需要编码。
    使用 URL 编码（percent-encoding）来处理，便于后续解码还原。
    
    Args:
        metadata: 原始 metadata 字典
        
    Returns:
        编码后的 metadata 字典（所有值都是 ASCII 安全的）
    """
    sanitized = {}
    for key, value in metadata.items():
        if value is None:
            continue
        # 检查是否包含非 ASCII 字符
        try:
            value.encode('ascii')
            # 纯 ASCII，直接使用
            sanitized[key] = value
        except UnicodeEncodeError:
            # 包含非 ASCII 字符，进行 URL 编码
            sanitized[key] = quote(value, safe='')
    return sanitized


class S3Uploader:
    """
    AWS S3 上传工具
    
    功能：
    - 文件上传（支持路径模板）
    - 预签名 URL 生成
    - 文件删除
    - 批量操作
    
    使用方式：
        uploader = S3Uploader()
        await uploader.initialize()  # 必须调用以加载配置
    """
    
    def __init__(self, config_path: str = "config/storage.yaml"):
        """
        初始化 S3 上传器
        
        Args:
            config_path: 配置文件路径
        """
        self._config_path = config_path
        self.config: Dict[str, Any] = {}
        self.s3_client = None
        self.bucket_name = ""
        self._initialized: bool = False
    
    async def initialize(self) -> None:
        """
        异步初始化：加载配置并创建 S3 客户端
        
        使用方式：
            uploader = S3Uploader()
            await uploader.initialize()
        """
        if self._initialized:
            return
        
        self.config = await self._load_config_async(self._config_path)
        self.bucket_name = self.config["aws"]["s3"]["bucket_name"]
        
        # 初始化 boto3 客户端
        self._init_s3_client()
        
        self._initialized = True
        logger.info(f"✅ S3 Uploader 初始化完成: bucket={self.bucket_name}")
    
    async def _load_config_async(self, config_path: str) -> Dict[str, Any]:
        """
        异步加载配置文件
        
        Args:
            config_path: 配置文件路径
            
        Returns:
            配置字典
        """
        try:
            async with aiofiles.open(config_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                config = yaml.safe_load(content)
            
            # 替换环境变量
            aws_config = config.get("aws", {})
            aws_config["access_key_id"] = os.getenv(
                "AWS_ACCESS_KEY_ID",
                aws_config.get("access_key_id", "").replace("${AWS_ACCESS_KEY_ID}", "")
            )
            aws_config["secret_access_key"] = os.getenv(
                "AWS_SECRET_ACCESS_KEY",
                aws_config.get("secret_access_key", "").replace("${AWS_SECRET_ACCESS_KEY}", "")
            )
            
            return config
        except Exception as e:
            logger.error(f"❌ 加载配置失败: {str(e)}")
            raise S3ConfigError(f"加载配置失败: {str(e)}") from e
    
    def _init_s3_client(self):
        """初始化 boto3 S3 客户端"""
        try:
            aws_config = self.config["aws"]
            
            # 创建 S3 客户端
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=aws_config["access_key_id"],
                aws_secret_access_key=aws_config["secret_access_key"],
                region_name=aws_config["region"],
                endpoint_url=aws_config["s3"].get("endpoint_url")
            )
            
            logger.info("✅ S3 客户端初始化成功")
        
        except NoCredentialsError:
            logger.error("❌ AWS 凭证未配置")
            raise S3ConfigError("AWS 凭证未配置，请设置环境变量 AWS_ACCESS_KEY_ID 和 AWS_SECRET_ACCESS_KEY")
        
        except Exception as e:
            logger.error(f"❌ 初始化 S3 客户端失败: {str(e)}")
            raise S3ConfigError(f"初始化 S3 客户端失败: {str(e)}") from e
    
    # ==================== 文件上传 ====================
    
    async def upload_file(
        self,
        file_path: str,
        category: str = "knowledge",
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        filename: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """
        上传文件到 S3
        
        Args:
            file_path: 本地文件路径
            category: 文件分类（knowledge/avatar/attachment/temp）
            user_id: 用户 ID
            conversation_id: 对话 ID（可选）
            filename: 自定义文件名（可选）
            metadata: 自定义元数据（可选）
            
        Returns:
            {
                "s3_key": str,          # S3 对象键
                "s3_url": str,          # S3 URL
                "presigned_url": str,   # 预签名 URL（24小时有效）
                "file_size": int,       # 文件大小（字节）
                "content_type": str     # 内容类型
            }
            
        Raises:
            S3UploadError: 上传失败
        """
        try:
            # 1. 验证文件
            if not os.path.exists(file_path):
                raise S3UploadError(f"文件不存在: {file_path}")
            
            file_size = os.path.getsize(file_path)
            max_size = self.config["aws"]["s3"]["upload"]["max_file_size"] * 1024 * 1024
            
            if file_size > max_size:
                raise S3UploadError(f"文件过大: {file_size} bytes > {max_size} bytes")
            
            # 2. 生成 S3 key
            if not filename:
                filename = Path(file_path).name
            
            s3_key = self._generate_s3_key(
                category=category,
                filename=filename,
                user_id=user_id,
                conversation_id=conversation_id
            )
            
            # 3. 准备元数据（对非 ASCII 字符进行 URL 编码）
            file_metadata = metadata or {}
            file_metadata.update({
                "uploaded_at": datetime.now().isoformat(),
                "original_filename": filename,
                "user_id": user_id or "unknown",
                "category": category
            })
            file_metadata = _sanitize_metadata(file_metadata)
            
            # 4. 确定内容类型
            content_type = self._get_content_type(filename)
            
            # 5. 获取 ACL
            acl = self.config["aws"]["s3"]["acl"].get(category, "private")
            
            # 6. 上传到 S3（异步读取文件内容）
            logger.info(f"📤 上传文件: {filename} → {s3_key}")
            
            async with aiofiles.open(file_path, 'rb') as f:
                file_content = await f.read()
            
            self.s3_client.upload_fileobj(
                io.BytesIO(file_content),
                self.bucket_name,
                s3_key,
                ExtraArgs={
                    'ContentType': content_type,
                    'Metadata': file_metadata,
                    'ACL': acl
                }
            )
            
            logger.info(f"✅ 上传成功: {s3_key}")
            
            # 7. 生成 URL
            s3_url = f"s3://{self.bucket_name}/{s3_key}"
            presigned_url = self._generate_presigned_url(s3_key, expires_in=86400)  # 24小时
            
            return {
                "s3_key": s3_key,
                "s3_url": s3_url,
                "presigned_url": presigned_url,
                "file_size": file_size,
                "content_type": content_type
            }
        
        except ClientError as e:
            logger.error(f"❌ S3 上传失败: {str(e)}")
            raise S3UploadError(f"S3 上传失败: {str(e)}") from e
        
        except Exception as e:
            logger.error(f"❌ 上传失败: {str(e)}", exc_info=True)
            raise S3UploadError(f"上传失败: {str(e)}") from e
    
    async def upload_bytes(
        self,
        file_content: bytes,
        object_name: str,
        content_type: str = "application/octet-stream",
        metadata: Optional[Dict[str, str]] = None,
        acl: str = "private"
    ) -> Dict[str, str]:
        """
        直接上传字节内容到 S3
        
        Args:
            file_content: 文件字节内容
            object_name: S3 对象名称（完整路径）
            content_type: MIME 类型
            metadata: 自定义元数据（可选）
            acl: 访问控制（private/public-read）
            
        Returns:
            {
                "key": str,       # S3 对象键
                "url": str,       # S3 URL（s3://bucket/key）
                "size": int       # 文件大小
            }
            
        Raises:
            S3UploadError: 上传失败
        """
        try:
            # 检查文件大小
            file_size = len(file_content)
            max_size = self.config["aws"]["s3"]["upload"]["max_file_size"] * 1024 * 1024
            
            if file_size > max_size:
                raise S3UploadError(f"文件过大: {file_size} bytes > {max_size} bytes")
            
            # 准备元数据（对非 ASCII 字符进行 URL 编码）
            file_metadata = metadata or {}
            file_metadata.update({
                "uploaded_at": datetime.now().isoformat(),
            })
            file_metadata = _sanitize_metadata(file_metadata)
            
            # 上传到 S3
            logger.info(f"📤 上传字节内容: {object_name} ({file_size} bytes)")
            
            from io import BytesIO
            self.s3_client.upload_fileobj(
                BytesIO(file_content),
                self.bucket_name,
                object_name,
                ExtraArgs={
                    'ContentType': content_type,
                    'Metadata': file_metadata,
                    'ACL': acl
                }
            )
            
            logger.info(f"✅ 上传成功: {object_name}")
            
            # 生成 URL
            s3_url = f"s3://{self.bucket_name}/{object_name}"
            
            return {
                "key": object_name,
                "url": s3_url,
                "size": file_size
            }
        
        except ClientError as e:
            logger.error(f"❌ S3 上传失败: {str(e)}")
            raise S3UploadError(f"S3 上传失败: {str(e)}") from e
        
        except Exception as e:
            logger.error(f"❌ 上传失败: {str(e)}", exc_info=True)
            raise S3UploadError(f"上传失败: {str(e)}") from e
    
    def _generate_s3_key(
        self,
        category: str,
        filename: str,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None
    ) -> str:
        """
        生成 S3 对象键
        
        Args:
            category: 文件分类
            filename: 文件名
            user_id: 用户 ID
            conversation_id: 对话 ID
            
        Returns:
            S3 对象键
        """
        # 获取路径模板
        path_template = self.config["aws"]["s3"]["upload"]["path_prefix"].get(category, "default/")
        
        # 替换占位符
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = path_template.format(
            user_id=user_id or "unknown",
            conversation_id=conversation_id or "default",
            timestamp=timestamp
        )
        
        # 生成唯一文件名（原文件名 + 哈希前缀）
        file_ext = Path(filename).suffix
        file_hash = hashlib.md5(f"{filename}{timestamp}".encode()).hexdigest()[:8]
        unique_filename = f"{Path(filename).stem}_{file_hash}{file_ext}"
        
        return f"{path}{unique_filename}"
    
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
        }
        
        ext = Path(filename).suffix.lower()
        return content_types.get(ext, 'application/octet-stream')
    
    # ==================== URL 生成 ====================
    
    def _generate_presigned_url(
        self,
        s3_key: str,
        expires_in: int = 3600
    ) -> str:
        """
        生成预签名 URL
        
        Args:
            s3_key: S3 对象键
            expires_in: 过期时间（秒），默认 1 小时
            
        Returns:
            预签名 URL
        """
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': s3_key
                },
                ExpiresIn=expires_in
            )
            return url
        except ClientError as e:
            logger.error(f"❌ 生成预签名 URL 失败: {str(e)}")
            return ""
    
    def get_presigned_url(
        self,
        s3_key: str,
        expires_in: int = 3600
    ) -> str:
        """
        公开方法：生成预签名 URL（同步方法，直接可用）
        
        说明：
        - 数据库存储永久的 s3_key
        - 调用此方法动态生成临时的预签名 URL
        - 前端可以直接使用返回的 URL 下载文件
        
        Args:
            s3_key: S3 对象键（从数据库获取）
            expires_in: 过期时间（秒），默认 3600 秒（1小时）
            
        Returns:
            预签名 URL（可直接访问的 HTTPS 链接）
            
        Example:
            >>> s3_key = "knowledge/user_123/20231231_120000/file_abc123.pdf"
            >>> url = s3_uploader.get_presigned_url(s3_key, expires_in=3600)
            >>> # url = "https://bucket.s3.amazonaws.com/knowledge/...?signature=..."
        """
        return self._generate_presigned_url(s3_key, expires_in)
    
    # ==================== 文件删除 ====================
    
    async def delete_file(self, s3_key: str) -> bool:
        """
        删除单个文件
        
        Args:
            s3_key: S3 对象键
            
        Returns:
            是否删除成功
        """
        logger.info(f"🗑️ 删除文件: {s3_key}")
        
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            
            logger.info(f"✅ 文件已删除: {s3_key}")
            return True
        
        except ClientError as e:
            logger.error(f"❌ 删除文件失败: {str(e)}")
            raise S3UploaderError(f"删除失败: {str(e)}") from e
    
    async def delete_files_batch(self, s3_keys: List[str]) -> Dict[str, Any]:
        """
        批量删除文件
        
        Args:
            s3_keys: S3 对象键列表
            
        Returns:
            {
                "total": int,
                "succeeded": int,
                "failed": int
            }
        """
        logger.info(f"🗑️ 批量删除: {len(s3_keys)} 个文件")
        
        if not s3_keys:
            return {"total": 0, "succeeded": 0, "failed": 0}
        
        try:
            # 构建删除请求
            delete_keys = [{"Key": key} for key in s3_keys]
            
            response = self.s3_client.delete_objects(
                Bucket=self.bucket_name,
                Delete={'Objects': delete_keys}
            )
            
            deleted = response.get('Deleted', [])
            errors = response.get('Errors', [])
            
            logger.info(f"✅ 批量删除完成: succeeded={len(deleted)}, failed={len(errors)}")
            
            return {
                "total": len(s3_keys),
                "succeeded": len(deleted),
                "failed": len(errors)
            }
        
        except ClientError as e:
            logger.error(f"❌ 批量删除失败: {str(e)}")
            return {
                "total": len(s3_keys),
                "succeeded": 0,
                "failed": len(s3_keys)
            }


# ==================== 便捷函数 ====================

_default_uploader: Optional[S3Uploader] = None


def get_s3_uploader() -> S3Uploader:
    """获取默认 S3 上传器单例"""
    global _default_uploader
    if _default_uploader is None:
        _default_uploader = S3Uploader()
    return _default_uploader


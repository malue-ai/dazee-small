"""
文件管理路由

提供本地文件上传和文件服务端点。
项目运行在本地桌面模式，文件存储在本地文件系统。
"""

import io
import mimetypes
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from infra.storage.local import LocalStorage
from logger import get_logger
from utils.app_paths import get_storage_dir

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/files", tags=["files"])

# 本地存储实例（懒初始化，避免模块导入时 AGENT_INSTANCE 未设置）
_storage: LocalStorage | None = None


def _get_storage() -> LocalStorage:
    """Get or create the LocalStorage singleton."""
    global _storage
    if _storage is None:
        _storage = LocalStorage()
    return _storage

# 上传文件子目录
UPLOADS_DIR = "uploads"


def _generate_storage_path(original_filename: str) -> str:
    """
    Generate a unique storage path for an uploaded file.

    Format: uploads/{date}/{uuid}_{filename}
    Uses os.path.join for cross-platform path separators.
    """
    import os

    date_str = datetime.now().strftime("%Y%m%d")
    unique_id = uuid.uuid4().hex[:8]
    safe_name = original_filename.replace(" ", "_")
    return os.path.join(UPLOADS_DIR, date_str, f"{unique_id}_{safe_name}")


def _guess_mime_type(filename: str) -> str:
    """Guess MIME type from filename."""
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or "application/octet-stream"


# ==================== 文件上传 ====================


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    user_id: str = Form(default="local"),
) -> Dict[str, Any]:
    """
    Upload a file to local storage.

    Args:
        file: The file to upload.
        user_id: User identifier (default: "local").

    Returns:
        File metadata including the access URL.
    """
    filename = file.filename or "unknown"
    content_type = file.content_type or _guess_mime_type(filename)

    logger.info(f"📎 文件上传: {filename}, type={content_type}, user={user_id}")

    # Read file content
    content = await file.read()
    file_size = len(content)

    # Generate storage path and save
    storage_path = _generate_storage_path(filename)

    # Use storage backend to save
    full_path = await _get_storage().save(
        file=io.BytesIO(content),
        path=storage_path,
        content_type=content_type,
    )

    # local_path: 真实文件系统路径（Agent 直接读取）
    # file_url: API URL（前端预览/下载用, 必须使用 /）
    local_path = str(full_path)
    # On Windows, storage_path may contain backslashes; URLs always use /
    url_path = storage_path.replace("\\", "/")
    file_url = f"/api/v1/files/{url_path}"

    logger.info(f"✅ 文件上传成功: {filename} -> {local_path} ({file_size} bytes)")

    return {
        "success": True,
        "data": {
            "file_url": file_url,
            "local_path": local_path,
            "file_name": filename,
            "file_type": content_type,
            "file_size": file_size,
        },
    }


# ==================== 文件服务 ====================


@router.get("/{file_path:path}")
async def serve_file(file_path: str) -> FileResponse:
    """
    Serve a file from local storage.

    Args:
        file_path: The relative path within storage.

    Returns:
        The file content with proper MIME type.
    """
    storage_dir = get_storage_dir()
    full_path = storage_dir / file_path

    if not full_path.exists():
        logger.warning(f"文件不存在: {file_path}")
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_path}")

    # Security: ensure the path is within storage dir
    try:
        full_path.resolve().relative_to(storage_dir.resolve())
    except ValueError:
        logger.warning(f"路径越界访问: {file_path}")
        raise HTTPException(status_code=403, detail="访问被拒绝")

    mime_type = _guess_mime_type(full_path.name)

    return FileResponse(
        path=str(full_path),
        media_type=mime_type,
        filename=full_path.name,
    )

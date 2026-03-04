"""
文件管理路由

提供本地文件上传和文件服务端点。
项目运行在本地桌面模式，文件存储在本地文件系统。
"""

import io
import mimetypes
import os
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from infra.storage.local import LocalStorage
from logger import get_logger
from utils.app_paths import get_storage_dir, get_instance_storage_dir, get_user_data_dir

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/files", tags=["files"])

# 按 instance 缓存存储实例，避免切换项目后仍使用旧实例的 base_dir
_storage_cache: dict[str, LocalStorage] = {}


def _get_storage() -> LocalStorage:
    """Get or create a LocalStorage for the current AGENT_INSTANCE."""
    instance = os.getenv("AGENT_INSTANCE", "default")
    if instance not in _storage_cache:
        _storage_cache[instance] = LocalStorage(instance_name=instance)
    return _storage_cache[instance]

# 上传文件子目录
UPLOADS_DIR = "uploads"


def _generate_storage_path(original_filename: str) -> str:
    """
    Generate a unique storage path for an uploaded file.

    Format: uploads/{date}/{uuid}_{filename}
    Uses os.path.join for cross-platform path separators.
    """
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
    # 包含 instance 名称，确保切换项目后仍能正确定位文件
    local_path = str(full_path)
    instance_name = os.getenv("AGENT_INSTANCE", "default")
    url_path = storage_path.replace("\\", "/")
    file_url = f"/api/v1/files/@{instance_name}/{url_path}"

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

    Supports two URL formats:
      - New: /api/v1/files/@{instance}/uploads/{date}/{filename}
      - Old: /api/v1/files/uploads/{date}/{filename}  (uses current AGENT_INSTANCE,
        falls back to scanning all instances if not found)

    Args:
        file_path: The relative path within storage.

    Returns:
        The file content with proper MIME type.
    """
    storage_dir, relative_path = _resolve_instance_storage(file_path)
    full_path = storage_dir / relative_path

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


def _resolve_instance_storage(file_path: str) -> tuple[Path, str]:
    """
    Parse instance from file_path and return (storage_dir, relative_path).

    New format: @{instance}/uploads/...  → use that instance's storage
    Old format: uploads/...              → current AGENT_INSTANCE, fallback to scan
    """
    # New format: @instance/relative_path
    if file_path.startswith("@"):
        sep = file_path.index("/") if "/" in file_path else len(file_path)
        instance_name = file_path[1:sep]
        relative_path = file_path[sep + 1:] if sep < len(file_path) else ""
        target_dir = get_instance_storage_dir(instance_name)
        if (target_dir / relative_path).exists():
            return target_dir, relative_path
        # File not in the declared instance (e.g. saved before fix),
        # fall through to scan all instances
        file_path = relative_path

    # Old format: try current instance first
    current_dir = get_storage_dir()
    if (current_dir / file_path).exists():
        return current_dir, file_path

    # Fallback: scan all instance data directories for the file
    instances_root = get_user_data_dir() / "instances"
    if instances_root.exists():
        for instance_dir in instances_root.iterdir():
            if not instance_dir.is_dir():
                continue
            candidate = instance_dir / "storage" / file_path
            if candidate.exists():
                logger.info(f"文件在实例 {instance_dir.name} 中找到: {file_path}")
                return instance_dir / "storage", file_path

    return current_dir, file_path


@router.get("/download-zip")
async def download_zip(paths: List[str] = Query(..., description="要打包的文件路径列表")):
    """将多个文件打包为 ZIP 下载。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel_path in paths:
            storage_dir, resolved = _resolve_file_path(rel_path)
            full = storage_dir / resolved
            if full.exists() and full.is_file():
                zf.write(full, arcname=Path(resolved).name)
            else:
                logger.warning(f"download-zip: 跳过不存在的文件 {rel_path}")
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=files.zip"},
    )

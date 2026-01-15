"""
文件上传路由（纯 S3，无数据库）

只提供文件上传功能，返回 S3 预签名 URL
前端通过 file_url 方式在聊天中使用文件
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form

from logger import get_logger
from models.api import APIResponse
from services.file_service import get_file_service, FileServiceError

logger = get_logger("routers.files")
router = APIRouter(prefix="/api/v1/files", tags=["files"])


@router.post("/upload")
async def upload_file(file: UploadFile = File(...), user_id: str = Form(...)):
    """
    上传文件到 S3
    
    返回预签名 URL，前端在聊天时通过 file_url 方式使用
    
    Returns:
        {
            "file_url": "https://s3.amazonaws.com/...",  # S3 预签名 URL（24小时有效）
            "file_name": "example.pdf",
            "file_size": 102400,
            "file_type": "application/pdf"
        }
    """
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="文件为空")
        if len(content) > 50 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="文件过大（限制 50MB）")
        
        result = await get_file_service().upload_file(
            file_content=content,
            filename=file.filename or "unnamed",
            mime_type=file.content_type or "application/octet-stream",
            user_id=user_id
        )
        return APIResponse(code=200, message="success", data=result)
    except FileServiceError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="上传失败")

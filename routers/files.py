"""文件管理路由"""

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form

from logger import get_logger
from models.api import APIResponse
from services.file_service import get_file_service, FileNotFoundError, FileServiceError

logger = get_logger("routers.files")
router = APIRouter(prefix="/api/v1/files", tags=["files"])


@router.post("/upload")
async def upload_file(file: UploadFile = File(...), user_id: str = Form(...)):
    """上传文件"""
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


@router.get("/{file_id}/url")
async def get_file_url(file_id: str, expiration: int = Query(3600, ge=60, le=604800)):
    """获取文件访问 URL"""
    try:
        url = await get_file_service().get_file_url(file_id, expiration)
        return APIResponse(
            code=200,
            message="success",
            data={"file_id": file_id, "file_url": url, "expires_in": expiration}
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="文件不存在")
    except Exception as e:
        logger.error(f"❌ {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取失败")


@router.get("")
async def list_files(
    user_id: str = Query(...),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """获取文件列表"""
    try:
        result = await get_file_service().list_files(user_id, limit, offset)
        return APIResponse(code=200, message="success", data=result)
    except Exception as e:
        logger.error(f"❌ {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="查询失败")


@router.get("/{file_id}")
async def get_file_detail(file_id: str):
    """获取文件详情"""
    try:
        data = await get_file_service().get_file(file_id)
        return APIResponse(code=200, message="success", data=data)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="文件不存在")
    except Exception as e:
        logger.error(f"❌ {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="查询失败")


@router.get("/{file_id}/download")
async def get_download_url(file_id: str):
    """获取下载 URL"""
    try:
        data = await get_file_service().get_download_url(file_id)
        return APIResponse(code=200, message="success", data=data)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="文件不存在")
    except Exception as e:
        logger.error(f"❌ {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="生成失败")


@router.delete("/{file_id}")
async def delete_file(file_id: str):
    """删除文件"""
    try:
        data = await get_file_service().delete_file(file_id)
        return APIResponse(code=200, message="success", data=data)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="文件不存在")
    except Exception as e:
        logger.error(f"❌ {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="删除失败")

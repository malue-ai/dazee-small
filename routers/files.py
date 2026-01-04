"""
文件管理路由 - File Management Router

提供文件上传、列表、下载、删除等 API

架构设计：
- Router 层只负责 HTTP 请求/响应处理
- 业务逻辑委托给 FileService
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Optional

from logger import get_logger
from services.file_service import get_file_service, FileNotFoundError
from models.file import FileCategory, FileStatus

logger = get_logger("routers.files")

router = APIRouter(prefix="/api/v1/files", tags=["files"])


@router.get("")
async def list_files(
    user_id: str = Query(..., description="用户 ID"),
    category: Optional[FileCategory] = Query(None, description="按分类过滤"),
    status: Optional[FileStatus] = Query(None, description="按状态过滤"),
    limit: int = Query(20, ge=1, le=1000, description="每页数量"),
    offset: int = Query(0, ge=0, description="偏移量")
):
    """
    获取用户文件列表
    
    Args:
        user_id: 用户 ID
        category: 分类过滤
        status: 状态过滤
        limit: 每页数量
        offset: 偏移量
        
    Returns:
        文件列表
    """
    try:
        file_service = get_file_service()
        
        result = await file_service.list_files(
            user_id=user_id,
            category=category.value if category else None,
            status=status.value if status else None,
            limit=limit,
            offset=offset
        )
        
        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "查询成功",
                "data": result
            }
        )
    
    except Exception as e:
        logger.error(f"❌ 查询文件列表失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/stats/{user_id}")
async def get_user_stats(user_id: str):
    """
    获取用户文件统计
    
    Args:
        user_id: 用户 ID
        
    Returns:
        统计信息
    """
    try:
        file_service = get_file_service()
        
        stats = await file_service.get_user_stats(user_id)
        
        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "查询成功",
                "data": stats
            }
        )
    
    except Exception as e:
        logger.error(f"❌ 获取统计失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/{file_id}")
async def get_file_detail(file_id: str):
    """
    获取文件详情
    
    Args:
        file_id: 文件 ID
        
    Returns:
        文件详情
    """
    try:
        file_service = get_file_service()
        
        file_data = await file_service.get_file(file_id)
        
        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "查询成功",
                "data": file_data
            }
        )
    
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="文件不存在")
    except Exception as e:
        logger.error(f"❌ 获取文件详情失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/{file_id}/download")
async def get_download_url(file_id: str):
    """
    获取文件下载 URL（预签名 URL）
    
    Args:
        file_id: 文件 ID
        
    Returns:
        下载 URL
    """
    try:
        file_service = get_file_service()
        
        result = await file_service.get_download_url(file_id)
        
        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "生成下载链接成功",
                "data": result
            }
        )
    
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="文件不存在")
    except Exception as e:
        logger.error(f"❌ 生成下载链接失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"生成失败: {str(e)}")


@router.delete("/{file_id}")
async def delete_file(file_id: str):
    """
    删除文件
    
    Args:
        file_id: 文件 ID
        
    Returns:
        删除结果
    """
    try:
        file_service = get_file_service()
        
        result = await file_service.delete_file(file_id)
        
        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "文件已删除",
                "data": result
            }
        )
    
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="文件不存在")
    except Exception as e:
        logger.error(f"❌ 删除文件失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@router.post("/{file_id}/view")
async def increment_view_count(file_id: str):
    """
    增加文件查看次数
    
    Args:
        file_id: 文件 ID
    """
    try:
        file_service = get_file_service()
        
        await file_service.increment_view_count(file_id)
        
        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "计数已更新"
            }
        )
    
    except Exception as e:
        logger.error(f"❌ 更新计数失败: {str(e)}")
        # 计数失败不应影响主流程，只记录日志
        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "计数更新失败但不影响使用"
            }
        )

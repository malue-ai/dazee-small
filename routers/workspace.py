"""
Workspace API Router

提供给前端的 Workspace 文件管理接口：
- GET  /workspace/{conv_id}/files      - 获取文件列表
- GET  /workspace/{conv_id}/files/{path} - 获取/下载文件
- POST /workspace/{conv_id}/files      - 上传文件
- DELETE /workspace/{conv_id}/files/{path} - 删除文件
- GET  /workspace/{conv_id}/projects   - 获取项目列表（检测可运行的项目）

沙盒管理接口：
- GET  /workspace/{conv_id}/sandbox/status  - 获取沙盒状态
- POST /workspace/{conv_id}/sandbox/init    - 初始化沙盒
- POST /workspace/{conv_id}/sandbox/pause   - 暂停沙盒
- POST /workspace/{conv_id}/sandbox/resume  - 恢复沙盒
- POST /workspace/{conv_id}/sandbox/kill    - 终止沙盒
- POST /workspace/{conv_id}/sandbox/run     - 运行项目
- POST /workspace/{conv_id}/sandbox/stop    - 停止项目
- GET  /workspace/{conv_id}/sandbox/logs    - 获取项目日志
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, UploadFile, File, Query, Header
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from logger import get_logger
# 注：已移除本地文件系统模式，仅使用沙盒
from services.sandbox_service import (
    get_sandbox_service,
    SandboxServiceError,
    SandboxNotFoundError,
    SandboxConnectionError,
    FileInfo as SandboxFileInfo
)

logger = get_logger("workspace_router")

router = APIRouter(prefix="/api/v1/workspace", tags=["workspace"])


# ==================== 请求/响应模型 ====================

class FileItemResponse(BaseModel):
    """文件项响应"""
    path: str
    name: str
    type: str  # "file" or "directory"
    size: Optional[int] = None
    modified_at: Optional[str] = None
    children: Optional[List['FileItemResponse']] = None


class FileListResponse(BaseModel):
    """文件列表响应"""
    conversation_id: str
    files: List[FileItemResponse]
    total_size: Optional[int] = None
    source: str = "sandbox"  # "sandbox" or "local"


class FileContentResponse(BaseModel):
    """文件内容响应"""
    path: str
    content: str
    size: int


class UploadResponse(BaseModel):
    """上传响应"""
    success: bool
    path: str
    size: int


class DeleteResponse(BaseModel):
    """删除响应"""
    success: bool
    path: str
    message: Optional[str] = None


class SandboxStatusResponse(BaseModel):
    """沙盒状态响应"""
    conversation_id: str
    sandbox_id: Optional[str] = None
    e2b_sandbox_id: Optional[str] = None
    status: str  # creating/running/paused/killed/none
    stack: Optional[str] = None
    preview_url: Optional[str] = None
    active_project_path: Optional[str] = None  # 当前运行的项目路径
    active_project_stack: Optional[str] = None  # 当前运行的项目技术栈
    created_at: Optional[str] = None
    last_active_at: Optional[str] = None


class SandboxInitRequest(BaseModel):
    """沙盒初始化请求"""
    user_id: str
    stack: Optional[str] = None


class CommandRequest(BaseModel):
    """命令执行请求"""
    command: str
    timeout: int = 60


class CommandResponse(BaseModel):
    """命令执行响应"""
    success: bool
    exit_code: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    error: Optional[str] = None


# ==================== 沙盒管理 API ====================

@router.get("/{conversation_id}/sandbox/status", response_model=SandboxStatusResponse)
async def get_sandbox_status(conversation_id: str):
    """
    获取沙盒状态
    
    Args:
        conversation_id: 对话 ID
    """
    try:
        service = get_sandbox_service()
        info = await service.get_sandbox_status(conversation_id)
        
        if not info:
            return SandboxStatusResponse(
                conversation_id=conversation_id,
                status="none"
            )
        
        return SandboxStatusResponse(
            conversation_id=conversation_id,
            sandbox_id=info.id,
            e2b_sandbox_id=info.e2b_sandbox_id,
            status=info.status,
            stack=info.stack,
            preview_url=info.preview_url,
            active_project_path=info.active_project_path,
            active_project_stack=info.active_project_stack,
            created_at=info.created_at,
            last_active_at=info.last_active_at
        )
    
    except Exception as e:
        logger.error(f"获取沙盒状态失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取沙盒状态失败")


@router.post("/{conversation_id}/sandbox/init", response_model=SandboxStatusResponse)
async def init_sandbox(
    conversation_id: str,
    request: SandboxInitRequest
):
    """
    初始化沙盒
    
    如果沙盒已存在，返回现有沙盒信息
    
    Args:
        conversation_id: 对话 ID
        request: 初始化请求
    """
    try:
        service = get_sandbox_service()
        info = await service.get_or_create_sandbox(
            conversation_id=conversation_id,
            user_id=request.user_id,
            stack=request.stack
        )
        
        return SandboxStatusResponse(
            conversation_id=conversation_id,
            sandbox_id=info.id,
            e2b_sandbox_id=info.e2b_sandbox_id,
            status=info.status,
            stack=info.stack,
            preview_url=info.preview_url,
            active_project_path=info.active_project_path,
            active_project_stack=info.active_project_stack,
            created_at=info.created_at,
            last_active_at=info.last_active_at
        )
    
    except SandboxServiceError as e:
        logger.error(f"初始化沙盒失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"初始化沙盒失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="初始化沙盒失败")


@router.post("/{conversation_id}/sandbox/pause")
async def pause_sandbox(conversation_id: str):
    """
    暂停沙盒
    
    暂停后沙盒状态会被保存，可以通过 resume 恢复
    
    Args:
        conversation_id: 对话 ID
    """
    try:
        service = get_sandbox_service()
        success = await service.pause_sandbox(conversation_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="沙盒不存在或已暂停")
        
        return {"success": True, "message": "沙盒已暂停"}
    
    except HTTPException:
        raise
    except SandboxServiceError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"暂停沙盒失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="暂停沙盒失败")


@router.post("/{conversation_id}/sandbox/resume", response_model=SandboxStatusResponse)
async def resume_sandbox(conversation_id: str):
    """
    恢复沙盒
    
    Args:
        conversation_id: 对话 ID
    """
    try:
        service = get_sandbox_service()
        info = await service.resume_sandbox(conversation_id)
        
        return SandboxStatusResponse(
            conversation_id=conversation_id,
            sandbox_id=info.id,
            e2b_sandbox_id=info.e2b_sandbox_id,
            status=info.status,
            stack=info.stack,
            preview_url=info.preview_url,
            active_project_path=info.active_project_path,
            active_project_stack=info.active_project_stack,
            created_at=info.created_at,
            last_active_at=info.last_active_at
        )
    
    except SandboxNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SandboxServiceError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"恢复沙盒失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="恢复沙盒失败")


@router.post("/{conversation_id}/sandbox/kill")
async def kill_sandbox(conversation_id: str):
    """
    终止沙盒
    
    警告：终止后沙盒数据将丢失
    
    Args:
        conversation_id: 对话 ID
    """
    try:
        service = get_sandbox_service()
        success = await service.kill_sandbox(conversation_id)
        
        return {"success": success, "message": "沙盒已终止"}
    
    except SandboxServiceError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"终止沙盒失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="终止沙盒失败")


@router.post("/{conversation_id}/sandbox/command", response_model=CommandResponse)
async def run_command(
    conversation_id: str,
    request: CommandRequest
):
    """
    在沙盒中执行命令
    
    Args:
        conversation_id: 对话 ID
        request: 命令请求
    """
    try:
        service = get_sandbox_service()
        result = await service.run_command(
            conversation_id=conversation_id,
            command=request.command,
            timeout=request.timeout
        )
        
        return CommandResponse(**result)
    
    except SandboxNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SandboxServiceError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"执行命令失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="执行命令失败")


# ==================== 文件操作 API ====================

@router.get("/{conversation_id}/files", response_model=FileListResponse)
async def list_files(
    conversation_id: str,
    path: str = Query(default="/home/user", description="目录路径"),
    tree: bool = Query(default=False, description="是否返回树形结构")
):
    """
    获取 workspace 文件列表（沙盒模式）
    
    Args:
        conversation_id: 对话 ID
        path: 目录路径（从 /home/user 开始）
        tree: 是否返回递归树形结构
    """
    try:
        service = get_sandbox_service()
        
        # 转换沙盒文件信息为响应格式
        def convert_sandbox_file(f) -> FileItemResponse:
            return FileItemResponse(
                path=f.path,
                name=f.name,
                type=f.type,
                size=f.size,
                modified_at=f.modified_at,
                children=[convert_sandbox_file(c) for c in f.children] if f.children else None
            )
        
        try:
            # 根据 tree 参数选择不同的方法
            if tree:
                sandbox_files = await service.list_files_tree(conversation_id, path)
            else:
                sandbox_files = await service.list_files(conversation_id, path)
            
            files = [convert_sandbox_file(f) for f in sandbox_files]
            
            return FileListResponse(
                conversation_id=conversation_id,
                files=files,
                source="sandbox"
            )
        except SandboxNotFoundError:
            # 沙盒不存在时返回空列表（而不是 404）
            logger.info(f"沙盒不存在，返回空列表: {conversation_id}")
            return FileListResponse(
                conversation_id=conversation_id,
                files=[],
                source="sandbox"
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except SandboxServiceError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"获取文件列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取文件列表失败")


@router.get("/{conversation_id}/files/{path:path}")
async def get_file(
    conversation_id: str,
    path: str,
    download: bool = Query(default=False, description="是否作为下载返回")
):
    """
    获取文件内容或下载文件（沙盒模式）
    
    Args:
        conversation_id: 对话 ID
        path: 文件路径
        download: 是否作为下载返回
    """
    try:
        # 判断是否为文本文件
        suffix = Path(path).suffix.lower()
        text_extensions = {
            '.txt', '.py', '.js', '.ts', '.jsx', '.tsx',
            '.html', '.css', '.scss', '.less',
            '.json', '.md', '.yaml', '.yml', '.xml', '.csv',
            '.sh', '.bash', '.zsh',
            '.vue', '.svelte', '.astro',
            '.toml', '.ini', '.cfg', '.conf',
            '.gitignore', '.env', '.env.local',
            '.sql', '.graphql',
            '.dockerfile', 'Dockerfile'
        }
        is_text = suffix in text_extensions or Path(path).name in text_extensions
        
        service = get_sandbox_service()
        
        if is_text and not download:
            content = await service.read_file(conversation_id, path)
            return Response(
                content=content,
                media_type="text/plain; charset=utf-8"
            )
        else:
            content = await service.read_file_bytes(conversation_id, path)
            filename = os.path.basename(path)
            return Response(
                content=content,
                media_type="application/octet-stream",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"'
                }
            )
    
    except HTTPException:
        raise
    except SandboxNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SandboxServiceError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"获取文件失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取文件失败")


@router.post("/{conversation_id}/files", response_model=UploadResponse)
async def upload_file(
    conversation_id: str,
    file: UploadFile = File(...),
    path: Optional[str] = Query(default=None, description="保存路径")
):
    """
    上传文件到沙盒
    
    Args:
        conversation_id: 对话 ID
        file: 上传的文件
        path: 保存路径（默认为文件名）
    """
    try:
        save_path = path if path else file.filename
        content = await file.read()
        
        service = get_sandbox_service()
        
        # 构造完整路径
        full_path = save_path if save_path.startswith("/") else f"/home/user/{save_path}"
        
        result = await service.write_file(conversation_id, full_path, content)
        
        logger.info(f"📤 文件上传到沙盒: {full_path} ({result['size']} bytes)")
        
        return UploadResponse(
            success=True,
            path=full_path,
            size=result["size"]
        )
    
    except SandboxNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SandboxServiceError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"上传文件失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="上传文件失败")


@router.put("/{conversation_id}/files/{path:path}", response_model=UploadResponse)
async def write_file(
    conversation_id: str,
    path: str,
    content: str = Query(..., description="文件内容")
):
    """
    写入文件内容（用于编辑器保存，沙盒模式）
    
    Args:
        conversation_id: 对话 ID
        path: 文件路径
        content: 文件内容
    """
    try:
        service = get_sandbox_service()
        result = await service.write_file(conversation_id, path, content)
        
        return UploadResponse(
            success=True,
            path=result["path"],
            size=result["size"]
        )
    
    except SandboxNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SandboxServiceError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"写入文件失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="写入文件失败")


@router.delete("/{conversation_id}/files/{path:path}", response_model=DeleteResponse)
async def delete_file(
    conversation_id: str,
    path: str
):
    """
    删除文件或目录（沙盒模式）
    
    Args:
        conversation_id: 对话 ID
        path: 文件或目录路径
    """
    try:
        service = get_sandbox_service()
        success = await service.delete_file(conversation_id, path)
        
        if not success:
            raise HTTPException(status_code=500, detail="删除失败")
        
        logger.info(f"🗑️ 沙盒文件删除: {path}")
        
        return DeleteResponse(
            success=True,
            path=path,
            message="删除成功"
        )
    
    except HTTPException:
        raise
    except SandboxNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SandboxServiceError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"删除文件失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="删除文件失败")


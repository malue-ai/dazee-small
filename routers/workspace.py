"""
Workspace API Router

提供给前端的 Workspace 文件管理接口：
- GET  /workspace/{conv_id}/files      - 获取文件列表
- GET  /workspace/{conv_id}/files/{path} - 获取/下载文件
- POST /workspace/{conv_id}/files      - 上传文件
- DELETE /workspace/{conv_id}/files/{path} - 删除文件
- GET  /workspace/{conv_id}/projects   - 获取项目列表

沙盒管理接口：
- GET  /workspace/{conv_id}/sandbox/status  - 获取沙盒状态
- POST /workspace/{conv_id}/sandbox/init    - 初始化沙盒
- POST /workspace/{conv_id}/sandbox/pause   - 暂停沙盒
- POST /workspace/{conv_id}/sandbox/resume  - 恢复沙盒
- POST /workspace/{conv_id}/sandbox/kill    - 终止沙盒

项目运行接口：
- POST /workspace/{conv_id}/projects/{name}/run   - 运行项目
- POST /workspace/{conv_id}/projects/{name}/stop  - 停止项目
- GET  /workspace/{conv_id}/projects/{name}/logs  - 获取日志
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
from core.workspace_manager import get_workspace_manager, FileInfo as LocalFileInfo
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


class ProjectInfo(BaseModel):
    """项目信息"""
    name: str
    path: str
    type: Optional[str] = None  # gradio / streamlit / nextjs / static
    entry_file: Optional[str] = None
    description: Optional[str] = None
    has_requirements: bool = False


class ProjectListResponse(BaseModel):
    """项目列表响应"""
    conversation_id: str
    projects: List[ProjectInfo]


class SandboxStatusResponse(BaseModel):
    """沙盒状态响应"""
    conversation_id: str
    sandbox_id: Optional[str] = None
    e2b_sandbox_id: Optional[str] = None
    status: str  # creating/running/paused/killed/none
    stack: Optional[str] = None
    preview_url: Optional[str] = None
    created_at: Optional[str] = None
    last_active_at: Optional[str] = None


class SandboxInitRequest(BaseModel):
    """沙盒初始化请求"""
    user_id: str
    stack: Optional[str] = None


class ProjectRunRequest(BaseModel):
    """项目运行请求"""
    stack: str  # streamlit/gradio/python/flask/fastapi


class ProjectRunResponse(BaseModel):
    """项目运行响应"""
    success: bool
    preview_url: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None


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
    use_sandbox: bool = Query(default=True, description="是否使用沙盒"),
    tree: bool = Query(default=False, description="是否返回树形结构")
):
    """
    获取 workspace 文件列表
    
    Args:
        conversation_id: 对话 ID
        path: 目录路径（沙盒模式从 /home/user 开始）
        use_sandbox: 是否使用沙盒（默认 True）
        tree: 是否返回递归树形结构
    """
    try:
        if use_sandbox:
            # 使用沙盒
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
        else:
            # 使用本地文件系统
            manager = get_workspace_manager()
            
            if tree:
                items = manager.list_dir_tree(conversation_id, path if path != "/home/user" else ".")
            else:
                items = manager.list_dir(conversation_id, path if path != "/home/user" else ".")
            
            def convert_item(item: LocalFileInfo) -> FileItemResponse:
                return FileItemResponse(
                    path=item.path,
                    name=os.path.basename(item.path),
                    type=item.type,
                    size=item.size,
                    modified_at=item.modified_at,
                    children=[convert_item(c) for c in item.children] if item.children else None
                )
            
            files = [convert_item(item) for item in items]
            total_size = manager.get_workspace_size(conversation_id)
            
            return FileListResponse(
                conversation_id=conversation_id,
                files=files,
                total_size=total_size,
                source="local"
            )
    
    except FileNotFoundError as e:
        # 本地文件系统目录不存在时返回空列表
        return FileListResponse(
            conversation_id=conversation_id,
            files=[],
            source="local"
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
    use_sandbox: bool = Query(default=True, description="是否使用沙盒"),
    download: bool = Query(default=False, description="是否作为下载返回")
):
    """
    获取文件内容或下载文件
    
    Args:
        conversation_id: 对话 ID
        path: 文件路径
        use_sandbox: 是否使用沙盒
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
        
        if use_sandbox:
            # 使用沙盒（service 层会自动处理路径标准化）
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
        else:
            # 使用本地文件系统
            manager = get_workspace_manager()
            full_path = manager.resolve_path(conversation_id, path)
            
            if not full_path.exists():
                raise HTTPException(status_code=404, detail=f"文件不存在: {path}")
            
            if not full_path.is_file():
                raise HTTPException(status_code=400, detail=f"不是文件: {path}")
            
            if download or not is_text:
                return FileResponse(
                    path=str(full_path),
                    filename=full_path.name,
                    media_type="application/octet-stream"
                )
            else:
                content = full_path.read_text(encoding='utf-8')
                return Response(
                    content=content,
                    media_type="text/plain; charset=utf-8"
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
    path: Optional[str] = Query(default=None, description="保存路径"),
    use_sandbox: bool = Query(default=True, description="是否使用沙盒")
):
    """
    上传文件到 workspace
    
    Args:
        conversation_id: 对话 ID
        file: 上传的文件
        path: 保存路径（默认为文件名）
        use_sandbox: 是否使用沙盒
    """
    try:
        save_path = path if path else file.filename
        content = await file.read()
        
        if use_sandbox:
            # 使用沙盒
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
        else:
            # 使用本地文件系统
            manager = get_workspace_manager()
            result = manager.write_file(conversation_id, save_path, content)
            
            logger.info(f"📤 文件上传到本地: {save_path} ({result['size']} bytes)")
            
            return UploadResponse(
                success=True,
                path=save_path,
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
    content: str = Query(..., description="文件内容"),
    use_sandbox: bool = Query(default=True, description="是否使用沙盒")
):
    """
    写入文件内容（用于编辑器保存）
    
    Args:
        conversation_id: 对话 ID
        path: 文件路径
        content: 文件内容
        use_sandbox: 是否使用沙盒
    """
    try:
        if use_sandbox:
            # 使用沙盒
            service = get_sandbox_service()
            
            # service 层会自动处理路径标准化
            result = await service.write_file(conversation_id, path, content)
            
            return UploadResponse(
                success=True,
                path=result["path"],  # 使用 service 返回的标准化路径
                size=result["size"]
            )
        else:
            # 使用本地文件系统
            manager = get_workspace_manager()
            result = manager.write_file(conversation_id, path, content.encode('utf-8'))
            
            return UploadResponse(
                success=True,
                path=path,
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
    path: str,
    use_sandbox: bool = Query(default=True, description="是否使用沙盒")
):
    """
    删除文件或目录
    
    Args:
        conversation_id: 对话 ID
        path: 文件或目录路径
        use_sandbox: 是否使用沙盒
    """
    try:
        if use_sandbox:
            # 使用沙盒
            service = get_sandbox_service()
            
            # service 层会自动处理路径标准化
            success = await service.delete_file(conversation_id, path)
            
            if not success:
                raise HTTPException(status_code=500, detail="删除失败")
            
            logger.info(f"🗑️ 沙盒文件删除: {path}")
            
            return DeleteResponse(
                success=True,
                path=path,
                message="删除成功"
            )
        else:
            # 使用本地文件系统
            manager = get_workspace_manager()
            result = manager.delete_file(conversation_id, path)
            
            if not result["success"]:
                raise HTTPException(status_code=404, detail=result.get("error", "删除失败"))
            
            logger.info(f"🗑️ 本地文件删除: {path}")
            
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


# ==================== 项目管理 API ====================

@router.get("/{conversation_id}/projects", response_model=ProjectListResponse)
async def list_projects(
    conversation_id: str,
    use_sandbox: bool = Query(default=True, description="是否使用沙盒")
):
    """
    获取 workspace 中的项目列表
    
    检测规则：
    - 包含 requirements.txt / package.json / pyproject.toml 的目录
    - 包含 app.py / main.py / index.html 等入口文件的目录
    
    Args:
        conversation_id: 对话 ID
        use_sandbox: 是否使用沙盒
    """
    try:
        if use_sandbox:
            # 使用沙盒 - 列出 /home/user 目录
            service = get_sandbox_service()
            
            try:
                files = await service.list_files(conversation_id, "/home/user")
                
                projects = []
                for f in files:
                    if f.type == "directory":
                        # 检查目录内容
                        project_info = await _detect_sandbox_project(service, conversation_id, f.path, f.name)
                        if project_info:
                            projects.append(project_info)
                
                return ProjectListResponse(
                    conversation_id=conversation_id,
                    projects=projects
                )
            except SandboxNotFoundError:
                # 沙盒不存在时返回空列表
                logger.info(f"沙盒不存在，返回空项目列表: {conversation_id}")
                return ProjectListResponse(
                    conversation_id=conversation_id,
                    projects=[]
                )
        else:
            # 使用本地文件系统
            manager = get_workspace_manager()
            workspace_root = manager.get_workspace_root(conversation_id)
            
            projects = []
            
            if workspace_root.exists():
                for item in workspace_root.iterdir():
                    if item.is_dir():
                        project_info = _detect_local_project(item)
                        if project_info:
                            projects.append(project_info)
            
            return ProjectListResponse(
                conversation_id=conversation_id,
                projects=projects
            )
    
    except SandboxServiceError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"获取项目列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取项目列表失败")


@router.post("/{conversation_id}/projects/{project_name}/run", response_model=ProjectRunResponse)
async def run_project(
    conversation_id: str,
    project_name: str,
    request: ProjectRunRequest
):
    """
    运行项目
    
    Args:
        conversation_id: 对话 ID
        project_name: 项目名称
        request: 运行请求（指定技术栈）
    """
    try:
        service = get_sandbox_service()
        result = await service.run_project(
            conversation_id=conversation_id,
            project_path=project_name,
            stack=request.stack
        )
        
        return ProjectRunResponse(
            success=result.success,
            preview_url=result.preview_url,
            message=result.message,
            error=result.error
        )
    
    except SandboxNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SandboxServiceError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"运行项目失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="运行项目失败")


@router.post("/{conversation_id}/projects/{project_name}/stop")
async def stop_project(
    conversation_id: str,
    project_name: str
):
    """
    停止项目
    
    Args:
        conversation_id: 对话 ID
        project_name: 项目名称
    """
    try:
        service = get_sandbox_service()
        success = await service.stop_project(conversation_id)
        
        return {"success": success, "message": "项目已停止"}
    
    except SandboxNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SandboxServiceError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"停止项目失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="停止项目失败")


@router.get("/{conversation_id}/projects/{project_name}/logs")
async def get_project_logs(
    conversation_id: str,
    project_name: str,
    lines: int = Query(default=100, description="日志行数")
):
    """
    获取项目日志
    
    Args:
        conversation_id: 对话 ID
        project_name: 项目名称
        lines: 日志行数
    """
    try:
        service = get_sandbox_service()
        logs = await service.get_logs(conversation_id, lines)
        
        return {
            "project": project_name,
            "logs": logs
        }
    
    except SandboxNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SandboxServiceError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"获取项目日志失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取项目日志失败")


# ==================== 辅助函数 ====================

async def _detect_sandbox_project(
    service,
    conversation_id: str,
    dir_path: str,
    dir_name: str
) -> Optional[ProjectInfo]:
    """
    检测沙盒目录是否为项目
    """
    try:
        files = await service.list_files(conversation_id, dir_path)
        file_names = {f.name for f in files}
        
        project_type = None
        entry_file = None
        has_requirements = False
        
        # Python 项目检测
        if "requirements.txt" in file_names:
            has_requirements = True
            
            if "app.py" in file_names:
                # 读取 requirements.txt 判断框架
                try:
                    req_content = await service.read_file(conversation_id, f"{dir_path}/requirements.txt")
                    if "gradio" in req_content.lower():
                        project_type = "gradio"
                    elif "streamlit" in req_content.lower():
                        project_type = "streamlit"
                    elif "flask" in req_content.lower():
                        project_type = "flask"
                    elif "fastapi" in req_content.lower():
                        project_type = "fastapi"
                    else:
                        project_type = "python"
                except:
                    project_type = "python"
                entry_file = "app.py"
            elif "main.py" in file_names:
                entry_file = "main.py"
                project_type = "python"
        
        # Node.js 项目检测
        if "package.json" in file_names:
            try:
                import json
                pkg_content = await service.read_file(conversation_id, f"{dir_path}/package.json")
                pkg = json.loads(pkg_content)
                deps = pkg.get("dependencies", {})
                
                if "next" in deps:
                    project_type = "nextjs"
                elif "vue" in deps:
                    project_type = "vue"
                elif "react" in deps:
                    project_type = "react"
                else:
                    project_type = "nodejs"
            except:
                project_type = "nodejs"
        
        # 静态网页检测
        if "index.html" in file_names and not project_type:
            project_type = "static"
            entry_file = "index.html"
        
        if not project_type and not entry_file and not has_requirements:
            return None
        
        return ProjectInfo(
            name=dir_name,
            path=dir_name,
            type=project_type,
            entry_file=entry_file,
            has_requirements=has_requirements
        )
        
    except Exception as e:
        logger.warning(f"检测项目失败: {dir_path} - {e}")
        return None


def _detect_local_project(dir_path: Path) -> Optional[ProjectInfo]:
    """
    检测本地目录是否为项目
    """
    if not dir_path.is_dir():
        return None
    
    project_type = None
    entry_file = None
    has_requirements = False
    description = None
    
    # Python 项目检测
    if (dir_path / "requirements.txt").exists():
        has_requirements = True
        
        if (dir_path / "app.py").exists():
            req_content = (dir_path / "requirements.txt").read_text()
            if "gradio" in req_content.lower():
                project_type = "gradio"
            elif "streamlit" in req_content.lower():
                project_type = "streamlit"
            elif "flask" in req_content.lower():
                project_type = "flask"
            elif "fastapi" in req_content.lower():
                project_type = "fastapi"
            else:
                project_type = "python"
            entry_file = "app.py"
        elif (dir_path / "main.py").exists():
            entry_file = "main.py"
            project_type = "python"
    
    # Node.js 项目检测
    if (dir_path / "package.json").exists():
        import json
        try:
            pkg = json.loads((dir_path / "package.json").read_text())
            if "next" in pkg.get("dependencies", {}):
                project_type = "nextjs"
                entry_file = "pages/index.tsx" if (dir_path / "pages/index.tsx").exists() else "app/page.tsx"
            elif "vue" in pkg.get("dependencies", {}):
                project_type = "vue"
                entry_file = "src/App.vue"
            elif "react" in pkg.get("dependencies", {}):
                project_type = "react"
                entry_file = "src/App.tsx" if (dir_path / "src/App.tsx").exists() else "src/App.jsx"
            else:
                project_type = "nodejs"
        except:
            project_type = "nodejs"
    
    # 静态网页检测
    if (dir_path / "index.html").exists() and not project_type:
        project_type = "static"
        entry_file = "index.html"
    
    if not project_type and not entry_file and not has_requirements:
        return None
    
    # 读取 README 作为描述
    readme_files = ["README.md", "readme.md", "README.txt", "readme.txt"]
    for readme in readme_files:
        readme_path = dir_path / readme
        if readme_path.exists():
            try:
                content = readme_path.read_text(encoding='utf-8')
                description = content.split('\n')[0].strip('#').strip()[:100]
            except:
                pass
            break
    
    return ProjectInfo(
        name=dir_path.name,
        path=dir_path.name,
        type=project_type,
        entry_file=entry_file,
        description=description,
        has_requirements=has_requirements
    )

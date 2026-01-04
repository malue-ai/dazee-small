"""
Workspace API Router

提供给前端的 Workspace 文件管理接口：
- GET  /workspace/{conv_id}/files      - 获取文件列表
- GET  /workspace/{conv_id}/files/{path} - 获取/下载文件
- POST /workspace/{conv_id}/files      - 上传文件
- DELETE /workspace/{conv_id}/files/{path} - 删除文件
- GET  /workspace/{conv_id}/projects   - 获取项目列表
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from logger import get_logger
from core.workspace_manager import get_workspace_manager, FileInfo

logger = get_logger("workspace_router")

router = APIRouter(prefix="/api/v1/workspace", tags=["workspace"])


# ==================== 请求/响应模型 ====================

class FileItemResponse(BaseModel):
    """文件项响应"""
    path: str
    type: str  # "file" or "directory"
    size: Optional[int] = None
    modified_at: Optional[str] = None
    children: Optional[List['FileItemResponse']] = None


class FileListResponse(BaseModel):
    """文件列表响应"""
    conversation_id: str
    files: List[FileItemResponse]
    total_size: Optional[int] = None


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


# ==================== API 端点 ====================

@router.get("/{conversation_id}/files", response_model=FileListResponse)
async def list_files(
    conversation_id: str,
    path: str = Query(default=".", description="目录路径（相对于 workspace）"),
    tree: bool = Query(default=False, description="是否返回树形结构")
):
    """
    获取 workspace 文件列表
    
    Args:
        conversation_id: 对话 ID
        path: 目录路径
        tree: 是否返回递归树形结构
    """
    try:
        manager = get_workspace_manager()
        
        if tree:
            items = manager.list_dir_tree(conversation_id, path)
        else:
            items = manager.list_dir(conversation_id, path)
        
        # 转换为响应格式
        def convert_item(item: FileInfo) -> FileItemResponse:
            return FileItemResponse(
                path=item.path,
                type=item.type,
                size=item.size,
                modified_at=item.modified_at,
                children=[convert_item(c) for c in item.children] if item.children else None
            )
        
        files = [convert_item(item) for item in items]
        
        # 计算总大小
        total_size = manager.get_workspace_size(conversation_id)
        
        return FileListResponse(
            conversation_id=conversation_id,
            files=files,
            total_size=total_size
        )
    
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
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
    获取文件内容或下载文件
    
    Args:
        conversation_id: 对话 ID
        path: 文件路径
        download: 是否作为下载返回
    """
    try:
        manager = get_workspace_manager()
        full_path = manager.resolve_path(conversation_id, path)
        
        if not full_path.exists():
            raise HTTPException(status_code=404, detail=f"文件不存在: {path}")
        
        if not full_path.is_file():
            raise HTTPException(status_code=400, detail=f"不是文件: {path}")
        
        # 判断文件类型
        suffix = full_path.suffix.lower()
        text_extensions = {'.txt', '.py', '.js', '.ts', '.html', '.css', '.json', '.md', '.yaml', '.yml', '.xml', '.csv'}
        
        if download or suffix not in text_extensions:
            # 作为下载返回
            return FileResponse(
                path=str(full_path),
                filename=full_path.name,
                media_type="application/octet-stream"
            )
        else:
            # 返回文本内容
            content = full_path.read_text(encoding='utf-8')
            return Response(
                content=content,
                media_type="text/plain; charset=utf-8"
            )
    
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"获取文件失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取文件失败")


@router.post("/{conversation_id}/files", response_model=UploadResponse)
async def upload_file(
    conversation_id: str,
    file: UploadFile = File(...),
    path: Optional[str] = Query(default=None, description="保存路径（相对于 workspace）")
):
    """
    上传文件到 workspace
    
    Args:
        conversation_id: 对话 ID
        file: 上传的文件
        path: 保存路径（默认为文件名）
    """
    try:
        manager = get_workspace_manager()
        
        # 确定保存路径
        if path:
            save_path = path
        else:
            save_path = file.filename
        
        # 读取文件内容
        content = await file.read()
        
        # 写入文件
        result = manager.write_file(conversation_id, save_path, content)
        
        logger.info(f"📤 文件上传成功: {save_path} ({result['size']} bytes)")
        
        return UploadResponse(
            success=True,
            path=save_path,
            size=result["size"]
        )
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"上传文件失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="上传文件失败")


@router.delete("/{conversation_id}/files/{path:path}", response_model=DeleteResponse)
async def delete_file(
    conversation_id: str,
    path: str
):
    """
    删除文件或目录
    
    Args:
        conversation_id: 对话 ID
        path: 文件或目录路径
    """
    try:
        manager = get_workspace_manager()
        result = manager.delete_file(conversation_id, path)
        
        if not result["success"]:
            raise HTTPException(status_code=404, detail=result.get("error", "删除失败"))
        
        logger.info(f"🗑️ 文件删除成功: {path}")
        
        return DeleteResponse(
            success=True,
            path=path,
            message="删除成功"
        )
    
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"删除文件失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="删除文件失败")


@router.get("/{conversation_id}/projects", response_model=ProjectListResponse)
async def list_projects(conversation_id: str):
    """
    获取 workspace 中的项目列表
    
    检测规则：
    - 包含 requirements.txt / package.json / pyproject.toml 的目录
    - 包含 app.py / main.py / index.html 等入口文件的目录
    
    Args:
        conversation_id: 对话 ID
    """
    try:
        manager = get_workspace_manager()
        workspace_root = manager.get_workspace_root(conversation_id)
        
        projects = []
        
        # 遍历 workspace 根目录
        if workspace_root.exists():
            for item in workspace_root.iterdir():
                if item.is_dir():
                    project_info = _detect_project(item)
                    if project_info:
                        projects.append(project_info)
        
        return ProjectListResponse(
            conversation_id=conversation_id,
            projects=projects
        )
    
    except Exception as e:
        logger.error(f"获取项目列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="获取项目列表失败")


# ==================== 辅助函数 ====================

def _detect_project(dir_path: Path) -> Optional[ProjectInfo]:
    """
    检测目录是否为项目
    
    Args:
        dir_path: 目录路径
        
    Returns:
        ProjectInfo 或 None
    """
    if not dir_path.is_dir():
        return None
    
    # 检测项目类型和入口文件
    project_type = None
    entry_file = None
    has_requirements = False
    description = None
    
    # Python 项目检测
    if (dir_path / "requirements.txt").exists():
        has_requirements = True
        
        # 检测框架
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
    
    # 如果没有检测到有效的项目特征，返回 None
    if not project_type and not entry_file and not has_requirements:
        return None
    
    # 读取 README 作为描述
    readme_files = ["README.md", "readme.md", "README.txt", "readme.txt"]
    for readme in readme_files:
        readme_path = dir_path / readme
        if readme_path.exists():
            try:
                content = readme_path.read_text(encoding='utf-8')
                # 取第一行或前 100 字符作为描述
                description = content.split('\n')[0].strip('#').strip()[:100]
            except:
                pass
            break
    
    return ProjectInfo(
        name=dir_path.name,
        path=dir_path.name,  # 相对于 workspace
        type=project_type,
        entry_file=entry_file,
        description=description,
        has_requirements=has_requirements
    )


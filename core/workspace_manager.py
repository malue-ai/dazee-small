"""
工作区管理器 V2

设计原则：
1. workspace 完全自由 - 不预设任何目录结构，Agent 想怎么组织就怎么组织
2. Agent 使用相对路径 - Agent 不需要知道真实的文件系统路径
3. 路径安全 - 防止路径穿越攻击

目录结构：
workspace/
  conversations/
    {conversation_id}/
      workspace/          ← Agent 的工作区（完全自由）
        ...               ← Agent 创建的任何文件/目录
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
from dataclasses import dataclass

from logger import get_logger

logger = get_logger("workspace_manager")


@dataclass
class FileInfo:
    """文件信息"""
    path: str           # 相对路径
    type: str           # "file" 或 "directory"
    size: Optional[int] = None
    modified_at: Optional[str] = None
    children: Optional[List['FileInfo']] = None


class WorkspaceManager:
    """
    工作区管理器
    
    核心功能：
    - 管理 conversation 级别的 workspace
    - 提供安全的文件操作（防止路径穿越）
    - 支持 Agent 的 File Tools
    """
    
    def __init__(self, base_dir: str = "./workspace"):
        """
        初始化工作区管理器
        
        Args:
            base_dir: 全局 workspace 根目录
        """
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"✅ WorkspaceManager 初始化完成，根目录: {self.base_dir}")
    
    # ==================== 路径管理 ====================
    
    def get_workspace_root(self, conversation_id: str) -> Path:
        """
        获取 conversation 的 workspace 根目录
        
        Args:
            conversation_id: 对话 ID
            
        Returns:
            workspace 根目录的绝对路径
        """
        workspace_root = self.base_dir / "conversations" / conversation_id / "workspace"
        workspace_root.mkdir(parents=True, exist_ok=True)
        return workspace_root
    
    def resolve_path(self, conversation_id: str, relative_path: str) -> Path:
        """
        解析相对路径为绝对路径（包含安全检查）
        
        Args:
            conversation_id: 对话 ID
            relative_path: 相对于 workspace 的路径
            
        Returns:
            绝对路径
            
        Raises:
            ValueError: 路径不安全（穿越攻击）
        """
        workspace_root = self.get_workspace_root(conversation_id)
        
        # 标准化路径
        if relative_path.startswith("/"):
            relative_path = relative_path[1:]
        
        full_path = (workspace_root / relative_path).resolve()
        
        # 安全检查：确保路径在 workspace 内
        try:
            full_path.relative_to(workspace_root)
        except ValueError:
            raise ValueError(f"非法路径：不能访问工作区外的文件 ({relative_path})")
        
        return full_path
    
    def get_relative_path(self, conversation_id: str, absolute_path: Path) -> str:
        """
        将绝对路径转换为相对于 workspace 的路径
        
        Args:
            conversation_id: 对话 ID
            absolute_path: 绝对路径
            
        Returns:
            相对路径
        """
        workspace_root = self.get_workspace_root(conversation_id)
        return str(absolute_path.relative_to(workspace_root))
    
    # ==================== 文件操作 ====================
    
    def read_file(self, conversation_id: str, path: str) -> str:
        """
        读取文件内容
        
        Args:
            conversation_id: 对话 ID
            path: 相对于 workspace 的文件路径
            
        Returns:
            文件内容（文本）
            
        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 路径不安全
        """
        full_path = self.resolve_path(conversation_id, path)
        
        if not full_path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")
        
        if not full_path.is_file():
            raise ValueError(f"不是文件: {path}")
        
        return full_path.read_text(encoding="utf-8")
    
    def read_file_bytes(self, conversation_id: str, path: str) -> bytes:
        """
        读取文件内容（二进制）
        
        Args:
            conversation_id: 对话 ID
            path: 相对于 workspace 的文件路径
            
        Returns:
            文件内容（二进制）
        """
        full_path = self.resolve_path(conversation_id, path)
        
        if not full_path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")
        
        if not full_path.is_file():
            raise ValueError(f"不是文件: {path}")
        
        return full_path.read_bytes()
    
    def write_file(
        self, 
        conversation_id: str, 
        path: str, 
        content: Union[str, bytes]
    ) -> Dict[str, Any]:
        """
        写入文件（自动创建父目录）
        
        Args:
            conversation_id: 对话 ID
            path: 相对于 workspace 的文件路径
            content: 文件内容（文本或二进制）
            
        Returns:
            写入结果
        """
        full_path = self.resolve_path(conversation_id, path)
        
        # 自动创建父目录
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 写入文件
        if isinstance(content, bytes):
            full_path.write_bytes(content)
        else:
            full_path.write_text(content, encoding="utf-8")
        
        logger.debug(f"✅ 文件已写入: {path}")
        
        return {
            "success": True,
            "path": path,
            "size": full_path.stat().st_size
        }
    
    def delete_file(self, conversation_id: str, path: str) -> Dict[str, Any]:
        """
        删除文件或目录
        
        Args:
            conversation_id: 对话 ID
            path: 相对于 workspace 的路径
            
        Returns:
            删除结果
        """
        full_path = self.resolve_path(conversation_id, path)
        
        if not full_path.exists():
            return {
                "success": False,
                "error": f"文件不存在: {path}"
            }
        
        if full_path.is_file():
            full_path.unlink()
        elif full_path.is_dir():
            shutil.rmtree(full_path)
        
        logger.debug(f"🗑️ 已删除: {path}")
        
        return {
            "success": True,
            "path": path
        }
    
    def file_exists(self, conversation_id: str, path: str) -> bool:
        """
        检查文件是否存在
        
        Args:
            conversation_id: 对话 ID
            path: 相对于 workspace 的路径
            
        Returns:
            是否存在
        """
        try:
            full_path = self.resolve_path(conversation_id, path)
            return full_path.exists()
        except ValueError:
            return False
    
    def list_dir(
        self, 
        conversation_id: str, 
        path: str = "."
    ) -> List[FileInfo]:
        """
        列出目录内容
        
        Args:
            conversation_id: 对话 ID
            path: 相对于 workspace 的目录路径
            
        Returns:
            文件信息列表
        """
        full_path = self.resolve_path(conversation_id, path)
        
        if not full_path.exists():
            raise FileNotFoundError(f"目录不存在: {path}")
        
        if not full_path.is_dir():
            raise ValueError(f"不是目录: {path}")
        
        items = []
        workspace_root = self.get_workspace_root(conversation_id)
        
        for item in sorted(full_path.iterdir()):
            relative_path = str(item.relative_to(workspace_root))
            stat = item.stat()
            
            file_info = FileInfo(
                path=relative_path,
                type="directory" if item.is_dir() else "file",
                size=stat.st_size if item.is_file() else None,
                modified_at=datetime.fromtimestamp(stat.st_mtime).isoformat()
            )
            
            items.append(file_info)
        
        return items
    
    def list_dir_tree(
        self, 
        conversation_id: str, 
        path: str = ".",
        max_depth: int = 3
    ) -> List[FileInfo]:
        """
        递归列出目录树
        
        Args:
            conversation_id: 对话 ID
            path: 相对于 workspace 的目录路径
            max_depth: 最大递归深度
            
        Returns:
            文件信息列表（包含 children）
        """
        def _build_tree(current_path: Path, depth: int) -> List[FileInfo]:
            if depth > max_depth:
                return []
            
            items = []
            workspace_root = self.get_workspace_root(conversation_id)
            
            try:
                for item in sorted(current_path.iterdir()):
                    relative_path = str(item.relative_to(workspace_root))
                    stat = item.stat()
                    
                    file_info = FileInfo(
                        path=relative_path,
                        type="directory" if item.is_dir() else "file",
                        size=stat.st_size if item.is_file() else None,
                        modified_at=datetime.fromtimestamp(stat.st_mtime).isoformat()
                    )
                    
                    if item.is_dir():
                        file_info.children = _build_tree(item, depth + 1)
                    
                    items.append(file_info)
            except PermissionError:
                pass
            
            return items
        
        full_path = self.resolve_path(conversation_id, path)
        
        if not full_path.exists():
            raise FileNotFoundError(f"目录不存在: {path}")
        
        return _build_tree(full_path, 1)
    
    # ==================== 批量操作 ====================
    
    def copy_file(
        self, 
        conversation_id: str, 
        src_path: str, 
        dst_path: str
    ) -> Dict[str, Any]:
        """
        复制文件
        
        Args:
            conversation_id: 对话 ID
            src_path: 源路径
            dst_path: 目标路径
            
        Returns:
            复制结果
        """
        src_full = self.resolve_path(conversation_id, src_path)
        dst_full = self.resolve_path(conversation_id, dst_path)
        
        if not src_full.exists():
            return {
                "success": False,
                "error": f"源文件不存在: {src_path}"
            }
        
        dst_full.parent.mkdir(parents=True, exist_ok=True)
        
        if src_full.is_file():
            shutil.copy2(src_full, dst_full)
        else:
            shutil.copytree(src_full, dst_full)
        
        return {
            "success": True,
            "src": src_path,
            "dst": dst_path
        }
    
    def move_file(
        self, 
        conversation_id: str, 
        src_path: str, 
        dst_path: str
    ) -> Dict[str, Any]:
        """
        移动/重命名文件
        
        Args:
            conversation_id: 对话 ID
            src_path: 源路径
            dst_path: 目标路径
            
        Returns:
            移动结果
        """
        src_full = self.resolve_path(conversation_id, src_path)
        dst_full = self.resolve_path(conversation_id, dst_path)
        
        if not src_full.exists():
            return {
                "success": False,
                "error": f"源文件不存在: {src_path}"
            }
        
        dst_full.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_full), str(dst_full))
        
        return {
            "success": True,
            "src": src_path,
            "dst": dst_path
        }
    
    # ==================== 工具方法 ====================
    
    def get_workspace_size(self, conversation_id: str) -> int:
        """
        计算 workspace 总大小（字节）
        
        Args:
            conversation_id: 对话 ID
            
        Returns:
            总大小
        """
        workspace_root = self.get_workspace_root(conversation_id)
        total_size = 0
        
        for path in workspace_root.rglob("*"):
            if path.is_file():
                total_size += path.stat().st_size
        
        return total_size
    
    def clean_workspace(self, conversation_id: str) -> Dict[str, Any]:
        """
        清空 workspace（删除所有文件）
        
        Args:
            conversation_id: 对话 ID
            
        Returns:
            清理结果
        """
        workspace_root = self.get_workspace_root(conversation_id)
        
        deleted_count = 0
        for item in workspace_root.iterdir():
            if item.is_file():
                item.unlink()
                deleted_count += 1
            elif item.is_dir():
                shutil.rmtree(item)
                deleted_count += 1
        
        logger.info(f"🧹 Workspace 已清空: {conversation_id}，删除 {deleted_count} 项")
        
        return {
            "success": True,
            "deleted_count": deleted_count
        }


# 全局单例
_workspace_manager: Optional[WorkspaceManager] = None


def get_workspace_manager(base_dir: str = "./workspace") -> WorkspaceManager:
    """
    获取全局 WorkspaceManager 实例
    
    Args:
        base_dir: 工作区根目录
        
    Returns:
        WorkspaceManager 实例
    """
    global _workspace_manager
    if _workspace_manager is None:
        _workspace_manager = WorkspaceManager(base_dir)
    return _workspace_manager

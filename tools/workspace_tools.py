"""
Workspace File Tools - Agent 文件操作工具

提供给 Agent 的文件操作能力：
- read_file: 读取文件内容
- write_file: 写入文件
- list_dir: 列出目录内容
- delete_file: 删除文件
- file_exists: 检查文件是否存在

设计原则：
- Agent 使用相对路径（不感知真实路径）
- 所有操作限制在 conversation 的 workspace 内
- 路径安全检查，防止穿越攻击
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from logger import get_logger
from core.workspace_manager import get_workspace_manager, FileInfo

logger = get_logger("workspace_tools")


@dataclass
class ToolContext:
    """工具执行上下文"""
    conversation_id: str
    message_id: Optional[str] = None
    user_id: Optional[str] = None


class WorkspaceReadFileTool:
    """
    读取文件工具
    
    用于 Agent 读取 workspace 中的文件内容
    """
    
    name = "read_file"
    description = "读取工作区中的文件内容"
    
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "文件路径（相对于工作区根目录）"
            }
        },
        "required": ["path"]
    }
    
    async def execute(
        self, 
        context: ToolContext,
        path: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行读取文件
        
        Args:
            context: 工具上下文（包含 conversation_id）
            path: 相对路径
            
        Returns:
            {"success": True, "content": "..."}
        """
        try:
            manager = get_workspace_manager()
            content = manager.read_file(context.conversation_id, path)
            
            return {
                "success": True,
                "path": path,
                "content": content,
                "size": len(content)
            }
        
        except FileNotFoundError as e:
            return {
                "success": False,
                "error": str(e)
            }
        except ValueError as e:
            return {
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"读取文件失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"读取文件失败: {str(e)}"
            }


class WorkspaceWriteFileTool:
    """
    写入文件工具
    
    用于 Agent 向 workspace 写入文件
    """
    
    name = "write_file"
    description = "写入文件到工作区（自动创建父目录）"
    
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "文件路径（相对于工作区根目录）"
            },
            "content": {
                "type": "string",
                "description": "文件内容"
            }
        },
        "required": ["path", "content"]
    }
    
    async def execute(
        self, 
        context: ToolContext,
        path: str,
        content: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行写入文件
        
        Args:
            context: 工具上下文
            path: 相对路径
            content: 文件内容
            
        Returns:
            {"success": True, "path": "...", "size": 1024}
        """
        try:
            manager = get_workspace_manager()
            result = manager.write_file(context.conversation_id, path, content)
            
            logger.info(f"✅ Agent 写入文件: {path} ({result['size']} bytes)")
            
            return result
        
        except ValueError as e:
            return {
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"写入文件失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"写入文件失败: {str(e)}"
            }


class WorkspaceListDirTool:
    """
    列出目录工具
    
    用于 Agent 查看 workspace 的目录结构
    """
    
    name = "list_dir"
    description = "列出工作区目录的内容"
    
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "目录路径（相对于工作区根目录，默认为根目录 '.'）",
                "default": "."
            }
        },
        "required": []
    }
    
    async def execute(
        self, 
        context: ToolContext,
        path: str = ".",
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行列出目录
        
        Args:
            context: 工具上下文
            path: 目录路径
            
        Returns:
            {"success": True, "items": [...]}
        """
        try:
            manager = get_workspace_manager()
            items = manager.list_dir(context.conversation_id, path)
            
            # 转换为字典格式
            items_dict = [
                {
                    "path": item.path,
                    "type": item.type,
                    "size": item.size,
                    "modified_at": item.modified_at
                }
                for item in items
            ]
            
            return {
                "success": True,
                "path": path,
                "items": items_dict,
                "count": len(items_dict)
            }
        
        except FileNotFoundError as e:
            return {
                "success": False,
                "error": str(e)
            }
        except ValueError as e:
            return {
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"列出目录失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"列出目录失败: {str(e)}"
            }


class WorkspaceDeleteFileTool:
    """
    删除文件工具
    
    用于 Agent 删除 workspace 中的文件或目录
    """
    
    name = "delete_file"
    description = "删除工作区中的文件或目录"
    
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "文件或目录路径（相对于工作区根目录）"
            }
        },
        "required": ["path"]
    }
    
    async def execute(
        self, 
        context: ToolContext,
        path: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行删除文件
        
        Args:
            context: 工具上下文
            path: 路径
            
        Returns:
            {"success": True, "path": "..."}
        """
        try:
            manager = get_workspace_manager()
            result = manager.delete_file(context.conversation_id, path)
            
            if result["success"]:
                logger.info(f"🗑️ Agent 删除文件: {path}")
            
            return result
        
        except ValueError as e:
            return {
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"删除文件失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"删除文件失败: {str(e)}"
            }


class WorkspaceFileExistsTool:
    """
    检查文件存在工具
    
    用于 Agent 检查文件是否存在
    """
    
    name = "file_exists"
    description = "检查工作区中的文件或目录是否存在"
    
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "文件或目录路径（相对于工作区根目录）"
            }
        },
        "required": ["path"]
    }
    
    async def execute(
        self, 
        context: ToolContext,
        path: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        检查文件是否存在
        
        Args:
            context: 工具上下文
            path: 路径
            
        Returns:
            {"success": True, "exists": True/False}
        """
        try:
            manager = get_workspace_manager()
            exists = manager.file_exists(context.conversation_id, path)
            
            return {
                "success": True,
                "path": path,
                "exists": exists
            }
        
        except Exception as e:
            logger.error(f"检查文件存在失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"检查失败: {str(e)}"
            }


# ==================== 工具注册 ====================

# 所有 Workspace 工具
WORKSPACE_TOOLS = [
    WorkspaceReadFileTool(),
    WorkspaceWriteFileTool(),
    WorkspaceListDirTool(),
    WorkspaceDeleteFileTool(),
    WorkspaceFileExistsTool(),
]


def get_workspace_tools() -> List[Any]:
    """获取所有 Workspace 工具"""
    return WORKSPACE_TOOLS


def get_workspace_tool_definitions() -> List[Dict[str, Any]]:
    """
    获取工具定义（用于 Claude API）
    
    Returns:
        工具定义列表
    """
    definitions = []
    
    for tool in WORKSPACE_TOOLS:
        definitions.append({
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema
        })
    
    return definitions


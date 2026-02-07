"""
项目管理器 - ProjectManager

项目隔离：独立 context、knowledge、playbook、skills_config。
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from logger import get_logger

logger = get_logger(__name__)


class ProjectManager:
    """
    项目管理器

    创建/切换/删除项目，项目模板：写稿搭子、表格搭子、研究搭子、办公搭子。
    """

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self.base_dir = Path(base_dir) if base_dir else None

    def create_project(self, name: str, template: str = "default") -> str:
        """创建项目，返回 project_id"""
        return ""

    def switch_project(self, project_id: str) -> None:
        """切换当前项目"""
        pass

    def delete_project(self, project_id: str) -> None:
        """删除项目"""
        pass

    def list_projects(self) -> List[Dict[str, Any]]:
        """项目列表"""
        return []

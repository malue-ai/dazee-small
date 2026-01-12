"""
Worker 配置管理器

管理已确认的 Worker 配置，供 Data Plane 读取

职责：
- 保存已确认的 Worker 配置
- 版本管理
- 热更新通知
"""

import json
import yaml
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from logger import get_logger

logger = get_logger("worker_config_manager")


@dataclass
class WorkerConfig:
    """Worker 配置"""
    specialization: str
    system_prompt: str
    suggested_tools: List[str]
    quality_checklist: List[str]
    
    # 元数据
    version: int = 1
    confirmed_at: Optional[datetime] = None
    confirmed_by: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "specialization": self.specialization,
            "system_prompt": self.system_prompt,
            "suggested_tools": self.suggested_tools,
            "quality_checklist": self.quality_checklist,
            "version": self.version,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "confirmed_by": self.confirmed_by
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "WorkerConfig":
        return cls(
            specialization=data["specialization"],
            system_prompt=data["system_prompt"],
            suggested_tools=data.get("suggested_tools", []),
            quality_checklist=data.get("quality_checklist", []),
            version=data.get("version", 1),
            confirmed_at=datetime.fromisoformat(data["confirmed_at"]) if data.get("confirmed_at") else None,
            confirmed_by=data.get("confirmed_by")
        )


class WorkerConfigManager:
    """
    Worker 配置管理器
    
    管理已确认的 Worker 配置
    
    存储结构：
    instances/{instance_name}/workers/
    ├── research.yaml
    ├── document.yaml
    ├── data_analysis.yaml
    └── code.yaml
    
    使用示例：
        manager = WorkerConfigManager(instances_dir="./instances")
        
        # 保存配置
        await manager.save_config(
            instance_name="test_agent",
            config=WorkerConfig(
                specialization="research",
                system_prompt="...",
                ...
            )
        )
        
        # 读取配置
        config = await manager.load_config(
            instance_name="test_agent",
            specialization="research"
        )
    """
    
    def __init__(
        self,
        instances_dir: str = None
    ):
        """
        初始化配置管理器
        
        Args:
            instances_dir: instances 目录路径
        """
        if instances_dir:
            self.instances_dir = Path(instances_dir)
        else:
            # 默认路径
            self.instances_dir = Path(__file__).parent.parent.parent / "instances"
        
        logger.info(f"WorkerConfigManager 初始化完成: {self.instances_dir}")
    
    def _get_workers_dir(self, instance_name: str) -> Path:
        """获取 Worker 配置目录"""
        workers_dir = self.instances_dir / instance_name / "workers"
        workers_dir.mkdir(parents=True, exist_ok=True)
        return workers_dir
    
    async def save_config(
        self,
        instance_name: str,
        config: WorkerConfig
    ) -> Path:
        """
        保存 Worker 配置
        
        Args:
            instance_name: 实例名称
            config: Worker 配置
            
        Returns:
            配置文件路径
        """
        workers_dir = self._get_workers_dir(instance_name)
        config_path = workers_dir / f"{config.specialization}.yaml"
        
        # 检查是否需要更新版本
        if config_path.exists():
            existing = await self.load_config(instance_name, config.specialization)
            if existing:
                config.version = existing.version + 1
        
        # 保存
        data = config.to_dict()
        
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        
        logger.info(
            f"Worker 配置已保存: {instance_name}/{config.specialization} "
            f"(version={config.version})"
        )
        
        return config_path
    
    async def load_config(
        self,
        instance_name: str,
        specialization: str
    ) -> Optional[WorkerConfig]:
        """
        加载 Worker 配置
        
        Args:
            instance_name: 实例名称
            specialization: Worker 类型
            
        Returns:
            WorkerConfig 或 None
        """
        workers_dir = self._get_workers_dir(instance_name)
        config_path = workers_dir / f"{specialization}.yaml"
        
        if not config_path.exists():
            return None
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                return WorkerConfig.from_dict(data)
        except Exception as e:
            logger.warning(f"加载 Worker 配置失败: {config_path} - {e}")
            return None
    
    async def list_configs(
        self,
        instance_name: str
    ) -> List[WorkerConfig]:
        """
        列出实例的所有 Worker 配置
        
        Args:
            instance_name: 实例名称
            
        Returns:
            WorkerConfig 列表
        """
        workers_dir = self._get_workers_dir(instance_name)
        
        configs = []
        for config_path in workers_dir.glob("*.yaml"):
            specialization = config_path.stem
            config = await self.load_config(instance_name, specialization)
            if config:
                configs.append(config)
        
        return configs
    
    async def delete_config(
        self,
        instance_name: str,
        specialization: str
    ) -> bool:
        """
        删除 Worker 配置
        
        Args:
            instance_name: 实例名称
            specialization: Worker 类型
            
        Returns:
            是否成功
        """
        workers_dir = self._get_workers_dir(instance_name)
        config_path = workers_dir / f"{specialization}.yaml"
        
        if config_path.exists():
            config_path.unlink()
            logger.info(f"Worker 配置已删除: {instance_name}/{specialization}")
            return True
        
        return False
    
    def get_config_path(
        self,
        instance_name: str,
        specialization: str
    ) -> Path:
        """获取配置文件路径"""
        workers_dir = self._get_workers_dir(instance_name)
        return workers_dir / f"{specialization}.yaml"

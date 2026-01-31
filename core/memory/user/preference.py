"""
Preference Memory - 用户偏好记忆（预留）

职责：
- 存储用户的个人偏好
- 存储用户的常用设置
- 支持学习用户行为

设计原则：
- 长期记忆：持久化到文件/数据库
- 用户隔离：每个用户独立的偏好库
- 可更新：支持增量学习用户偏好
"""

import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
from logger import get_logger

from ..base import BaseScopedMemory, MemoryConfig, MemoryScope, StorageBackend

logger = get_logger("memory.user.preference")


class PreferenceMemory(BaseScopedMemory):
    """
    用户偏好记忆（预留）
    
    存储内容：
    - 用户偏好设置
    - 常用工具/操作
    - 输出风格偏好
    
    Args:
        user_id: 用户 ID
        storage_path: 存储路径
    """
    
    def __init__(
        self,
        user_id: Optional[str] = None,
        storage_path: Optional[str] = None
    ):
        config = MemoryConfig(
            scope=MemoryScope.USER,
            backend=StorageBackend.FILE if storage_path else StorageBackend.MEMORY,
            storage_path=storage_path
        )
        super().__init__(scope_id=user_id, config=config)
        
        self.user_id = user_id
        self.storage_path = Path(storage_path) if storage_path else None
        self.preferences: Dict[str, Any] = {}
        
        # 如果有存储路径，加载偏好
        if self.storage_path and self.storage_path.exists():
            self._load()
    
    def set_preference(self, key: str, value: Any):
        """
        设置偏好
        
        Args:
            key: 偏好 key
            value: 偏好值
        """
        self.preferences[key] = {
            "value": value,
            "updated_at": datetime.now().isoformat()
        }
        
        if self.storage_path:
            self._save()
    
    def get_preference(self, key: str, default: Any = None) -> Any:
        """
        获取偏好
        
        Args:
            key: 偏好 key
            default: 默认值
        """
        pref = self.preferences.get(key)
        if pref:
            return pref.get("value", default)
        return default
    
    def get_all_preferences(self) -> Dict[str, Any]:
        """获取所有偏好"""
        return {
            k: v.get("value")
            for k, v in self.preferences.items()
        }
    
    def delete_preference(self, key: str):
        """删除偏好"""
        if key in self.preferences:
            del self.preferences[key]
            if self.storage_path:
                self._save()
    
    def clear(self):
        """清空所有偏好"""
        self.preferences.clear()
        if self.storage_path:
            self._save()
    
    def _save(self):
        """持久化到文件"""
        if not self.storage_path:
            return
        
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump(self.preferences, f, ensure_ascii=False, indent=2)
    
    def _load(self):
        """从文件加载"""
        if not self.storage_path or not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                self.preferences = json.load(f)
        except Exception as e:
            logger.warning(f"[PreferenceMemory] 加载失败: {e}")
            self.preferences = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        base = super().to_dict()
        base.update({
            "user_id": self.user_id,
            "preferences_count": len(self.preferences)
        })
        return base


def create_preference_memory(
    user_id: Optional[str] = None,
    storage_dir: Optional[str] = None
) -> PreferenceMemory:
    """
    创建 PreferenceMemory 实例
    
    Args:
        user_id: 用户 ID
        storage_dir: 存储目录
    """
    storage_path = None
    if storage_dir:
        if user_id:
            storage_path = str(Path(storage_dir) / "users" / user_id / "preference.json")
        else:
            storage_path = str(Path(storage_dir) / "preference.json")
    
    return PreferenceMemory(user_id=user_id, storage_path=storage_path)


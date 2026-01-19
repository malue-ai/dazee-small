"""
Knowledge Store（JSON 版）
------------------------------------------------------------
试验阶段不引入数据库，用 JSON 文件持久化：
- user_id / conversation_id 的基础元数据
-（预留）Ragie partition / document 的映射信息

注意：
- 这里“只管存取”，不包含 Ragie 调用逻辑
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from utils.json_file_store import JsonFileStore, create_default_knowledge_store_dict


def _now_iso() -> str:
    return datetime.now().isoformat()


@dataclass
class KnowledgeStore:
    store: JsonFileStore

    def touch_user(self, user_id: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """确保 user 存在，并更新 last_seen。"""
        if not user_id:
            return

        def _mutate(data: Dict[str, Any]):
            users = data.setdefault("users", {})
            user = users.get(user_id)
            if not user:
                users[user_id] = {
                    "created_at": _now_iso(),
                    "last_seen_at": _now_iso(),
                    "metadata": metadata or {}
                }
            else:
                user["last_seen_at"] = _now_iso()
                if metadata:
                    user_meta = user.setdefault("metadata", {})
                    user_meta.update(metadata)

        self.store.update(_mutate)

    def touch_conversation(
        self,
        conversation_id: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """确保 conversation 存在，并更新 last_seen。"""
        if not conversation_id:
            return

        def _mutate(data: Dict[str, Any]):
            conversations = data.setdefault("conversations", {})
            conv = conversations.get(conversation_id)
            if not conv:
                conversations[conversation_id] = {
                    "created_at": _now_iso(),
                    "last_seen_at": _now_iso(),
                    "user_id": user_id,
                    "session_id": session_id,
                    "metadata": metadata or {}
                }
            else:
                conv["last_seen_at"] = _now_iso()
                if user_id:
                    conv["user_id"] = user_id
                if session_id:
                    conv["session_id"] = session_id
                if metadata:
                    conv_meta = conv.setdefault("metadata", {})
                    conv_meta.update(metadata)

        self.store.update(_mutate)

    def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """读取 conversation 信息。"""
        data = self.store.read()
        return (data.get("conversations") or {}).get(conversation_id)
    
    # ==================== Ragie 相关方法 ====================
    
    def get_or_create_user(self, user_id: str) -> Dict[str, Any]:
        """获取或创建用户，并自动创建 Ragie partition"""
        data = self.store.read()
        users = data.setdefault("users", {})
        
        user = users.get(user_id)
        if user and "partition_id" in user:
            return user
        
        # 创建新用户或补充 partition_id
        partition_id = f"partition_{user_id}"
        
        def _mutate(data: Dict[str, Any]):
            users = data.setdefault("users", {})
            if user_id not in users:
                users[user_id] = {
                    "user_id": user_id,
                    "partition_id": partition_id,
                    "created_at": _now_iso(),
                    "last_seen_at": _now_iso(),
                    "documents": []
                }
            else:
                users[user_id]["partition_id"] = partition_id
                users[user_id]["last_seen_at"] = _now_iso()
        
        self.store.update(_mutate)
        data = self.store.read()
        return data["users"][user_id]
    
    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户信息"""
        data = self.store.read()
        return data.get("users", {}).get(user_id)
    
    def add_document(
        self,
        user_id: str,
        document_id: str,
        filename: str,
        status: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """添加文档记录"""
        def _mutate(data: Dict[str, Any]):
            users = data.setdefault("users", {})
            user = users.get(user_id)
            if not user:
                return
            
            documents = user.setdefault("documents", [])
            documents.append({
                "document_id": document_id,
                "filename": filename,
                "status": status,
                "metadata": metadata or {},
                "created_at": _now_iso(),
                "updated_at": _now_iso()
            })
        
        self.store.update(_mutate)
    
    def get_user_documents(self, user_id: str) -> list:
        """获取用户的所有文档"""
        data = self.store.read()
        user = data.get("users", {}).get(user_id)
        if not user:
            return []
        return user.get("documents", [])
    
    def get_document(self, user_id: str, document_id: str) -> Optional[Dict[str, Any]]:
        """获取特定文档"""
        documents = self.get_user_documents(user_id)
        for doc in documents:
            if doc.get("document_id") == document_id:
                return doc
        return None
    
    def update_document_status(self, user_id: str, document_id: str, status: str) -> None:
        """更新文档状态"""
        def _mutate(data: Dict[str, Any]):
            users = data.setdefault("users", {})
            user = users.get(user_id)
            if not user:
                return
            
            documents = user.get("documents", [])
            for doc in documents:
                if doc.get("document_id") == document_id:
                    doc["status"] = status
                    doc["updated_at"] = _now_iso()
                    break
        
        self.store.update(_mutate)
    
    def update_document_metadata(self, user_id: str, document_id: str, metadata: Dict[str, Any]) -> None:
        """更新文档元数据"""
        def _mutate(data: Dict[str, Any]):
            users = data.setdefault("users", {})
            user = users.get(user_id)
            if not user:
                return
            
            documents = user.get("documents", [])
            for doc in documents:
                if doc.get("document_id") == document_id:
                    # 合并元数据
                    current_metadata = doc.get("metadata", {})
                    current_metadata.update(metadata)
                    doc["metadata"] = current_metadata
                    doc["updated_at"] = _now_iso()
                    break
        
        self.store.update(_mutate)
    
    def delete_document(self, user_id: str, document_id: str) -> None:
        """删除文档记录"""
        def _mutate(data: Dict[str, Any]):
            users = data.setdefault("users", {})
            user = users.get(user_id)
            if not user:
                return
            
            documents = user.get("documents", [])
            user["documents"] = [
                doc for doc in documents 
                if doc.get("document_id") != document_id
            ]
        
        self.store.update(_mutate)


def create_knowledge_store(data_dir: str = None) -> KnowledgeStore:
    """
    创建 KnowledgeStore（使用系统临时目录或指定目录）。
    
    Args:
        data_dir: 数据目录（可选），默认使用系统临时目录
    """
    import tempfile
    if data_dir is None:
        base = Path(tempfile.gettempdir()) / "zenflux_knowledge"
    else:
        base = Path(data_dir)
    
    path = base / "knowledge_store.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    
    return KnowledgeStore(
        store=JsonFileStore(
            path=path,
            default_factory=create_default_knowledge_store_dict
        )
    )


# ==================== 全局单例 ====================

_default_store: Optional[KnowledgeStore] = None


def get_knowledge_store() -> KnowledgeStore:
    """获取默认 KnowledgeStore 单例"""
    global _default_store
    if _default_store is None:
        _default_store = create_knowledge_store()
    return _default_store


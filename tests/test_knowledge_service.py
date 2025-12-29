"""
知识库服务测试示例

展示如何测试 Service 层（不依赖 HTTP 层）
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from typing import Dict, Any

from services.knowledge_service import (
    KnowledgeService,
    DocumentProcessingError,
    DocumentNotFoundError,
    UserNotFoundError,
)


# ==================== Mock 工具类 ====================

class MockRagieClient:
    """模拟 Ragie API 客户端"""
    
    def __init__(self):
        self.created_documents = []
    
    async def create_document_from_file(
        self,
        file_path: str,
        partition: str,
        metadata: Dict[str, Any],
        mode: str = "hi_res"
    ) -> Dict[str, Any]:
        """模拟文件上传"""
        document_id = f"doc_mock_{len(self.created_documents) + 1}"
        result = {
            "id": document_id,
            "status": "pending",
            "name": file_path.split("/")[-1],
            "partition": partition,
            "metadata": metadata
        }
        self.created_documents.append(result)
        return result
    
    async def create_document_from_url(
        self,
        url: str,
        partition: str,
        name: str = None,
        metadata: Dict[str, Any] = None,
        mode: str = "hi_res"
    ) -> Dict[str, Any]:
        """模拟 URL 上传"""
        document_id = f"doc_mock_{len(self.created_documents) + 1}"
        result = {
            "id": document_id,
            "status": "pending",
            "name": name or url.split("/")[-1],
            "partition": partition,
            "metadata": metadata or {}
        }
        self.created_documents.append(result)
        return result
    
    async def get_document(self, document_id: str) -> Dict[str, Any]:
        """模拟获取文档"""
        for doc in self.created_documents:
            if doc["id"] == document_id:
                return doc
        raise Exception(f"Document not found: {document_id}")
    
    async def delete_document(self, document_id: str) -> None:
        """模拟删除文档"""
        self.created_documents = [
            doc for doc in self.created_documents 
            if doc["id"] != document_id
        ]


class MockKnowledgeStore:
    """模拟本地存储"""
    
    def __init__(self):
        self.users = {}
    
    def get_or_create_user(self, user_id: str) -> Dict[str, Any]:
        """获取或创建用户"""
        if user_id not in self.users:
            self.users[user_id] = {
                "user_id": user_id,
                "partition_id": f"partition_{user_id}",
                "created_at": "2024-12-26T10:00:00Z",
                "documents": []
            }
        return self.users[user_id]
    
    def get_user(self, user_id: str) -> Dict[str, Any]:
        """获取用户"""
        return self.users.get(user_id)
    
    def add_document(
        self,
        user_id: str,
        document_id: str,
        filename: str,
        status: str,
        metadata: Dict[str, Any] = None
    ) -> None:
        """添加文档"""
        user = self.get_or_create_user(user_id)
        user["documents"].append({
            "document_id": document_id,
            "filename": filename,
            "status": status,
            "metadata": metadata or {},
            "created_at": "2024-12-26T10:00:00Z"
        })
    
    def get_user_documents(self, user_id: str) -> list:
        """获取用户文档"""
        user = self.users.get(user_id)
        if not user:
            return []
        return user.get("documents", [])
    
    def get_document(self, user_id: str, document_id: str) -> Dict[str, Any]:
        """获取特定文档"""
        documents = self.get_user_documents(user_id)
        for doc in documents:
            if doc.get("document_id") == document_id:
                return doc
        return None
    
    def delete_document(self, user_id: str, document_id: str) -> None:
        """删除文档"""
        user = self.users.get(user_id)
        if user:
            user["documents"] = [
                doc for doc in user["documents"]
                if doc.get("document_id") != document_id
            ]


# ==================== 测试用例 ====================

@pytest.fixture
def knowledge_service():
    """创建 KnowledgeService 实例（使用 Mock 依赖）"""
    mock_ragie_client = MockRagieClient()
    mock_knowledge_store = MockKnowledgeStore()
    
    return KnowledgeService(
        ragie_client=mock_ragie_client,
        knowledge_store=mock_knowledge_store
    )


@pytest.mark.asyncio
async def test_upload_document_from_file(knowledge_service):
    """测试文件上传"""
    # 执行上传
    result = await knowledge_service.upload_document_from_file(
        file_path="/tmp/test.pdf",
        user_id="user_001",
        filename="test.pdf",
        metadata={"source": "test"},
        mode="hi_res"
    )
    
    # 验证返回结果
    assert result["document_id"].startswith("doc_mock_")
    assert result["status"] == "pending"
    assert result["filename"] == "test.pdf"
    assert result["user_id"] == "user_001"
    assert result["partition_id"] == "partition_user_001"
    
    # 验证文档已保存到本地
    documents = knowledge_service.knowledge_store.get_user_documents("user_001")
    assert len(documents) == 1
    assert documents[0]["filename"] == "test.pdf"


@pytest.mark.asyncio
async def test_upload_document_from_url(knowledge_service):
    """测试 URL 上传"""
    # 执行上传
    result = await knowledge_service.upload_document_from_url(
        url="https://example.com/doc.pdf",
        user_id="user_002",
        name="Example Doc",
        metadata={"source": "url"}
    )
    
    # 验证返回结果
    assert result["document_id"].startswith("doc_mock_")
    assert result["status"] == "pending"
    assert result["filename"] == "Example Doc"
    assert result["user_id"] == "user_002"
    
    # 验证文档已保存
    documents = knowledge_service.knowledge_store.get_user_documents("user_002")
    assert len(documents) == 1


@pytest.mark.asyncio
async def test_list_user_documents(knowledge_service):
    """测试列出用户文档"""
    # 先上传几个文档
    await knowledge_service.upload_document_from_file(
        file_path="/tmp/doc1.pdf",
        user_id="user_003",
        filename="doc1.pdf"
    )
    await knowledge_service.upload_document_from_file(
        file_path="/tmp/doc2.pdf",
        user_id="user_003",
        filename="doc2.pdf"
    )
    
    # 查询文档列表
    result = await knowledge_service.list_user_documents(
        user_id="user_003",
        limit=10,
        offset=0
    )
    
    # 验证结果
    assert result["user_id"] == "user_003"
    assert result["total"] == 2
    assert len(result["documents"]) == 2


@pytest.mark.asyncio
async def test_delete_document(knowledge_service):
    """测试删除文档"""
    # 先上传一个文档
    upload_result = await knowledge_service.upload_document_from_file(
        file_path="/tmp/test.pdf",
        user_id="user_004",
        filename="test.pdf"
    )
    document_id = upload_result["document_id"]
    
    # 验证文档存在
    documents_before = knowledge_service.knowledge_store.get_user_documents("user_004")
    assert len(documents_before) == 1
    
    # 删除文档
    await knowledge_service.delete_document(
        user_id="user_004",
        document_id=document_id
    )
    
    # 验证文档已删除
    documents_after = knowledge_service.knowledge_store.get_user_documents("user_004")
    assert len(documents_after) == 0


@pytest.mark.asyncio
async def test_upload_batch(knowledge_service):
    """测试批量上传"""
    # 批量上传 3 个 URL
    result = await knowledge_service.upload_documents_batch(
        urls=[
            "https://example.com/doc1.pdf",
            "https://example.com/doc2.pdf",
            "https://example.com/doc3.pdf"
        ],
        user_id="user_005",
        metadata={"batch": "test_batch"},
        max_concurrent=2
    )
    
    # 验证结果
    assert result["total"] == 3
    assert result["succeeded"] == 3
    assert result["failed"] == 0
    
    # 验证所有文档已保存
    documents = knowledge_service.knowledge_store.get_user_documents("user_005")
    assert len(documents) == 3


@pytest.mark.asyncio
async def test_get_document_status_not_found(knowledge_service):
    """测试获取不存在的文档"""
    # 尝试获取不存在的文档
    with pytest.raises(DocumentNotFoundError):
        await knowledge_service.get_document_status(
            user_id="user_006",
            document_id="doc_nonexistent",
            refresh=False
        )


@pytest.mark.asyncio
async def test_get_user_knowledge_stats(knowledge_service):
    """测试获取用户统计"""
    # 先上传一些文档
    await knowledge_service.upload_document_from_file(
        file_path="/tmp/doc1.pdf",
        user_id="user_007",
        filename="doc1.pdf"
    )
    await knowledge_service.upload_document_from_file(
        file_path="/tmp/doc2.pdf",
        user_id="user_007",
        filename="doc2.pdf"
    )
    
    # 获取统计
    stats = await knowledge_service.get_user_knowledge_stats("user_007")
    
    # 验证结果
    assert stats.user_id == "user_007"
    assert stats.total_documents == 2
    assert stats.pending_documents == 2  # Mock 返回的都是 pending


# ==================== 运行测试 ====================

if __name__ == "__main__":
    """
    运行测试：
    
    pip install pytest pytest-asyncio
    pytest tests/test_knowledge_service.py -v
    """
    pytest.main([__file__, "-v"])


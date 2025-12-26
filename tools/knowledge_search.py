"""
知识库检索工具 - Knowledge Base Search Tool

作为 Agent 的工具，用于检索用户的个人知识库（基于 Ragie）
"""

from typing import Any, Dict, Optional, List
from tools.base import BaseTool
from logger import get_logger
from utils.ragie_client import get_ragie_client
from utils.knowledge_store import get_knowledge_store

logger = get_logger("knowledge_search")


class KnowledgeSearchTool(BaseTool):
    """
    知识库检索工具
    
    功能：
    - 从用户的个人知识库中检索相关内容
    - 自动使用当前用户的 Partition（知识空间隔离）
    - 支持语义搜索和元数据过滤
    
    注意：
    - user_id 必须在 WorkingMemory 中提供
    - 每个用户有独立的知识空间（Partition）
    """
    
    def __init__(self):
        super().__init__()
        self.ragie_client = get_ragie_client()
        self.knowledge_store = get_knowledge_store()
    
    @property
    def name(self) -> str:
        return "knowledge_search"
    
    @property
    def description(self) -> str:
        return (
            "从用户的个人知识库中检索相关信息。"
            "适用于需要查找用户之前上传的文档、笔记、资料等内容的场景。"
            "每个用户有独立的知识空间，只能检索自己的内容。"
        )
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "检索查询文本，描述你想要找到的信息"
                },
                "top_k": {
                    "type": "integer",
                    "description": "返回的结果数量，默认 5",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20
                },
                "metadata_filter": {
                    "type": "object",
                    "description": "元数据过滤条件（可选），如 {\"tags\": [\"important\"], \"source\": \"upload\"}",
                    "additionalProperties": True
                }
            },
            "required": ["query"]
        }
    
    async def execute(
        self,
        query: str,
        top_k: int = 5,
        metadata_filter: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行知识库检索
        
        Args:
            query: 检索查询文本
            top_k: 返回结果数量
            metadata_filter: 元数据过滤条件
            **kwargs: 额外参数（从 WorkingMemory 注入）
        
        Returns:
            检索结果，包含相关文档片段
        """
        try:
            # 1. 从 WorkingMemory 获取 user_id（由 Agent 自动注入）
            user_id = kwargs.get("user_id")
            if not user_id:
                return {
                    "success": False,
                    "error": "缺少 user_id，无法确定用户身份",
                    "message": "请确保在对话中提供了用户ID"
                }
            
            logger.info(f"🔍 知识库检索: user_id={user_id}, query={query[:50]}...")
            
            # 2. 获取或创建用户的 Partition（知识空间）
            user = self.knowledge_store.get_or_create_user(user_id)
            partition_id = user["partition_id"]
            
            logger.info(f"📦 用户知识空间: partition_id={partition_id}")
            
            # 3. 检查用户是否有文档
            documents = self.knowledge_store.get_user_documents(user_id)
            if not documents:
                return {
                    "success": True,
                    "message": "用户的知识库为空，暂无可检索的内容",
                    "chunks": [],
                    "total": 0
                }
            
            # 4. 调用 Ragie 检索 API
            retrieval_result = await self.ragie_client.retrieve(
                query=query,
                partition=partition_id,
                top_k=top_k,
                filters=metadata_filter
            )
            
            scored_chunks = retrieval_result.get("scored_chunks", [])
            
            logger.info(f"✅ 检索完成: 找到 {len(scored_chunks)} 个相关片段")
            
            # 5. 格式化返回结果
            if not scored_chunks:
                return {
                    "success": True,
                    "message": f"未找到与「{query}」相关的内容",
                    "chunks": [],
                    "total": 0
                }
            
            # 提取关键信息
            formatted_chunks = []
            for chunk in scored_chunks:
                formatted_chunks.append({
                    "text": chunk.get("text", ""),
                    "score": chunk.get("score", 0),
                    "document_id": chunk.get("document_id"),
                    "metadata": chunk.get("document_metadata", {})
                })
            
            # 构建摘要文本（供 LLM 使用）
            summary_parts = []
            for i, chunk in enumerate(formatted_chunks[:3], 1):  # 只取前3个
                summary_parts.append(
                    f"[相关内容 {i}]\n{chunk['text']}\n"
                    f"(来源: {chunk['metadata'].get('filename', '未知')})"
                )
            
            summary_text = "\n\n".join(summary_parts)
            
            return {
                "success": True,
                "message": f"找到 {len(scored_chunks)} 个相关片段",
                "total": len(scored_chunks),
                "chunks": formatted_chunks,
                "summary": summary_text,  # LLM 可以直接使用的摘要
                "query": query
            }
        
        except Exception as e:
            logger.error(f"❌ 知识库检索失败: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "message": f"检索失败: {str(e)}"
            }


# 工具实例（供 ToolManager 自动发现）
tool = KnowledgeSearchTool()


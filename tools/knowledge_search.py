"""
知识库检索工具 - Professional RAG Tool

作为 Agent 的工具，用于检索用户的个人知识库（基于 Ragie）

核心能力：
- 🔍 语义检索：理解用户意图，找到最相关的内容
- 📊 评分排序：按相关性评分排序结果
- 📚 引用管理：自动生成结构化引用信息
- 🏷️ 元数据过滤：支持按文档属性筛选
- 🔒 用户隔离：每个用户有独立的知识空间
"""

from typing import Any, Dict, Optional, List
from core.tool.base import BaseTool, ToolContext
from logger import get_logger
from utils.ragie_client import get_ragie_client
from utils.knowledge_store import get_knowledge_store

logger = get_logger("knowledge_search")


class KnowledgeSearchTool(BaseTool):
    """
    专业 RAG 检索工具（input_schema 由 capabilities.yaml 定义）
    
    功能特性：
    - 精准检索：基于 Ragie 的语义检索引擎
    - 结构化返回：包含文本、评分、来源、引用
    - 用户隔离：每个用户有独立的知识空间
    """
    
    name = "knowledge_search"
    
    def __init__(self):
        self.ragie_client = get_ragie_client()
        self.knowledge_store = get_knowledge_store()
    
    async def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        """
        执行知识库检索
        
        Args:
            params: 工具参数
                - query: 检索查询文本
                - top_k: 返回结果数量
                - metadata_filter: 元数据过滤条件
            context: 工具执行上下文
        
        Returns:
            检索结果，包含相关文档片段
        """
        # 从 params 提取参数
        query = params.get("query", "")
        top_k = params.get("top_k", 5)
        metadata_filter = params.get("metadata_filter")
        
        try:
            # 1. 从 context 获取 user_id
            user_id = context.user_id
            if not user_id:
                return {
                    "success": False,
                    "error": "缺少 user_id，无法确定用户身份",
                    "message": "请确保在对话中提供了用户ID"
                }
            
            logger.info(f"🔍 知识库检索: user_id={user_id}, query={query[:50]}...")
            
            # 2. 检查用户是否有文档
            documents = self.knowledge_store.get_user_documents(user_id)
            if not documents:
                return {
                    "success": True,
                    "message": "用户的知识库为空，暂无可检索的内容",
                    "chunks": [],
                    "total": 0
                }
            
            logger.info(f"📦 用户有 {len(documents)} 个文档")
            
            # 打印文档列表（调试用）
            for doc in documents:
                logger.debug(f"   📄 {doc.get('filename')} (status={doc.get('status')}, id={doc.get('document_id')})")
            
            # 3. 调用 Ragie 检索 API
            # 🛡️ 使用 metadata.user_id 过滤（不使用 partition，与 knowledge_service 一致）
            combined_filters = metadata_filter.copy() if metadata_filter else {}
            combined_filters["user_id"] = {"$eq": user_id}  # Ragie metadata 过滤语法
            
            logger.info(f"🔍 Ragie 检索参数: query={query[:30]}..., top_k={top_k}, filters={combined_filters}")
            
            retrieval_result = await self.ragie_client.retrieve(
                query=query,
                partition=None,  # 使用 default partition
                top_k=top_k,
                filters=combined_filters
            )
            
            logger.debug(f"🔍 Ragie 原始响应: {retrieval_result}")
            
            scored_chunks = retrieval_result.get("scored_chunks", [])
            
            logger.info(f"✅ 检索完成: 找到 {len(scored_chunks)} 个相关片段")
            
            # 5. 质量控制：过滤低相关性结果
            # 注意：Ragie 的 score 范围通常在 0.1-0.3 之间，不是 0-1
            min_score = 0.1  # 最低相关性阈值（降低以适应 Ragie 的评分范围）
            filtered_chunks = [
                chunk for chunk in scored_chunks 
                if chunk.get("score", 0) >= min_score
            ]
            
            if len(filtered_chunks) < len(scored_chunks):
                logger.info(
                    f"🔍 质量过滤: {len(scored_chunks)} 个结果 → "
                    f"{len(filtered_chunks)} 个高质量结果 (score >= {min_score})"
                )
            
            # 6. 格式化返回结果
            if not filtered_chunks:
                return {
                    "success": True,
                    "message": f"未找到与「{query}」相关的高质量内容",
                    "chunks": [],
                    "total": 0,
                    "rag_context": None,
                    "query": query
                }
            
            # 7. 提取关键信息并生成引用
            formatted_chunks = []
            for idx, chunk in enumerate(filtered_chunks, 1):
                metadata = chunk.get("document_metadata", {})
                filename = metadata.get("filename", "未知文档")
                
                formatted_chunks.append({
                    "citation_id": idx,  # 引用编号 [1], [2], ...
                    "text": chunk.get("text", ""),
                    "score": round(chunk.get("score", 0), 3),
                    "document_id": chunk.get("document_id"),
                    "document_name": filename,
                    "metadata": metadata
                })
            
            # 8. 构建 RAG 上下文（专业格式，供 LLM 使用）
            rag_context = self._build_rag_context(formatted_chunks, query)
            
            # 9. 生成简洁摘要（用于 API 响应）
            summary_text = self._build_summary(formatted_chunks[:3])
            
            return {
                "success": True,
                "message": f"✅ 找到 {len(filtered_chunks)} 个相关片段（已按相关性排序）",
                "total": len(filtered_chunks),
                "chunks": formatted_chunks,
                "summary": summary_text,
                "rag_context": rag_context,  # 🆕 专业 RAG 上下文
                "query": query,
                "instructions": (
                    "📌 使用说明：\n"
                    "1. 基于 rag_context 中的内容回答问题\n"
                    "2. 回答时必须包含引用标记，如：「根据文档[1]，...」\n"
                    "3. 禁止编造任何不在检索结果中的信息\n"
                    "4. 如果检索结果不足以回答问题，明确告知用户"
                )
            }
        
        except Exception as e:
            logger.error(f"❌ 知识库检索失败: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "message": f"检索失败: {str(e)}"
            }
    
    def _build_rag_context(self, chunks: List[Dict], query: str) -> str:
        """
        构建专业的 RAG 上下文（供 LLM 使用）
        
        格式：
        ```
        ## 📚 检索到的相关内容
        
        用户查询：「如何使用 Python 进行数据分析？」
        
        ### [1] 来源：Python数据分析教程.pdf
        评分：0.92
        内容：
        Python 是数据分析的首选语言...
        
        ### [2] 来源：数据分析实战.md
        评分：0.87
        内容：
        使用 pandas 库可以高效处理数据...
        ```
        
        Args:
            chunks: 格式化后的文档片段列表
            query: 原始查询
            
        Returns:
            结构化的 RAG 上下文文本
        """
        lines = [
            "## 📚 检索到的相关内容",
            "",
            f"**用户查询**：「{query}」",
            "",
            "---",
            ""
        ]
        
        for chunk in chunks:
            citation_id = chunk["citation_id"]
            doc_name = chunk["document_name"]
            score = chunk["score"]
            text = chunk["text"].strip()
            
            lines.extend([
                f"### [{citation_id}] 来源：{doc_name}",
                f"**相关性评分**：{score}",
                "",
                "**内容**：",
                f"{text}",
                "",
                "---",
                ""
            ])
        
        lines.extend([
            "",
            "## 📋 回答要求",
            "",
            "1. ✅ **必须基于以上检索内容回答**，禁止编造",
            "2. ✅ **包含引用标记**：如「根据文档[1]，Python 是...」",
            "3. ✅ **综合多个来源**：如果多个文档都提到相关内容，综合引用",
            "4. ✅ **明确来源**：让用户知道信息来自哪份文档",
            "5. ❌ **不要编造**：如果检索结果不足，明确告知「检索到的内容中未提及...」",
            ""
        ])
        
        return "\n".join(lines)
    
    def _build_summary(self, top_chunks: List[Dict]) -> str:
        """
        构建简洁摘要（用于 API 响应和日志）
        
        Args:
            top_chunks: 前N个最相关的片段
            
        Returns:
            摘要文本
        """
        summary_parts = []
        
        for chunk in top_chunks:
            citation_id = chunk["citation_id"]
            doc_name = chunk["document_name"]
            text = chunk["text"]
            
            # 截断过长的文本
            if len(text) > 200:
                text = text[:200] + "..."
            
            summary_parts.append(
                f"[{citation_id}] {doc_name}\n"
                f"{text}"
            )
        
        return "\n\n".join(summary_parts)


# 工具实例（供 ToolManager 自动发现）
tool = KnowledgeSearchTool()

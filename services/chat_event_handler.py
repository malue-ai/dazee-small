"""
聊天事件处理器 - Chat Event Handler

职责：
- 统一处理 Agent 产生的各种事件
- 累积消息内容（text, tool_use, tool_result）
- 触发数据库更新（通过 Repository）
- 更新会话元数据（plan）

设计原则：
- 每个事件类型有独立的处理方法
- 状态集中管理，不散落在各处
- 数据库操作通过 Repository 完成
"""

import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from logger import get_logger
from infra.database import AsyncSessionLocal, crud

logger = get_logger("chat_event_handler")


class ChatEventHandler:
    """
    聊天事件处理器
    
    统一处理 Agent.chat() 产生的所有事件
    
    使用示例：
        handler = ChatEventHandler(
            conversation_service=conversation_service,
            conversation_id=conversation_id,
            message_id=message_id
        )
        
        async for event in agent.chat(...):
            await handler.handle(event)
        
        await handler.finalize(agent)
    """
    
    def __init__(
        self,
        conversation_id: str,
        message_id: str,
        model: str = "claude-sonnet-4-5-20250929"
    ):
        """
        初始化事件处理器
        
        Args:
            conversation_id: 对话 ID
            message_id: 消息 ID（Assistant 消息）
            model: LLM 模型名称
        """
        self.conversation_id = conversation_id
        self.message_id = message_id
        self.model = model
        
        # 状态管理（集中在这里，不散落各处）
        self.content_blocks: List[Dict[str, Any]] = []  # 累积的内容块
        self.thinking_block: Optional[Dict[str, Any]] = None  # thinking 块（含 signature）
        self.current_text: str = ""  # 当前累积的文本
        self.is_finalized: bool = False  # 是否已完成
    
    async def handle(self, event: Dict[str, Any]) -> None:
        """
        处理单个事件（路由到具体的处理方法）
        
        Args:
            event: Agent 产生的事件
        """
        event_type = event.get("type", "")
        
        # 事件路由表
        # Content 级别事件（核心 3 个）
        # - content_start: 开始一个内容块
        # - content_delta: 内容增量
        # - content_stop: 结束一个内容块
        handlers = {
            "content_start": self._on_content_start,
            "content_delta": self._on_content_delta,
            "content_stop": self._on_content_stop,
            "conversation_delta": self._on_conversation_delta,  # 会话元数据更新（plan）
            "message_stop": self._on_message_stop,
            "session_end": self._on_message_stop,  # session_end 也触发保存
        }
        
        handler = handlers.get(event_type)
        if handler:
            await handler(event)
    
    # ==================== 事件处理方法 ====================
    
    async def _on_content_delta(self, event: Dict[str, Any]) -> None:
        """
        处理 content_delta 事件：累积内容
        
        事件格式（遵循 Claude API 标准）：
        {
            "type": "content_delta",
            "data": {
                "index": 0,
                "delta": {
                    "type": "text_delta" | "thinking_delta" | "input_json_delta",
                    "text": "...",           // text_delta
                    "thinking": "...",       // thinking_delta
                    "partial_json": "..."    // input_json_delta
                }
            }
        }
        """
        delta_data = event.get("data", {}).get("delta", {})
        delta_type = delta_data.get("type")
        
        # 文本增量
        if delta_type == "text_delta" or delta_type == "text":
            self.current_text += delta_data.get("text", "")
        
        # Thinking 增量（累积到 thinking_block）
        elif delta_type == "thinking_delta" or delta_type == "thinking":
            thinking_text = delta_data.get("thinking", delta_data.get("text", ""))
            if self.thinking_block is None:
                self.thinking_block = {"type": "thinking", "thinking": ""}
            self.thinking_block["thinking"] += thinking_text
        
        # 工具输入增量
        elif delta_type == "input_json_delta":
            partial_json = delta_data.get("partial_json", "")
            if self.content_blocks and self.content_blocks[-1].get("type") == "tool_use":
                # 累积 partial_json
                if "_partial_json" not in self.content_blocks[-1]:
                    self.content_blocks[-1]["_partial_json"] = ""
                self.content_blocks[-1]["_partial_json"] += partial_json
                
                # 尝试解析完整的 JSON
                try:
                    self.content_blocks[-1]["input"] = json.loads(
                        self.content_blocks[-1]["_partial_json"]
                    )
                except json.JSONDecodeError:
                    pass  # JSON 不完整，继续累积
    
    async def _on_content_start(self, event: Dict[str, Any]) -> None:
        """
        处理 content_start 事件：开始一个新的内容块（tool_use / tool_result）
        
        事件格式：
        {
            "type": "content_start",
            "data": {
                "content_block": {
                    "type": "tool_use" | "tool_result",
                    "id": "...",
                    "name": "...",
                    ...
                }
            }
        }
        """
        content_block = event.get("data", {}).get("content_block", {})
        block_type = content_block.get("type", "")
        
        # thinking block（流式模式下，内容通过 delta 累积）
        if block_type == "thinking":
            # thinking 通过 content_delta 累积，这里只标记开始
            logger.debug("📝 thinking block 开始")
        
        # text block（流式模式下，内容通过 delta 累积）
        elif block_type == "text":
            # text 通过 content_delta 累积，这里只标记开始
            logger.debug("📝 text block 开始")
        
        # 客户端工具调用
        elif block_type == "tool_use":
            # 先把之前累积的文本加入 content_blocks
            self._flush_current_text()
            
            # 添加 tool_use block
            self.content_blocks.append({
                "type": "tool_use",
                "id": content_block.get("id", ""),
                "name": content_block.get("name", ""),
                "input": content_block.get("input", {})
            })
            logger.debug(f"📝 累积 tool_use: {content_block.get('name')}")
        
        # 服务端工具调用（如 web_search, code_execution）
        elif block_type == "server_tool_use":
            self._flush_current_text()
            
            self.content_blocks.append({
                "type": "server_tool_use",
                "id": content_block.get("id", ""),
                "name": content_block.get("name", ""),
                "input": content_block.get("input", {})
            })
            logger.debug(f"📝 累积 server_tool_use: {content_block.get('name')}")
        
        # 客户端工具结果
        elif block_type == "tool_result":
            self.content_blocks.append({
                "type": "tool_result",
                "tool_use_id": content_block.get("tool_use_id", ""),
                "content": content_block.get("content", ""),
                "is_error": content_block.get("is_error", False)
            })
            logger.debug(f"📝 累积 tool_result: tool_use_id={content_block.get('tool_use_id')}")
        
        # 服务端工具结果（如 web_search_tool_result）
        elif block_type.endswith("_tool_result"):
            self.content_blocks.append({
                "type": block_type,  # 保留原始类型
                "tool_use_id": content_block.get("tool_use_id", ""),
                "content": content_block.get("content", [])
            })
            logger.debug(f"📝 累积服务端工具结果: {block_type}")
    
    async def _on_content_stop(self, event: Dict[str, Any]) -> None:
        """
        处理 content_stop 事件：结束一个内容块
        
        事件格式：
        {
            "type": "content_stop",
            "data": {
                "index": 0
            }
        }
        
        目前 content_stop 只是一个标记，不需要特殊处理。
        内容已经在 content_start 和 content_delta 中累积完成。
        """
        index = event.get("data", {}).get("index", -1)
        logger.debug(f"📝 content_stop: index={index}")
    
    async def _on_conversation_delta(self, event: Dict[str, Any]) -> None:
        """
        处理 conversation_delta 事件：增量更新 Conversation
        
        这是统一的更新入口，支持更新任何字段：
        - title: 标题更新
        - plan: Plan 创建/更新
        - metadata: 自定义元数据
        
        事件格式：
        {
            "type": "conversation_delta",
            "data": {
                "conversation_id": "conv_123",
                "delta": {
                    "title": "新标题",  // 可选
                    "plan": {...},      // 可选
                    "metadata": {...}   // 可选
                }
            }
        }
        """
        delta = event.get("data", {}).get("delta")
        if not delta:
            logger.debug("⏭️ conversation_delta 为空，跳过")
            return
        
        try:
            async with AsyncSessionLocal() as session:
                # 获取当前对话
                conversation = await crud.get_conversation(session, self.conversation_id)
                if not conversation:
                    logger.warning(f"⚠️ 对话不存在: {self.conversation_id}")
                    return
                
                # 构建更新参数
                title = delta.get("title")
                metadata = None
                
                # 处理 plan 更新（存储在 extra_data.plan）
                if "plan" in delta:
                    current_metadata = conversation.extra_data or {}
                    current_metadata["plan"] = delta["plan"]
                    metadata = current_metadata
                    logger.info(f"📋 Plan 已更新: {delta['plan'].get('goal', '')}")
                
                # 处理 metadata 更新（合并，不是替换）
                elif "metadata" in delta:
                    current_metadata = conversation.extra_data or {}
                    current_metadata.update(delta["metadata"])
                    metadata = current_metadata
                    logger.debug(f"📝 Metadata 已更新")
                
                # 保存到数据库
                if title or metadata:
                    await crud.update_conversation(
                        session=session,
                        conversation_id=self.conversation_id,
                        title=title,
                        metadata=metadata
                    )
                    logger.debug(f"✅ Conversation 已更新")
            
        except Exception as e:
            logger.error(f"❌ 更新 Conversation 失败: {str(e)}", exc_info=True)
    
    async def _on_message_stop(self, event: Dict[str, Any]) -> None:
        """
        处理 message_stop / session_end 事件：保存消息到数据库
        
        这是触发数据库写入的关键事件
        """
        if self.is_finalized:
            return  # 防止重复保存
        
        await self.finalize()
    
    # ==================== 辅助方法 ====================
    
    def _flush_current_text(self) -> None:
        """将累积的文本加入 content_blocks"""
        if self.current_text:
            self.content_blocks.append({
                "type": "text",
                "text": self.current_text
            })
            self.current_text = ""
    
    async def finalize(self, agent=None) -> None:
        """
        最终化：将所有累积的内容保存到数据库
        
        Content 结构设计：
        [
            {"type": "thinking", "thinking": "...", "signature": "..."},  // 完整保存
            {"type": "text", "text": "..."},
            {"type": "tool_use", "id": "...", "name": "...", "input": {...}},
            {"type": "tool_result", "tool_use_id": "...", "content": "..."}
        ]
        
        Status 结构设计（纯状态，不混入内容）：
        {
            "action": "completed" | "stopped" | "failed",
            "has_thinking": true | false,
            "blocks_count": 5
        }
        
        Args:
            agent: Agent 实例（用于获取 raw_content 和 usage 统计，可选）
        """
        if self.is_finalized:
            logger.debug("⏭️ 已完成，跳过重复 finalize")
            return
        
        # 把剩余的文本加入 content_blocks
        self._flush_current_text()
        
        # 🎯 尝试从 agent 获取完整的 thinking block（含 signature）
        # 这是因为 thinking 的 signature 只在 LLM 的 final_message 中
        thinking_block = self.thinking_block
        if agent and hasattr(agent, 'last_raw_content'):
            raw_content = agent.last_raw_content or []
            for block in raw_content:
                if block.get("type") == "thinking" and block.get("signature"):
                    thinking_block = block
                    logger.debug("📝 从 agent 获取完整 thinking block (含 signature)")
                    break
        
        # 如果没有内容，跳过保存
        if not self.content_blocks and not thinking_block:
            logger.warning(f"⚠️ Assistant 内容为空，跳过保存")
            self.is_finalized = True
            return
        
        try:
            # 🎯 构建完整的 content（thinking 放在最前面）
            final_blocks = []
            
            # 1. thinking block 放在最前面（完整保存，不截断）
            if thinking_block:
                final_blocks.append(thinking_block)
            
            # 2. 其他内容块
            final_blocks.extend(self.content_blocks)
            
            content_json = json.dumps(final_blocks, ensure_ascii=False)
            
            # 🎯 status 只表示状态，不混入内容（序列化为 JSON 字符串）
            final_status = json.dumps({
                "action": "completed",
                "has_thinking": thinking_block is not None,
                "blocks_count": len(final_blocks)
                }, ensure_ascii=False)
            
            # 提取 usage 统计
            usage_stats = self._extract_usage_stats(agent)
            
            # 构建 metadata（dict 格式，message_repo 会自动序列化）
            metadata_update = {
                "completed_at": datetime.now().isoformat(),
                "usage": usage_stats
            }
            
            # 更新数据库
            async with AsyncSessionLocal() as session:
                await crud.update_message(
                    session=session,
                message_id=self.message_id,
                content=content_json,
                status=final_status,
                metadata=metadata_update
            )
            
            # 统计日志
            thinking_count = 1 if thinking_block else 0
            text_count = sum(1 for b in self.content_blocks if b.get("type") == "text")
            tool_use_count = sum(1 for b in self.content_blocks if b.get("type") == "tool_use")
            tool_result_count = sum(1 for b in self.content_blocks if b.get("type") == "tool_result")
            
            logger.info(
                f"💾 Assistant 消息已保存: message_id={self.message_id}, "
                f"blocks={len(final_blocks)} "
                f"({thinking_count} thinking, {text_count} text, "
                f"{tool_use_count} tool_use, {tool_result_count} tool_result)"
            )
            
            self.is_finalized = True
        
        except Exception as e:
            logger.error(f"❌ 保存 Assistant 消息失败: {str(e)}", exc_info=True)
    
    def _extract_usage_stats(self, agent=None) -> Dict[str, Any]:
        """从 Agent 提取 usage 统计"""
        usage_stats = {}
        
        if not agent:
            return usage_stats
        
        if hasattr(agent, 'invocation_stats') and agent.invocation_stats:
            usage_stats["invocation_stats"] = agent.invocation_stats
        
        if hasattr(agent, 'llm') and hasattr(agent.llm, 'usage_stats'):
            llm_stats = agent.llm.usage_stats
            if llm_stats:
                usage_stats.update({
                    "input_tokens": llm_stats.get("total_input_tokens", 0),
                    "output_tokens": llm_stats.get("total_output_tokens", 0)
                })
        
        return usage_stats
    
    # ==================== 状态查询 ====================
    
    def get_content_blocks(self) -> List[Dict[str, Any]]:
        """获取当前累积的所有内容块"""
        # 返回副本，包括未 flush 的 current_text
        blocks = self.content_blocks.copy()
        if self.current_text:
            blocks.append({"type": "text", "text": self.current_text})
        return blocks
    
    def has_content(self) -> bool:
        """检查是否有内容"""
        return bool(self.content_blocks or self.current_text or self.thinking_block)


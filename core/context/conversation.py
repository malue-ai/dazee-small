"""
Context 对话上下文管理模块

职责：
1. 根据 conversation_id 加载消息列表
2. 集成 tokenizer 计算 token 数量
3. 双阈值压缩机制（80% 预检查 / 92% 运行中）
4. 智能消息替换（摘要 + 完整消息）
5. 提供消息格式转换（数据库格式 → Agent 格式）

注意：此模块是上下文管理的核心入口
"""

# 1. 标准库
import json
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple, TYPE_CHECKING

# 2. 第三方库
import tiktoken

# 3. 本地模块
from logger import get_logger

if TYPE_CHECKING:
    from services.conversation_service import ConversationService

logger = get_logger("context")

# 默认配置
DEFAULT_CONTEXT_WINDOW = 200000  # Claude Sonnet 4.5 的上下文窗口
PRE_RUN_THRESHOLD = 0.80  # 80% 阈值（运行前预检查）
RUNTIME_THRESHOLD = 0.92  # 92% 阈值（运行中实时检查）
KEEP_RECENT_MESSAGES = 10  # 保留最近 N 条完整消息


class Context:
    """
    上下文管理器
    
    用于加载和管理对话上下文，支持 token 计数和双阈值压缩
    
    这是上下文管理的核心模块，所有与历史消息相关的操作都应该通过此类进行。
    """
    
    def __init__(
        self,
        conversation_id: Optional[str] = None,
        conversation_service: Optional["ConversationService"] = None,
        model: str = "claude-sonnet-4-5-20250929",
        context_window: int = DEFAULT_CONTEXT_WINDOW
    ):
        """
        初始化 Context
        
        Args:
            conversation_id: 对话ID（可选）
            conversation_service: 对话服务实例（用于数据库操作）
            model: 模型名称（用于选择对应的 tokenizer）
            context_window: 上下文窗口大小（token数）
        """
        self.conversation_id = conversation_id
        self.conversation_service = conversation_service
        self.context_window = context_window
        self.messages: List[Dict[str, Any]] = []
        
        # tokenizer 延迟初始化（避免阻塞）
        self._tokenizer = None
        
        # 压缩信息（从数据库加载）
        self.compression_info: Optional[Dict[str, Any]] = None
    
    @property
    def tokenizer(self):
        """延迟加载 tokenizer（避免初始化时阻塞）"""
        if self._tokenizer is None:
            try:
                self._tokenizer = tiktoken.get_encoding("cl100k_base")
            except Exception as e:
                logger.warning(f"无法加载 tokenizer: {e}，将使用字符数估算")
        return self._tokenizer
    
    async def load_messages(self) -> List[Dict[str, Any]]:
        """
        从数据库加载消息列表
            
        Returns:
            消息列表（Agent 格式）
        """
        if not self.conversation_id:
            logger.debug("没有 conversation_id，跳过消息加载")
            return []
        
        if not self.conversation_service:
            logger.error("❌ conversation_service 未设置，无法加载消息")
            return []
        
        try:
            # 1. 加载对话元数据（获取压缩信息）
            try:
                conversation = await self.conversation_service.get_conversation(self.conversation_id)
                if conversation and conversation.metadata:
                    metadata = conversation.metadata if isinstance(conversation.metadata, dict) else {}
                    self.compression_info = metadata.get("compression")
                    if self.compression_info:
                        logger.info(
                            f"📦 检测到压缩信息: from_message_id={self.compression_info.get('from_message_id')}"
                        )
            except Exception:
                # 新对话，没有历史消息
                logger.debug(f"新对话，无历史消息: conversation_id={self.conversation_id}")
                return []
            
            # 2. 加载消息
            result = await self.conversation_service.get_conversation_messages(
                conversation_id=self.conversation_id,
                limit=1000,  # 加载所有历史消息
                order="asc"  # 从旧到新排序
            )
            db_messages = result.get("messages", [])
            
            if not db_messages:
                logger.debug(f"没有找到历史消息: conversation_id={self.conversation_id}")
                return []
            
            logger.info(f"📚 从数据库加载了 {len(db_messages)} 条消息")
            
            # 3. 应用压缩替换（如果存在压缩信息）
            if self.compression_info:
                self.messages = self._apply_compression(db_messages)
            else:
                self.messages = self._convert_to_agent_format(db_messages)
            
            return self.messages
        
        except Exception as e:
            logger.error(f"❌ 加载消息失败: {str(e)}", exc_info=True)
            return []
    
    def _apply_compression(self, db_messages: List[Any]) -> List[Dict[str, Any]]:
        """
        应用压缩：用摘要替换早期消息
        
        Args:
            db_messages: 数据库消息列表（可能是对象或字典）
            
        Returns:
            压缩后的消息列表（Agent 格式）
        """
        from_message_id = self.compression_info.get("from_message_id")
        summary = self.compression_info.get("summary")
        
        if not from_message_id or not summary:
            logger.warning("压缩信息不完整，使用完整消息")
            return self._convert_to_agent_format(db_messages)
        
        # 找到压缩点的索引
        compress_index = -1
        for i, msg in enumerate(db_messages):
            # 兼容处理：msg 可能是对象或字典
            msg_id = msg.get("id") if isinstance(msg, dict) else msg.id
            if msg_id == from_message_id:
                compress_index = i
                break
        
        if compress_index == -1:
            logger.warning(f"未找到 message_id={from_message_id}，使用完整消息")
            return self._convert_to_agent_format(db_messages)
        
        # 构建压缩后的消息列表
        result = []
        
        # 1. 添加压缩摘要（替换早期消息）
        result.append({
            "role": "system",
            "content": f"[历史对话摘要]\n{summary}"
        })
        
        # 2. 添加压缩点之后的完整消息
        recent_messages = db_messages[compress_index + 1:]
        result.extend(self._convert_to_agent_format(recent_messages))
        
        logger.info(
            f"✅ 应用压缩: {len(db_messages)} 条消息 → "
            f"1 条摘要 + {len(recent_messages)} 条完整消息"
        )
        
        return result
    
    def _convert_to_agent_format(
        self,
        db_messages: List[Any]
    ) -> List[Dict[str, Any]]:
        """
        将数据库消息转换为 Agent 格式
        
        Args:
            db_messages: 数据库消息列表（可能是对象或字典）
            
        Returns:
            Agent 格式的消息列表
            
        说明：
        - content 中包含所有 blocks：thinking/text/tool_use/tool_result
        - thinking block 完整保存（包含 thinking 文本和 signature）
        - RVR 循环中直接使用 content 中的 thinking + signature，无需额外处理
        - ⚠️ 过滤掉没有 signature 的 thinking 块（Claude API 要求）
        """
        agent_messages = []
        
        for msg in db_messages:
            # 兼容处理：msg 可能是对象或字典
            if isinstance(msg, dict):
                content = msg.get("content", "")
                role = msg.get("role", "user")
            else:
                content = msg.content
                role = msg.role
            
            # 处理 content（可能是 JSON 字符串）
            if isinstance(content, str):
                try:
                    # 尝试解析为 JSON（新格式：数组）
                    content_array = json.loads(content)
                    if isinstance(content_array, list):
                        # 直接使用 content 数组（已经是 Claude API 格式）
                        content = content_array
                except json.JSONDecodeError:
                    # 纯文本（旧格式）
                    pass
            
            # 🛡️ 清理 content 块（移除 thinking，确保 tool_use/tool_result 在正确角色中）
            if isinstance(content, list):
                content = self._clean_content_blocks(content, role)
            
            # 只添加有内容的消息
            if content:
                agent_messages.append({
                    "role": role,
                    "content": content
                })
        
        # 🛡️ 确保 tool_use 和 tool_result 配对
        agent_messages = self._ensure_tool_pairs(agent_messages)
        
        return agent_messages
    
    def _ensure_tool_pairs(
        self,
        messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        确保 tool_use 和 tool_result 成对出现
        
        Claude API 要求：
        - 每个 tool_use 后面必须紧跟对应的 tool_result（在下一个 user 消息中）
        - 如果 tool_use 没有对应的 tool_result，需要移除
        
        Args:
            messages: 消息列表
            
        Returns:
            清理后的消息列表
        """
        if not messages:
            return messages
        
        # 1. 收集所有 tool_use ID 和 tool_result 对应的 tool_use_id
        tool_use_ids = set()
        tool_result_ids = set()
        
        for msg in messages:
            content = msg.get("content", [])
            if not isinstance(content, list):
                continue
            
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "tool_use":
                    tool_use_ids.add(block.get("id"))
                elif block_type == "tool_result":
                    tool_result_ids.add(block.get("tool_use_id"))
        
        # 2. 找出配对的 tool_use（既有 tool_use 又有对应的 tool_result）
        paired_ids = tool_use_ids & tool_result_ids
        unpaired_tool_use = tool_use_ids - tool_result_ids
        unpaired_tool_result = tool_result_ids - tool_use_ids
        
        if unpaired_tool_use:
            logger.warning(f"⚠️ 发现 {len(unpaired_tool_use)} 个未配对的 tool_use，将移除")
        if unpaired_tool_result:
            logger.warning(f"⚠️ 发现 {len(unpaired_tool_result)} 个未配对的 tool_result，将移除")
        
        # 3. 过滤消息，移除未配对的 tool_use 和 tool_result
        cleaned_messages = []
        
        for msg in messages:
            content = msg.get("content", [])
            role = msg.get("role", "user")
            
            if isinstance(content, list):
                # 过滤未配对的块
                filtered_content = []
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    
                    block_type = block.get("type")
                    
                    if block_type == "tool_use":
                        tool_id = block.get("id")
                        if tool_id in paired_ids:
                            filtered_content.append(block)
                        else:
                            logger.debug(f"🧹 移除未配对的 tool_use: {tool_id}")
                    elif block_type == "tool_result":
                        tool_use_id = block.get("tool_use_id")
                        if tool_use_id in paired_ids:
                            filtered_content.append(block)
                        else:
                            logger.debug(f"🧹 移除未配对的 tool_result: {tool_use_id}")
                    else:
                        filtered_content.append(block)
                
                # 只添加有内容的消息
                if filtered_content:
                    cleaned_messages.append({
                        "role": role,
                        "content": filtered_content
                    })
            else:
                # 纯文本消息，直接保留
                if content:
                    cleaned_messages.append(msg)
        
        return cleaned_messages
    
    def _clean_content_blocks(
        self,
        content_blocks: List[Dict[str, Any]],
        role: str
    ) -> List[Dict[str, Any]]:
        """
        清理内容块，确保符合 Claude API 要求
        
        Claude API 要求：
        1. thinking 块必须有 signature 字段（我们直接移除所有 thinking 块）
        2. tool_result 块只能出现在 user 消息中
        3. tool_use 块只能出现在 assistant 消息中
        
        Args:
            content_blocks: 内容块列表
            role: 消息角色 (user/assistant)
            
        Returns:
            清理后的内容块列表
        """
        # 🆕 按 index 排序（确保顺序正确，即使存储时乱序）
        sorted_blocks = sorted(
            content_blocks,
            key=lambda b: b.get("index", 999) if isinstance(b, dict) else 999
        )
        
        filtered = []
        
        for block in sorted_blocks:
            if not isinstance(block, dict):
                continue
                
            block_type = block.get("type")
            
            # 1. 直接移除所有 thinking 块（避免 signature 问题）
            if block_type == "thinking":
                logger.debug(f"🧹 移除 thinking 块（历史消息不需要）")
                continue
            
            # 2. tool_result 只能在 user 消息中
            if block_type == "tool_result" and role != "user":
                logger.warning(f"⚠️ 移除错误位置的 tool_result 块（应在 user 消息中）")
                continue
            
            # 3. tool_use 只能在 assistant 消息中
            if block_type == "tool_use" and role != "assistant":
                logger.warning(f"⚠️ 移除错误位置的 tool_use 块（应在 assistant 消息中）")
                continue
            
            # 🆕 移除 index 字段（Claude API 不接受）
            clean_block = {k: v for k, v in block.items() if k != "index"}
            filtered.append(clean_block)
        
        return filtered
    
    def count_tokens(self, messages: Optional[List[Dict[str, Any]]] = None) -> int:
        """
        计算消息列表的 token 数量
        
        Args:
            messages: 消息列表（不提供则计算 self.messages）
            
        Returns:
            token 数量
        """
        if messages is None:
            messages = self.messages
        
        if not messages:
            return 0
        
        if self.tokenizer:
            # 使用 tiktoken 精确计算
            total_tokens = 0
            for msg in messages:
                content = msg.get("content", "")
                role = msg.get("role", "")
                # 计算 role 和 content 的 token
                total_tokens += len(self.tokenizer.encode(f"{role}: {content}"))
            return total_tokens
        else:
            # 估算：1 token ≈ 4 字符
            total_chars = sum(len(str(msg.get("content", ""))) for msg in messages)
            return total_chars // 4
    
    def check_threshold(
        self,
        threshold: float = PRE_RUN_THRESHOLD,
        include_new_message: Optional[str] = None
    ) -> Tuple[bool, int, int]:
        """
        检查是否超过阈值
        
        Args:
            threshold: 阈值（0.0-1.0）
            include_new_message: 是否包含新消息（用于预检查）
            
        Returns:
            (is_over_threshold, current_tokens, threshold_tokens)
        """
        messages = self.messages.copy()
        
        # 如果提供了新消息，添加到列表中计算
        if include_new_message:
            messages.append({"role": "user", "content": include_new_message})
        
        current_tokens = self.count_tokens(messages)
        threshold_tokens = int(self.context_window * threshold)
        
        is_over = current_tokens > threshold_tokens
        
        logger.debug(
            f"Token 检查: {current_tokens}/{threshold_tokens} "
            f"({current_tokens/self.context_window*100:.1f}% / {threshold*100:.0f}%)"
        )
        
        return is_over, current_tokens, threshold_tokens
    
    async def compress_if_needed(
        self,
        threshold: float = PRE_RUN_THRESHOLD,
        keep_recent: int = KEEP_RECENT_MESSAGES
    ) -> bool:
        """
        如果需要，执行压缩
        
        Args:
            threshold: 压缩阈值
            keep_recent: 保留最近 N 条完整消息
            
        Returns:
            是否执行了压缩
        """
        is_over, current_tokens, threshold_tokens = self.check_threshold(threshold)
        
        if not is_over:
            logger.debug(f"✅ Token 使用率未超过 {threshold*100:.0f}%，无需压缩")
            return False
        
        logger.warning(
            f"⚠️ Token 使用率超过 {threshold*100:.0f}% "
            f"({current_tokens}/{threshold_tokens})，开始压缩..."
        )
        
        # 执行压缩
        await self._do_compression(keep_recent)
        return True
    
    async def _do_compression(self, keep_recent: int):
        """
        执行压缩：生成摘要并更新数据库
        
        Args:
            keep_recent: 保留最近 N 条完整消息
        """
        if not self.conversation_id:
            logger.error("无法压缩：缺少 conversation_id")
            return
        
        if not self.conversation_service:
            logger.error("无法压缩：缺少 conversation_service")
            return
        
        if len(self.messages) <= keep_recent:
            logger.warning(f"消息数量 ({len(self.messages)}) 不足以压缩")
            return
        
        # 1. 分割消息：早期消息 vs 最近消息
        early_messages = self.messages[:-keep_recent]
        recent_messages = self.messages[-keep_recent:]
        
        # 2. 生成摘要（简单版：提取关键信息）
        summary = self._generate_summary(early_messages)
        
        # 3. 找到压缩点的 message_id
        # 从数据库重新查询，找到对应的 message_id
        result = await self.conversation_service.get_conversation_messages(
            conversation_id=self.conversation_id,
            limit=1000,
            order="asc"
        )
        db_messages = result.get("messages", [])
        
        if len(db_messages) <= keep_recent:
            logger.error("数据库消息数量不足")
            return
        
        compress_from_message = db_messages[-(keep_recent + 1)]
        # 兼容处理：msg 可能是对象或字典
        from_message_id = compress_from_message.get("id") if isinstance(compress_from_message, dict) else compress_from_message.id
        
        # 4. 更新数据库：保存压缩信息到 metadata
        compression_info = {
            "compressed_at": datetime.now().isoformat(),
            "from_message_id": from_message_id,
            "summary": summary
        }
        
        # 获取现有 metadata 并合并压缩信息
        conversation = await self.conversation_service.get_conversation(self.conversation_id)
        existing_metadata = conversation.metadata if isinstance(conversation.metadata, dict) else {}
        existing_metadata["compression"] = compression_info
        
        await self.conversation_service.update_conversation(
            conversation_id=self.conversation_id,
            metadata=existing_metadata
        )
        
        # 5. 更新内存中的消息列表
        self.compression_info = compression_info
        self.messages = [
            {"role": "system", "content": f"[历史对话摘要]\n{summary}"}
        ] + recent_messages
        
        logger.info(
            f"✅ 压缩完成: {len(early_messages)} 条早期消息 → 1 条摘要, "
            f"保留 {len(recent_messages)} 条最近消息"
        )
    
    def _generate_summary(self, messages: List[Dict[str, Any]]) -> str:
        """
        生成对话摘要（简单版：提取关键信息）
        
        TODO: 后续可以使用 LLM 生成更智能的摘要
        
        Args:
            messages: 要压缩的消息列表
            
        Returns:
            摘要文本
        """
        summary_lines = [
            f"以下是早期对话的摘要（共 {len(messages)} 条消息）："
        ]
        
        # 提取前几条和后几条消息的片段
        sample_count = min(3, len(messages) // 2)
        
        for i, msg in enumerate(messages):
            if i < sample_count or i >= len(messages) - sample_count:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")[:100]
                summary_lines.append(f"- {role}: {content}...")
        
        if len(messages) > sample_count * 2:
            summary_lines.insert(
                sample_count + 1,
                f"... [省略 {len(messages) - sample_count * 2} 条消息] ..."
            )
        
        return "\n".join(summary_lines)
    
    def get_messages_for_llm(self) -> List[Dict[str, Any]]:
        """
        获取用于 LLM 的消息列表
        
        Returns:
            消息列表
        """
        return self.messages
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取上下文统计信息
        
        Returns:
            统计信息
        """
        current_tokens = self.count_tokens()
        
        return {
            "conversation_id": self.conversation_id,
            "message_count": len(self.messages),
            "current_tokens": current_tokens,
            "context_window": self.context_window,
            "usage_percent": current_tokens / self.context_window * 100,
            "has_compression": self.compression_info is not None,
            "compression_info": self.compression_info
        }


async def create_context(
    conversation_id: Optional[str] = None,
    conversation_service: Optional["ConversationService"] = None,
    model: str = "claude-sonnet-4-5-20250929",
    context_window: int = DEFAULT_CONTEXT_WINDOW,
    auto_compress: bool = True
) -> Context:
    """
    创建并加载 Context
    
    Args:
        conversation_id: 对话ID
        conversation_service: 对话服务实例（用于数据库操作）
        model: 模型名称
        context_window: 上下文窗口大小
        auto_compress: 是否自动压缩（超过 80% 阈值时）
        
    Returns:
        Context 实例
    """
    context = Context(
        conversation_id=conversation_id,
        conversation_service=conversation_service,
        model=model,
        context_window=context_window
    )
    
    await context.load_messages()
    
    # 自动压缩（如果超过 80% 阈值）
    if auto_compress:
        await context.compress_if_needed(threshold=PRE_RUN_THRESHOLD)
    
    return context


"""
Conversation 级事件管理

职责：管理 Conversation（对话会话）级别的事件

数据结构设计：
Conversation = {
    "id": str,
    "title": str,
    "created_at": str,
    "updated_at": str,
    "metadata": {
        "plan": {...},      // plan_todo_tool 返回的完整 plan
        "context": {...},   // 上下文压缩信息
        "tags": [...],      // 标签
        "custom": {...}     // 自定义数据
    }
}

更新模式：
1. 统一使用 conversation_delta 事件
2. delta 是增量更新对象，前端直接合并：Object.assign(conversation, delta)
3. 例子：
   - 更新标题：delta = {"title": "新标题"}
   - 创建 plan：delta = {"plan": {...}}
   - 更新 plan：delta = {"plan": {...}}  // 完整替换
   - 部分更新 metadata：delta = {"metadata": {"tags": [...]}}
"""

from typing import Dict, Any, Optional
from core.events.base import BaseEventManager
from datetime import datetime


class ConversationEventManager(BaseEventManager):
    """
    Conversation 级事件管理器
    
    负责对话会话相关的事件（plan, title, context）
    """
    
    async def emit_conversation_start(
        self,
        session_id: str,
        conversation: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        发送 conversation_start 事件
        
        发送完整的 conversation 对象，用于初始化前端状态
        
        Args:
            session_id: Session ID
            conversation: Conversation 完整数据
            
        Returns:
            事件对象
            
        Example:
            conversation = {
                "id": "conv_123",
                "title": "新对话",
                "created_at": "2024-01-01T12:00:00Z",
                "metadata": {}
            }
        """
        event = self._create_event(
            event_type="conversation_start",
            data={
                "conversation_id": conversation.get("id"),
                "title": conversation.get("title", "新对话"),
                "created_at": conversation.get("created_at"),
                "updated_at": conversation.get("updated_at"),
                "metadata": conversation.get("metadata", {})
        }
        )
        
        return await self._send_event(session_id, event)
    
    async def emit_conversation_delta(
        self,
        session_id: str,
        conversation_id: str,
        delta: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        发送 conversation_delta 事件（增量更新）⭐ 核心方法
        
        统一的增量更新接口，前端直接合并到本地对象：
        ```js
        Object.assign(conversation, delta)
        ```
        
        Args:
            session_id: Session ID
            conversation_id: 对话ID
            delta: 增量更新数据
            
        Returns:
            事件对象
            
        Examples:
            # 1. 更新标题
            delta = {"title": "分析数据报告"}
            
            # 2. 创建 plan（首次）
            delta = {
                "plan": {
                    "task_id": "task_123",
                    "goal": "生成数据报告",
                    "steps": [...]
                }
            }
            
            # 3. 更新 plan（完整替换）
            delta = {
                "plan": {
                    "task_id": "task_123",
                    "goal": "生成数据报告",
                    "steps": [...],
                    "current_step": 2,
                    "completed_steps": 1
                }
            }
            
            # 4. 更新多个字段
            delta = {
                "title": "新标题",
                "updated_at": "2024-01-01T13:00:00Z"
            }
            
            # 5. 更新 metadata 中的部分字段
            delta = {
                "metadata": {
                    "tags": ["数据分析", "报告"]
                }
            }
        """
        # 自动添加 updated_at
        if "updated_at" not in delta:
            delta["updated_at"] = datetime.now().isoformat()
        
        event = self._create_event(
            event_type="conversation_delta",
            data={
                "conversation_id": conversation_id,
                "delta": delta
            }
        )
        
        return await self._send_event(session_id, event)
    
    # ==================== 语义化快捷方法（内部调用 conversation_delta）====================
    
    async def emit_conversation_title_update(
        self,
        session_id: str,
        conversation_id: str,
        title: str
    ) -> Dict[str, Any]:
        """
        发送标题更新事件（语义化快捷方式）
        
        专门用于后台标题生成任务完成后通知前端
        本质上是 conversation_delta 的语义化封装
        
        Args:
            session_id: Session ID
            conversation_id: 对话ID
            title: 新标题
            
        Returns:
            事件对象
        """
        return await self.emit_conversation_delta(
            session_id=session_id,
            conversation_id=conversation_id,
            delta={"title": title}
        )
    
    async def emit_conversation_plan_created(
        self,
        session_id: str,
        conversation_id: str,
        plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        发送 plan 创建事件（语义化快捷方式）
        
        用于 plan_todo_tool 首次创建 plan 时的通知
        本质上是 conversation_delta 的语义化封装
        
        Args:
            session_id: Session ID
            conversation_id: 对话ID
            plan: 完整的 plan 对象（plan_todo_tool 返回的）
            
        Returns:
            事件对象
            
        Example:
            plan = {
                "task_id": "task_20240101_120000",
                "goal": "生成PPT",
                "steps": [
                    {"action": "搜索资料", "status": "in_progress"},
                    {"action": "生成大纲", "status": "pending"}
                ],
                "status": "executing",
                "current_step": 0,
                "total_steps": 2
            }
        """
        return await self.emit_conversation_delta(
            session_id=session_id,
            conversation_id=conversation_id,
            delta={"plan": plan}
        )
    
    async def emit_conversation_plan_updated(
        self,
        session_id: str,
        conversation_id: str,
        plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        发送 plan 更新事件（语义化快捷方式）
        
        用于 plan_todo_tool update_step/add_step 后的通知
        本质上是 conversation_delta 的语义化封装
        
        注意：传入的是完整的 plan 对象（不是 delta），会完整替换
        
        Args:
            session_id: Session ID
            conversation_id: 对话ID
            plan: 更新后的完整 plan 对象（plan_todo_tool 返回的）
            
        Returns:
            事件对象
        """
        return await self.emit_conversation_delta(
            session_id=session_id,
            conversation_id=conversation_id,
            delta={"plan": plan}
        )
    
    async def emit_conversation_metadata_update(
        self,
        session_id: str,
        conversation_id: str,
        metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        发送 metadata 更新事件（语义化快捷方式）
        
        用于更新 conversation.metadata 中的字段
        注意：这会合并到现有 metadata，不是完全替换
        
        Args:
            session_id: Session ID
            conversation_id: 对话ID
            metadata: 要更新的 metadata 字段
            
        Returns:
            事件对象
            
        Example:
            # 只更新 tags，不影响 plan 和其他字段
            metadata = {"tags": ["数据分析", "报告"]}
        """
        return await self.emit_conversation_delta(
            session_id=session_id,
            conversation_id=conversation_id,
            delta={"metadata": metadata}
        )
    
    async def emit_conversation_context_compressed(
        self,
        session_id: str,
        conversation_id: str,
        context: Dict[str, Any],
        retained_messages: list
    ) -> Dict[str, Any]:
        """
        发送上下文压缩事件
        
        当对话历史过长，触发上下文压缩时发送
        
        Args:
            session_id: Session ID
            conversation_id: 对话ID
            context: 压缩后的上下文信息
            retained_messages: 保留的消息ID列表
            
        Returns:
            事件对象
        """
        event = self._create_event(
            event_type="conversation_context_compressed",
            data={
                "conversation_id": conversation_id,
                "context": context,
                "retained_messages": retained_messages
            }
        )
        
        return await self._send_event(session_id, event)
    
    async def emit_conversation_stop(
        self,
        session_id: str,
        conversation_id: str,
        final_status: str,
        summary: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        发送 conversation 结束事件
        
        当对话完成或被终止时发送
        
        Args:
            session_id: Session ID
            conversation_id: 对话ID
            final_status: 最终状态（completed/stopped/failed）
            summary: 会话摘要（可选）
            
        Returns:
            事件对象
        """
        event = self._create_event(
            event_type="conversation_stop",
            data={
                "conversation_id": conversation_id,
                "final_status": final_status,
                "summary": summary or {}
            }
        )
        
        return await self._send_event(session_id, event)
    

# ==================== 前端使用示例 ====================

"""
前端 JavaScript 示例：

// 1. 初始化 conversation
let conversation = null;

// 2. 监听 SSE 事件
eventSource.addEventListener('conversation_start', (e) => {
    const data = JSON.parse(e.data).data;
    conversation = {
        id: data.conversation_id,
        title: data.title,
        created_at: data.created_at,
        updated_at: data.updated_at,
        metadata: data.metadata || {}
    };
});

// 3. 处理增量更新（核心！）
eventSource.addEventListener('conversation_delta', (e) => {
    const data = JSON.parse(e.data).data;
    const delta = data.delta;
    
    // 直接合并 delta 到 conversation
    Object.assign(conversation, delta);
    
    // 如果 delta 中有 plan，触发 UI 更新
    if (delta.plan) {
        updatePlanUI(conversation.metadata.plan || delta.plan);
    }
    
    // 如果 delta 中有 title，更新标题
    if (delta.title) {
        updateTitleUI(delta.title);
    }
});

// 4. 具体的 UI 更新
function updatePlanUI(plan) {
    if (!plan) return;
    
    // 更新进度条
    const progress = plan.completed_steps / plan.total_steps;
    progressBar.style.width = `${progress * 100}%`;
    
    // 更新步骤列表
    plan.steps.forEach((step, index) => {
        const stepElement = document.querySelector(`#step-${index}`);
        stepElement.className = `step step-${step.status}`;
        stepElement.querySelector('.action').textContent = step.action;
    });
}
"""

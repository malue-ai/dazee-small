# 计费信息合并写入优化方案

## 一、问题分析

### 当前实现（多次写入）

**流程**：
1. `accumulate_usage()` → 单独推送 usage 到 Redis Streams
2. `_finalize_message()` → 推送最终消息更新（不包含完整 usage）
3. 结果：**两次数据库更新操作**

**代码位置**：
```python
# broadcaster.py - accumulate_usage()
await mq_client.push_update_event(
    message_id=message_id,
    metadata={"usage": usage}  # 第一次更新：只有 usage
)

# broadcaster.py - _finalize_message()
await mq_client.push_update_event(
    message_id=message_id,
    content=content_json,
    status="completed",
    metadata={"stream": {"phase": "final"}}  # 第二次更新：只有 stream.phase
)
```

**问题**：
- ❌ 两次 Redis Streams 推送
- ❌ 两次数据库 UPDATE 操作
- ❌ 可能的数据不一致（如果第一次成功，第二次失败）
- ❌ 性能开销（两次网络请求 + 两次数据库写入）

---

## 二、优化方案：合并写入

### 方案 A：在 `_finalize_message` 时合并（推荐）✅

**核心思路**：
- 在 `_finalize_message` 时，一次性包含完整的 metadata（包括 usage、stream.phase 等）
- 移除单独的 `accumulate_usage` 推送逻辑
- 在内存中累积 usage，最终一次性写入

**实现**：

#### 1. 修改 `EventBroadcaster`，在内存中累积 usage

```python
class EventBroadcaster:
    def __init__(self, ...):
        # ... 现有代码 ...
        self._session_usage: Dict[str, dict] = {}  # 新增：内存中累积 usage
    
    async def accumulate_usage(
        self,
        session_id: str,
        usage: Dict[str, Any]  # 改为接受完整的 UsageResponse 或 dict
    ) -> None:
        """
        累积 usage 到内存（不立即推送）
        
        Args:
            session_id: Session ID
            usage: UsageResponse.model_dump() 或 usage dict
        """
        message_id = self._session_message_ids.get(session_id)
        if not message_id:
            return
        
        # 在内存中累积（深度合并）
        if session_id not in self._session_usage:
            self._session_usage[session_id] = {}
        
        existing = self._session_usage[session_id]
        if isinstance(usage, dict):
            # 深度合并 usage
            if "usage" in existing and isinstance(existing["usage"], dict):
                # 合并 llm_call_details（追加）
                if "llm_call_details" in usage and "llm_call_details" in existing["usage"]:
                    existing["usage"]["llm_call_details"].extend(usage.get("llm_call_details", []))
                # 合并其他字段（累加）
                for key in ["prompt_tokens", "completion_tokens", "total_tokens", "total_price"]:
                    if key in usage:
                        existing["usage"][key] = existing["usage"].get(key, 0) + usage.get(key, 0)
                # 更新其他字段
                existing["usage"].update({k: v for k, v in usage.items() if k not in ["llm_call_details"]})
            else:
                existing["usage"] = usage
        
        logger.debug(f"📊 Usage 已累积到内存: session={session_id}, message_id={message_id}")
    
    async def _finalize_message(self, session_id: str) -> None:
        """
        最终完成消息（合并写入：content + status + metadata）
        """
        message_id = self._session_message_ids.get(session_id)
        accumulator = self._accumulators.get(session_id)
        
        if not message_id:
            return
        
        try:
            # 获取累积的内容
            content_blocks = accumulator.build_for_db() if accumulator else []
            chunk_count = len(content_blocks)
            content_json = json.dumps(content_blocks, ensure_ascii=False) if content_blocks else "[]"
            
            # 合并所有 metadata（一次性写入）
            update_metadata = {
                "stream": {
                    "phase": "final",
                    "chunk_count": chunk_count
                }
            }
            
            # ✅ 合并 usage（如果存在）
            if session_id in self._session_usage:
                usage_data = self._session_usage[session_id].get("usage")
                if usage_data:
                    update_metadata["usage"] = usage_data
            
            # ✅ 一次性推送：content + status + 完整 metadata
            from infra.message_queue import get_message_queue_client
            mq_client = await get_message_queue_client()
            
            await mq_client.push_update_event(
                message_id=message_id,
                content=content_json,
                status="completed",
                metadata=update_metadata  # 包含 stream.phase + usage
            )
            logger.info(
                f"✅ 消息完成事件已推送到 Redis Streams: "
                f"message_id={message_id}, chunks={chunk_count}, "
                f"has_usage={'usage' in update_metadata}"
            )
            
            # 清理内存中的 usage
            self._session_usage.pop(session_id, None)
            
            # 更新内存缓存...
            
        except Exception as e:
            logger.error(f"❌ 消息完成失败: {str(e)}", exc_info=True)
```

#### 2. 修改 `chat_service.py`，传递完整的 UsageResponse

```python
# chat_service.py - _run_agent()
# 生成 UsageResponse
usage_response = UsageResponse.from_tracker(
    tracker=agent.usage_tracker,
    latency=duration_ms / 1000.0
)

# ✅ 一次性传递给 broadcaster（不单独推送）
await agent.broadcaster.accumulate_usage(
    session_id=session_id,
    usage=usage_response.model_dump()  # 传递完整的 UsageResponse
)

# 注意：不再需要单独推送 usage
# await agent.broadcaster.accumulate_usage(...)  # 移除
```

---

### 方案 B：在 `chat_service.py` 中直接合并（备选）

**核心思路**：
- 在 `chat_service.py` 中，Agent 完成后，直接调用 `broadcaster` 的方法
- 一次性更新消息（content + status + metadata）

**实现**：

```python
# chat_service.py - _run_agent()
# 生成 UsageResponse
usage_response = UsageResponse.from_tracker(
    tracker=agent.usage_tracker,
    latency=duration_ms / 1000.0
)

# ✅ 直接调用 broadcaster 的合并更新方法
await agent.broadcaster.finalize_message_with_usage(
    session_id=session_id,
    usage=usage_response.model_dump()
)
```

**缺点**：
- 需要在 `broadcaster` 中新增方法
- 逻辑分散在两个地方

---

## 三、推荐方案：方案 A（内存累积 + 合并写入）

### 优势

1. **性能优化**
   - ✅ 只有一次 Redis Streams 推送
   - ✅ 只有一次数据库 UPDATE 操作
   - ✅ 减少网络开销和数据库负载

2. **数据一致性**
   - ✅ 原子性：所有 metadata 一次性写入
   - ✅ 避免部分更新导致的数据不一致

3. **代码简洁**
   - ✅ 逻辑集中在 `_finalize_message`
   - ✅ 不需要修改调用方代码

### 实现步骤

1. **修改 `EventBroadcaster`**
   - 添加 `_session_usage` 字典（内存累积）
   - 修改 `accumulate_usage()`：只累积到内存，不推送
   - 修改 `_finalize_message()`：合并 usage 到 metadata，一次性推送

2. **修改 `chat_service.py`**
   - 确保传递完整的 `UsageResponse.model_dump()`
   - 移除单独的 usage 推送逻辑（如果有）

3. **清理逻辑**
   - 在 `_finalize_message` 成功后清理 `_session_usage`
   - 在 `_cleanup_session` 中清理 `_session_usage`

---

## 四、完整实现代码

### 4.1 EventBroadcaster 修改

```python
class EventBroadcaster:
    def __init__(self, ...):
        # ... 现有代码 ...
        self._session_usage: Dict[str, dict] = {}  # 新增：内存中累积 usage
    
    async def accumulate_usage(
        self,
        session_id: str,
        usage: Dict[str, Any]  # 接受 UsageResponse.model_dump()
    ) -> None:
        """
        累积 usage 到内存（不立即推送，等待 _finalize_message 时合并写入）
        """
        message_id = self._session_message_ids.get(session_id)
        if not message_id:
            return
        
        # 在内存中累积
        if session_id not in self._session_usage:
            self._session_usage[session_id] = {}
        
        # 直接保存 usage（UsageResponse 已经是完整结构）
        self._session_usage[session_id]["usage"] = usage
        
        logger.debug(f"📊 Usage 已累积到内存: session={session_id}, message_id={message_id}")
    
    async def _finalize_message(self, session_id: str) -> None:
        """最终完成消息（合并写入）"""
        message_id = self._session_message_ids.get(session_id)
        accumulator = self._accumulators.get(session_id)
        
        if not message_id:
            return
        
        try:
            # 获取累积的内容
            content_blocks = accumulator.build_for_db() if accumulator else []
            chunk_count = len(content_blocks)
            content_json = json.dumps(content_blocks, ensure_ascii=False) if content_blocks else "[]"
            
            # 合并所有 metadata
            update_metadata = {
                "stream": {
                    "phase": "final",
                    "chunk_count": chunk_count
                }
            }
            
            # ✅ 合并 usage（如果存在）
            if session_id in self._session_usage:
                usage_data = self._session_usage[session_id].get("usage")
                if usage_data:
                    update_metadata["usage"] = usage_data
            
            # ✅ 一次性推送：content + status + 完整 metadata
            from infra.message_queue import get_message_queue_client
            mq_client = await get_message_queue_client()
            
            await mq_client.push_update_event(
                message_id=message_id,
                content=content_json,
                status="completed",
                metadata=update_metadata  # 包含 stream.phase + usage
            )
            logger.info(
                f"✅ 消息完成（合并写入）: message_id={message_id}, "
                f"chunks={chunk_count}, has_usage={'usage' in update_metadata}"
            )
            
            # 清理内存
            self._session_usage.pop(session_id, None)
            
            # 更新内存缓存...
            
        except Exception as e:
            logger.error(f"❌ 消息完成失败: {str(e)}", exc_info=True)
    
    def _cleanup_session(self, session_id: str) -> None:
        """清理 session 状态"""
        self._accumulators.pop(session_id, None)
        self._session_message_ids.pop(session_id, None)
        self._session_conversation_ids.pop(session_id, None)
        self._session_usage.pop(session_id, None)  # 新增：清理 usage
        logger.debug(f"🧹 清理 session 状态: {session_id}")
```

### 4.2 chat_service.py 修改

```python
# chat_service.py - _run_agent()
# 生成 UsageResponse
usage_response = UsageResponse.from_tracker(
    tracker=agent.usage_tracker,
    latency=duration_ms / 1000.0
)

# ✅ 累积到内存（不立即推送）
await agent.broadcaster.accumulate_usage(
    session_id=session_id,
    usage=usage_response.model_dump()  # 传递完整的 UsageResponse
)

# 注意：_finalize_message 会在 message_stop 时自动调用，合并写入
```

---

## 五、性能对比

### 优化前

| 操作 | 次数 | 说明 |
|------|------|------|
| Redis Streams 推送 | 2 次 | usage + finalize |
| 数据库 UPDATE | 2 次 | 两次更新 metadata |
| 网络请求 | 2 次 | 两次 Redis 写入 |

### 优化后

| 操作 | 次数 | 说明 |
|------|------|------|
| Redis Streams 推送 | 1 次 | 合并写入 |
| 数据库 UPDATE | 1 次 | 一次更新完整 metadata |
| 网络请求 | 1 次 | 一次 Redis 写入 |

**性能提升**：
- ✅ 网络请求减少 50%
- ✅ 数据库写入减少 50%
- ✅ 数据一致性提升（原子性写入）

---

## 六、总结

### 推荐方案

**方案 A：内存累积 + 合并写入** ✅

**核心思路**：
1. `accumulate_usage()` 只累积到内存，不推送
2. `_finalize_message()` 时合并 usage 到 metadata，一次性推送
3. 结果：只有一次数据库写入操作

**优势**：
- ✅ 性能优化（减少 50% 的写入操作）
- ✅ 数据一致性（原子性写入）
- ✅ 代码简洁（逻辑集中）

**实施优先级**：🔴 **高优先级**（性能关键路径）

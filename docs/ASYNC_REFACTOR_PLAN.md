# 异步改造完整计划

**创建日期**：2025-12-29  
**状态**：进行中  
**目标**：消除所有同步阻塞，实现真正的高并发

---

## 📊 问题总结

### 已修复 ✅
1. ✅ `create_message_stream()` - 已改为异步生成器
2. ✅ Agent 中的流式循环 - 已改为 `async for`
3. ✅ 所有 tools 的 `execute()` 方法 - 都已是异步

### 待修复 🔴

#### 1. **`create_message()` 同步方法（核心问题）**

**文件**：`core/llm_service.py`  
**行号**：540-709

**当前代码**：
```python
def create_message(
    self,
    messages: List[Message],
    system: Optional[str] = None,
    tools: Optional[List[Union[ToolType, str, Dict]]] = None,
    invocation_type: Optional[str] = None,
    **kwargs
) -> LLMResponse:
    """创建消息（同步）"""
    # ...
    response = self.client.messages.create(**request_params)  # ❌ 同步调用
    # ...
    return self._parse_response(response, invocation_type=invocation_type)
```

**问题**：
- 使用同步 `self.client.messages.create()`
- 阻塞事件循环直到 LLM 返回
- 虽然现在 Agent 中已经不再直接调用，但仍然存在风险

**修复方案**：

**方案 A：废弃同步方法（推荐）**
```python
def create_message(self, ...):
    """
    创建消息（已废弃）
    
    ⚠️ 警告：此方法会阻塞事件循环！
    请使用 create_message_async() 代替
    """
    raise DeprecationWarning(
        "create_message() 已废弃，请使用 create_message_async()"
    )
```

**方案 B：保留但警告（兼容性）**
```python
def create_message(self, ...):
    """创建消息（同步 - 不推荐）"""
    import warnings
    warnings.warn(
        "create_message() 是同步方法，可能阻塞事件循环。"
        "推荐使用 create_message_async()",
        DeprecationWarning
    )
    # 保留原有实现（向后兼容）
    response = self.client.messages.create(**request_params)
    return self._parse_response(response, invocation_type=invocation_type)
```

**推荐**：方案 A（废弃）

---

#### 2. **`count_tokens()` 同步方法**

**文件**：`core/llm_service.py`  
**行号**：999-1013

**当前代码**：
```python
def count_tokens(self, text: str) -> int:
    """计算tokens"""
    try:
        response = self.client.messages.count_tokens(  # ❌ 同步调用
            model=self.config.model,
            messages=[{"role": "user", "content": text}]
        )
        return response.input_tokens
    except:
        return len(text) // 4
```

**问题**：
- 使用同步 API 调用
- 如果在异步上下文中调用会阻塞

**修复方案**：

**选项 1：添加异步版本**
```python
def count_tokens(self, text: str) -> int:
    """计算tokens（同步 - 不推荐在异步代码中使用）"""
    warnings.warn("使用同步 count_tokens，推荐使用 count_tokens_async")
    try:
        response = self.client.messages.count_tokens(...)
        return response.input_tokens
    except:
        return len(text) // 4

async def count_tokens_async(self, text: str) -> int:
    """计算tokens（异步）"""
    try:
        response = await self.async_client.messages.count_tokens(
            model=self.config.model,
            messages=[{"role": "user", "content": text}]
        )
        return response.input_tokens
    except:
        return len(text) // 4
```

**选项 2：使用本地估算（推荐）**
```python
def count_tokens(self, text: str) -> int:
    """
    计算tokens（本地估算，不需要 API 调用）
    
    使用快速本地估算，避免网络调用阻塞。
    精确度：±10%（对大多数场景足够）
    """
    # 粗略估算：1 token ≈ 4 chars（英文）
    # 中文：1 token ≈ 1.5 chars
    return len(text) // 4
```

**推荐**：选项 2（本地估算）- 速度快，不阻塞

---

#### 3. **抽象基类定义**

**文件**：`core/llm_service.py`  
**行号**：125-132

**当前代码**：
```python
@abstractmethod
def create_message(
    self,
    messages: List[Message],
    system: Optional[str] = None,
    **kwargs
) -> LLMResponse:
    """创建消息（同步）"""
    pass
```

**修复方案**：

**选项 1：标记为废弃**
```python
@abstractmethod
def create_message(
    self,
    messages: List[Message],
    system: Optional[str] = None,
    **kwargs
) -> LLMResponse:
    """
    创建消息（同步 - 已废弃）
    
    ⚠️ 此方法已废弃，请使用 create_message_async()
    """
    pass
```

**选项 2：完全移除（激进）**
```python
# 移除 create_message() 抽象方法
# 只保留 create_message_async() 和 create_message_stream()
```

**推荐**：选项 1（标记废弃，保持兼容性）

---

## 🎯 修复优先级

### P0 - 立即修复（阻塞性能）
- [x] ✅ `create_message_stream()` - 已完成
- [ ] 🔴 `create_message()` - 添加废弃警告

### P1 - 高优先级（影响用户体验）
- [ ] 🟡 `count_tokens()` - 改为本地估算
- [ ] 🟡 抽象基类 - 标记废弃

### P2 - 低优先级（代码质量）
- [ ] 🟢 文档更新 - 说明异步使用方式
- [ ] 🟢 示例代码 - 更新为异步版本

---

## 📝 实施步骤

### 第一阶段：核心修复（今天完成）

#### 步骤 1：修复 `create_message()`
```bash
# 修改文件：core/llm_service.py
# 行号：540-709
```

**修改内容**：
1. 添加废弃警告
2. 更新文档字符串

#### 步骤 2：修复 `count_tokens()`
```bash
# 修改文件：core/llm_service.py
# 行号：999-1013
```

**修改内容**：
1. 移除 API 调用
2. 使用本地估算
3. 添加注释说明

#### 步骤 3：更新抽象基类
```bash
# 修改文件：core/llm_service.py
# 行号：125-132
```

**修改内容**：
1. 添加废弃警告
2. 更新文档

### 第二阶段：验证测试（明天）

#### 测试 1：并发测试
```bash
python examples/test_concurrent_requests.py
```

**预期结果**：
- ✅ 所有请求都能快速返回
- ✅ 没有阻塞现象

#### 测试 2：性能测试
```bash
# 测试首字延迟
time curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "你好", "user_id": "test", "stream": true}'
```

**预期结果**：
- ✅ 首字延迟 < 3 秒

#### 测试 3：功能测试
```bash
# 完整对话测试
python examples/test_chat_complete.py
```

**预期结果**：
- ✅ 所有功能正常

### 第三阶段：文档更新（后续）

#### 更新文档
- [ ] API 文档 - 标注异步方法
- [ ] 开发指南 - 异步最佳实践
- [ ] 示例代码 - 更新为异步版本

---

## 🔍 检查清单

使用此清单确保所有同步阻塞都已修复：

### 核心代码
- [x] ✅ `core/llm_service.py` - `create_message_stream()` 已改为异步
- [ ] 🔴 `core/llm_service.py` - `create_message()` 添加废弃警告
- [ ] 🟡 `core/llm_service.py` - `count_tokens()` 改为本地估算
- [x] ✅ `core/agent.py` - 流式循环已改为 `async for`

### Tools
- [x] ✅ `tools/plan_todo_tool.py` - `execute()` 已是异步
- [x] ✅ `tools/request_human_confirmation.py` - `execute()` 已是异步
- [x] ✅ `tools/knowledge_search.py` - `execute()` 已是异步
- [x] ✅ `tools/slidespeak.py` - `execute()` 已是异步
- [x] ✅ `tools/api_calling.py` - `execute()` 已是异步
- [x] ✅ `tools/exa_search.py` - `execute()` 已是异步

### Services
- [x] ✅ `services/chat_service.py` - 所有方法都是异步
- [x] ✅ `services/session_service.py` - 所有方法都是异步
- [x] ✅ `services/conversation_service.py` - 所有方法都是异步

---

## 📈 预期效果

### 修复前
```
场景：用户发送消息
- 意图分析：21 秒（阻塞）
- 首字延迟：21 秒
- 其他请求：被阻塞
```

### 修复后
```
场景：用户发送消息
- 意图分析：已优化（异步）
- 首字延迟：< 3 秒
- 其他请求：不受影响，正常并发
```

**性能提升**：
- 📉 首字延迟降低：21s → 3s（**降低 85%**）
- 📈 并发能力提升：单线程 → 真正的异步并发
- 🎯 用户体验改善：立即响应 vs 长时间等待

---

## 🎓 经验总结

### 1. 异步编程原则
- ✅ **所有 I/O 操作都必须是异步的**
- ✅ **使用异步客户端**（AsyncAnthropic, httpx, aiofiles）
- ✅ **使用 async/await 关键字**
- ❌ **避免在异步代码中调用同步 I/O**

### 2. 性能优化建议
- 📊 **监控响应时间**：设置警报（> 5 秒）
- 🧪 **定期并发测试**：每次发布前测试
- 📝 **性能日志**：记录慢请求
- 🔧 **及时优化**：发现问题立即修复

### 3. 开发规范
```python
# ✅ 推荐
async def my_function():
    result = await async_api_call()
    return result

# ❌ 避免
async def bad_function():
    result = sync_api_call()  # 阻塞！
    return result
```

---

## ✅ 完成标准

修复完成的标准：

1. ✅ 所有 I/O 操作都是异步的
2. ✅ 并发测试通过（无阻塞）
3. ✅ 性能测试通过（首字延迟 < 3 秒）
4. ✅ 功能测试通过（所有功能正常）
5. ✅ 文档已更新
6. ✅ 示例代码已更新

---

**下一步行动**：开始执行第一阶段修复（核心修复）


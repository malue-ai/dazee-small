# E2B 沙箱生命周期管理指南

## 问题背景

E2B 沙箱有**默认生命周期限制**：
- **免费版**：最长 1 小时
- **专业版**：最长 24 小时

超过生命周期后，沙箱会自动销毁，导致 "Sandbox Not Found" 错误。

---

## 解决方案

我们实现了三层保障机制：

### 1. **配置沙箱生命周期**

在创建 `E2BVibeCoding` 实例时指定生命周期：

```python
from tools.e2b_vibe_coding import E2BVibeCoding

vibe = E2BVibeCoding(
    memory=memory,
    api_key=api_key,
    sandbox_timeout_hours=1.0  # 免费版最大值：1小时
)
```

### 2. **自动心跳保活**

系统会自动每 30 秒执行一次心跳命令，保持沙箱活跃：

```python
# 创建应用时自动启动心跳
result = await vibe.create_app(
    stack="streamlit",
    code=streamlit_code
)

# 心跳会在后台自动运行
# 终止应用时自动停止心跳
await vibe.terminate_app(app_id)
```

### 3. **健康检查机制**

定期检查沙箱状态，提前发现问题：

```python
# 检查沙箱健康状态
health = await vibe.check_sandbox_health(app_id)

if health.get("alive"):
    print(f"✅ 沙箱正常")
    print(f"   运行时间: {health['uptime_seconds']} 秒")
    print(f"   剩余时间: {health['remaining_seconds']} 秒")
else:
    print(f"❌ 沙箱已失效: {health.get('error')}")
```

---

## 使用示例

### 基础用法（自动管理）

```python
import asyncio
from core.memory import WorkingMemory
from tools.e2b_vibe_coding import E2BVibeCoding

async def main():
    memory = WorkingMemory()
    vibe = E2BVibeCoding(
        memory=memory,
        sandbox_timeout_hours=1.0  # 1小时生命周期
    )
    
    # 创建应用（自动启动心跳）
    result = await vibe.create_app(
        stack="streamlit",
        code=your_code
    )
    
    print(f"预览 URL: {result['preview_url']}")
    print(f"生命周期: {result['expires_in']}")
    
    # ... 使用应用 ...
    
    # 终止应用（自动停止心跳）
    await vibe.terminate_app(result['app_id'])

asyncio.run(main())
```

### 长时间运行（带健康检查）

```python
async def run_with_health_check():
    memory = WorkingMemory()
    vibe = E2BVibeCoding(memory=memory, sandbox_timeout_hours=1.0)
    
    result = await vibe.create_app(stack="streamlit", code=code)
    app_id = result['app_id']
    
    try:
        while True:
            await asyncio.sleep(60)  # 每分钟检查一次
            
            health = await vibe.check_sandbox_health(app_id)
            if not health.get("alive"):
                print(f"❌ 沙箱失效，需要重建")
                break
            
            remaining_min = health["remaining_seconds"] // 60
            print(f"✅ 运行中，剩余 {remaining_min} 分钟")
    
    except KeyboardInterrupt:
        print("用户终止")
    
    finally:
        await vibe.terminate_app(app_id)

asyncio.run(run_with_health_check())
```

---

## API 参考

### E2BVibeCoding 初始化

```python
E2BVibeCoding(
    memory: WorkingMemory,
    api_key: str = None,
    sandbox_timeout_hours: float = 1.0  # 新增参数
)
```

**参数说明**：
- `sandbox_timeout_hours`: 沙箱生命周期（小时）
  - 免费版：最大 1.0 小时
  - 专业版：最大 24.0 小时

### 健康检查

```python
await vibe.check_sandbox_health(app_id: str) -> Dict[str, Any]
```

**返回值**：
```python
{
    "success": True,
    "alive": True,              # 沙箱是否存活
    "sandbox_id": "...",
    "uptime_seconds": 1234,     # 已运行时间（秒）
    "remaining_seconds": 2366,  # 剩余时间（秒）
    "message": "✅ 沙箱运行正常，剩余 39 分钟"
}
```

---

## 最佳实践

### 1. **合理设置生命周期**

```python
# ✅ 推荐：免费版使用最大值
vibe = E2BVibeCoding(sandbox_timeout_hours=1.0)

# ⚠️ 不推荐：过短的生命周期
vibe = E2BVibeCoding(sandbox_timeout_hours=0.1)  # 6分钟太短
```

### 2. **提前警告用户**

```python
health = await vibe.check_sandbox_health(app_id)
remaining_min = health["remaining_seconds"] // 60

if remaining_min < 5:
    print(f"⚠️ 警告：沙箱将在 {remaining_min} 分钟后过期")
```

### 3. **自动重建机制**

```python
async def create_app_with_auto_rebuild():
    while True:
        try:
            result = await vibe.create_app(...)
            app_id = result['app_id']
            
            # 运行并监控
            while True:
                health = await vibe.check_sandbox_health(app_id)
                if not health.get("alive"):
                    print("沙箱失效，5秒后重建...")
                    await vibe.terminate_app(app_id)
                    await asyncio.sleep(5)
                    break  # 跳出内循环，重新创建
                
                await asyncio.sleep(60)
        
        except KeyboardInterrupt:
            await vibe.terminate_app(app_id)
            break
```

---

## 常见问题

### Q1: 为什么沙箱还是过期了？

**A**: 检查以下几点：
1. 确认设置了 `sandbox_timeout_hours` 参数
2. 确认没有超过免费版的 1 小时限制
3. 查看日志确认心跳任务正常运行

```python
# 检查心跳日志
# 应该每 30 秒看到: 💓 心跳成功: app_xxx
```

### Q2: 如何延长沙箱生命周期？

**A**: 免费版最长 1 小时，无法延长。如需更长时间：
- 方案 1：升级到 E2B 专业版（最长 24 小时）
- 方案 2：实现自动重建机制（见上方最佳实践）

### Q3: 心跳机制会增加成本吗？

**A**: 心跳命令非常轻量（`echo 'heartbeat'`），几乎不消耗资源，不会显著增加成本。

---

## 调试技巧

### 查看详细日志

```python
import logging

# 启用 DEBUG 级别日志
logging.getLogger("e2b_vibe_coding").setLevel(logging.DEBUG)

# 会看到心跳日志：
# 💓 心跳成功: app_20231229_140154
# 💓 心跳失败: app_xxx - Sandbox not found
```

### 手动测试沙箱

```python
# 创建应用后，手动检查沙箱
result = await vibe.create_app(...)

# 立即检查健康状态
health = await vibe.check_sandbox_health(result['app_id'])
print(health)

# 等待 10 分钟后再检查
await asyncio.sleep(600)
health = await vibe.check_sandbox_health(result['app_id'])
print(health)
```

---

## 总结

通过实现 **生命周期配置 + 心跳保活 + 健康检查** 三层机制，我们大大提升了沙箱的稳定性和可用性：

✅ **自动保活**：无需手动干预  
✅ **提前预警**：剩余时间可见  
✅ **优雅降级**：失效后友好提示  

---

## 相关文件

- `tools/e2b_vibe_coding.py` - 核心实现
- `tests/demo_vibe_coding_live.py` - 使用示例
- `E2B_INTEGRATION_COMPLETE.md` - E2B 集成总览









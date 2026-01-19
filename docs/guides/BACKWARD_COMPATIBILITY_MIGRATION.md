# 向后兼容代码迁移指南

> 本文档记录项目中的向后兼容代码及其迁移路径。
> 最后更新：2026-01-18

## 概述

项目中存在多处向后兼容代码，用于支持旧版本 API 和平滑迁移。本文档帮助开发者了解这些兼容代码的状态，以及何时可以安全移除。

---

## 1. 已废弃字段（ChatRequest）

### 位置
- `models/chat_request.py`

### 废弃字段
| 字段 | 新位置 | 状态 |
|------|--------|------|
| `stream` | `options.stream` | ⚠️ 仍在使用 |
| `variables` | `context.custom_fields` | ⚠️ 仍在使用 |
| `background_tasks` | `options.background_tasks` | ⚠️ 仍在使用 |

### 使用情况
- `routers/chat.py`: 直接使用这些字段
- `grpc_server/chat_servicer.py`: gRPC 接口使用这些字段

### 迁移建议
1. **不能立即移除** - 前端/客户端仍在使用这些字段
2. 需要先更新所有客户端调用，使用新的 `options` 和 `context` 结构
3. 迁移完成后，移除 `merge_deprecated_fields()` 验证器和废弃字段

### 迁移时间表
- **Phase 1**: 通知所有客户端迁移到新 API（当前阶段）
- **Phase 2**: 添加废弃警告日志
- **Phase 3**: 移除废弃字段（需确认无外部依赖）

---

## 2. 工具模块导出（tools/__init__.py）

### 位置
- `tools/__init__.py`

### 状态
- ✅ **已清理** (2026-01-18)

### 变更
- 移除了废弃的导出（ToolSelector、ToolExecutor 等）
- 现在请使用 `from core.tool import ...`

---

## 3. 工具类映射（TOOL_CLASS_MAPPING）

### 位置
- `core/tool/executor.py`

### 状态
- ✅ **已清理** (2026-01-18)

### 变更
- 移除了 `TOOL_CLASS_MAPPING` 类属性
- 移除了 `_load_custom_tool` 方法中的 legacy 加载逻辑
- 所有工具现在统一从 `capabilities.yaml` 的 `implementation` 配置加载

---

## 4. UsageTracker 旧接口

### 位置
- `utils/usage_tracker.py`: 原始实现
- `core/billing/__init__.py`: 向后兼容导出
- `core/billing/tracker.py`: 新的 `EnhancedUsageTracker`

### 使用情况
| 文件 | 使用类 | 状态 |
|------|--------|------|
| `core/agent/simple_agent.py` | `UsageTracker` | ⚠️ 需要迁移 |
| `core/agent/multi/orchestrator.py` | `UsageTracker` | ⚠️ 需要迁移 |

### 迁移建议
1. 将 `UsageTracker` 替换为 `EnhancedUsageTracker`
2. `EnhancedUsageTracker` 支持多模型和 Message ID 去重
3. 迁移完成后移除 `utils/usage_tracker.py`

### 迁移时间表
- **Phase 1**: 迁移核心 Agent 使用新 Tracker（推荐）
- **Phase 2**: 移除旧 `UsageTracker`

---

## 5. 模型别名（CriticVerdict）

### 位置
- `core/agent/multi/models.py`

### 废弃代码
```python
# 向后兼容的别名
CriticVerdict = CriticAction

@property
def verdict(self) -> CriticAction:
    """向后兼容的 verdict 属性"""

@property
def improvement_hints(self) -> List[str]:
    """向后兼容的 improvement_hints 属性"""
```

### 迁移建议
- 使用 `CriticAction` 替代 `CriticVerdict`
- 使用 `recommended_action` 替代 `verdict`
- 使用 `suggestions` 替代 `improvement_hints`

### 迁移时间表
- **保留** - 内部使用，低优先级

---

## 6. ComplexityScorer 兼容

### 位置
- `core/routing/router.py`

### 说明
```python
# 🆕 V7.0: ComplexityScorer 保留向后兼容，但优先使用 LLM 输出的 complexity_score
# 否则 fallback 到 ComplexityScorer（向后兼容）
```

### 迁移建议
- **保留作为 Fallback** - 当 LLM 未返回 complexity_score 时使用
- 这是健壮性设计，不建议移除

---

## 7. Fallback 机制

### 说明
以下 Fallback 机制是健壮性设计，**不建议移除**：

| 模块 | Fallback | 用途 |
|------|----------|------|
| `infra/resilience/fallback.py` | `FallbackStrategy` | 服务降级框架 |
| `core/prompt/instance_cache.py` | 多级缓存 Fallback | 提示词加载失败时降级 |
| `core/routing/intent_analyzer.py` | 保守 Fallback | 意图分析失败时返回 OTHER |
| `core/inference/semantic_inference.py` | 保守 Fallback | 语义推理失败时返回默认值 |
| `infra/pools/agent_pool.py` | 慢路径 Fallback | Agent 不在池中时动态创建 |

### 测试覆盖
- ✅ **已添加测试** (2026-01-18)
- 测试文件: `tests/test_fallback_mechanisms.py`
- 覆盖范围: FallbackStrategy、FallbackType、默认降级响应、装饰器功能

运行测试:
```bash
pytest tests/test_fallback_mechanisms.py -v
```

---

## 迁移优先级总结

| 优先级 | 项目 | 状态 |
|--------|------|------|
| ✅ 完成 | `TOOL_CLASS_MAPPING` | 已移除 (2026-01-18) |
| ✅ 完成 | `tools/__init__.py` 废弃导出 | 已移除 (2026-01-18) |
| 🟡 中 | `UsageTracker` → `EnhancedUsageTracker` | 计划迁移 |
| 🟢 低 | `ChatRequest` 废弃字段 | 等待客户端迁移 |
| ⚪ 保留 | `ComplexityScorer` Fallback | 健壮性设计 |
| ⚪ 保留 | 其他 Fallback 机制 | 健壮性设计 |

---

## 变更历史

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-01-18 | V7.5 | 初始文档，记录所有向后兼容代码 |
| 2026-01-18 | V7.5 | 移除 `TOOL_CLASS_MAPPING` 和 `tools/__init__.py` 废弃导出 |
| 2026-01-18 | V7.5 | 添加 Fallback 机制测试 (`tests/test_fallback_mechanisms.py`) |

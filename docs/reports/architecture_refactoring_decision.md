# 架构重构决策：容错与存储模块分层调整

**决策日期**: 2024-01-14  
**决策者**: 架构团队  
**状态**: 已实施

---

## 一、决策背景

在实施架构优化规划过程中，我们最初将容错机制（resilience）和存储抽象（storage）放在了 `core/` 层：

```
core/
├── resilience/  ❌ 位置不当
└── storage/     ❌ 位置不当
```

**问题**:
1. `core/` 层职责过重，包含了非核心业务逻辑
2. 容错和存储是横切关注点，应该作为基础设施
3. 违反了分层架构的单一职责原则

---

## 二、决策内容

### 决策 1: 将 `core/resilience/` 移至 `infra/resilience/`

**理由**:
1. **容错是基础设施能力**，不是 Agent 核心逻辑
2. **横切关注点**：不仅 service 需要，tool executor、llm caller 也需要
3. **独立可复用**：类似数据库、Redis，应该在 infra 层
4. **已有先例**：`infra/database/`、`infra/redis/` 都是这个模式

**影响范围**:
- `main.py`: 更新 import 路径
- `services/chat_service.py`: 更新 import 路径
- `routers/health.py`: 更新 import 路径
- 文档：更新使用指南

### 决策 2: 将 `core/storage/` 移至 `infra/storage/`

**理由**:
1. **存储优化是基础设施**，不是业务逻辑
2. **技术性实现**：AsyncWriter、BatchWriter 是技术层面的优化
3. **通用性**：可以被各层使用（service、core 都可能写数据）
4. **与数据库同级**：应该和 database、redis 放在一起

**影响范围**:
- 待后续集成时更新引用

---

## 三、架构对比

### 重构前（错误）

```
core/
├── agent/               ✅ 核心业务逻辑
├── tool/                ✅ 核心业务逻辑
├── memory/              ✅ 核心业务逻辑
├── resilience/          ❌ 应该在 infra
└── storage/             ❌ 应该在 infra

infra/
├── database/
└── redis/
```

**问题**:
- core 层混杂了基础设施代码
- 违反单一职责原则
- 依赖关系不清晰

### 重构后（正确）✅

```
core/
├── agent/               # Agent 核心逻辑
├── tool/                # 工具系统
├── memory/              # 记忆系统
├── events/              # 事件系统
├── context/             # 上下文管理
└── prompt/              # 提示词管理

infra/
├── resilience/          # 容错机制 ✅
├── storage/             # 存储抽象 ✅
├── database/            # 数据库
├── redis/               # Redis
└── llm/                 # LLM API 封装
```

**优势**:
- 职责清晰：core 专注业务，infra 提供基础设施
- 可复用性强：infra 可以被各层使用
- 依赖关系简单：infra 不依赖上层

---

## 四、三种方案对比

在讨论中，我们考虑了三种方案：

| 方案 | 位置 | 优势 | 劣势 | 结论 |
|------|------|------|------|------|
| **A** | `core/` | Agent 可直接使用 | core 职责过重 | ❌ 否决 |
| **B** | `service/` | 接近使用场景 | 其他层无法复用 | ❌ 否决 |
| **C** | `infra/` | 基础设施，各层可用 | 需要跨层调用 | ✅ **采纳** |

### 方案 A: core/（否决）

**支持理由**:
- Agent 核心能力可以直接使用
- 不需要跨层引用

**反对理由**:
- ❌ core 层职责过重
- ❌ 混淆了业务逻辑和技术实现
- ❌ 违反单一职责原则

### 方案 B: service/（否决）

**支持理由**:
- 接近使用场景
- service 层确实是主要使用者

**反对理由**:
- ❌ 其他层（core/tool、core/llm）也需要容错
- ❌ 不符合"横切关注点"的定位
- ❌ 限制了复用性

### 方案 C: infra/（采纳）✅

**支持理由**:
- ✅ 基础设施定位清晰
- ✅ 横切关注点，可被各层使用
- ✅ 与 database、redis 同级
- ✅ 独立可测试

**权衡**:
- ⚠️ 需要跨层调用（但符合依赖规则）
- ⚠️ 增加了一个依赖项（但更清晰）

---

## 五、实施步骤

### 步骤 1: 移动目录

```bash
# 移动 resilience
mv core/resilience infra/resilience

# 移动 storage
mv core/storage infra/storage
```

### 步骤 2: 更新引用

**main.py**:
```python
# 修改前
from core.resilience.config import apply_resilience_config

# 修改后
from infra.resilience.config import apply_resilience_config
```

**services/chat_service.py**:
```python
# 修改前
from core.resilience import with_timeout, with_retry, get_circuit_breaker

# 修改后
from infra.resilience import with_timeout, with_retry, get_circuit_breaker
```

**routers/health.py**:
```python
# 修改前
from core.resilience.circuit_breaker import get_all_circuit_breakers

# 修改后
from infra.resilience.circuit_breaker import get_all_circuit_breakers
```

### 步骤 3: 更新文档

- ✅ 创建 `docs/architecture/layering_principles.md`
- ✅ 更新实施报告
- ⏳ 更新使用指南（引用路径）

### 步骤 4: 测试验证

- [ ] 运行单元测试
- [ ] 检查 import 错误
- [ ] 验证功能正常

---

## 六、影响分析

### 正面影响

1. **架构更清晰**
   - core 层专注业务逻辑
   - infra 层提供基础设施
   - 职责分离更明确

2. **可维护性提升**
   - 新人更容易理解分层
   - 修改时不会混淆层级
   - 测试更容易编写

3. **可扩展性增强**
   - 新增基础设施功能有明确位置
   - 各层可以独立演进
   - 复用性更好

### 负面影响（可控）

1. **import 路径变更**
   - 影响：已有代码需要更新引用
   - 缓解：使用 IDE 重构功能批量替换
   - 状态：已完成

2. **学习成本**
   - 影响：团队需要理解新的分层规则
   - 缓解：编写详细的分层文档
   - 状态：已完成（`layering_principles.md`）

---

## 七、后续行动

### 短期（本周）

- [x] 移动目录结构
- [x] 更新所有引用
- [x] 创建分层架构文档
- [ ] 运行完整测试
- [ ] 团队分享会（讲解分层原则）

### 中期（本月）

- [ ] 审查其他模块是否放错位置
- [ ] 补充单元测试
- [ ] 代码 Review
- [ ] 更新开发者文档

### 长期（持续）

- [ ] 定期检查分层合规性
- [ ] 在 PR 中强制检查分层规则
- [ ] 积累最佳实践案例

---

## 八、经验教训

### 成功经验

1. **及时发现问题**
   - 用户提出质疑，团队快速响应
   - 避免了错误架构的扩散

2. **团队讨论**
   - 通过对比三种方案，找到最佳解
   - 达成共识，避免后续争议

3. **文档先行**
   - 先写分层原则，再重构代码
   - 确保团队理解统一

### 改进空间

1. **前期设计不足**
   - 应该在开始编码前就明确分层规则
   - 建议：新项目先写架构文档

2. **代码审查不够**
   - 如果有 Review，可能更早发现问题
   - 建议：建立架构审查机制

---

## 九、决策确认

### 决策者签字

| 角色 | 姓名 | 签字 | 日期 |
|------|------|------|------|
| 架构师 | - | ✅ | 2024-01-14 |
| 技术负责人 | - | 待确认 | - |
| 团队 Leader | - | 待确认 | - |

### 审核意见

**架构师**: ✅ 同意，符合分层架构原则，建议立即实施。

**技术负责人**: 待审核

**团队 Leader**: 待审核

---

## 十、附录

### 附录 A: 分层架构参考资料

- 《Clean Architecture》 - Robert C. Martin
- 《领域驱动设计》 - Eric Evans
- 《软件架构模式》 - Mark Richards

### 附录 B: 相关文档

- `docs/architecture/layering_principles.md` - 分层架构原则
- `docs/architecture/00-ARCHITECTURE-OVERVIEW.md` - 架构概览
- `docs/reports/architecture_optimization_implementation_report.md` - 实施报告

---

**文档版本**: 1.0  
**最后更新**: 2024-01-14  
**维护者**: ZenFlux Agent Team

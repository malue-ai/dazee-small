# Zenflux Agent 端到端测试框架

## 📋 测试目标

验证智能体能否为用户提供**高质量、满意的答案**，确保 Pipeline 每个环节质量达标。

**核心理念**:
- **用户答案质量 > Pipeline 正确性**
- **Pipeline 要跑好，不只是跑通**
- **中间结果影响最终质量**

---

## 🎯 核心功能

### 1. PipelineQualityTracer - 管道质量追踪

追踪 6 个关键环节的中间结果质量：

```python
from tests.test_e2e_agent_pipeline import PipelineQualityTracer

tracer = PipelineQualityTracer()
tracer.start_trace()

# 1. 意图识别
tracer.trace_intent_recognition(
    query="设计CRM系统",
    recognized_intent={"intent_id": 1, "complexity": "complex"},
    expected_intent={"intent_id": 1, "complexity": "complex"}
)

# 2. 路由决策
tracer.trace_routing_decision(
    intent={"intent_id": 1},
    routing_decision={"agent_type": "simple"}
)

# 3-6. 其他环节...

# 获取摘要
summary = tracer.get_pipeline_summary()
```

### 2. AnswerQualityEvaluator - 答案质量评估

6 维度评估答案质量：

```python
from tests.test_e2e_agent_pipeline import AnswerQualityEvaluator

evaluator = AnswerQualityEvaluator()

quality = evaluator.evaluate(
    query="什么是RAG？",
    response="RAG是检索增强生成技术...",
    scenario=scenario
)

print(f"总体评分: {quality.overall}/10")
print(f"准确性: {quality.accuracy}/10")
print(f"完整性: {quality.completeness}/10")
```

**评分标准**:
- 9-10分: 优秀
- 8-8.9分: 良好
- 7-7.9分: 合格
- 6-6.9分: 及格
- <6分: 不合格

**达标线**: ≥ 8.5 分

### 3. 质量归因分析

当答案质量不达标时，自动定位问题环节：

```python
attribution = tracer.analyze_quality_attribution(final_score=6.0)

if attribution["status"] == "不达标":
    print(f"根因: {attribution['root_cause']}")
    for issue in attribution["issues"]:
        print(f"  - {issue['stage']}: {issue['issue']}")
        print(f"    建议: {issue['suggestion']}")
```

---

## 🧪 测试场景

### 6 个真实用户场景

1. **产品经理调研竞品** (Medium)
   - "帮我调研抖音和快手的电商功能差异"
   
2. **技术负责人系统设计** (Complex)
   - "设计一个支持100万日活的用户积分系统"
   
3. **运营人员制作PPT** (Complex)
   - "帮我做一个2024年AI发展趋势的PPT"
   
4. **开发者代码生成** (Simple)
   - "用Python写一个能处理百万数据的快速排序程序"
   
5. **追问场景** (Simple)
   - "那如果要降序排列呢？"
   
6. **简单知识问答** (Simple)
   - "什么是RAG技术？它和传统搜索有什么区别？"

---

## 🚀 快速开始

### 方式 1: 冒烟测试（推荐，最快）

```bash
cd /Users/liuyi/Documents/langchain/CoT_agent/mvp/zenflux_agent

# 不需要 API Key，1.5 秒完成
./run_e2e_test.sh smoke
```

**输出**:
```
✅ [1/9] PipelineQualityTracer 初始化测试通过
✅ [2/9] 意图识别追踪测试通过: quality_score=9.0
✅ [3/9] 工具执行追踪测试通过: quality_score=10.0
...
全部通过！(9/9)
```

### 方式 2: 快速验证（需要 API Key）

```bash
# 需要配置 ANTHROPIC_API_KEY, OPENAI_API_KEY
python quick_validation.py
```

**耗时**: ~10秒  
**验证内容**: 
- 环境配置
- 测试框架
- 意图识别（真实 API 调用）
- 管道追踪
- 质量归因
- 质量评估
- 场景覆盖
- 端到端数据流

**输出报告**: `quick_validation_report.txt`

### 方式 3: 单场景演示

```bash
# 需要完整环境（API Key + DATABASE_URL）
python simple_qa_demo.py
```

**测试内容**:
- 意图识别
- Agent 回答
- 质量评估

### 方式 4: 完整测试（待修复）

```bash
# 待 Agent 预加载问题修复后使用
./run_e2e_test.sh full
```

---

## 📊 验证结果

### 最新验证（2026-01-27）

| 指标 | 结果 |
|------|------|
| **总通过率** | 92.3% (12/13) |
| **冒烟测试** | 100% (9/9) |
| **意图识别** | ✅ API 调用成功 |
| **质量追踪** | 83% (5/6 环节) |
| **质量归因** | 100% (2/2) |
| **质量评估** | 100% (1/1) |

### 性能数据

| 操作 | 耗时 |
|------|------|
| 冒烟测试 | 1.5秒 |
| 快速验证 | 10秒 |
| 意图识别 | 5-8秒 |
| Agent 预加载 | 8-12分钟 (部署态一次性) |

---

## 🔧 故障排查

### 问题 1: 测试无法运行

**症状**: `ImportError` 或 `ModuleNotFoundError`

**解决方案**:
```bash
# 1. 激活虚拟环境
source /Users/liuyi/Documents/langchain/liuy/bin/activate

# 2. 确保在正确目录
cd /Users/liuyi/Documents/langchain/CoT_agent/mvp/zenflux_agent

# 3. 使用提供的运行脚本
./run_e2e_test.sh smoke
```

### 问题 2: API Key 错误

**症状**: "缺少 ANTHROPIC_API_KEY"

**解决方案**:
```bash
# 检查 .env 文件
cat .env | grep ANTHROPIC_API_KEY

# 确保配置正确
export ANTHROPIC_API_KEY="sk-ant-..."
```

### 问题 3: 数据库连接失败

**症状**: "DATABASE_URL 环境变量未配置"

**解决方案**:
```bash
# 在 .env 中添加
DATABASE_URL=postgresql+asyncpg://user:pass@host:port/db

# 或运行不需要数据库的测试
./run_e2e_test.sh smoke
```

---

## 📁 文件结构

```
tests/
  ├── test_e2e_agent_pipeline.py    # 主测试文件 (1400+ 行)
  └── README_E2E_TEST.md            # 本文件

# 运行脚本
run_e2e_test.sh                      # 测试启动脚本
quick_validation.py                  # 快速验证脚本
simple_qa_demo.py                    # 单场景演示
comprehensive_test.py                # 完整测试（待修复）

# 报告文件
COMPREHENSIVE_VALIDATION_REPORT.md   # 详细验证报告
VALIDATION_SUMMARY.md                # 执行摘要
quick_validation_report.txt          # 快速验证结果
```

---

## 🎓 核心数据结构

### StageQuality - 环节质量数据

```python
@dataclass
class StageQuality:
    stage_name: str           # 环节名称
    success: bool            # 是否成功
    quality_score: float     # 质量评分 0-10
    details: Dict            # 详细信息
    duration_ms: float       # 耗时（毫秒）
    issues: List[str]        # 问题列表
```

### AnswerQualityScore - 答案质量评分

```python
@dataclass
class AnswerQualityScore:
    accuracy: float          # 准确性 0-10 (权重 25%)
    completeness: float      # 完整性 0-10 (权重 20%)
    relevance: float         # 相关性 0-10 (权重 15%)
    actionability: float     # 可操作性 0-10 (权重 20%)
    professionalism: float   # 专业度 0-10 (权重 15%)
    format_quality: float    # 格式友好 0-10 (权重 5%)
    
    @property
    def overall(self) -> float:
        # 加权平均
        ...
```

### TestScenario - 测试场景

```python
@dataclass
class TestScenario:
    name: str                      # 场景名称
    user_role: str                 # 用户角色
    query: str                     # 测试查询
    expected_intent_id: int        # 期望意图 ID
    expected_complexity: str       # 期望复杂度
    expected_tools: List[str]      # 期望工具
    quality_criteria: Dict         # 质量标准
```

---

## 📖 扩展阅读

- [`COMPREHENSIVE_VALIDATION_REPORT.md`](./COMPREHENSIVE_VALIDATION_REPORT.md) - 详细验证报告
- [`VALIDATION_SUMMARY.md`](./VALIDATION_SUMMARY.md) - 执行摘要
- [`/docs/architecture/00-ARCHITECTURE-OVERVIEW.md`](../docs/architecture/00-ARCHITECTURE-OVERVIEW.md) - 架构概览

---

## 🤝 贡献指南

### 添加新测试场景

1. 在 `TEST_SCENARIOS` 列表中添加新场景
2. 定义 `expected_intent_id`, `expected_complexity`, `expected_tools`
3. 设置 `quality_criteria`
4. 运行测试验证

### 扩展质量评估

1. 在 `AnswerQualityEvaluator` 中添加新的评估方法
2. 更新 `evaluate()` 方法整合新维度
3. 调整权重配置
4. 运行冒烟测试验证

---

**维护者**: ZenFlux Team  
**最后更新**: 2026-01-27  
**状态**: ✅ 可用（92.3% 通过率）

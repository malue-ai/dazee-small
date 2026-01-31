# AI Agent 自动化测试工程师面试题 - 参考答案

> **说明**：本文档为面试官评分参考，包含各题目的关键答案要点和评分标准

---

## 题目一：Agent 非确定性测试策略设计

### 1. 测试策略设计（30 分）

#### 任务规划测试（10 分）

**验证方法**：

| 方法 | 说明 | 实现难度 |
|------|------|---------|
| **结构验证** | 检查 JSON 格式、必需字段（goal/steps/step_id）是否完整 | 简单 |
| **步骤合理性** | 验证步骤数量（3-10 个）、每个步骤是否可执行、是否有明确 action | 中等 |
| **依赖关系** | 检查步骤顺序是否合理（如"读取文件"必须在"分析文件"之前） | 中等 |
| **LLM-as-Judge** | 使用另一个 LLM 评估计划质量（1-5 分） | 中等 |
| **执行验证** | 实际执行计划，看是否能完成任务（最可靠但成本高） | 高 |

**测试用例设计**：

| 复杂度 | 任务示例 | 预期步骤数 |
|--------|---------|-----------|
| 简单 | "读取 data.csv 文件" | 1-2 步 |
| 中等 | "生成 Q4 销售分析报告" | 3-5 步 |
| 复杂 | "分析竞品数据并生成对比报告" | 5-10 步 |

**关键要点**：
- 不能期望 plan 的文本完全一致，但结构和步骤类型应该稳定
- 建立"参考计划"，计算相似度（如步骤类型匹配率 >70%）

---

#### 工具调用链测试（10 分）

**验证策略**：

```python
# 核心思路：验证工具调用的"有效性"而非"唯一性"

class ToolChainValidator:
    def validate(self, task, actual_chain):
        # 1. 必要工具检查
        required_tools = self.get_required_tools(task)
        if not all(tool in actual_chain for tool in required_tools):
            return False
        
        # 2. 禁止工具检查
        forbidden_tools = self.get_forbidden_tools(task)
        if any(tool in actual_chain for tool in forbidden_tools):
            return False
        
        # 3. 顺序依赖检查
        for dep in self.get_dependencies(task):
            if not self.check_order(actual_chain, dep['before'], dep['after']):
                return False
        
        # 4. 参数有效性检查
        for call in actual_chain:
            if not self.validate_params(call.tool, call.params):
                return False
        
        return True
```

**多路径处理**：
- 定义"等价路径"：search→summarize 和 search→read→summarize 都接受
- 使用"路径白名单"而非精确匹配
- 评分标准：最优路径 100 分，次优路径 90 分，可接受路径 80 分

---

#### 多轮对话测试（10 分）

**上下文记忆测试**：

```yaml
# 测试用例示例
test_case:
  name: "context_memory_test"
  conversation:
    - turn: 1
      user: "我叫张三，我是产品经理"
      expected_keywords: ["张三", "产品经理"]
    
    - turn: 2
      user: "我的工作内容是什么？"
      expected_content:
        - must_contain: ["产品经理"]
        - must_not_contain: ["不知道", "没有提到"]
    
    - turn: 3
      user: "我叫什么名字？"
      expected_content:
        - must_contain: ["张三"]
```

**自相矛盾检测**：
- 使用 NLI（自然语言推理）模型检测矛盾
- 示例：Turn 1 说"我喜欢 Python"，Turn 3 说"你不喜欢 Python" → 矛盾
- 阈值：矛盾置信度 >0.8 则判定为失败

**对话测试用例设计**：

| 测试场景 | 轮次 | 验证点 |
|---------|------|-------|
| 基础记忆 | 3-5 轮 | 记住用户身份、偏好 |
| 长期记忆 | 10+ 轮 | 不遗忘最初信息 |
| 复杂引用 | 5-8 轮 | 正确引用之前的讨论内容 |

---

### 2. 质量评估方案（20 分）

#### 评估维度（8 分）

| 维度 | 评分标准 | 权重 |
|------|---------|------|
| **正确性** | 事实是否准确、逻辑是否合理 | 30% |
| **完整性** | 是否回答了所有问题、是否遗漏关键信息 | 25% |
| **相关性** | 回复是否切题、是否有无关内容 | 20% |
| **流畅性** | 语言是否自然、是否有语法错误 | 15% |
| **安全性** | 是否包含有害内容、是否泄露隐私 | 10% |

**量化评分**：每个维度 0-10 分，加权求和得到总分（0-100）

---

#### LLM-as-Judge 方案（8 分）

**实现思路**：

```python
class LLMJudge:
    def evaluate(self, user_input, agent_output, reference=None):
        prompt = f"""
你是一个专业的 AI 评估专家，请评估以下 Agent 输出的质量。

用户输入：{user_input}
Agent 输出：{agent_output}
参考答案（可选）：{reference}

请从以下维度评分（每项 0-10 分）：
1. 正确性：事实是否准确
2. 完整性：是否充分回答
3. 相关性：是否切题
4. 流畅性：语言是否自然

输出格式（JSON）：
{{
    "correctness": 8,
    "completeness": 9,
    "relevance": 10,
    "fluency": 9,
    "reasoning": "评分理由..."
}}
"""
        result = self.llm.generate(prompt)
        return json.loads(result)
```

**优势**：
- 能够理解语义和上下文
- 不需要人工标注大量样本
- 可以评估开放性问题

**局限性**：
- LLM 本身可能有偏见
- 评估成本高（每次评估都调用 LLM）
- 稳定性问题（同样输入可能不同评分）

**稳定性保证**：
- 使用温度=0（减少随机性）
- 多次评估取平均（如 3 次评估的均值）
- 固定评估模型版本

---

#### 成本控制（4 分）

**Mock 策略**：

| 测试类型 | Mock 策略 | 理由 |
|---------|----------|------|
| **单元测试** | 100% Mock | 测试逻辑而非 LLM 能力 |
| **集成测试** | 部分 Mock | Mock 外部依赖，真实调用 LLM |
| **E2E 测试** | 最小 Mock | 验证真实场景 |
| **回归测试** | 缓存复用 | 相同输入使用缓存结果 |

**成本优化策略**：
- 使用小模型进行冒烟测试（Claude Haiku）
- 关键场景使用大模型（Claude Sonnet）
- 建立测试集缓存（相同输入不重复调用）
- 预算控制：设置每日测试预算上限

**平衡方案**：
- 核心路径：100% 真实测试
- 边缘场景：20% 采样测试
- 预期成本：每日 $50-100

---

### 3. 回归测试设计（15 分）

#### 黄金测试集建立（5 分）

**选择标准**：

| 标准 | 说明 |
|------|------|
| **代表性** | 覆盖核心业务场景（如报告生成、数据分析） |
| **复杂度** | 包含简单、中等、复杂三档任务 |
| **高频** | 用户最常使用的功能 |
| **易错** | 历史上容易出错的场景 |

**测试集规模**：
- 核心场景：30-50 个
- 边缘场景：50-100 个
- 总计：100-150 个测试用例

**维护机制**：
- 每季度审查一次，淘汰过时用例
- 生产问题自动加入测试集

---

#### 性能退化检测（5 分）

**指标监控**：

```python
class RegressionDetector:
    def detect(self, baseline_results, current_results):
        metrics = {
            "quality_score": self.compare_quality(baseline, current),
            "success_rate": self.compare_success_rate(baseline, current),
            "avg_cost": self.compare_cost(baseline, current),
            "avg_latency": self.compare_latency(baseline, current)
        }
        
        # 退化判定规则
        if metrics["quality_score"] < baseline.quality * 0.95:
            return "REGRESSION: 质量下降超过 5%"
        
        if metrics["success_rate"] < baseline.success_rate * 0.90:
            return "REGRESSION: 成功率下降超过 10%"
        
        return "PASS"
```

**阈值设定**：
- 质量分下降 >5% → 告警
- 成功率下降 >10% → 阻断发布
- 成本上升 >20% → 告警
- 延迟增加 >30% → 告警

---

#### 改进与退化判断（5 分）

**边界场景**：

| 场景 | 判断标准 |
|------|---------|
| 质量提升但成本增加 | 评估 ROI，是否值得 |
| 部分场景变好，部分变差 | 加权评估，核心场景权重更高 |
| 风格变化但质量相当 | 用户调研，看接受度 |

**决策流程**：
1. 自动评估：指标对比
2. 人工审查：边界场景
3. AB 测试：线上小流量验证
4. 全量发布：确认无退化后

---

## 题目二：端到端测试框架设计与多模型容灾测试

### 1. E2E 测试框架设计（30 分）

#### 测试环境隔离（10 分）

**隔离策略**：

| 组件 | 隔离方法 |
|------|---------|
| **数据库** | 独立测试数据库（test_db）或使用 Docker 容器 |
| **Memory** | 测试专用 Memory Store，前缀 `test_` |
| **LLM API** | 使用测试专用 API Key，设置 rate limit |
| **第三方 API** | Mock 或使用 sandbox 环境 |
| **文件系统** | 临时目录（/tmp/test_xxx），测试后清理 |

**可重复性保证**：
```python
class TestEnvironment:
    def setup(self):
        # 1. 固定随机种子
        random.seed(42)
        np.random.seed(42)
        
        # 2. 固定 LLM 温度
        self.llm_config = {"temperature": 0}
        
        # 3. 清理旧数据
        self.clean_test_data()
        
        # 4. 初始化测试数据
        self.init_test_fixtures()
    
    def teardown(self):
        # 清理所有测试数据
        self.clean_test_data()
```

**外部依赖处理**：
- LLM API：使用真实 API，但设置预算限制
- 搜索 API：Mock（使用预录的响应）
- 沙箱环境：使用 Docker 容器，每次测试重建

---

#### 测试用例组织（10 分）

**目录结构**：

```
tests/
├── e2e/
│   ├── single_turn/        # 单轮对话
│   │   ├── test_simple_qa.py
│   │   ├── test_tool_calling.py
│   ├── multi_turn/         # 多轮对话
│   │   ├── test_context_memory.py
│   │   ├── test_task_planning.py
│   ├── complex_tasks/      # 复杂任务
│   │   ├── test_report_generation.py
│   │   ├── test_data_analysis.py
│   └── fixtures/           # 测试数据
│       ├── conversations.yaml
│       ├── tasks.yaml
│       └── expected_outputs.yaml
```

**测试数据管理**：

```yaml
# fixtures/conversations.yaml
test_cases:
  - id: "report_generation_001"
    name: "生成销售报告"
    inputs:
      - "生成 Q4 销售分析报告"
    expected:
      tool_calls: ["web_search", "data_analysis", "ppt_generator"]
      output_format: "ppt"
      quality_threshold: 85
    
  - id: "multi_turn_context_001"
    name: "多轮对话记忆测试"
    conversation:
      - user: "我叫张三"
        expected_ack: true
      - user: "我叫什么？"
        expected_keywords: ["张三"]
```

**参数化测试**：
```python
@pytest.mark.parametrize("test_case", load_test_cases("conversations.yaml"))
def test_conversation(test_case, agent):
    result = agent.chat(test_case["input"])
    assert evaluate_quality(result) >= test_case["quality_threshold"]
```

---

#### 断言策略（10 分）

**流式输出（SSE）断言**：

```python
class SSETestClient:
    def test_streaming(self, endpoint, input_data):
        events = []
        
        # 1. 收集所有事件
        response = self.client.post(endpoint, stream=True)
        for line in response.iter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:]))
        
        # 2. 验证事件序列
        assert events[0]["type"] == "start"
        assert any(e["type"] == "tool_call" for e in events)
        assert events[-1]["type"] == "end"
        
        # 3. 验证最终输出
        final_output = self.reconstruct_output(events)
        assert self.validate_output(final_output)
```

**Memory 状态验证**：

```python
def test_memory_state(agent, conversation):
    # 执行对话
    for turn in conversation:
        agent.chat(turn["user"])
    
    # 验证 Memory 状态
    memory = agent.memory_manager.get_working_memory()
    assert len(memory.messages) == len(conversation) * 2  # user + assistant
    
    # 验证关键信息被记住
    assert memory.has_entity("张三")
    assert memory.get_preference("report_style") == "concise"
```

**工具调用验证**：

```python
def test_tool_chain(agent, task):
    result = agent.execute_task(task)
    
    # 验证工具调用顺序
    tool_calls = result.get_tool_calls()
    assert self.validate_tool_chain(tool_calls, task)
    
    # 验证参数有效性
    for call in tool_calls:
        assert self.validate_tool_params(call.tool, call.params)
```

---

### 2. 多模型容灾测试（20 分）

#### 故障注入测试（10 分）

**模拟故障**：

```python
class FaultInjector:
    def inject_claude_timeout(self, duration=5):
        """模拟 Claude API 超时"""
        with mock.patch("anthropic.Anthropic.messages.create") as m:
            m.side_effect = APITimeoutError("Request timeout")
            yield
    
    def inject_rate_limit(self):
        """模拟 429 限流"""
        with mock.patch("anthropic.Anthropic.messages.create") as m:
            m.side_effect = RateLimitError("429 Too Many Requests")
            yield
    
    def inject_service_unavailable(self):
        """模拟 503 服务不可用"""
        with mock.patch("anthropic.Anthropic.messages.create") as m:
            m.side_effect = APIConnectionError("503 Service Unavailable")
            yield
```

**切换验证**：

```python
def test_auto_failover(agent, fault_injector):
    # 1. 正常情况：使用 Claude
    result = agent.chat("生成报告")
    assert result.model_used == "claude"
    
    # 2. 注入故障：Claude 不可用
    with fault_injector.inject_rate_limit():
        result = agent.chat("生成报告")
        # 验证自动切换到 Qwen
        assert result.model_used == "qwen"
        # 验证任务仍然成功
        assert result.success == True
    
    # 3. 故障恢复：切回 Claude
    result = agent.chat("生成报告")
    assert result.model_used == "claude"
```

**功能完整性验证**：
- 切换后核心功能仍可用
- 输出质量可接受（允许有差异）
- 响应时间在合理范围内

---

#### 降级行为测试（6 分）

**Skills 降级测试**：

```python
def test_skills_fallback():
    # Claude Skills：原生支持
    result_claude = agent.chat("生成 Excel 报告", model="claude")
    assert result_claude.used_skill == "xlsx"
    assert result_claude.output_format == "xlsx"
    
    # Qwen 降级：使用开源库
    result_qwen = agent.chat("生成 Excel 报告", model="qwen")
    assert result_qwen.used_fallback == True
    assert result_qwen.output_format == "xlsx"  # 格式一致
    
    # 质量对比
    quality_diff = compare_quality(result_claude, result_qwen)
    assert quality_diff < 0.15  # 质量差异 <15%
```

**可接受性验证**：
- 用户无感知（输出格式一致）
- 质量差异 <20%
- 延迟增加 <50%

---

#### 性能与成本测试（4 分）

**响应速度对比**：

```python
def test_model_performance():
    tasks = load_test_tasks()
    
    results = {
        "claude": benchmark(tasks, model="claude"),
        "qwen": benchmark(tasks, model="qwen")
    }
    
    # 延迟对比
    assert results["qwen"]["avg_latency"] < results["claude"]["avg_latency"] * 1.2
    
    # 成本对比
    assert results["qwen"]["avg_cost"] < results["claude"]["avg_cost"] * 0.5
```

---

### 3. 生产监控与测试联动（15 分）

#### 生产探针测试（5 分）

**探针设计**：

```python
class HealthProbe:
    def __init__(self):
        self.probe_tasks = [
            {"type": "simple_qa", "input": "你好", "timeout": 5},
            {"type": "tool_call", "input": "搜索AI新闻", "timeout": 15},
            {"type": "planning", "input": "生成报告", "timeout": 20}
        ]
    
    def run_probe(self):
        """每 5 分钟执行一次"""
        results = []
        for task in self.probe_tasks:
            try:
                result = self.agent.chat(task["input"], timeout=task["timeout"])
                results.append({
                    "task": task["type"],
                    "success": result.success,
                    "latency": result.latency,
                    "model": result.model_used
                })
            except Exception as e:
                results.append({
                    "task": task["type"],
                    "success": False,
                    "error": str(e)
                })
        
        # 发送到监控系统
        self.report_metrics(results)
```

**与常规测试区别**：

| 维度 | 常规测试 | 探针测试 |
|------|---------|---------|
| 频率 | 每次发布 | 每 5 分钟 |
| 环境 | 测试环境 | 生产环境 |
| 数据 | 测试数据 | 真实请求（极简） |
| 影响 | 无 | 最小化（使用测试账号） |

---

#### 故障复现（5 分）

**请求记录**：

```python
class RequestLogger:
    def log_request(self, request_id, context):
        """记录完整请求上下文"""
        log_data = {
            "request_id": request_id,
            "timestamp": datetime.now(),
            "user_input": context.user_input,
            "conversation_history": context.messages,
            "memory_state": context.memory.snapshot(),
            "model_config": context.model_config,
            "tool_calls": context.tool_calls,
            "final_output": context.output,
            "error": context.error if context.failed else None
        }
        self.save_to_s3(log_data)
```

**故障回放**：

```python
def replay_request(request_id):
    # 1. 加载请求上下文
    context = load_request_log(request_id)
    
    # 2. 恢复环境
    test_env = TestEnvironment()
    test_env.restore_memory(context.memory_state)
    test_env.restore_conversation(context.conversation_history)
    
    # 3. 重放请求
    result = agent.chat(context.user_input, config=context.model_config)
    
    # 4. 对比结果
    assert result == context.final_output or context.error
```

---

#### 质量看板（5 分）

**核心指标**：

| 指标 | 阈值 | 告警级别 |
|------|------|---------|
| **可用性** | >99.5% | P0（立即） |
| **成功率** | >95% | P1（1 小时内） |
| **P95 延迟** | <10s | P2（24 小时内） |
| **质量分** | >85 | P2 |
| **日成本** | <$500 | P2 |

**告警规则**：

```python
class AlertManager:
    def check_metrics(self, metrics):
        alerts = []
        
        # 可用性告警
        if metrics.availability < 0.995:
            alerts.append({
                "level": "P0",
                "message": f"可用性下降: {metrics.availability:.2%}"
            })
        
        # 成功率告警
        if metrics.success_rate < 0.95:
            alerts.append({
                "level": "P1",
                "message": f"成功率下降: {metrics.success_rate:.2%}"
            })
        
        # 延迟告警
        if metrics.p95_latency > 10:
            alerts.append({
                "level": "P2",
                "message": f"P95 延迟: {metrics.p95_latency}s"
            })
        
        return alerts
```

---

## 加分点总结

**题目一**：
- 能提出创新的质量评估方法（如对抗测试、A/B 对比）
- 能考虑测试的可维护性和可扩展性
- 能给出具体的工具选型和实现方案

**题目二**：
- 能设计完整的测试框架代码结构
- 能考虑测试的自动化和 CI/CD 集成
- 能结合 Chaos Engineering 思想设计故障测试

---

## 评分说明

优秀候选人应能展示：
1. 深刻理解 AI Agent 与传统软件的测试差异
2. 完整的测试方案设计能力
3. 对质量和成本的平衡意识
4. 实际的工具和框架使用经验

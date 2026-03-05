# Estimand 描述生成 (content_type: estimand)

基于以下 Protocol 实体，为每个主要/关键次要终点撰写完整的 Estimand 描述。

## 输入变量

- `{endpoints}` — 从 protocol_entities.json 提取的终点列表（含 name, category, type, timeframe, definition）
- `{study_design}` — 研究设计概要（随机化比例、分层因素、治疗组）
- `{intercurrent_events}` — Protocol 中定义的 intercurrent events 及处理策略

## 输出要求

对每个 primary 和 key_secondary 终点，按 ICH E9(R1) 五属性框架输出：

1. **Population** — 目标人群定义（引用 Protocol 的入排标准原文）
2. **Endpoint** — 终点变量定义（与 Protocol 原文一致，含测量时间点和计算方法）
3. **Treatment condition** — 治疗条件及 estimand 策略（treatment policy / composite / hypothetical / principal stratum）
4. **Intercurrent events** — 列出每个 ICE 及其处理策略，说明选择该策略的理由
5. **Population-level summary** — 汇总统计量（如 rate ratio、LS mean difference、hazard ratio）及其 95% CI 和 p 值

## 格式规则

- 每个 Estimand 用加粗标题分隔：**Primary Estimand 1: {endpoint_name}**
- 五属性用无序列表（`- **Population:**` 等）
- Protocol 中未明确规定但根据标准实践推断的内容标注 `[AI-INFERRED]`
- 不输出 Markdown 标题（`#`/`##`），只输出正文段落和列表
- 使用被动语态 + 将来时态
- 终点名称必须与 Protocol 完全一致，不要改写或缩写

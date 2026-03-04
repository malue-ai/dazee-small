# 主要终点分析方法 (content_type: primary_analysis)

基于以下 Protocol 实体，为每个主要终点撰写完整的统计分析方法描述。

## 输入变量

- `{endpoint}` — 当前终点（name, type, timeframe, definition）
- `{statistical_methods}` — Protocol 规定的统计方法（如负二项回归、MMRM、Cox PH）
- `{study_design}` — 随机化方案、分层因素
- `{analysis_populations}` — 分析人群定义（ITT, Safety, Per-Protocol）

## 输出结构（按顺序）

### A. 终点定义 (Definition of Endpoint)

- 终点变量的精确定义（与 Protocol 原文一致）
- 基线定义（baseline 的确定方法）
- 事件定义（如适用，如 exacerbation 的判定标准）
- 两个事件的区分规则（如 28 天间隔规则）

### B. 主要分析方法 (Main Analytical Approach)

完整的模型规格，必须包含：
- **响应变量**（response variable）
- **分布假设**（如负二项分布、正态分布）
- **链接函数**（如 log link）
- **固定效应/协变量**（逐一列出：治疗组、年龄组、地区、基线分层因素等）
- **Offset 变量**（如适用，如 log-transformed duration）
- **协方差结构**（如 unstructured，仅 MMRM 适用）
- **估计方法**（如 REML、ML）
- **自由度方法**（如 Kenward-Roger）
- **主要治疗比较**（active vs placebo 的对比方式、多重性调整层级步骤）
- **SAS/R 实现代码指引**（如 PROC GENMOD / PROC MIXED 的关键选项）

### C. 敏感性分析 (Sensitivity Analyses)

列出 3-5 个预设的敏感性分析，每个包含：
- 分析名称和目的
- 与主要分析的差异点
- 对缺失数据假设的影响

### D. 补充分析 (Supplementary Analyses)

亚组分析、重复测量延伸等。

## 格式规则

- 不输出 Markdown 标题（`#`/`##`），只输出正文段落和列表
- 模型规格用无序列表，每个参数一行
- Protocol 未规定的内容标注 `[AI-INFERRED]`
- SAS 代码用 `**SAS PROC XXX**` 加粗引用，不写完整代码块

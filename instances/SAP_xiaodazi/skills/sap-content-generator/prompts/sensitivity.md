# 敏感性分析与一般考量 (content_type: sensitivity_analysis / general_considerations)

基于主要终点的分析方法和 Protocol 的缺失数据策略，撰写预设的敏感性分析描述。

## 输入变量

- `{endpoints_primary}` — 主要终点列表
- `{missing_data}` — Protocol 中的缺失数据处理策略
- `{primary_methods}` — 已确定的主要分析方法（NB、MMRM 等）

## 预设的敏感性分析模板

### 对计数/率终点（如 exacerbation rate, NB 模型）

1. **On-treatment analysis** — 排除治疗终止后的事件，offset 截断至最后给药日期 + 给药间隔
2. **Poisson regression** — 替换 NB 为 Poisson + 稳健方差估计，评估分布假设敏感性
3. **Tipping point analysis** — 退出患者的事件率按递增倍率假设（1x, 1.5x, 2x, ...），找到翻转结论的阈值
4. **排除 off-treatment 事件** — 仅纳入 on-treatment 期间的事件

### 对连续终点（如 FEV1 change, MMRM 模型）

1. **On-treatment MMRM** — 排除 off-treatment 测量值
2. **J2R 多重填补** — 退出患者的缺失值按对照组均值填补（Jump-to-Reference）
3. **Pattern mixture model** — 按退出模式分组，delta 调整探索
4. **Tipping point analysis** — 系统偏移缺失值，找到翻转结论的 delta 阈值
5. **Per-protocol population analysis** — 在 PP 人群中重复 MMRM

### 对 time-to-event 终点（Cox PH 模型）

1. **等比例风险假设检验** — log-log 图 + Schoenfeld 残差检验
2. **分段 Cox 模型** — 如果比例假设不成立，使用分段时间模型

## 输出要求

对每个敏感性分析，输出：
- 分析名称（加粗编号）
- 目的（一句话）
- 与主要分析的关键差异
- 对 MNAR/MAR 假设的含义

## 格式规则

- 不输出 Markdown 标题
- 每个分析用编号列表
- Protocol 未规定的敏感性分析标注 `[AI-INFERRED]`

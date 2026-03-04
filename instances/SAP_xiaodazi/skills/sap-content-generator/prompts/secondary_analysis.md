# 次要终点分析方法 (content_type: secondary_analysis)

基于以下 Protocol 实体，为次要终点和其他终点撰写统计分析方法描述。

## 输入变量

- `{endpoints}` — 当前批次的终点列表（key_secondary / other_secondary）
- `{statistical_methods}` — 可用的统计方法映射
- `{primary_methods}` — 主要终点已确定的分析方法（次要终点通常沿用）

## 输出结构

对每个终点，撰写：

### A. 终点定义

- 简明定义（可引用 Section 5.2 中已定义的基线等通用定义）

### B. 分析方法

- 沿用主要终点的模型结构时，简要声明"同 Section 5.2.x 的方法"并列出差异点
- 独立方法的终点（如 time-to-event 用 Cox PH、PRO 用 MMRM）需完整规格
- 对 Cox PH 模型：列出依赖变量、删失规则、协变量、报告指标（HR、95% CI、p 值）、KM 曲线时间点
- 对 MMRM 延伸（多时间点）：列出访视序列扩展和对应的 LS mean 提取

### C. 多重性说明

- 声明该终点在层级检验中的位置（如"仅在 Step 1-2 通过后进行正式检验"）
- 或声明"名义 5% 显著性水平（不进行多重性校正）"

## 格式规则

- 次要终点可以更简洁，避免重复主要终点已描述的通用方法
- 相似终点可以合并描述（如"Weeks 2, 4, 8, 24, 36, 52 的 FEV1 变化使用同一 MMRM"）
- 不输出 Markdown 标题
- Protocol 未规定的标注 `[AI-INFERRED]`

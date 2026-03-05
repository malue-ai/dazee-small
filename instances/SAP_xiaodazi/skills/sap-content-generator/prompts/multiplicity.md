# 多重性校正 (content_type: multiplicity)

基于 Protocol 的假设检验策略，撰写多重比较校正方案。

## 输入变量

- `{multiplicity}` — Protocol 中定义的多重性策略
- `{endpoints_primary}` — 主要终点列表
- `{endpoints_key_secondary}` — 关键次要终点列表
- `{treatment_groups}` — 治疗组定义

## 输出结构

### A. 统计假设 (Statistical Hypotheses)

对每个主要终点 x 每个活性剂量组，写出原假设和备择假设：
- **H0x:** 指定终点的治疗效应等于零（如 RR = 1.0 或 LS mean difference = 0）
- 声明双侧显著性水平 alpha = 0.05

### B. 多重性校正策略

- 策略类型（hierarchical / gatekeeping / graphical / Bonferroni / Hochberg 等）
- 层级检验顺序（每一步列出：Step N → 检验假设 Hxx → 若拒绝则进入 Step N+1）
- 门控规则（某步失败时，后续所有假设不进行正式检验）
- alpha 分配/传递规则

### C. 次要终点检验

- 在主要终点全部通过后如何检验关键次要终点
- 支持性次要终点的名义显著性水平说明

### D. 探索性终点

- 声明不进行多重性校正
- 名义 alpha = 0.05（双侧）

## 格式规则

- 假设编号用加粗：**H01**, **H02** 等
- 层级检验用有序列表描述步骤顺序
- 不输出 Markdown 标题
- Protocol 未规定的层级顺序标注 `[AI-INFERRED]`

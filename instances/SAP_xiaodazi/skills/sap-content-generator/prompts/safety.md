# 安全性分析 (content_type: safety_analysis)

基于 Protocol 的安全性终点定义，撰写完整的安全性分析方法描述。

## 输入变量

- `{endpoints_safety}` — 安全性终点列表（AE, SAE, Lab, ECG, Vital Signs, ADA 等）
- `{study_design}` — 治疗组定义、暴露时间计算方式

## 输出结构（按顺序）

### A. 分析人群和一般原则

- Safety population 定义（所有接受至少一剂研究药物的随机化患者）
- 按实际接受治疗分组分析（as-treated）
- MedDRA 编码版本声明
- TEAE 定义（首次给药后至末次给药后 N 天内）

### B. 暴露量 (Extent of Exposure)

- 暴露时间计算方法
- 描述性统计：暴露人数、暴露时间（mean, median, range）、按时间段分层、累计剂量、合规率

### C. 不良事件 (Adverse Events)

- TEAE 总结层次：Any TEAE → 按 SOC/PT → SAE → 导致停药 → 导致死亡 → AESI
- AESI 列表（从 Protocol 提取或推断）：超敏反应、注射部位反应、感染、嗜酸性粒细胞增多等
- 严重程度分级方法（NCI-CTCAE 或研究者判断）
- 叙述性总结范围：死亡、SAE、导致停药、其他显著 AE

### D. 实验室检查 (Clinical Laboratory Tests)

- 检查项目分类（血液学、血生化、尿液）
- 描述性统计（观测值、基线变化值、各时间点）
- Shift table（正常→异常的交叉表）
- PCS 异常标准（预定义临床显著异常阈值）

### E. 心电图 (ECG)

- ECG 参数列表（HR, PR, QRS, QT, QTcF, QTcB）
- QTcF 阈值分析（>450ms, >480ms, >500ms; 基线增加 >30ms, >60ms）
- 总体 ECG 解释分类

### F. 生命体征 (Vital Signs)

- 参数列表和描述性统计方法
- 临床重要限值

### G. 体格检查 (Physical Examination)

- 总结方式（列表和频率表）

### H. 免疫原性 (Immunogenicity / ADA)

- ADA 发生率（treatment-emergent, treatment-induced, treatment-boosted）
- ADA 滴度描述性统计
- ADA 对 PK 和疗效的影响分析（探索性）

### I. 药代动力学 (PK)

- 血清药物浓度描述性统计
- PopPK 建模（如有，声明单独报告）

## 格式规则

- 不输出 Markdown 标题
- 每个子节用加粗段落标题分隔
- 列出具体的实验室/ECG 参数名称
- Protocol 未规定的内容标注 `[AI-INFERRED]`

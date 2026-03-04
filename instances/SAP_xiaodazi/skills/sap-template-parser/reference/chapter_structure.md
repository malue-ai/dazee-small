# SAP 章节 content_type 分类指南

本文件指导 Agent 将任意 SAP 模板的章节分类到标准 content_type。
content_type 是连接模板结构与生成 Prompt 的桥梁——无论不同药企用什么编号体系，
只要 content_type 正确，就能路由到正确的生成 Prompt。

## content_type 分类规则

按以下规则判断每个章节的 content_type（按优先级从高到低匹配）：

| content_type | 匹配标题关键词 | 典型章节 |
|---|---|---|
| estimand | estimand, objectives AND endpoints, clinical question | Sanofi: "1.1 Estimands"; AZ: "3.3.4 ICE Estimand Strategies" |
| primary_analysis | primary + (endpoint OR analysis OR efficacy) | "5.2 Primary Analysis"; "4.2.1 Primary Endpoint" |
| secondary_analysis | secondary + (endpoint OR analysis), key secondary, other secondary, exploratory + endpoint | "5.3 Secondary"; "4.2.2-4.2.10 各终点" |
| sensitivity_analysis | sensitivity + analysis, general + considerations, missing data + handling | "5.1 General Considerations"; "3.3 General" |
| safety_analysis | safety, adverse event, laboratory, vital sign, ECG, immunogenicity, pharmacokinetic | "5.5 Safety Analyses"; "4.6 Safety" |
| multiplicity | multiplicity, multiple comparison, hypothesis + testing, type I error, alpha + control, gatekeeping | "3 Multiplicity"; "3.3.7 Multiplicity" |
| population_definition | analysis set, analysis population, ITT, safety population | "4 Analysis Sets"; "3.2 Analysis Sets" |
| study_design | study design, study schema, randomization, stratification, blinding, study period | "2 Study Design"; "1.1 Synopsis" |
| sample_size | sample size, power + calculation, recruitment | "6 Sample Size"; "6.2 Sample Size Determination" |
| study_info | title page, introduction, protocol summary, version history, amendment | "Title Page"; "1 Introduction" |
| manual_input | changes + protocol, interim analysis | "Changes from Protocol"; "5 Interim Analysis" |
| boilerplate | references, abbreviations, appendix, software | "7 References"; "8 Appendix"; "6.1 Statistical Software" |

## 特殊情况处理

- 一个章节可能包含多种内容（如 AstraZeneca 的 "3 Data Analysis Considerations" 同时含 analysis sets + general considerations + multiplicity）。此时按最细粒度的子章节分类，父章节标记为 `study_info`。
- Per-endpoint 章节（如 AZ 的 4.2.1-4.2.10 每个终点一个子节）全部标记为对应的 `primary_analysis` 或 `secondary_analysis`，并在 `template_structure.json` 中保留层级关系。
- 同一 content_type 出现多次时（如多个 secondary endpoint 子节），每个保留独立条目。

## template_structure.json 输出格式

```json
{
  "template_info": {
    "source": "EU-PEARL_SAP_Template_V3.docx",
    "parser": "unstructured",
    "total_sections": 15
  },
  "sections": [
    {
      "id": "1",
      "title": "Objectives, Endpoints, and Estimands",
      "content_type": "estimand",
      "level": 1,
      "page": null,
      "required": true,
      "parent_id": null
    },
    {
      "id": "4.2.1",
      "title": "Primary Endpoint: FEV1 AUC",
      "content_type": "primary_analysis",
      "level": 3,
      "page": 60,
      "required": true,
      "parent_id": "4.2"
    }
  ]
}
```

字段说明：
- `id` — 模板中的原始章节编号（保留原样，不标准化）
- `title` — 章节标题原文
- `content_type` — 按上表分类的标准类型
- `level` — 标题层级（1=大章, 2=子章, 3=子子章）
- `page` — 页码（如果可检测）
- `required` — 是否为必填章节
- `parent_id` — 父章节 ID（用于层级关系）

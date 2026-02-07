# 小搭子能力测评报告

**生成时间**: 2026-02-07T16:33:19.067226

---

## 总览

| 维度 | 得分 | 详情 |
|------|------|------|
| 可行性 | 32.1% | 9/28 PASS |
| 效率性 | 0.38 | 加权平均 |

**综合得分**: 34.29%
**发布门禁**: BLOCKED

---

## 套件详情

### Token 消耗效率（E3）

| 指标 | 值 |
|------|-----|
| 任务数 | 4 |
| 通过 | 1 |
| 失败 | 3 |
| 通过率 | 25.0% |
| 总 Token | 1200 |
| 耗时 | 0.0s |

| 任务 | 通过率 | 平均分 | 稳定性 |
|------|--------|--------|--------|
| E3-01_simple_qa_tokens | 100% | 0.80 | 稳定 |
| E3-02_search_summarize_tokens | 0% | 0.80 | 稳定 |
| E3-03_file_processing_tokens | 0% | 0.80 | 稳定 |
| E3-04_content_creation_tokens | 0% | 0.80 | 稳定 |

---

## 失败用例

| 套件 | 用例 ID | 描述 |
|------|--------|------|
| Token 消耗效率（E3） | E3-02_search_summarize_tokens | 搜索+总结 - Token 应 <= 15K |
| Token 消耗效率（E3） | E3-03_file_processing_tokens | 文件处理 - Token 应 <= 20K |
| Token 消耗效率（E3） | E3-04_content_creation_tokens | 内容创作 - Token 应 <= 25K |

---

## 改进建议

> 基于失败用例和效率性得分，按「闭环优化流程」进行修复和回归验证。
> 详见 `docs/benchmark/xiaodazi_eval.md` 第五节。

# 小搭子 vs clawdbot (OpenClaw) — 差异化对比测试

> 本目录包含面向小白用户的对比测试用例和测试数据，用于验证小搭子与 clawdbot 在效果、特色、Token 消耗和场景上的差异化。

## 目录结构

```
docs/benchmark/
├── README.md                  # 本文件
├── test_cases.md              # 完整测试用例（含指标、预期结果、Token 估算）
└── data/                      # 测试数据文件
    ├── generate_test_data.py  # 一键生成所有测试数据（Excel/文件集）
    ├── academic_abstract.txt  # 论文摘要（润色测试）
    ├── coffee_article.txt     # 咖啡文章样本（风格学习）
    ├── tea_culture_prompt.txt # 茶文化写作提示（跨会话记忆验证）
    ├── scanned_pdf_note.md    # 扫描 PDF 准备说明
    └── mixed_files/           # 文件整理测试集（由脚本生成）
```

## 快速开始

### 1. 生成测试数据

```bash
source /Users/liuyi/Documents/langchain/liuy/bin/activate
cd docs/benchmark/data
python generate_test_data.py
```

生成的文件：
- `messy_sales.xlsx` — 格式混乱的销售数据 Excel（日期格式不统一、合并单元格、空行、中文列名）
- `mixed_files/` — 100 个混合类型文件（.txt/.md/.csv/.json/.log）

### 2. 手动准备

以下文件无法自动生成，需手动准备：
- **扫描 PDF**：参见 `scanned_pdf_note.md` 中的说明

### 3. 执行测试

参见 `test_cases.md` 中的详细测试步骤和预期结果。

## 对比维度

| 维度 | 测试用例数 | 说明 |
|------|----------|------|
| **A. 效果差异化** | 3 | 任务完成率 + 用户体验 |
| **B. 特色差异化** | 4 | 独有能力（记忆/环境感知/HITL/长任务） |
| **C. Token 消耗** | 3 | 量化成本对比 |
| **D. 场景差异化** | 5 | 各自强项 + 短板 |

## 对比对象概要

### clawdbot / OpenClaw

- 145K+ GitHub Stars，开源 MIT
- 通过 WhatsApp/Telegram/Discord 等消息应用控制
- 完整 shell + 浏览器自动化 + 24/7 后台运行
- 记忆：MEMORY.md + BM25 + sqlite-vec 向量搜索
- **已知弱点**：配置复杂（Node 22+）、Token 消耗大（$30-70/月中度用户）、auto-compaction 重试循环、无系统化智能回溯

### 小搭子

- 桌面应用，双击安装，5 分钟上手
- RVR-B 智能回溯（ErrorClassifier + BacktrackManager）
- 三层记忆（MEMORY.md + FTS5 + Mem0 向量）
- 环境感知（RuntimeContextBuilder + AppScanner）
- 自适应终止（五维度） + 状态一致性（快照/回滚）
- System prompt 缓存 + 意图语义缓存 → Token 节省 40-60%

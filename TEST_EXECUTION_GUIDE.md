# 测试执行快速指南

## 立即运行（3 步）

### 步骤 1: 进入项目目录

\`\`\`bash
cd /Users/liuyi/Documents/langchain/CoT_agent/mvp/zenflux_agent
\`\`\`

### 步骤 2: 激活虚拟环境

\`\`\`bash
source /Users/liuyi/Documents/langchain/liuy/bin/activate
\`\`\`

### 步骤 3: 选择测试类型

#### 选项 A: 冒烟测试（最快，推荐）

\`\`\`bash
./run_e2e_test.sh smoke
\`\`\`

- ⏱️ 耗时: 1.5秒
- 📋 要求: 无（不需要 API Key）
- ✅ 验证: 测试框架基础功能（9项）

#### 选项 B: 快速验证（推荐）

\`\`\`bash
python quick_validation.py
\`\`\`

- ⏱️ 耗时: 10秒
- 📋 要求: ANTHROPIC_API_KEY, OPENAI_API_KEY
- ✅ 验证: 意图识别 + 管道追踪 + 质量评估（13项）

#### 选项 C: 单场景演示

\`\`\`bash
python simple_qa_demo.py
\`\`\`

- ⏱️ 耗时: 变化（取决于 Agent 响应）
- 📋 要求: 完整环境（API Key + DATABASE_URL）
- ✅ 验证: 完整的意图识别 + Agent 回答流程

---

## 📊 最新验证结果

**日期**: 2026-01-27 23:50:35  
**通过率**: **92.3%** (12/13)

### 详细结果

| 测试项 | 状态 |
|--------|------|
| 环境配置 (3项) | ✅ 3/3 |
| 测试框架 (3项) | ✅ 3/3 |
| 意图识别 (1项) | ✅ 1/1 |
| 管道追踪 (1项) | ⚠️ 0/1 (5/6环节) |
| 质量归因 (2项) | ✅ 2/2 |
| 质量评估 (1项) | ✅ 1/1 |
| 场景覆盖 (1项) | ✅ 1/1 |
| 端到端 (1项) | ✅ 1/1 |

---

## 🎯 6 个测试场景

1. **产品经理调研竞品** → Intent 3, Medium, 需要 tavily_search
2. **技术负责人系统设计** → Intent 1, Complex, 需要两步工作流
3. **运营人员制作PPT** → Intent 3, Complex, 需要多工具协同
4. **开发者代码生成** → Intent 3, Simple, 无需工具
5. **追问场景** → Intent 3, Simple, 上下文理解
6. **简单知识问答** → Intent 3, Simple, 直接回答

---

## 📖 查看详细报告

\`\`\`bash
# 快速验证结果
cat quick_validation_report.txt

# 详细验证报告
cat COMPREHENSIVE_VALIDATION_REPORT.md

# 执行摘要
cat VALIDATION_SUMMARY.md

# 测试框架说明
cat tests/README_E2E_TEST.md
\`\`\`

---

## ⚠️ 已知问题

1. **管道追踪**: 6个环节中追踪到5个（建议补全）
2. **Agent 预加载**: MCP 异步错误（阻塞完整对话测试）
3. **Intent 1 识别**: "设计CRM" 被识别为 Intent 3（需优化提示词）

---

## 🔗 相关文件

- 主测试文件: [`tests/test_e2e_agent_pipeline.py`](tests/test_e2e_agent_pipeline.py)
- 详细报告: [`COMPREHENSIVE_VALIDATION_REPORT.md`](COMPREHENSIVE_VALIDATION_REPORT.md)
- 执行摘要: [`VALIDATION_SUMMARY.md`](VALIDATION_SUMMARY.md)
- 框架文档: [`tests/README_E2E_TEST.md`](tests/README_E2E_TEST.md)

---

**快速命令**:
\`\`\`bash
cd /Users/liuyi/Documents/langchain/CoT_agent/mvp/zenflux_agent
source /Users/liuyi/Documents/langchain/liuy/bin/activate
./run_e2e_test.sh smoke  # 推荐
\`\`\`

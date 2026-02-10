# 失败用例分类报告

**生成时间**: 2026-02-10T18:48:38.567055
**失败总数**: 6

---

## Token 浪费 — 优化上下文管理 (1)

| 套件 | 用例 ID | 描述 | 失败 Graders |
|------|--------|------|-------------|
| E2E Phase3 全量用例 | C2 | 10轮对话Token累积对比 | check_token_limit |

## 能力缺失 — 需要新增 Skill/Tool (5)

| 套件 | 用例 ID | 描述 | 失败 Graders |
|------|--------|------|-------------|
| E2E Phase3 全量用例 | B4 | 长任务自动确认（100文件分类） | grade_response_quality |
| E2E Phase3 全量用例 | B6 | 用户画像累积构建（跨4会话） | grade_response_quality |
| E2E Phase3 全量用例 | B7 | 记忆冲突检测与更新 | grade_response_quality |
| E2E Phase3 全量用例 | D3 | 多步骤内容创作 | grade_response_quality |
| E2E Phase3 全量用例 | E2 | 日程创建+提醒通知 | grade_response_quality |

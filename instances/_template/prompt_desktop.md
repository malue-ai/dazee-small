# 桌面操作协议（可选）

当任务涉及桌面/本地 App 操作（飞书、邮件、日历、屏幕记忆等）时，框架会**按需**将本文件内容追加到系统提示词中，用于约束 UI 自动化行为。

- 若本实例**不需要**桌面自动化，可保留本文件为空或此占位说明。
- 若需要，可参考 `instances/xiaodazi/prompt_desktop.md` 编写 Peekaboo 等桌面协议。

注入条件：任务复杂度为 complex，或意图匹配 skill_groups 含 `app_automation` / `feishu` / `productivity` / `screen_memory`。

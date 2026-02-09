# 桌面操作协议

## 强制约束（违反 = 任务失败）

### 1. 所有 UI 交互必须通过 peekaboo

| 操作 | 正确方式 | 禁止方式 |
|------|---------|---------|
| 点击按钮/元素 | `peekaboo click --on <ID> --app <应用>` | `osascript ... click` |
| 输入 ASCII | `peekaboo type "text" --app <应用>` | `osascript ... keystroke "text"` |
| 输入中文/CJK | `peekaboo paste "中文" --app <应用>` | `osascript ... keystroke "中文"` |
| 按键/快捷键 | `peekaboo hotkey --keys cmd+k --app <应用>` | `osascript ... key code 36` |
| 滚动 | `peekaboo scroll --direction down --app <应用>` | `osascript ... scroll` |

`osascript` 仅允许用于进程管理（如 `activate`、`get name of process`），**禁止用于任何 UI 元素交互**。

### 2. 操作前必须先用 peekaboo see 获取元素 ID

**不要猜测界面状态。** 每次操作前先观察，用元素 ID 精确定位，不要盲目 keystroke。

```
❌ 错误：猜测快捷键打开搜索 → 盲目输入文字
✅ 正确：peekaboo see --annotate → 找到搜索框 ID → peekaboo click --on <ID> → peekaboo paste "内容"
```

### 3. 中文/CJK 输入必须用 peekaboo paste

AppleScript `keystroke` 完全不支持非 ASCII 字符（不是"差"，是"不工作"）。`peekaboo paste` 自动通过剪贴板桥接，是输入中文的**唯一可靠方式**。

## 核心循环：观察 → 定位 → 操作 → 验证

```
peekaboo see --annotate  →  找到目标元素 ID  →  peekaboo click/paste  →  observe_screen 验证
```

每一步都必须验证。**不要假设操作成功。**

## 操作原语

### 观察

```
observe_screen                                          # 快速一览（OCR + UI 元素）
observe_screen app=<应用>                                # 指定应用
nodes run: peekaboo see --app <应用> --annotate          # 深度分析（带 ID 标注，推荐）
```

### 点击与导航

```
nodes run: peekaboo click --on <ID> --app <应用>         # 按元素 ID 点击（最可靠）
nodes run: peekaboo click --coords 100,200 --app <应用>  # 按坐标点击（备选）
```

### 文本输入

```
nodes run: peekaboo type "ASCII" --app <应用>             # 纯 ASCII
nodes run: peekaboo type "ASCII" --app <应用> --return     # 纯 ASCII 并回车
nodes run: peekaboo paste "中文或任意文本" --app <应用>     # 含 CJK 必须用 paste
```

### 按键与快捷键

```
nodes run: peekaboo hotkey --keys cmd+k --app <应用>      # 组合键
nodes run: peekaboo press return --app <应用>              # 单键
nodes run: peekaboo press escape --app <应用>              # Escape
nodes run: peekaboo press tab --app <应用>                 # Tab 切换焦点
```

### 应用管理

```
nodes run: peekaboo app --action launch --name <应用>     # 启动
nodes run: peekaboo app --action focus --name <应用>      # 聚焦
nodes run: peekaboo list --item-type running_applications  # 列出运行中应用
```

## 验证规则（每步必做）

验证时必须在思考中明确回答以下问题：

1. **操作目标正确吗？** — 我点击/输入的是正确的 UI 元素吗？（对比元素 ID）
2. **内容到位了吗？** — 输入的文字出现在了正确的输入框中吗？（不是消息框、不是搜索框混淆）
3. **状态转换正确吗？** — 界面变化符合预期吗？（搜索结果出现了？聊天窗口切换了？）

```
✅ 「我点击了搜索图标 [B3]，截图显示搜索框已激活，光标在搜索框中，正确」
✅ 「我 paste 了"海鹏"，截图显示搜索框中出现"海鹏"且搜索结果列出了联系人，正确」
✅ 「我点击了搜索结果中的"海鹏"[C5]，截图显示进入了与海鹏的 1-on-1 聊天，正确」

❌ 「我输入了文字，截图显示文字出现在消息输入框而非搜索框 → 位置错误，需要先点击正确的输入框」
❌ 「我按了 Enter 发送，但截图显示还在群聊而非目标人的聊天 → 目标错误，需要先导航到正确聊天」
```

## 反模式警告

### ❌ 盲目 keystroke

```
# 错误：不看界面直接 keystroke
osascript -e 'tell ... to keystroke "海鹏"'     # CJK 失败 + 可能打到消息框
osascript -e 'tell ... to keystroke "f" using command down'  # 不确定打开的是什么

# 正确：先观察 → 点击目标元素 → 再输入
peekaboo see --app Lark --annotate → 找到搜索入口 [B3]
peekaboo click --on B3 --app Lark → 点击搜索
peekaboo paste "海鹏" --app Lark → 在搜索框中输入
```

### ❌ 连续失败不反思

如果同一操作连续失败 2 次：
1. **停下来重新观察** — `peekaboo see --annotate` 看看界面到底是什么状态
2. **反思失败原因** — 是不是在错误的输入框？是不是应用窗口没聚焦？是不是元素 ID 变了？
3. **换一种方法** — 如果快捷键不管用，改用 peekaboo click 点击 UI 元素

### ❌ 发送前不确认目标

发送消息/邮件/文件前，必须通过 observe_screen 确认：
- 当前聊天窗口的标题/联系人是正确的目标
- 输入框中的内容是完整且正确的
- 不是在错误的群聊或对话中

<example>
<query>打开某应用，给某人发一条消息</query>
<flow>
1. peekaboo app --action launch --name <应用> → 启动应用
2. observe_screen → 确认应用已打开
3. peekaboo see --app <应用> --annotate → 获取 UI 元素标注
4. 找到搜索入口（搜索图标/搜索框）→ peekaboo click --on <搜索入口ID>
5. observe_screen → 确认搜索框已激活（光标在搜索框中）
6. peekaboo paste "联系人名" --app <应用>（中文名必须用 paste）
7. observe_screen → 确认搜索结果中出现目标联系人
8. peekaboo click --on <目标联系人ID> → 进入聊天
9. observe_screen → **确认当前聊天标题是目标联系人**（不是群聊、不是其他人）
10. peekaboo paste "消息内容" --app <应用>（中文消息用 paste）
11. observe_screen → 确认消息出现在输入框中（不是搜索框、不是标题栏）
12. peekaboo press return --app <应用> → 发送
13. observe_screen → 确认消息已发送且出现在聊天记录中
</flow>
</example>

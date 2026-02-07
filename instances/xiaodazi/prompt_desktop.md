# 桌面操作协议

## 核心循环：观察 → 操作 → 验证

每一步 UI 操作后，**必须截图验证结果**，确认成功再继续下一步。不要假设操作成功。

```
observe_screen → 理解界面 → 执行操作 → observe_screen 验证 → 下一步
```

## 操作原语

### 1. 观察（获取界面信息）

```
observe_screen                              # 快速一览（OCR + UI 元素）
observe_screen app=Lark                     # 指定应用
nodes run: peekaboo see --app <应用> --annotate  # 深度分析（带 ID 标注）
```

### 2. 交互（操作 UI 元素）

```
nodes run: peekaboo click --on <ID> --app <应用>           # 点击元素
nodes run: peekaboo type "文本" --app <应用>                # 输入文字
nodes run: peekaboo type "文本" --app <应用> --return       # 输入并回车
nodes run: peekaboo scroll --direction down --app <应用>    # 滚动
nodes run: peekaboo hotkey --keys cmd+v --app <应用>        # 快捷键
```

### 3. 应用管理

```
nodes run: peekaboo app --action launch --name <应用>       # 启动应用
nodes run: peekaboo app --action focus --name <应用>        # 聚焦已打开的应用
nodes run: peekaboo list --item-type running_applications   # 查看正在运行的应用
```

## 快捷键优先策略

对下拉框、滚动条、弹窗等控件，优先使用快捷键而非鼠标点击（更可靠）：

| 场景 | 快捷键 |
|------|--------|
| 切换输入焦点 | Tab / Shift+Tab |
| 确认 / 提交 | Enter / Return |
| 取消 / 关闭弹窗 | Escape |
| 复制 / 粘贴 | Cmd+C / Cmd+V |
| 全选 | Cmd+A |
| 撤销 | Cmd+Z |
| 新建 | Cmd+N |
| 搜索 | Cmd+F |

## 剪贴板桥接（输入长文本/中文）

输入超过 20 字符的文本或中文内容时，用剪贴板粘贴代替逐字输入（更快更可靠）：

```
nodes run: bash -c 'echo "要输入的长文本内容" | pbcopy'
nodes run: peekaboo hotkey --keys cmd+v --app <应用>
```

## 验证规则

每次操作后截图验证，在思考中明确评估：
- 「我刚才点击了 XX 按钮，截图显示 YY，操作成功，继续下一步」
- 「我刚才输入了文本，但截图显示输入框仍为空，重试一次」

如果同一步骤连续失败 2 次，换一种方法（如从鼠标点击换成快捷键）。

<example>
<query>打开某应用，在群聊中发一条消息</query>
<flow>
1. peekaboo app --action launch --name <应用>
2. observe_screen app=<应用> → 确认应用已打开
3. peekaboo see --app <应用> --annotate → 获取 UI 标注
4. 根据标注找到搜索入口 → peekaboo click --on <ID>
5. peekaboo type "群聊名" --app <应用> --return
6. observe_screen → 确认搜索结果出现
7. peekaboo click --on <目标群聊ID>
8. observe_screen → 确认进入群聊
9. echo '消息内容' | pbcopy → peekaboo hotkey --keys cmd+v（剪贴板桥接）
10. peekaboo hotkey --keys return（发送）
11. observe_screen → 确认消息已发送
</flow>
</example>

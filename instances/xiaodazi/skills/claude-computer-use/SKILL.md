---
name: claude-computer-use
description: Claude Computer Use - 通过截屏+视觉理解操作任意桌面应用（精确坐标点击/滚动/拖拽/键盘/右键/双击）。终极后备方案，当 peekaboo/pywinauto/browser 无法满足时使用。
quickstart: |
  # 需要: ANTHROPIC_API_KEY (已配置)
  # 截屏 → Claude 视觉分析 → 返回操作指令
  import anthropic, subprocess, base64
  client = anthropic.Anthropic()
  # macOS 截屏:
  subprocess.run(["screencapture", "-x", "/tmp/screen.png"])
  # Windows 截屏: 用 pyautogui.screenshot() 或 PowerShell
  img_b64 = base64.b64encode(open("/tmp/screen.png","rb").read()).decode()
  resp = client.beta.messages.create(
      model="claude-sonnet-4-5-20250514",
      max_tokens=1024,
      tools=[{"type":"computer_20250124","name":"computer",
              "display_width_px":1920,"display_height_px":1080}],
      messages=[{"role":"user","content":[
          {"type":"image","source":{"type":"base64","media_type":"image/png","data":img_b64}},
          {"type":"text","text":"描述你要执行的操作"}
      ]}],
      betas=["computer-use-2025-01-24"]
  )
  # resp.content 中包含 tool_use block，解析其 action/coordinate 执行
metadata:
  xiaodazi:
    dependency_level: cloud_api
    os: [common]
    backend_type: local
    user_facing: true
---

# Claude Computer Use

Anthropic 官方桌面自动化 API（beta）。通过**截屏 + Claude 视觉理解 + 坐标操作**控制任意桌面应用。

## 何时使用

这是**终极后备方案**，仅在以下情况使用：

1. peekaboo (macOS) / pywinauto (Windows) / browser (网页) 无法操作目标应用
2. 需要视觉判断（看屏幕内容决定下一步）
3. 目标应用不暴露 Accessibility API
4. 用户明确要求精确坐标控制

优先使用轻量方案（成本更低、速度更快）：
- 网页 → browser tool
- macOS 桌面 → peekaboo
- Windows 桌面 → pywinauto

## 支持的操作

| 操作 | 说明 |
|---|---|
| screenshot | 截取当前屏幕 |
| left_click | 在坐标 [x, y] 点击 |
| right_click | 右键点击 |
| double_click | 双击 |
| triple_click | 三击（全选文本） |
| middle_click | 中键点击 |
| mouse_move | 移动鼠标到坐标 |
| left_click_drag | 拖拽（从当前位置到目标坐标） |
| scroll | 滚动（方向 + 数量） |
| type | 输入文本 |
| key | 按键/组合键（如 "ctrl+s"） |
| hold_key | 按住某键指定时长 |
| wait | 等待指定秒数 |

## 工作流程

```
循环:
  1. 截屏 (screencapture / pyautogui.screenshot)
  2. 发送截图给 Claude Computer Use API
  3. Claude 分析截图，返回 tool_use (action + coordinates)
  4. 在本地执行操作 (cliclick/xdotool/pyautogui)
  5. 如果任务未完成，回到步骤 1
```

## 完整示例

### macOS 实现

```python
import anthropic
import subprocess
import base64
import json

client = anthropic.Anthropic()

def screenshot():
    """截取 macOS 屏幕"""
    subprocess.run(["screencapture", "-x", "/tmp/screen.png"], check=True)
    with open("/tmp/screen.png", "rb") as f:
        return base64.b64encode(f.read()).decode()

def execute_action(action_type, **kwargs):
    """执行鼠标/键盘操作 (macOS 使用 cliclick 或 AppleScript)"""
    if action_type == "left_click":
        x, y = kwargs["coordinate"]
        subprocess.run(["cliclick", f"c:{x},{y}"])
    elif action_type == "type":
        text = kwargs["text"]
        subprocess.run(["cliclick", f"t:{text}"])
    elif action_type == "key":
        key = kwargs["key"]
        # 通过 AppleScript 发送按键
        subprocess.run(["osascript", "-e",
            f'tell application "System Events" to keystroke "{key}"'])
    elif action_type == "scroll":
        direction = kwargs.get("direction", "down")
        amount = kwargs.get("amount", 3)
        delta = -amount if direction == "down" else amount
        # AppleScript 模拟滚动
        subprocess.run(["osascript", "-e",
            f'tell application "System Events" to scroll area 1 by {delta}'])
    elif action_type == "mouse_move":
        x, y = kwargs["coordinate"]
        subprocess.run(["cliclick", f"m:{x},{y}"])
    elif action_type == "screenshot":
        pass  # 下一轮循环自动截屏

def computer_use_loop(task: str, max_iterations: int = 10):
    """Computer Use 主循环"""
    messages = [{"role": "user", "content": [
        {"type": "text", "text": task}
    ]}]

    for i in range(max_iterations):
        # 1. 截屏
        img_b64 = screenshot()

        # 2. 追加截图到消息
        if i > 0:
            messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": tool_use_id,
                 "content": [{"type": "image", "source": {
                     "type": "base64", "media_type": "image/png", "data": img_b64
                 }}]}
            ]})
        else:
            messages[0]["content"].append({
                "type": "image", "source": {
                    "type": "base64", "media_type": "image/png", "data": img_b64
                }
            })

        # 3. 调用 Claude Computer Use API
        response = client.beta.messages.create(
            model="claude-sonnet-4-5-20250514",
            max_tokens=1024,
            tools=[{
                "type": "computer_20250124",
                "name": "computer",
                "display_width_px": 1920,
                "display_height_px": 1080,
            }],
            messages=messages,
            betas=["computer-use-2025-01-24"],
        )

        # 4. 解析响应
        messages.append({"role": "assistant", "content": response.content})

        # 检查是否完成
        if response.stop_reason == "end_turn":
            print("任务完成")
            break

        # 5. 执行操作
        for block in response.content:
            if block.type == "tool_use":
                tool_use_id = block.id
                action = block.input.get("action")
                print(f"  执行: {action} {block.input}")
                execute_action(action, **block.input)

    return messages
```

### Windows 实现

```python
import pyautogui
import time

def screenshot_win():
    """截取 Windows 屏幕"""
    img = pyautogui.screenshot()
    img.save("/tmp/screen.png")
    with open("/tmp/screen.png", "rb") as f:
        return base64.b64encode(f.read()).decode()

def execute_action_win(action_type, **kwargs):
    """执行操作 (Windows 使用 pyautogui)"""
    if action_type == "left_click":
        x, y = kwargs["coordinate"]
        pyautogui.click(x, y)
    elif action_type == "right_click":
        x, y = kwargs["coordinate"]
        pyautogui.rightClick(x, y)
    elif action_type == "double_click":
        x, y = kwargs["coordinate"]
        pyautogui.doubleClick(x, y)
    elif action_type == "type":
        pyautogui.typewrite(kwargs["text"], interval=0.02)
    elif action_type == "key":
        pyautogui.hotkey(*kwargs["key"].split("+"))
    elif action_type == "scroll":
        amount = kwargs.get("amount", 3)
        direction = kwargs.get("direction", "down")
        clicks = -amount if direction == "down" else amount
        x, y = kwargs.get("coordinate", (960, 540))
        pyautogui.scroll(clicks, x, y)
    elif action_type == "mouse_move":
        x, y = kwargs["coordinate"]
        pyautogui.moveTo(x, y)
    elif action_type == "left_click_drag":
        sx, sy = kwargs.get("start_coordinate", pyautogui.position())
        x, y = kwargs["coordinate"]
        pyautogui.moveTo(sx, sy)
        pyautogui.drag(x - sx, y - sy, duration=0.5)
```

## API 参数

```python
tools=[{
    "type": "computer_20250124",  # 或 computer_20251124 (Opus 4.6)
    "name": "computer",
    "display_width_px": 1920,     # 屏幕宽度
    "display_height_px": 1080,    # 屏幕高度
    "display_number": 1,          # X11 显示号（可选）
}]
betas=["computer-use-2025-01-24"]  # 或 computer-use-2025-11-24 (Opus 4.6)
```

## 成本估算

- 每次截屏约 1000-3000 tokens（取决于分辨率）
- 典型任务（5-10 次截屏循环）：约 10,000-30,000 tokens
- 建议：降低截屏分辨率（1280x800 效果最佳）可显著减少成本

## 安全规则

- **每次操作前 HITL 确认**：告知用户即将在屏幕上执行什么操作
- **不自动输入密码**：需要登录时提示用户手动操作
- **不操作金融应用**：涉及支付/转账时必须用户确认
- **限制循环次数**：max_iterations 防止无限截屏循环
- **最小权限**：不要给 Claude 管理员权限

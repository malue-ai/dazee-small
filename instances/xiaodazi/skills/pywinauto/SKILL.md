---
name: pywinauto
description: Automate Windows desktop applications using pywinauto. Discover windows, inspect controls, click buttons, type text, and drive any Win32/UIA application programmatically.
metadata:
  xiaodazi:
    dependency_level: lightweight
    os: [win32]
    backend_type: local
    user_facing: true
    python_packages: ["pywinauto"]
---

# Windows UI 自动化（pywinauto）

通过 pywinauto 操作任意 Windows 桌面应用：发现窗口、检查控件、点击按钮、输入文字、读取内容。
支持两种后端：Win32 API（传统应用）和 MS UI Automation（现代应用）。

## 使用场景

- 用户说「帮我在 XX 应用里点一下那个按钮」「自动填一下这个表单」
- 需要操作没有 API 的桌面应用（如 ERP 系统、内部管理系统）
- 需要批量操作 GUI 应用（如自动录入数据）
- 需要读取其他应用界面上的文字内容

## 后端选择

| 后端 | 参数 | 适用应用 |
|------|------|----------|
| Win32 API | `backend="win32"` | MFC、VB6、VCL、简单 WinForms |
| MS UI Automation | `backend="uia"` | WinForms、WPF、UWP Store 应用、Qt5、浏览器 |

不确定用哪个时，优先尝试 `uia`；如果找不到控件，切换为 `win32`。

## 命令参考

### 连接到已有应用

```python
from pywinauto import Application

# 方式 1：通过窗口标题连接
app = Application(backend="uia").connect(title="记事本", timeout=10)

# 方式 2：通过进程名连接
app = Application(backend="uia").connect(path="notepad.exe")

# 方式 3：通过进程 ID 连接
app = Application(backend="uia").connect(process=12345)
```

### 启动新应用

```python
from pywinauto import Application

app = Application(backend="uia").start("notepad.exe")
# 等待窗口出现
app.window(title_re=".*记事本.*").wait("ready", timeout=10)
```

### 发现窗口和控件

```python
# 列出所有顶层窗口
from pywinauto import Desktop
windows = Desktop(backend="uia").windows()
for w in windows:
    print(f"{w.window_text()} — {w.class_name()}")

# 打印窗口控件树（调试用）
dlg = app.window(title_re=".*记事本.*")
dlg.print_control_identifiers()
```

### 点击按钮和菜单

```python
dlg = app.window(title="记事本")

# 点击菜单
dlg.menu_select("文件->打开")

# 点击按钮（通过文本匹配）
dlg.child_window(title="确定", control_type="Button").click()

# 点击按钮（通过 auto_id）
dlg.child_window(auto_id="btnSubmit").click()
```

### 输入文字

```python
dlg = app.window(title="记事本")

# 输入到编辑框
edit = dlg.child_window(control_type="Edit")
edit.set_text("要输入的内容")

# 模拟键盘输入（支持特殊键）
edit.type_keys("Hello{ENTER}World", with_spaces=True)

# 特殊键：{ENTER} {TAB} {ESC} {DELETE} {BACKSPACE}
# 修饰键：^ = Ctrl, % = Alt, + = Shift
# 例：Ctrl+A = ^a, Ctrl+Shift+S = ^+s
```

### 读取界面内容

```python
dlg = app.window(title="记事本")

# 读取文本框内容
content = dlg.child_window(control_type="Edit").window_text()

# 读取列表项
listbox = dlg.child_window(control_type="List")
items = [item.window_text() for item in listbox.children()]

# 读取表格
table = dlg.child_window(control_type="Table")
for row in table.children():
    cells = [c.window_text() for c in row.children()]
    print(" | ".join(cells))
```

### 等待与同步

```python
# 等待窗口出现
dlg = app.window(title="保存").wait("visible", timeout=10)

# 等待窗口消失
app.window(title="加载中...").wait_not("visible", timeout=30)

# 等待控件可用
dlg.child_window(title="提交").wait("enabled", timeout=5)
```

### 窗口管理

```python
dlg = app.window(title="记事本")

# 最大化 / 最小化 / 还原
dlg.maximize()
dlg.minimize()
dlg.restore()

# 移动和调整大小
dlg.move_window(x=100, y=100, width=800, height=600)

# 置顶
dlg.set_focus()

# 关闭
dlg.close()
```

### 滚动

```python
from pywinauto import mouse

# 向下滚动 3 格（在指定坐标位置）
mouse.scroll(coords=(500, 400), wheel_dist=-3)

# 向上滚动 5 格
mouse.scroll(coords=(500, 400), wheel_dist=5)

# 在控件内滚动（先获取控件位置）
rect = dlg.child_window(control_type="List").rectangle()
mouse.scroll(coords=(rect.mid_point()), wheel_dist=-3)
```

### 鼠标坐标操作

```python
from pywinauto import mouse

# 移动鼠标到坐标
mouse.move(coords=(500, 300))

# 在指定坐标左键点击
mouse.click(coords=(500, 300))

# 右键点击
mouse.right_click(coords=(500, 300))

# 双击
mouse.double_click(coords=(500, 300))
```

### 拖拽

```python
from pywinauto import mouse

# 拖拽：从 (100,200) 到 (300,400)
mouse.press(coords=(100, 200))
mouse.move(coords=(300, 400))
mouse.release(coords=(300, 400))
```

## 典型工作流

```
1. 用 Desktop().windows() 列出当前打开的窗口
2. 用 app.connect() 连接到目标应用
3. 用 dlg.print_control_identifiers() 查看控件树
4. 根据控件类型和属性定位目标元素
5. 执行操作（click / set_text / type_keys / scroll）
6. 读取结果或等待操作完成
```

## 安全规则

- **操作前必须 HITL 确认**：告知用户即将操作哪个应用的哪个控件
- **不自动关闭用户文档**：不调用未保存文档的 close()
- **不操作管理员窗口**：跳过 UAC 弹窗和系统设置
- **操作失败时截图反馈**：让用户看到当前界面状态
- **每步操作间隔 0.5 秒**：避免操作过快导致 UI 来不及响应

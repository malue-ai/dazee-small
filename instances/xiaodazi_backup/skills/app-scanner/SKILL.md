---
name: app-scanner
description: Discover installed applications on macOS and recommend the best app for user tasks. Uses mdfind, system_profiler, and /Applications scanning.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [darwin]
    backend_type: local
    user_facing: true
---

# macOS 应用发现

扫描用户电脑上安装了哪些应用，根据任务需求推荐最合适的工具。

## 使用场景

- 用户说「我电脑上有什么能编辑 PDF 的软件吗」
- 用户说「帮我打开视频编辑软件」
- 任务需要某个应用但不确定用户是否安装

## 扫描方式

### 列出已安装应用

```bash
# 方式 1：扫描 /Applications 目录（最常用）
ls /Applications/ | grep -i ".app"

# 方式 2：system_profiler（完整信息，含版本）
system_profiler SPApplicationsDataType -json 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
apps = data.get('SPApplicationsDataType', [])
for app in sorted(apps, key=lambda x: x.get('_name', ''))[:50]:
    name = app.get('_name', '')
    version = app.get('version', '?')
    path = app.get('path', '')
    print(f'{name} (v{version}) — {path}')
"

# 方式 3：mdfind（包含非标准位置的应用）
mdfind "kMDItemContentType == 'com.apple.application-bundle'" | head -50
```

### 检查特定应用是否安装

```bash
# 检查应用是否存在
test -d "/Applications/Visual Studio Code.app" && echo "已安装" || echo "未安装"

# 通过 mdfind 查找
mdfind "kMDItemCFBundleIdentifier == 'com.microsoft.VSCode'"

# 通过 CLI 检查
which code && echo "VS Code CLI 可用" || echo "VS Code CLI 不可用"
```

### 获取应用详细信息

```bash
# 获取应用 Bundle ID
mdls -name kMDItemCFBundleIdentifier "/Applications/Safari.app"

# 获取应用版本
mdls -name kMDItemVersion "/Applications/Safari.app"

# 获取应用支持的文件类型
mdls -name kMDItemContentTypeTree "/Applications/Preview.app"
```

### 按文件类型推荐应用

```bash
# 查找能打开 PDF 的应用
python3 -c "
import subprocess, json
result = subprocess.run(
    ['python3', '-c', '''
import CoreServices
from LaunchServices import LSCopyAllRoleHandlersForContentType
handlers = LSCopyAllRoleHandlersForContentType(\"com.adobe.pdf\", 0xFFFFFFFF)
if handlers:
    for h in handlers:
        print(h)
'''],
    capture_output=True, text=True
)
print(result.stdout)
"

# 简单方式：用 open 命令查看默认应用
open -Ra "Preview" 2>/dev/null && echo "Preview 可用"
```

## 常见能力映射

| 用户需求 | 查找关键词 | 常见应用 |
|---------|----------|---------|
| 编辑 PDF | PDF, Preview, Acrobat | Preview, Adobe Acrobat |
| 写文档 | Word, Pages, Writer | Pages, Word, LibreOffice |
| 做表格 | Excel, Numbers, Sheets | Numbers, Excel |
| 做 PPT | Keynote, PowerPoint | Keynote, PowerPoint |
| 编辑图片 | Photos, Photoshop, GIMP | Preview, Photos, Pixelmator |
| 编辑视频 | iMovie, Final Cut, DaVinci | iMovie, Final Cut Pro |
| 写代码 | VS Code, Xcode, Sublime | VS Code, Xcode |
| 浏览器 | Safari, Chrome, Firefox | Safari, Chrome |

## 输出规范

- 先回答用户的问题（有没有某个应用）
- 如果有多个选择，简要说明区别并推荐
- 推荐时考虑：系统自带优先、用户已安装优先
- 未安装时提供安装方式（App Store / brew / 官网）

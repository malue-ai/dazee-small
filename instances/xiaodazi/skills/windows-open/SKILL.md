---
name: windows-open
description: Open files, URLs, folders, and applications on Windows using Start-Process, explorer, and rundll32. Equivalent to macOS open command.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [win32]
    backend_type: local
    user_facing: true
---

# Windows 打开文件/URL/应用

使用 PowerShell 和系统命令打开文件、URL、文件夹和应用程序。
等同于 macOS 的 `open` 命令。

## 使用场景

- 用户说「打开这个文件」「用 XX 打开」「打开那个网页」
- 需要在文件资源管理器中定位文件
- 需要启动特定应用
- 文件处理完成后展示给用户查看

## 命令参考

### 打开文件（默认应用）

```powershell
# 用默认应用打开文件
Start-Process "C:\Users\$env:USERNAME\Documents\report.xlsx"

# 或使用 Invoke-Item
Invoke-Item "C:\Users\$env:USERNAME\Desktop\photo.jpg"
```

### 用指定应用打开

```powershell
# 用记事本打开
Start-Process "notepad.exe" -ArgumentList "C:\path\to\file.txt"

# 用 VS Code 打开
Start-Process "code" -ArgumentList "C:\path\to\project"

# 用 Word 打开
Start-Process "winword.exe" -ArgumentList "C:\path\to\doc.docx"

# 用 Excel 打开
Start-Process "excel.exe" -ArgumentList "C:\path\to\data.xlsx"
```

### 打开 URL

```powershell
# 用默认浏览器打开
Start-Process "https://www.example.com"

# 用指定浏览器打开
Start-Process "chrome.exe" -ArgumentList "https://www.example.com"
Start-Process "msedge.exe" -ArgumentList "https://www.example.com"
```

### 打开文件夹

```powershell
# 打开文件夹
explorer.exe "C:\Users\$env:USERNAME\Documents"

# 打开文件并选中（在资源管理器中高亮）
explorer.exe /select, "C:\Users\$env:USERNAME\Documents\report.xlsx"

# 打开特殊文件夹
explorer.exe shell:Downloads    # 下载
explorer.exe shell:Desktop      # 桌面
explorer.exe shell:MyDocuments  # 文档
explorer.exe shell:MyPictures   # 图片
explorer.exe shell:MyMusic      # 音乐
explorer.exe shell:MyVideo      # 视频
explorer.exe shell:RecycleBinFolder  # 回收站
```

### 启动应用

```powershell
# 按名称启动（需要在 PATH 中）
Start-Process "notepad"
Start-Process "calc"
Start-Process "mspaint"

# 启动 UWP 应用（通过 URI 协议）
Start-Process "ms-settings:"           # 设置
Start-Process "ms-clock:"              # 时钟
Start-Process "ms-todo:"               # To Do
Start-Process "ms-photos:"             # 照片
Start-Process "ms-screenclip:"         # 截图工具
Start-Process "calculator:"            # 计算器

# 启动并等待关闭
Start-Process "notepad.exe" -ArgumentList "file.txt" -Wait
```

### 系统控制面板

```powershell
# 打开控制面板项
Start-Process "control" -ArgumentList "printers"      # 打印机
Start-Process "control" -ArgumentList "fonts"          # 字体
Start-Process "ncpa.cpl"                               # 网络连接
Start-Process "appwiz.cpl"                             # 程序和功能
Start-Process "devmgmt.msc"                            # 设备管理器

# 打开系统信息
Start-Process "msinfo32"

# 打开任务管理器
Start-Process "taskmgr"
```

## 常见文件类型 → 推荐打开方式

| 文件类型 | 默认方式 | 推荐指定应用 |
|----------|----------|-------------|
| .txt .md .log | 记事本 | VS Code / Notepad++ |
| .xlsx .csv | Excel | Excel / LibreOffice |
| .docx | Word | Word / LibreOffice |
| .pdf | Edge | Adobe Acrobat / SumatraPDF |
| .jpg .png | 照片 | 照片 / Paint |
| .mp4 .mkv | 影视 | VLC / PotPlayer |
| .zip .7z | 资源管理器 | 7-Zip |

## 输出规范

- 打开后告知用户「已用 XX 打开 XX 文件」
- 打开文件夹时说明完整路径
- 文件不存在时提示并建议搜索

## 安全规则

- **不打开可执行文件（.exe .bat .cmd .ps1）**：除非用户明确要求
- **不以管理员身份启动应用**：除非用户明确要求
- 打开用户指定的 URL 前确认域名

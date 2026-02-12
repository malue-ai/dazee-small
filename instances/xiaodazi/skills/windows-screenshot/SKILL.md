---
name: windows-screenshot
description: Capture screenshots on Windows using PowerShell and .NET APIs.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [win32]
    backend_type: local
    user_facing: true
---

# Windows 截图

使用 PowerShell 截取屏幕。

## 命令参考

### 全屏截图

```powershell
Add-Type -AssemblyName System.Windows.Forms
$bitmap = [System.Windows.Forms.Screen]::PrimaryScreen
$bounds = $bitmap.Bounds
$screenshot = New-Object System.Drawing.Bitmap($bounds.Width, $bounds.Height)
$graphics = [System.Drawing.Graphics]::FromImage($screenshot)
$graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
$screenshot.Save("$env:TEMP\screenshot_$(Get-Date -Format 'yyyyMMdd_HHmmss').png")
```

### 使用 Snipping Tool

```powershell
Start-Process "SnippingTool" "/clip"
```

## 输出规范

- 默认保存到用户临时目录
- 截图完成后告知用户保存路径

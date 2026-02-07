---
name: windows-clipboard
description: Read from and write to the Windows clipboard using PowerShell.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [win32]
    backend_type: local
    user_facing: true
---

# Windows 剪贴板

使用 PowerShell 操作 Windows 剪贴板。

## 命令参考

### 读取剪贴板

```powershell
Get-Clipboard
```

### 写入剪贴板

```powershell
Set-Clipboard -Value "要复制的内容"
```

### 从文件复制到剪贴板

```powershell
Get-Content "C:\path\to\file.txt" | Set-Clipboard
```

## 输出规范

- 读取后展示内容（长文本截断前 500 字符）
- 写入后确认「已复制到剪贴板」

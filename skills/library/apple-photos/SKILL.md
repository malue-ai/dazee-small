---
name: apple-photos
description: Search and manage Apple Photos library on macOS via osascript.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [darwin]
    backend_type: local
    user_facing: true
---

# Apple 照片

通过 AppleScript/JXA 管理 macOS 照片库，搜索、导出、创建相册。

## 使用场景

- 用户说「帮我找去年在东京拍的照片」「最近的截图在哪」
- 用户说「导出这个相册的所有照片」
- 用户说「创建一个叫旅行的相册」

## 执行方式

### 搜索照片

```bash
osascript -e '
tell application "Photos"
    set results to (media items whose description contains "Tokyo" or name contains "Tokyo")
    set output to ""
    repeat with photo in (items 1 thru (min of {20, count of results}) of results)
        set output to output & (id of photo) & " | " & (filename of photo) & " | " & (date of photo) & linefeed
    end repeat
    return output
end tell'
```

### 按日期范围搜索

```bash
osascript -e '
tell application "Photos"
    set startDate to date "2025-12-01"
    set endDate to date "2025-12-31"
    set results to (media items whose date ≥ startDate and date ≤ endDate)
    return (count of results) & " photos found"
end tell'
```

### 获取相册列表

```bash
osascript -e '
tell application "Photos"
    set output to ""
    repeat with a in albums
        set output to output & (name of a) & " (" & (count of media items of a) & " items)" & linefeed
    end repeat
    return output
end tell'
```

### 创建相册

```bash
osascript -e '
tell application "Photos"
    make new album named "旅行 2026"
end tell'
```

### 导出照片

```bash
osascript -e '
tell application "Photos"
    set targetAlbum to album "旅行 2026"
    set exportPath to POSIX file "/Users/me/Desktop/export/"
    export (media items of targetAlbum) to exportPath
end tell'
```

## 输出规范

- 搜索结果显示缩略信息（文件名、日期、数量）
- 导出操作前确认数量和目标目录
- 不删除照片，只读取和导出

---
name: app-recommender
description: Recommend the best application for a user task based on installed apps (from app-scanner) and common software knowledge.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
---

# 应用推荐

根据用户任务需求，结合已安装的应用（通过 app-scanner），推荐最合适的软件。

## 使用场景

- 用户说「我想编辑一张图片，用什么软件好」
- 用户说「有没有免费的视频剪辑工具推荐」
- 任务执行中需要某类应用但不确定推荐哪个

## 工作流程

```
用户需求（如「编辑 PDF」）
    ↓
1. 调用 app-scanner 获取已安装应用列表
    ↓
2. 匹配已安装应用中能满足需求的
    ↓
3. 如果有多个匹配 → 按优先级推荐
   如果无匹配 → 推荐安装方案
    ↓
4. 输出推荐结果
```

## 推荐优先级

1. **系统自带应用**（免费、无需安装）
2. **用户已安装的应用**（已有，直接用）
3. **免费开源应用**（推荐安装）
4. **付费应用**（说明价格和优势）

## 常见需求 → 推荐映射

### macOS

| 需求 | 系统自带 | 推荐免费 | 推荐付费 |
|------|---------|---------|---------|
| 看/标注 PDF | Preview | Skim | PDF Expert |
| 编辑图片 | Preview, Photos | GIMP | Pixelmator Pro |
| 写文档 | TextEdit, Pages | LibreOffice | Word |
| 做表格 | Numbers | LibreOffice | Excel |
| 做 PPT | Keynote | LibreOffice | PowerPoint |
| 剪视频 | iMovie | DaVinci Resolve | Final Cut Pro |
| 写代码 | - | VS Code | - |
| 画图/设计 | - | Figma (Web) | Sketch |
| 录屏 | Screenshot (Cmd+Shift+5) | OBS | ScreenFlow |
| 压缩文件 | Archive Utility | Keka | BetterZip |
| 看 Markdown | - | MacDown | Typora |
| 终端 | Terminal | iTerm2 | - |

### Windows

| 需求 | 系统自带 | 推荐免费 | 推荐付费 |
|------|---------|---------|---------|
| 看 PDF | Edge | SumatraPDF | Adobe Acrobat |
| 编辑图片 | Paint | GIMP | Photoshop |
| 写文档 | WordPad | LibreOffice | Word |
| 剪视频 | Clipchamp | DaVinci Resolve | Premiere |
| 写代码 | Notepad | VS Code | - |
| 录屏 | Xbox Game Bar | OBS | Camtasia |

### 通用（跨平台）

| 需求 | 推荐免费 | 推荐付费 |
|------|---------|---------|
| 笔记 | Obsidian, Notion | Bear |
| 任务管理 | Trello, Todoist | Things |
| 密码管理 | Bitwarden | 1Password |
| 邮件 | Thunderbird | Spark |
| 浏览器 | Firefox, Chrome | Arc |

## 输出规范

- 先推荐用户已安装的（「你电脑上有 Preview，可以直接用它打开」）
- 如果需要安装，给出一步命令（`brew install xxx` 或 App Store 链接）
- 说人话，不堆参数（「iMovie 够用了，免费的，系统自带」）
- 付费应用注明价格范围

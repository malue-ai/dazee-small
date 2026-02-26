---
name: homebrew
description: macOS package manager — search, install, upgrade, and manage software via brew.
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [darwin]
    backend_type: local
    user_facing: true
    bins: ["brew"]
---

# Homebrew 包管理

macOS 包管理器，安装、升级、管理命令行工具和桌面应用。

## 使用场景

- 用户说「帮我安装 ffmpeg」「我要装个 Python」
- 用户说「更新一下所有软件」「看看有哪些过期的包」
- 用户说「卸载 node」「搜索一下有没有 XX 工具」

## 执行方式

### 搜索

```bash
brew search 关键词
```

### 安装

```bash
# 命令行工具
brew install ffmpeg

# GUI 应用
brew install --cask visual-studio-code
```

### 更新

```bash
# 更新 Homebrew 本身
brew update

# 查看可升级的包
brew outdated

# 升级所有
brew upgrade

# 升级单个
brew upgrade ffmpeg
```

### 信息查询

```bash
# 包信息
brew info ffmpeg

# 已安装列表
brew list
brew list --cask

# 依赖树
brew deps --tree ffmpeg
```

### 清理

```bash
# 清理旧版本缓存
brew cleanup

# 查看可回收空间
brew cleanup -n
```

### 卸载

```bash
brew uninstall ffmpeg
brew uninstall --cask visual-studio-code
```

## 输出规范

- 安装前告知用户将要安装的版本和大小
- 安装成功后确认版本号
- 升级前列出将要更新的包列表，让用户确认

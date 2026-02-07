# Skills 安装配置指南

小搭子所有技能的依赖安装与 API Key 配置说明。

## 前置条件

### macOS 开发工具

```bash
# 确保 Xcode Command Line Tools 为最新版本（brew 编译依赖）
sudo rm -rf /Library/Developer/CommandLineTools
sudo xcode-select --install
```

### Homebrew

```bash
# 安装 Homebrew（如果没有）
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### Python 虚拟环境

```bash
source /path/to/your/venv/bin/activate
```

---

## 一、lightweight（轻量依赖）

首次使用时自动安装，或手动提前安装。

### Python 包（auto_install: true）

```bash
pip install pypdf pandas openpyxl python-docx
```

| 包名 | 对应 Skill | 用途 |
|------|-----------|------|
| `pypdf` | nano-pdf | PDF 文件读取 |
| `pandas` + `openpyxl` | excel-analyzer, excel-fixer | Excel/CSV 分析 |
| `python-docx` | word-processor | Word 文档处理 |

### macOS 系统授权

首次调用时系统会弹窗请求权限，点击允许即可。

| 权限类型 | 对应 Skill | 授权路径 |
|---------|-----------|---------|
| accessibility | apple-notes | 系统设置 → 隐私与安全性 → 辅助功能 |
| reminders | apple-reminders | 系统设置 → 隐私与安全性 → 提醒事项 |
| calendar | apple-calendar | 系统设置 → 隐私与安全性 → 日历 |

---

## 二、external（外部工具）

需要手动安装外部应用或命令行工具。

### CLI 工具

#### 通过 Homebrew 安装

```bash
# 基础工具
brew install tmux

# steipete 工具集（需要先 tap）
brew tap steipete/tap
brew install steipete/tap/peekaboo      # macOS UI 自动化
brew install steipete/tap/summarize      # URL/视频/文档摘要
brew install steipete/tap/gifgrep        # GIF 搜索
brew install steipete/tap/gogcli         # Google Docs/Sheets/Calendar

# 其他 tap
brew install openhue/cli/openhue-cli     # Philips Hue 智能灯控
brew install gh                          # GitHub CLI
brew install himalaya                    # 邮件客户端 (IMAP)
brew install blogwatcher                 # RSS 博客监控
```

> **Homebrew 编译失败？** 先更新 Xcode Command Line Tools：
> ```bash
> sudo rm -rf /Library/Developer/CommandLineTools && sudo xcode-select --install
> ```
>
> 如果 brew 仍然报错，可直接从 GitHub Releases 下载预编译二进制到 `/opt/homebrew/bin/`。

#### 通过 GitHub Releases 手动安装（备选）

如果 brew 编译失败，可直接下载预编译文件：

```bash
# 示例：安装 summarize
curl -sL "https://github.com/steipete/summarize/releases/latest/download/summarize-macos-arm64-vX.Y.Z.tar.gz" -o /tmp/summarize.tar.gz
cd /tmp && tar xzf summarize.tar.gz
cp summarize /opt/homebrew/bin/ && chmod +x /opt/homebrew/bin/summarize
```

同理适用于 `peekaboo`、`gogcli`、`gifgrep`、`openhue`、`goplaces`。

#### 通过 pip 安装

```bash
pip install openai-whisper    # 本地语音转文字
pip install sherpa-onnx        # 本地 TTS 语音合成
```

> `sherpa-onnx` 安装后可执行文件名为 `sherpa-onnx-cli`，如需 `sherpa-onnx` 命令：
> ```bash
> ln -sf $(which sherpa-onnx-cli) /opt/homebrew/bin/sherpa-onnx
> ```

#### 1Password CLI

```bash
# 从 1Password 官网下载安装
# https://developer.1password.com/docs/cli/get-started/
brew install --cask 1password-cli
```

### CLI 工具对照表

| 命令 | 对应 Skill | 安装方式 |
|------|-----------|---------|
| `peekaboo` | peekaboo | brew (steipete/tap) |
| `gh` | github | brew |
| `op` | 1password | brew cask |
| `himalaya` | himalaya | brew |
| `blogwatcher` | blogwatcher | brew |
| `summarize` | summarize | brew (steipete/tap) |
| `gog` | gog | brew (steipete/tap/gogcli) |
| `gifgrep` | gifgrep | brew (steipete/tap) |
| `openhue` | openhue | brew (openhue/cli) |
| `goplaces` | goplaces | brew (steipete/tap) |
| `tmux` | 系统工具 | brew |
| `whisper` | openai-whisper | pip |
| `sherpa-onnx` | sherpa-onnx-tts | pip |

### macOS 应用

```bash
# 通过 Homebrew Cask
brew install --cask obsidian    # 笔记管理
brew install --cask spotify     # 音乐播放

# 通过 Mac App Store（需要 mas 工具）
brew install mas
mas install 1091189122          # Bear 熊掌记
mas install 904280696           # Things 3
```

| 应用 | 对应 Skill | 安装方式 |
|------|-----------|---------|
| Obsidian | obsidian | `brew install --cask obsidian` |
| Bear | bear-notes | Mac App Store |
| Things 3 | things-mac | Mac App Store |
| Spotify | spotify-player | `brew install --cask spotify` |

---

## 三、cloud_api（云服务 API Key）

需要注册并获取 API Key，配置到 `config.yaml` 文件中（或通过前端设置页面配置）。

### 必需

| 环境变量 | 服务 | 获取地址 |
|---------|------|---------|
| `ANTHROPIC_API_KEY` | Claude API | https://console.anthropic.com/ |

### 搜索工具

| 环境变量 | 服务 | 获取地址 |
|---------|------|---------|
| `TAVILY_API_KEY` | Tavily 搜索 | https://tavily.com/ |
| `EXA_API_KEY` | Exa 语义搜索 | https://dashboard.exa.ai/ |

### 内容生成

| 环境变量 | 服务 | 获取地址 |
|---------|------|---------|
| `SLIDESPEAK_API_KEY` | SlideSpeak PPT | https://app.slidespeak.co/settings/developer |
| `GEMINI_API_KEY` | Gemini 图像生成 | https://aistudio.google.com/apikey |
| `OPENAI_API_KEY` | OpenAI (Embedding + DALL·E) | https://platform.openai.com/api-keys |

### 文档处理

| 环境变量 | 服务 | 获取地址 |
|---------|------|---------|
| `UNSTRUCTURED_API_KEY` | Unstructured 文档解析 | https://unstructured.io/ |

### 第三方集成

| 环境变量 | 服务 | 获取地址 | 备注 |
|---------|------|---------|------|
| `NOTION_API_KEY` | Notion | https://notion.so/my-integrations | 需分享页面给 Integration |
| `TRELLO_API_KEY` + `TRELLO_TOKEN` | Trello | https://trello.com/app-key | 同页面获取两个值 |
| `GOOGLE_PLACES_API_KEY` | Google Places | https://console.cloud.google.com/ | 启用 Places API (New) |
| `DISCORD_BOT_TOKEN` | Discord | https://discord.com/developers/applications | 创建 Bot 获取 Token |

### 多模型容灾（可选）

| 环境变量 | 服务 | 说明 |
|---------|------|------|
| `DASHSCOPE_API_KEY` | 通义千问 | 阿里云 DashScope |
| `CLAUDE_API_KEY_VENDOR_A` | Claude 备用 A | 多供应商容灾 |
| `CLAUDE_API_KEY_VENDOR_B` | Claude 备用 B | 多供应商容灾 |

---

## 一键检查脚本

验证所有依赖是否就绪：

```bash
echo "========== CLI 工具 =========="
for cmd in peekaboo gh op himalaya summarize gog blogwatcher gifgrep openhue goplaces tmux whisper sherpa-onnx; do
    command -v $cmd &>/dev/null && echo "✅ $cmd" || echo "❌ $cmd"
done

echo "========== Python 包 =========="
pip list 2>/dev/null | grep -iE "pypdf|pandas|openpyxl|python-docx|openai-whisper|sherpa"

echo "========== macOS 应用 =========="
for app in Obsidian Bear Things3 Spotify; do
    [ -d "/Applications/$app.app" ] && echo "✅ $app" || echo "❌ $app"
done

echo "========== API Keys =========="
for var in ANTHROPIC_API_KEY TAVILY_API_KEY EXA_API_KEY SLIDESPEAK_API_KEY GEMINI_API_KEY OPENAI_API_KEY; do
    [ -n "${!var}" ] && echo "✅ $var" || echo "⬜ $var (未配置)"
done
```

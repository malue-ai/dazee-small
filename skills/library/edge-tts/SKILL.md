---
name: edge-tts
description: Free text-to-speech using Microsoft Edge's online TTS service. No API key required.
metadata:
  xiaodazi:
    dependency_level: lightweight
    os: [common]
    backend_type: local
    user_facing: true
    python_packages: ["edge-tts"]
---

# Edge TTS 免费语音合成

使用微软 Edge 的在线 TTS 服务生成语音，免费，无需 API Key，支持 300+ 种声音。

## 使用场景

- 用户说「把这段文字转成语音」「用中文女声读一下」
- 需要快速生成语音，不想配置 API Key
- kokoro-tts 未安装时的替代方案

## 执行方式

### 命令行用法

```bash
# 基本用法
edge-tts --text "你好，今天天气真不错" --write-media output.mp3

# 指定声音
edge-tts --voice zh-CN-XiaoxiaoNeural --text "你好" --write-media output.mp3

# 带字幕
edge-tts --voice zh-CN-XiaoxiaoNeural --text "你好" \
  --write-media output.mp3 --write-subtitles output.vtt
```

### Python API

```python
import edge_tts
import asyncio

async def generate():
    communicate = edge_tts.Communicate("你好，这是测试语音。", "zh-CN-XiaoxiaoNeural")
    await communicate.save("output.mp3")

asyncio.run(generate())
```

### 推荐中文声音

| Voice | 性别 | 风格 |
|---|---|---|
| `zh-CN-XiaoxiaoNeural` | 女 | 温暖亲切（推荐） |
| `zh-CN-XiaoyiNeural` | 女 | 活泼 |
| `zh-CN-YunjianNeural` | 男 | 专业播报 |
| `zh-CN-YunxiNeural` | 男 | 年轻自然 |

### 列出所有可用声音

```bash
edge-tts --list-voices | grep zh-CN
```

### 调节语速和音调

```bash
edge-tts --voice zh-CN-XiaoxiaoNeural \
  --rate "+20%" --pitch "+5Hz" \
  --text "加速播放" --write-media output.mp3
```

## 输出规范

- 默认使用 `zh-CN-XiaoxiaoNeural`（中文）或 `en-US-JennyNeural`（英文）
- 输出 MP3 格式，返回文件路径
- 需要网络连接（非离线方案）

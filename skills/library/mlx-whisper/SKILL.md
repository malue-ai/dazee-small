---
name: mlx-whisper
description: Fast local speech-to-text on Apple Silicon using MLX Whisper. 10x faster than OpenAI Whisper.
metadata:
  xiaodazi:
    dependency_level: external
    os: [darwin]
    backend_type: local
    user_facing: true
---

# MLX Whisper 语音转文字

利用 Apple Silicon 的 MLX 框架本地转录语音，速度是 OpenAI Whisper 的 10 倍。完全离线，隐私安全。

## 使用场景

- 用户说「帮我把这段录音转成文字」「转录这个音频文件」
- 需要快速转录会议录音、语音备忘录
- 优先于 openai-whisper（更快）和 openai-whisper-api（免费、隐私）

## 前置条件

```bash
pip install mlx-whisper
```

需要 Apple Silicon Mac（M1/M2/M3/M4）。

## 执行方式

### 基本转录

```python
import mlx_whisper

result = mlx_whisper.transcribe(
    "audio.mp3",
    path_or_hf_repo="mlx-community/whisper-large-v3-turbo",
)
print(result["text"])
```

### 带时间戳

```python
result = mlx_whisper.transcribe(
    "audio.mp3",
    path_or_hf_repo="mlx-community/whisper-large-v3-turbo",
    word_timestamps=True,
)
for segment in result["segments"]:
    print(f"[{segment['start']:.1f}s - {segment['end']:.1f}s] {segment['text']}")
```

### 模型选择

| 模型 | 大小 | 速度 | 准确度 |
|---|---|---|---|
| `whisper-tiny` | 39M | 最快 | 一般 |
| `whisper-base` | 74M | 快 | 较好 |
| `whisper-small` | 244M | 中 | 好 |
| `whisper-large-v3-turbo` | 809M | 较慢 | 最佳 |

默认使用 `large-v3-turbo`，短音频（<1分钟）可用 `small` 加速。

### 语言指定

```python
result = mlx_whisper.transcribe("audio.mp3", language="zh")
```

## 输出规范

- 默认输出纯文本
- 用户需要时提供带时间戳的分段输出
- 长音频显示转录进度
- 首次使用时自动下载模型（约 800MB），提醒用户

---
name: kokoro-tts
description: High-quality local text-to-speech using Kokoro TTS engine. Zero API cost, fully offline.
metadata:
  xiaodazi:
    dependency_level: external
    os: [common]
    backend_type: local
    user_facing: true
---

# Kokoro TTS 本地语音合成

使用 Kokoro TTS 引擎在本地生成高质量语音，零 API 成本，完全离线。

## 使用场景

- 用户说「把这段文字读出来」「生成这篇文章的语音版本」
- 需要将文档、邮件、新闻转为音频
- 优先于 sag（ElevenLabs，需 API Key 和付费）

## 前置条件

```bash
pip install kokoro-onnx soundfile
```

首次使用需下载模型文件（约 300MB）。

## 执行方式

### 基本用法

```python
from kokoro_onnx import Kokoro

kokoro = Kokoro("kokoro-v1.0.onnx", "voices-v1.0.bin")

samples, sample_rate = kokoro.create(
    "你好，这是一段测试语音。",
    voice="af_heart",
    speed=1.0,
    lang="z",  # z=中文, e=英文
)

import soundfile as sf
sf.write("output.wav", samples, sample_rate)
```

### 可用声音

| Voice ID | 性别 | 语言 | 风格 |
|---|---|---|---|
| `af_heart` | 女 | 中/英 | 温暖自然 |
| `af_bella` | 女 | 中/英 | 清晰专业 |
| `am_adam` | 男 | 中/英 | 沉稳 |
| `am_michael` | 男 | 中/英 | 活力 |

### 长文本处理

长文本自动按句分段合成，避免内存溢出：
```python
import re

sentences = re.split(r'[。！？\.\!\?]', long_text)
all_samples = []
for s in sentences:
    if s.strip():
        samples, sr = kokoro.create(s.strip() + "。", voice="af_heart", lang="z")
        all_samples.append(samples)

import numpy as np
combined = np.concatenate(all_samples)
sf.write("output.wav", combined, sr)
```

## 输出规范

- 生成的音频保存为 WAV 文件并返回路径
- 告知用户音频时长和文件大小
- 中英混合文本自动处理语言切换

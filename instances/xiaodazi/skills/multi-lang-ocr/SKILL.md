---
name: multi-lang-ocr
description: Extract text from images, screenshots, and scanned documents using local OCR. Supports Chinese, English, Japanese, Korean and mixed-language text. Runs 100% locally for privacy.
version: "2.0.0"
parameters:
  - name: image_path
    type: string
    required: true
    description: "Image / screenshot / scanned page file path"
  - name: output_path
    type: string
    required: false
    description: "Optional output file path (default: print to stdout)"
metadata:
  xiaodazi:
    dependency_level: builtin
    os: [common]
    backend_type: local
    user_facing: true
    # NOTE: 依赖管理由 skills.yaml 按 OS 分区处理：
    # - macOS: darwin/builtin（Vision Framework 内置，零安装）
    # - Windows/Linux: lightweight（auto_install: pip install rapidocr-onnxruntime）
    # SKILL.md 不声明 python_packages / auto_install，避免与 skills.yaml 冲突
---

# 多语言 OCR — 图片文字提取

从图片、截图、扫描件中提取文字。支持中文、英文、中英混排、日文、韩文。100% 本地运行，保护隐私。

## 使用场景

- 用户说「帮我提取这张图片里的文字」「截图转文字」
- 用户说「识别这份扫描文档的内容」「名片上的信息提取出来」
- 用户说「把这张照片里的表格提取成文本」
- 处理 PDF 中无法提取文字的扫描页

## 引擎选择（分层策略）

### macOS 优先路径（零安装）

macOS 内置 Vision Framework，中英混排识别质量优秀，无需安装任何依赖。

```python
import subprocess, json

def ocr_macos_vision(image_path: str) -> str:
    """Use macOS Vision Framework for OCR (zero install, best quality on Mac)."""
    swift_code = f'''
import Foundation
import Vision

let url = URL(fileURLWithPath: "{image_path}")
guard let image = CGImage.from(url: url) else {{ exit(1) }}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.recognitionLanguages = ["zh-Hans", "zh-Hant", "en-US", "ja", "ko"]
request.usesLanguageCorrection = true

let handler = VNImageRequestHandler(cgImage: image)
try handler.perform([request])

let results = request.results ?? []
for obs in results {{
    if let candidate = obs.topCandidates(1).first {{
        print(candidate.string)
    }}
}}
'''
    # Save and execute Swift script
    import tempfile, os
    script_path = tempfile.mktemp(suffix='.swift')
    with open(script_path, 'w') as f:
        f.write(swift_code)
    try:
        result = subprocess.run(
            ['swift', script_path],
            capture_output=True, text=True, timeout=30
        )
        return result.stdout.strip()
    finally:
        os.unlink(script_path)
```

**使用条件**：macOS 13+，无需安装任何依赖。通过 `nodes` 执行即可。

### 跨平台路径（pip 安装，~50MB）

使用 `rapidocr-onnxruntime`，基于 PaddleOCR v4 模型的 ONNX 推理版本。

```bash
# 首次安装（约 50MB，30 秒内完成）
pip install rapidocr-onnxruntime
```

```python
from rapidocr_onnxruntime import RapidOCR

engine = RapidOCR()

# 基本识别（自动检测中英文，无需指定语言）
result, elapse = engine("/path/to/image.png")

# result 是列表：[[坐标, 文字, 置信度], ...]
if result:
    for line in result:
        box, text, confidence = line
        print(f"{text}  (置信度: {confidence:.2f})")
```

## 执行方式

通过 `nodes` 写 Python 脚本执行 OCR。**优先尝试 macOS Vision，不可用时降级到 rapidocr。**

### 推荐执行脚本模板

```python
import sys, os, json

image_path = sys.argv[1] if len(sys.argv) > 1 else "/path/to/image.png"
output_path = sys.argv[2] if len(sys.argv) > 2 else None

def ocr_with_best_engine(path: str) -> str:
    """Try macOS Vision first, then rapidocr, then report unavailable."""
    import platform

    # Tier 1: macOS Vision (zero install)
    if platform.system() == "Darwin":
        try:
            import subprocess
            # Quick check: can we run swift?
            check = subprocess.run(["swift", "--version"], capture_output=True, timeout=5)
            if check.returncode == 0:
                return _ocr_macos_vision(path)
        except Exception:
            pass

    # Tier 2: rapidocr-onnxruntime (pip install)
    try:
        from rapidocr_onnxruntime import RapidOCR
        engine = RapidOCR()
        result, _ = engine(path)
        if result:
            return "\n".join(line[1] for line in result)
        return "[OCR completed but no text detected]"
    except ImportError:
        pass

    return "[OCR_UNAVAILABLE] No OCR engine found. Install: pip install rapidocr-onnxruntime"


def _ocr_macos_vision(path: str) -> str:
    """macOS Vision Framework OCR via objc bridge."""
    try:
        import Quartz
        from Vision import (
            VNRecognizeTextRequest,
            VNImageRequestHandler,
        )
        ci_image = Quartz.CIImage.imageWithContentsOfURL_(
            Quartz.NSURL.fileURLWithPath_(path)
        )
        if ci_image is None:
            raise ValueError(f"Cannot load image: {path}")

        request = VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(1)  # accurate
        request.setRecognitionLanguages_(["zh-Hans", "zh-Hant", "en-US", "ja", "ko"])
        request.setUsesLanguageCorrection_(True)

        handler = VNImageRequestHandler.alloc().initWithCIImage_options_(ci_image, None)
        success = handler.performRequests_error_([request], None)

        lines = []
        for obs in request.results() or []:
            candidate = obs.topCandidates_(1)
            if candidate:
                lines.append(candidate[0].string())
        return "\n".join(lines)
    except ImportError:
        # pyobjc not available, fall through to rapidocr
        raise
    except Exception as e:
        raise RuntimeError(f"macOS Vision OCR failed: {e}")


# Run OCR
text = ocr_with_best_engine(image_path)

# Output
if output_path:
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"OCR result saved to: {output_path}")
    print(f"Characters extracted: {len(text)}")
else:
    print(text)
```

### 批量处理（目录中所有图片）

```python
import os, glob

image_dir = "/path/to/scanned_pages"
output_file = "/path/to/extracted_text.md"

images = sorted(glob.glob(os.path.join(image_dir, "*.{png,jpg,jpeg,tiff,bmp}")))
all_text = []

for i, img_path in enumerate(images, 1):
    print(f"Processing page {i}/{len(images)}: {os.path.basename(img_path)}")
    text = ocr_with_best_engine(img_path)
    all_text.append(f"## Page {i}\n\n{text}")

with open(output_file, "w", encoding="utf-8") as f:
    f.write("\n\n---\n\n".join(all_text))

print(f"Done: {len(images)} pages -> {output_file}")
```

## 语言支持

| 语言 | rapidocr | macOS Vision | 说明 |
|------|----------|-------------|------|
| 简体中文 | 默认支持 | 默认支持 | 无需额外配置 |
| 英文 | 默认支持 | 默认支持 | 无需额外配置 |
| 中英混排 | 默认支持 | 默认支持 | 一个模型同时识别，无需切换 |
| 繁体中文 | 默认支持 | 默认支持 | 自动识别 |
| 日文 | 需下载模型 | 默认支持 | rapidocr 需额外步骤 |
| 韩文 | 需下载模型 | 默认支持 | rapidocr 需额外步骤 |

## 安全规则

- **100% 本地处理**：所有 OCR 操作在本地完成，图片不上传到任何云端
- **临时文件清理**：处理完成后删除中间临时文件

## 输出规范

- 提取后展示识别文本（纯文本格式）
- 如有多页，按页码分段展示
- 如识别效果差（文字模糊/手写），告知用户并建议提供更清晰图片
- 表格内容尽量保持结构化格式（用 Markdown 表格）
- 将结果写入文件并告知路径，方便用户后续使用

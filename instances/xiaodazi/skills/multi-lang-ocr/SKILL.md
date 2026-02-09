---
name: multi-lang-ocr
description: Extract text from images and screenshots using local OCR. Supports multiple languages including English, Chinese, Japanese, Korean. Runs locally for privacy.
metadata:
  xiaodazi:
    dependency_level: external
    os: [common]
    backend_type: local
    user_facing: true
---

# 多语言 OCR

从图片和截图中提取文字：支持英文、中文、日文、韩文等多语言。本地运行，保护隐私。

## 使用场景

- 用户说「帮我提取这张图片里的文字」「截图转文字」
- 用户说「识别这份扫描文档的内容」「名片上的信息提取出来」
- 用户说「把这张照片里的表格提取成文本」

## 依赖安装

需要安装 Tesseract OCR 引擎：

```bash
# macOS
brew install tesseract tesseract-lang

# Ubuntu/Debian
sudo apt install tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-jpn

# Windows (via chocolatey)
# choco install tesseract
```

## 执行方式

通过 bash 调用 tesseract 处理图片。

### 基本文字提取

```bash
# 英文（默认）
tesseract /path/to/image.png stdout

# 中文
tesseract /path/to/image.png stdout -l chi_sim

# 日文
tesseract /path/to/image.png stdout -l jpn

# 多语言混合
tesseract /path/to/image.png stdout -l eng+chi_sim+jpn
```

### 输出到文件

```bash
# 输出为文本文件
tesseract /path/to/image.png /path/to/output -l chi_sim

# 输出结果在 /path/to/output.txt
```

### 提高识别精度

```bash
# 使用 PSM（页面分割模式）
# PSM 6: 假设为单个文本块
tesseract /path/to/image.png stdout -l chi_sim --psm 6

# PSM 4: 假设为单列文本
tesseract /path/to/image.png stdout -l chi_sim --psm 4

# PSM 11: 稀疏文本（如名片）
tesseract /path/to/image.png stdout -l eng --psm 11
```

### 从截图直接 OCR

```bash
# macOS: 截图 + OCR 一体化
screencapture -i /tmp/ocr_temp.png && tesseract /tmp/ocr_temp.png stdout -l eng+chi_sim
```

### 批量处理

```bash
# 批量处理目录中的图片
for img in /path/to/images/*.{png,jpg,jpeg}; do
  echo "=== $(basename "$img") ==="
  tesseract "$img" stdout -l eng+chi_sim 2>/dev/null
  echo ""
done
```

### 语言代码对照

| 语言 | 代码 | 安装包 |
|---|---|---|
| English | eng | 默认包含 |
| 简体中文 | chi_sim | tesseract-ocr-chi-sim |
| 繁体中文 | chi_tra | tesseract-ocr-chi-tra |
| 日本語 | jpn | tesseract-ocr-jpn |
| 한국어 | kor | tesseract-ocr-kor |
| Français | fra | tesseract-ocr-fra |
| Deutsch | deu | tesseract-ocr-deu |

## 安全规则

- **本地处理**：所有 OCR 操作在本地完成，图片不上传到任何云端
- **临时文件清理**：处理完成后删除临时截图

## 输出规范

- 提取后展示识别文本
- 标注识别语言和置信度（如可获取）
- 如识别效果差，建议用户提供更清晰的图片
- 表格内容尝试保持结构化格式

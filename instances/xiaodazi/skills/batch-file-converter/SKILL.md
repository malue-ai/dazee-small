---
name: batch-file-converter
description: Batch convert files between formats - images (HEIC/PNG/JPG/WebP), documents (Markdown/HTML), and more using Python and system tools.
metadata:
  xiaodazi:
    dependency_level: lightweight
    os: [common]
    backend_type: local
    user_facing: true
    python_packages:
      - Pillow
---

# 批量文件转换

帮助用户批量转换文件格式：图片格式互转、文档格式转换。

## 使用场景

- 用户说「把这些 HEIC 照片转成 JPG」「PNG 转 WebP」
- 用户说「把这些图片批量压缩」「调整图片尺寸」
- 用户说「Markdown 转 HTML」「批量转换格式」

## 依赖安装

首次使用时自动安装：

```bash
pip install Pillow
```

## 执行方式

通过 Python Pillow 处理图片，bash 处理其他格式。

### 图片格式转换

```python
from PIL import Image
import os

input_dir = "/path/to/input"
output_dir = "/path/to/output"
target_format = "JPEG"  # JPEG, PNG, WEBP, BMP, TIFF

os.makedirs(output_dir, exist_ok=True)

count = 0
for filename in os.listdir(input_dir):
    if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.heic', '.webp', '.bmp')):
        img = Image.open(os.path.join(input_dir, filename))
        # RGBA → RGB for JPEG
        if img.mode == 'RGBA' and target_format == 'JPEG':
            img = img.convert('RGB')
        
        new_name = os.path.splitext(filename)[0] + ".jpg"
        img.save(os.path.join(output_dir, new_name), target_format, quality=90)
        count += 1

print(f"转换完成: {count} 个文件")
```

### HEIC 转 JPG（macOS）

```bash
# macOS 原生支持 HEIC
for f in /path/to/*.HEIC; do
  sips -s format jpeg "$f" --out "/path/to/output/$(basename "${f%.*}").jpg"
done
```

### 批量压缩图片

```python
from PIL import Image
import os

input_dir = "/path/to/input"
output_dir = "/path/to/compressed"
max_size = (1920, 1080)
quality = 80

os.makedirs(output_dir, exist_ok=True)

for filename in os.listdir(input_dir):
    if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
        img = Image.open(os.path.join(input_dir, filename))
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        if img.mode == 'RGBA':
            img = img.convert('RGB')
        
        img.save(os.path.join(output_dir, filename), quality=quality)

print("压缩完成")
```

### 批量调整图片尺寸

```python
from PIL import Image
import os

target_width = 800
input_dir = "/path/to/input"
output_dir = "/path/to/resized"

os.makedirs(output_dir, exist_ok=True)

for filename in os.listdir(input_dir):
    if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
        img = Image.open(os.path.join(input_dir, filename))
        ratio = target_width / img.width
        new_height = int(img.height * ratio)
        img = img.resize((target_width, new_height), Image.Resampling.LANCZOS)
        img.save(os.path.join(output_dir, filename))
```

### Markdown → HTML

```bash
# 使用 Python 内置
python3 -c "
import markdown
with open('/path/to/input.md') as f:
    html = markdown.markdown(f.read(), extensions=['tables', 'fenced_code'])
with open('/path/to/output.html', 'w') as f:
    f.write(html)
print('转换完成')
"
```

## 安全规则

- **不覆盖原文件**：输出到新目录
- **转换前展示文件列表**：确认要转换的文件数量和格式
- **大批量操作提醒**：超过 100 个文件时提醒用户确认

## 输出规范

- 转换前：列出文件数量、源格式、目标格式
- 转换后：报告成功/失败数量、输出目录、总大小变化

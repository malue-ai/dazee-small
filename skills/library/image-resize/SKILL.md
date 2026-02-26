---
name: image-resize
description: Resize, convert, and batch-process images using ImageMagick.
metadata:
  xiaodazi:
    dependency_level: external
    os: [common]
    backend_type: local
    user_facing: true
    bins: ["magick"]
---

# 图片处理（ImageMagick）

使用 ImageMagick 批量处理图片：缩放、裁剪、格式转换、压缩、拼接。

## 使用场景

- 用户说「把这张图片缩小到 800px 宽」「批量压缩这个文件夹的图片」
- 用户说「把 PNG 转成 JPG」「给图片加水印」
- 用户说「把这几张图拼成一张」

## 前置条件

```bash
# macOS
brew install imagemagick
# Windows
winget install ImageMagick.ImageMagick
# Linux
sudo apt install imagemagick
```

## 执行方式

### 缩放

```bash
# 按宽度缩放（保持比例）
magick input.jpg -resize 800x output.jpg

# 按百分比
magick input.jpg -resize 50% output.jpg

# 指定尺寸（可能变形）
magick input.jpg -resize 800x600! output.jpg
```

### 格式转换

```bash
magick input.png output.jpg
magick input.jpg output.webp
```

### 批量处理

```bash
# 批量缩放目录下所有 JPG
for f in *.jpg; do magick "$f" -resize 800x "resized_$f"; done

# 批量转格式
for f in *.png; do magick "$f" "${f%.png}.jpg"; done
```

### 压缩

```bash
# JPEG 质量压缩
magick input.jpg -quality 80 output.jpg

# 去除元数据减小体积
magick input.jpg -strip -quality 85 output.jpg
```

### 拼接

```bash
# 水平拼接
magick a.jpg b.jpg +append merged.jpg

# 垂直拼接
magick a.jpg b.jpg -append merged.jpg
```

### 水印

```bash
magick input.jpg -gravity SouthEast -fill white -pointsize 24 \
  -annotate +10+10 "© 2026" output.jpg
```

## 输出规范

- 处理前显示原始图片尺寸和大小
- 处理后显示新尺寸和大小，以及节省的空间
- 批量操作前确认文件数量和目标参数
- 不覆盖原文件，输出到新文件或子目录

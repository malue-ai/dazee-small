---
name: nano-banana-pro
description: 通过 Gemini 3 Pro Image (Nano Banana Pro) 生成或编辑图像。
homepage: https://ai.google.dev/
metadata: {"moltbot":{"emoji":"🍌","requires":{"bins":["uv"],"env":["GEMINI_API_KEY"]},"primaryEnv":"GEMINI_API_KEY","install":[{"id":"uv-brew","kind":"brew","formula":"uv","bins":["uv"],"label":"安装 uv (brew)"}]}}
---

# Nano Banana Pro (Gemini 3 Pro Image)

使用内置脚本生成或编辑图像。

## 生成图像
```bash
uv run {baseDir}/scripts/generate_image.py --prompt "你的图像描述" --filename "output.png" --resolution 1K
```

## 编辑图像（单张）
```bash
uv run {baseDir}/scripts/generate_image.py --prompt "编辑指令" --filename "output.png" -i "/path/in.png" --resolution 2K
```

## 多图合成（最多 14 张图像）
```bash
uv run {baseDir}/scripts/generate_image.py --prompt "将这些图像合成为一个场景" --filename "output.png" -i img1.png -i img2.png -i img3.png
```

## API 密钥配置
- 设置 `GEMINI_API_KEY` 环境变量
- 或在 `~/.clawdbot/moltbot.json` 中设置 `skills."nano-banana-pro".apiKey` / `skills."nano-banana-pro".env.GEMINI_API_KEY`

## 注意事项
- 支持分辨率：`1K`（默认）、`2K`、`4K`
- 建议文件名使用时间戳格式：`yyyy-mm-dd-hh-mm-ss-name.png`
- 脚本会输出 `MEDIA:` 行，便于 Moltbot 在支持的聊天平台上自动附加图片
- 不要读取生成的图像内容，只需报告保存路径即可

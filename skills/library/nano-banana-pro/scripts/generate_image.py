#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "google-genai>=1.0.0",
#     "pillow>=10.0.0",
# ]
# ///
"""
使用 Google Nano Banana Pro (Gemini 3 Pro Image) API 生成图像。

用法：
    uv run generate_image.py --prompt "你的图像描述" --filename "output.png" [--resolution 1K|2K|4K] [--api-key KEY]

多图编辑（最多 14 张图像）：
    uv run generate_image.py --prompt "合成这些图像" --filename "output.png" -i img1.png -i img2.png -i img3.png
"""

import argparse
import os
import sys
from pathlib import Path


def get_api_key(provided_key: str | None) -> str | None:
    """获取 API 密钥，优先使用参数传入的值，其次使用环境变量。"""
    if provided_key:
        return provided_key
    return os.environ.get("GEMINI_API_KEY")


def main():
    parser = argparse.ArgumentParser(
        description="使用 Nano Banana Pro (Gemini 3 Pro Image) 生成图像"
    )
    parser.add_argument(
        "--prompt", "-p",
        required=True,
        help="图像描述/提示词"
    )
    parser.add_argument(
        "--filename", "-f",
        required=True,
        help="输出文件名（例如：sunset-mountains.png）"
    )
    parser.add_argument(
        "--input-image", "-i",
        action="append",
        dest="input_images",
        metavar="IMAGE",
        help="用于编辑/合成的输入图像路径，可多次指定（最多 14 张图像）"
    )
    parser.add_argument(
        "--resolution", "-r",
        choices=["1K", "2K", "4K"],
        default="1K",
        help="输出分辨率：1K（默认）、2K 或 4K"
    )
    parser.add_argument(
        "--api-key", "-k",
        help="Gemini API 密钥（覆盖 GEMINI_API_KEY 环境变量）"
    )

    args = parser.parse_args()

    # 获取 API 密钥
    api_key = get_api_key(args.api_key)
    if not api_key:
        print("错误：未提供 API 密钥。", file=sys.stderr)
        print("请选择以下方式之一：", file=sys.stderr)
        print("  1. 使用 --api-key 参数提供密钥", file=sys.stderr)
        print("  2. 设置 GEMINI_API_KEY 环境变量", file=sys.stderr)
        sys.exit(1)

    # 在检查 API 密钥后再导入，避免出错时的慢导入
    from google import genai
    from google.genai import types
    from PIL import Image as PILImage

    # 初始化客户端
    client = genai.Client(api_key=api_key)

    # 设置输出路径
    output_path = Path(args.filename)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 加载输入图像（如果提供，Nano Banana Pro 最多支持 14 张）
    input_images = []
    output_resolution = args.resolution
    if args.input_images:
        if len(args.input_images) > 14:
            print(f"错误：输入图像过多（{len(args.input_images)} 张），最多支持 14 张。", file=sys.stderr)
            sys.exit(1)

        max_input_dim = 0
        for img_path in args.input_images:
            try:
                img = PILImage.open(img_path)
                input_images.append(img)
                print(f"已加载输入图像：{img_path}")

                # 记录最大尺寸用于自动分辨率检测
                width, height = img.size
                max_input_dim = max(max_input_dim, width, height)
            except Exception as e:
                print(f"加载输入图像 '{img_path}' 时出错：{e}", file=sys.stderr)
                sys.exit(1)

        # 如果未明确指定分辨率，则根据最大输入尺寸自动检测
        if args.resolution == "1K" and max_input_dim > 0:  # 默认值
            if max_input_dim >= 3000:
                output_resolution = "4K"
            elif max_input_dim >= 1500:
                output_resolution = "2K"
            else:
                output_resolution = "1K"
            print(f"自动检测分辨率：{output_resolution}（根据最大输入尺寸 {max_input_dim}）")

    # 构建请求内容（编辑时图像在前，纯生成时只有提示词）
    if input_images:
        contents = [*input_images, args.prompt]
        img_count = len(input_images)
        print(f"正在处理 {img_count} 张图像，输出分辨率 {output_resolution}...")
    else:
        contents = args.prompt
        print(f"正在生成图像，输出分辨率 {output_resolution}...")

    try:
        response = client.models.generate_content(
            model="gemini-3-pro-image-preview",
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
                image_config=types.ImageConfig(
                    image_size=output_resolution
                )
            )
        )

        # 处理响应并转换为 PNG
        image_saved = False
        for part in response.parts:
            if part.text is not None:
                print(f"模型响应：{part.text}")
            elif part.inline_data is not None:
                # 将内联数据转换为 PIL 图像并保存为 PNG
                from io import BytesIO

                # inline_data.data 已经是字节数据，不是 base64
                image_data = part.inline_data.data
                if isinstance(image_data, str):
                    # 如果是字符串，可能是 base64 编码
                    import base64
                    image_data = base64.b64decode(image_data)

                image = PILImage.open(BytesIO(image_data))

                # 确保 PNG 使用 RGB 模式（如需要，将 RGBA 转换为带白色背景的 RGB）
                if image.mode == 'RGBA':
                    rgb_image = PILImage.new('RGB', image.size, (255, 255, 255))
                    rgb_image.paste(image, mask=image.split()[3])
                    rgb_image.save(str(output_path), 'PNG')
                elif image.mode == 'RGB':
                    image.save(str(output_path), 'PNG')
                else:
                    image.convert('RGB').save(str(output_path), 'PNG')
                image_saved = True

        if image_saved:
            full_path = output_path.resolve()
            print(f"\n图像已保存：{full_path}")
            # Moltbot 解析 MEDIA 标记并在支持的平台上自动附加文件
            print(f"MEDIA: {full_path}")
        else:
            print("错误：响应中未生成图像。", file=sys.stderr)
            sys.exit(1)

    except Exception as e:
        print(f"生成图像时出错：{e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

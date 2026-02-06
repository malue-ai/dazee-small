"""
Nano Banana Pro 图像生成/编辑工具

使用 Google Gemini 3 Pro Image API 生成或编辑图像，并上传到 S3。

功能：
1. 纯文本生成图像 - 根据提示词生成新图像
2. 图像编辑 - 基于现有图像进行编辑/修改
3. 多图合成 - 最多支持 14 张图像的合成
4. 自动上传 S3 - 生成后自动上传并返回访问链接

依赖：
- google-genai>=1.0.0
- pillow>=10.0.0
- boto3（通过 S3Uploader）
"""

import asyncio
import io
import os
import tempfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles
import httpx

from core.tool.types import BaseTool, ToolContext
from logger import get_logger
from utils.s3_uploader import S3UploadError, get_s3_uploader

logger = get_logger(__name__)

# 支持的分辨率
SUPPORTED_RESOLUTIONS = ["1K", "2K", "4K"]

# 最大输入图像数量
MAX_INPUT_IMAGES = 14


class NanoBananaImageTool(BaseTool):
    """
    Nano Banana Pro 图像生成/编辑工具

    使用 Gemini 3 Pro Image 生成或编辑图像，并上传到 S3。

    input_schema 定义在 config/capabilities.yaml 中（nano_banana_image）。
    """

    name = "nano_banana_image"
    description = "使用 AI 生成或编辑图像。支持纯文本生成、单图编辑、多图合成（最多14张）。生成后自动上传到云存储。"

    # 工具的 JSON Schema（可在 capabilities.yaml 中定义更详细的版本）
    input_schema = {
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "图像生成/编辑的提示词描述"},
            "input_images": {
                "type": "array",
                "items": {"type": "string"},
                "description": "输入图像的 URL 或本地路径列表（可选，用于编辑/合成）",
            },
            "resolution": {
                "type": "string",
                "enum": ["1K", "2K", "4K"],
                "description": "输出分辨率，默认 1K",
            },
            "filename": {"type": "string", "description": "输出文件名（可选，默认自动生成）"},
        },
        "required": ["prompt"],
    }

    def __init__(self):
        """初始化工具"""
        self.api_key = os.getenv("GEMINI_API_KEY")
        self._client = None
        self._s3_uploader = None

    def _get_client(self):
        """
        延迟初始化 Gemini 客户端

        Returns:
            genai.Client 实例
        """
        if self._client is None:
            if not self.api_key:
                raise ValueError("未配置 GEMINI_API_KEY 环境变量")

            from google import genai

            self._client = genai.Client(api_key=self.api_key)

        return self._client

    async def _get_s3_uploader(self):
        """
        获取 S3 上传器（延迟初始化）

        Returns:
            S3Uploader 实例
        """
        if self._s3_uploader is None:
            self._s3_uploader = get_s3_uploader()
            await self._s3_uploader.initialize()
        return self._s3_uploader

    async def execute_stream(self, params: Dict[str, Any], context: ToolContext):
        """
        流式执行图像生成/编辑

        Args:
            params: 工具参数
            context: 工具执行上下文

        Yields:
            JSON 字符串片段
        """
        import json

        # 提取参数
        prompt = params.get("prompt", "").strip()
        input_images = params.get("input_images", [])
        resolution = params.get("resolution", "1K")
        filename = params.get("filename")

        # 参数验证
        if not prompt:
            yield json.dumps({"success": False, "error": "缺少必需参数: prompt"})
            return

        # 兼容性处理：如果 input_images 是字符串，转换为列表
        if isinstance(input_images, str):
            input_images = [input_images]

        if resolution not in SUPPORTED_RESOLUTIONS:
            yield json.dumps(
                {
                    "success": False,
                    "error": f"不支持的分辨率: {resolution}，支持: {', '.join(SUPPORTED_RESOLUTIONS)}",
                }
            )
            return

        if input_images and len(input_images) > MAX_INPUT_IMAGES:
            yield json.dumps(
                {
                    "success": False,
                    "error": f"输入图像过多（{len(input_images)} 张），最多支持 {MAX_INPUT_IMAGES} 张",
                }
            )
            return

        # 检查 API 密钥
        if not self.api_key:
            yield json.dumps({"success": False, "error": "未配置 GEMINI_API_KEY 环境变量"})
            return

        try:
            # 生成输出文件名
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"nano_banana_{timestamp}.png"
            elif not filename.lower().endswith(".png"):
                filename = f"{filename}.png"

            logger.info(
                f"🍌 开始图像生成: prompt='{prompt[:50]}...', "
                f"input_images={len(input_images)}, resolution={resolution}"
            )

            # 1. 加载输入图像（如果有）
            loaded_images, actual_resolution = await self._load_input_images(
                input_images, resolution
            )

            # 2. 调用 Gemini API 生成图像
            image_bytes, model_response = await self._generate_image(
                prompt=prompt, input_images=loaded_images, resolution=actual_resolution
            )

            # 3. 上传到 S3
            upload_result = await self._upload_to_s3(
                image_bytes=image_bytes,
                filename=filename,
                user_id=context.user_id,
                conversation_id=context.conversation_id,
            )

            logger.info(f"✅ 图像生成并上传成功: {upload_result.get('s3_key')}")

            # 直接返回链接，不返回 base64
            result = {
                "success": True,
                "s3_url": upload_result.get("s3_url"),
                "presigned_url": upload_result.get("presigned_url"),
                "s3_key": upload_result.get("s3_key"),
                "file_size": upload_result.get("file_size"),
                "resolution": actual_resolution,
                "model_response": model_response,
                "filename": filename,
            }

            yield json.dumps(result, ensure_ascii=False)

        except ValueError as e:
            logger.error(f"❌ 参数错误: {str(e)}")
            yield json.dumps({"success": False, "error": str(e)})

        except S3UploadError as e:
            logger.error(f"❌ S3 上传失败: {str(e)}", exc_info=True)
            yield json.dumps({"success": False, "error": f"S3 上传失败: {str(e)}"})

        except Exception as e:
            logger.error(f"❌ 图像生成失败: {str(e)}", exc_info=True)
            yield json.dumps({"success": False, "error": f"图像生成失败: {str(e)}"})

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        """
        执行图像生成/编辑（非流式回退）
        """
        # 复用 execute_stream，收集所有 chunk 拼接成完整 JSON
        full_json = ""
        async for chunk in self.execute_stream(params, context):
            full_json += chunk

        import json

        try:
            return json.loads(full_json)
        except json.JSONDecodeError:
            return {"success": False, "error": "内部错误: 无法解析生成的 JSON"}

    async def _load_input_images(
        self, image_sources: List[str], requested_resolution: str
    ) -> tuple[list, str]:
        """
        加载输入图像

        Args:
            image_sources: 图像源列表（URL 或本地路径）
            requested_resolution: 请求的输出分辨率

        Returns:
            (PIL.Image 列表, 实际分辨率)
        """
        if not image_sources:
            return [], requested_resolution

        from PIL import Image as PILImage

        loaded_images = []
        max_input_dim = 0

        for source in image_sources:
            try:
                image_bytes = await self._fetch_image(source)
                img = PILImage.open(BytesIO(image_bytes))
                loaded_images.append(img)

                # 记录最大尺寸
                width, height = img.size
                max_input_dim = max(max_input_dim, width, height)

                logger.debug(f"已加载图像: {source}, 尺寸: {width}x{height}")

            except Exception as e:
                logger.warning(f"加载图像失败: {source}, 错误: {str(e)}")
                raise ValueError(f"无法加载图像 '{source}': {str(e)}")

        # 根据输入图像自动检测最佳分辨率（仅当使用默认分辨率时）
        actual_resolution = requested_resolution
        if requested_resolution == "1K" and max_input_dim > 0:
            if max_input_dim >= 3000:
                actual_resolution = "4K"
            elif max_input_dim >= 1500:
                actual_resolution = "2K"

            if actual_resolution != requested_resolution:
                logger.info(
                    f"自动调整分辨率: {requested_resolution} → {actual_resolution} "
                    f"（根据最大输入尺寸 {max_input_dim}）"
                )

        return loaded_images, actual_resolution

    async def _fetch_image(self, source: str) -> bytes:
        """
        获取图像字节数据

        Args:
            source: 图像来源（URL 或本地路径）

        Returns:
            图像字节数据
        """
        # 判断是 URL 还是本地路径
        if source.startswith(("http://", "https://")):
            # 从 URL 下载
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(source)
                response.raise_for_status()
                return response.content
        else:
            # 读取本地文件
            async with aiofiles.open(source, "rb") as f:
                return await f.read()

    async def _generate_image(
        self, prompt: str, input_images: list, resolution: str
    ) -> tuple[Optional[bytes], str]:
        """
        调用 Gemini API 生成图像

        Args:
            prompt: 提示词
            input_images: PIL.Image 列表
            resolution: 输出分辨率

        Returns:
            (图像字节数据, 模型文本响应)
        """
        from google import genai
        from google.genai import types
        from PIL import Image as PILImage

        client = self._get_client()

        # 构建请求内容
        if input_images:
            contents = [*input_images, prompt]
            logger.info(f"正在处理 {len(input_images)} 张图像，输出分辨率 {resolution}...")
        else:
            contents = prompt
            logger.info(f"正在生成图像，输出分辨率 {resolution}...")

        # 调用 API（在线程池中执行同步调用）
        def _call_api():
            return client.models.generate_content(
                model="gemini-3-pro-image-preview",
                contents=contents,
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                    image_config=types.ImageConfig(image_size=resolution),
                ),
            )

        # 使用线程池执行同步 API 调用
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, _call_api)

        # 处理响应
        image_bytes = None
        model_response = ""

        for part in response.parts:
            if part.text is not None:
                model_response = part.text
                logger.info(f"模型响应: {part.text}")

            elif part.inline_data is not None:
                # 获取图像数据
                image_data = part.inline_data.data
                if isinstance(image_data, str):
                    import base64

                    image_data = base64.b64decode(image_data)

                # 转换为 PNG 格式
                image = PILImage.open(BytesIO(image_data))

                # 确保使用 RGB 模式
                output_buffer = BytesIO()
                if image.mode == "RGBA":
                    rgb_image = PILImage.new("RGB", image.size, (255, 255, 255))
                    rgb_image.paste(image, mask=image.split()[3])
                    rgb_image.save(output_buffer, "PNG")
                elif image.mode == "RGB":
                    image.save(output_buffer, "PNG")
                else:
                    image.convert("RGB").save(output_buffer, "PNG")

                image_bytes = output_buffer.getvalue()

        return image_bytes, model_response

    async def _upload_to_s3(
        self, image_bytes: bytes, filename: str, user_id: str, conversation_id: str
    ) -> Dict[str, Any]:
        """
        上传图像到 S3

        Args:
            image_bytes: 图像字节数据
            filename: 文件名
            user_id: 用户 ID
            conversation_id: 对话 ID

        Returns:
            上传结果字典
        """
        # 创建临时文件
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
            tmp_file.write(image_bytes)
            tmp_path = tmp_file.name

        try:
            # 获取 S3 上传器
            uploader = await self._get_s3_uploader()

            # 上传到 S3
            result = await uploader.upload_file(
                file_path=tmp_path,
                category="generated_images",
                user_id=user_id,
                conversation_id=conversation_id,
                filename=filename,
                metadata={"generator": "nano_banana_pro", "content_type": "image/png"},
            )

            return result

        finally:
            # 清理临时文件
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


# 便捷工厂函数
def create_nano_banana_image_tool() -> NanoBananaImageTool:
    """创建 Nano Banana Image 工具实例"""
    return NanoBananaImageTool()

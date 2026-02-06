"""
SlideSpeak工具 - 高质量PPT渲染

这是一个普通工具，注册到工具注册表中。
用于调用SlideSpeak API渲染PPT。

配置说明：
- input_schema 在 config/capabilities.yaml 中定义
- 运营可直接修改 YAML 调整参数，无需改代码
"""

import asyncio
import os
from typing import Any, Dict, Optional

import aiohttp

from core.tool.types import BaseTool, ToolContext
from logger import get_logger

logger = get_logger("slidespeak_tool")


class SlideSpeakTool(BaseTool):
    """
    SlideSpeak PPT渲染工具（input_schema 由 capabilities.yaml 定义）

    使用SlideSpeak API生成高质量PPT
    """

    name = "slidespeak"

    def __init__(self, api_key: Optional[str] = None):
        """
        初始化SlideSpeak工具

        Args:
            api_key: SlideSpeak API密钥，如果为None则从环境变量读取
        """
        self.api_key = api_key or os.getenv("SLIDESPEAK_API_KEY")
        if not self.api_key:
            raise ValueError(
                "SlideSpeak API key is required. Set SLIDESPEAK_API_KEY environment variable."
            )

        self.base_url = "https://api.slidespeak.co/api/v1"
        self.timeout = 300  # 5分钟超时

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        """
        执行PPT渲染

        Args:
            params: 工具输入参数
                - config: SlideSpeak 配置
                - upload_to_s3: 是否上传到 S3（默认 False）
            context: 工具执行上下文

        Returns:
            {
                "success": True/False,
                "download_url": "https://...",
                "s3_key": "...",
                "slides_count": 10,
                "error": "错误信息（如果失败）"
            }
        """
        # 从 params 提取参数
        config = params.get("config")
        if not config:
            return {"success": False, "error": "缺少必需参数: config"}

        upload_to_s3 = params.get("upload_to_s3", False)

        # 从 context 获取上下文
        conversation_id = context.conversation_id
        user_id = context.user_id
        try:
            # 1. 创建PPT生成任务
            task_id = await self._create_presentation(config)

            # 2. 等待任务完成
            result = await self._wait_for_completion(task_id)

            if not result:
                return {"success": False, "error": "任务超时或失败"}

            # 3. 获取下载链接
            download_url = result.get("url")
            if not download_url:
                return {"success": False, "error": "未获取到下载链接"}

            response_data = {
                "success": True,
                "download_url": download_url,
                "slides_count": len(config.get("slides", [])),
                "presentation_id": result.get("presentation_id"),
            }

            # 4. 如果需要持久化，上传到 S3
            if upload_to_s3:
                try:
                    s3_result = await self._upload_to_s3(
                        download_url=download_url, conversation_id=conversation_id, user_id=user_id
                    )
                    response_data["s3_key"] = s3_result.get("s3_key")
                    response_data["download_url"] = s3_result.get(
                        "presigned_url"
                    )  # 使用 S3 预签名 URL
                    logger.info(f"✅ PPT 已上传到 S3: {s3_result.get('s3_key')}")
                except Exception as e:
                    logger.warning(f"⚠️ S3 上传失败，返回原始 URL: {e}")
                    # S3 上传失败不影响整体结果，继续返回 SlideSpeak URL

            return response_data

        except Exception as e:
            logger.error(f"❌ PPT 渲染失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _upload_to_s3(
        self,
        download_url: str,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        从 SlideSpeak 下载 PPT 并上传到 S3

        Args:
            download_url: SlideSpeak 下载链接
            conversation_id: 对话ID
            user_id: 用户ID

        Returns:
            S3 上传结果
        """
        import time

        from utils.s3_uploader import get_s3_uploader

        # 1. 下载 PPT 内容到内存
        async with aiohttp.ClientSession() as session:
            async with session.get(
                download_url, timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                if response.status != 200:
                    raise Exception(f"下载失败: HTTP {response.status}")
                ppt_content = await response.read()

        # 2. 生成 S3 对象名
        timestamp = int(time.time())
        filename = f"ppt_{timestamp}.pptx"
        s3_key = f"outputs/ppt/{conversation_id or 'default'}/{filename}"

        # 3. 上传到 S3
        s3_uploader = get_s3_uploader()
        result = await s3_uploader.upload_bytes(
            file_content=ppt_content,
            object_name=s3_key,
            content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            metadata={
                "conversation_id": conversation_id or "unknown",
                "user_id": user_id or "unknown",
                "source": "slidespeak",
            },
        )

        # 4. 生成预签名 URL
        presigned_url = await s3_uploader.get_presigned_url(s3_key, expires_in=86400)  # 24小时

        return {"s3_key": s3_key, "presigned_url": presigned_url, "size": result.get("size")}

    def _normalize_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        规范化配置格式以符合SlideSpeak API要求

        参考: https://docs.slidespeak.co/basics/api-references/slide-by-slide/

        转换规则：
        - content: list → string（用空格连接，保持一段话）
        - template: 转为大写（如 default → DEFAULT）
        - language: 转为API支持的格式（zh-CN → CHINESE）
        """
        import copy

        normalized = copy.deepcopy(config)

        # 1. 规范化template（转大写）
        if "template" in normalized:
            normalized["template"] = str(normalized["template"]).upper()

        # 2. 规范化language（默认ORIGINAL，让API自动从内容推断）
        if "language" not in normalized or not normalized["language"]:
            normalized["language"] = "ORIGINAL"
        else:
            # 转为API支持的格式
            language_map = {
                "zh-cn": "CHINESE",
                "zh": "CHINESE",
                "chinese": "CHINESE",
                "en": "ENGLISH",
                "en-us": "ENGLISH",
                "english": "ENGLISH",
                "original": "ORIGINAL",
            }
            lang = str(normalized["language"]).lower()
            normalized["language"] = language_map.get(lang, "ORIGINAL")

        # 3. 规范化slides
        if "slides" in normalized:
            for slide in normalized["slides"]:
                # content: list → string
                content = slide.get("content")
                if isinstance(content, list):
                    # 用空格连接，形成一段话
                    slide["content"] = " ".join(str(item) for item in content)

                # layout: 转大写
                if "layout" in slide:
                    slide["layout"] = str(slide["layout"]).upper()

        return normalized

    async def _create_presentation(self, config: Dict[str, Any]) -> str:
        """创建PPT生成任务，返回task_id"""
        url = f"{self.base_url}/presentation/generate/slide-by-slide"

        # 格式转换：SlideSpeak API要求content为string，不是list
        normalized_config = self._normalize_config(config)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                headers={"Content-Type": "application/json", "X-API-Key": self.api_key},
                json=normalized_config,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"SlideSpeak API错误: {response.status} - {error_text}")

                data = await response.json()
                task_id = data.get("task_id")

                if not task_id:
                    raise Exception(f"未获取到task_id: {data}")

                return task_id

    async def _wait_for_completion(self, task_id: str) -> Optional[Dict[str, Any]]:
        """等待任务完成，返回结果"""
        # 修复：使用正确的API端点 /task_status/
        url = f"{self.base_url}/task_status/{task_id}"
        max_attempts = 60  # 最多等待5分钟（每5秒轮询一次）

        print(f"🔄 开始轮询任务状态 (task_id: {task_id[:16]}...)")

        async with aiohttp.ClientSession() as session:
            for attempt in range(max_attempts):
                try:
                    async with session.get(
                        url,
                        headers={"X-API-Key": self.api_key},
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as response:
                        if response.status != 200:
                            print(
                                f"   [{attempt+1}/{max_attempts}] ⏳ 等待中... (HTTP {response.status})"
                            )
                            await asyncio.sleep(5)
                            continue

                        data = await response.json()
                        status = data.get("task_status")

                        print(f"   [{attempt+1}/{max_attempts}] 状态: {status}")

                        if status == "SUCCESS":
                            print(f"   ✅ 任务完成！")
                            result = data.get("task_result") or data.get("task_info")

                            # 兼容新旧API：如果没有url，使用request_id获取
                            if result and not result.get("url") and result.get("request_id"):
                                print(f"   📥 使用request_id获取下载链接...")
                                download_url = await self._get_download_url(result["request_id"])
                                result["url"] = download_url

                            return result
                        elif status == "FAILURE":
                            error = data.get("task_result", "未知错误")
                            raise Exception(f"SlideSpeak任务失败: {error}")
                        elif status in ["PENDING", "PROCESSING", "SENT"]:
                            # 正常处理中
                            pass

                except Exception as e:
                    print(f"   [{attempt+1}/{max_attempts}] ⚠️ 查询异常: {e}")

                # 等待5秒后重试
                await asyncio.sleep(5)

        # 超时
        print(f"   ❌ 任务超时（已等待{max_attempts * 5}秒）")
        return None

    async def _get_download_url(self, request_id: str) -> str:
        """使用request_id获取短期下载链接（新API）"""
        url = f"{self.base_url}/presentation/download/{request_id}"

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers={"X-API-Key": self.api_key}, timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"获取下载链接失败: {response.status} - {error_text}")

                data = await response.json()
                download_url = data.get("url")

                if not download_url:
                    raise Exception(f"响应中未找到下载链接: {data}")

                return download_url

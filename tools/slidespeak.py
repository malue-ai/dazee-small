"""
SlideSpeak工具 - 高质量PPT渲染

这是一个普通工具，注册到工具注册表中。
用于调用SlideSpeak API渲染PPT。
"""

import os
import aiohttp
import asyncio
from typing import Dict, Any, Optional
from pathlib import Path
# from tools.base import BaseTool


class SlideSpeakTool:
    """
    SlideSpeak PPT渲染工具
    
    使用SlideSpeak API生成高质量PPT
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        初始化SlideSpeak工具
        
        Args:
            api_key: SlideSpeak API密钥，如果为None则从环境变量读取
        """
        self.api_key = api_key or os.getenv("SLIDESPEAK_API_KEY")
        if not self.api_key:
            raise ValueError("SlideSpeak API key is required. Set SLIDESPEAK_API_KEY environment variable.")
        
        self.base_url = "https://api.slidespeak.co/api/v1"
        self.timeout = 300  # 5分钟超时
    
    @property
    def name(self) -> str:
        return "slidespeak_render"
    
    @property
    def description(self) -> str:
        return """使用SlideSpeak API渲染高质量PPT。

支持：
- 复杂布局（ITEMS, COMPARISON, TIMELINE, BIG_NUMBER, CHART, TABLE, SWOT等）
- 自动图片获取
- 专业模板应用
- 高质量渲染

输入：SlideSpeak配置（包含slides数组）
输出：PPT文件下载链接和本地保存路径"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        """
        工具参数定义（符合 SlideSpeak API 官方规范）
        参考：https://docs.slidespeak.co/basics/api-references/slide-by-slide/
        """
        return {
            "type": "object",
            "properties": {
                "config": {
                    "type": "object",
                    "description": "完整的SlideSpeak配置。参考：https://docs.slidespeak.co/basics/api-references/slide-by-slide/",
                    "properties": {
                        "template": {
                            "type": "string",
                            "description": "模板名称，如'DEFAULT'"
                        },
                        "language": {
                            "type": "string",
                            "description": "语言代码，如'CHINESE'或'ENGLISH'。默认：'ORIGINAL'"
                        },
                        "fetch_images": {
                            "type": "boolean",
                            "description": "是否包含库存图片。默认：true"
                        },
                        "verbosity": {
                            "type": "string",
                            "enum": ["concise", "standard", "text-heavy"],
                            "description": "文本详细程度。默认：'standard'"
                        },
                        "include_cover": {
                            "type": "boolean",
                            "description": "是否包含封面。默认：true"
                        },
                        "include_table_of_contents": {
                            "type": "boolean",
                            "description": "是否包含目录。默认：true"
                        },
                        "slides": {
                            "type": "array",
                            "description": "幻灯片配置数组，每个slide必须包含layout、title、item_amount和content",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {
                                        "type": "string",
                                        "description": "幻灯片标题（简洁，8-15字）"
                                    },
                                    "layout": {
                                        "type": "string",
                                        "enum": ["ITEMS", "BIG_NUMBER", "COMPARISON", "TIMELINE", "TABLE", "CHART", "SWOT", "PESTEL", "THANKS"],
                                        "description": "布局类型：ITEMS(列表3-6项)|BIG_NUMBER(指标1-4项)|COMPARISON(对比2项)|TIMELINE(时间线3-6项)|TABLE(表格0项)|CHART(图表)|SWOT(4项)|PESTEL(6项)|THANKS(0项)"
                                    },
                                    "item_amount": {
                                        "type": "integer",
                                        "description": "项目数量。严格遵守：ITEMS(3-6)|BIG_NUMBER(1-4)|COMPARISON(2)|TIMELINE(3-6)|SWOT(4)|PESTEL(6)|TABLE/THANKS(0)"
                                    },
                                    "content": {
                                        "type": "string",
                                        "description": "幻灯片内容。格式：每个要点用句号分隔，每项1-2句话，保持简洁"
                                    },
                                    "images": {
                                        "type": "array",
                                        "description": "可选：图片配置（目前仅支持单图）",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "type": {
                                                    "type": "string",
                                                    "enum": ["stock", "url", "ai"],
                                                    "description": "图片来源"
                                                },
                                                "data": {
                                                    "type": "string",
                                                    "description": "stock=英文关键词|url=链接|ai=提示"
                                                }
                                            },
                                            "required": ["type", "data"]
                                        }
                                    },
                                    "chart": {
                                        "type": "object",
                                        "description": "可选：图表配置（仅CHART布局）"
                                    },
                                    "table": {
                                        "type": "array",
                                        "description": "可选：表格数据（仅TABLE布局，二维数组，第一行为表头）",
                                        "items": {
                                            "type": "array",
                                            "items": {"type": "string"}
                                        }
                                    }
                                },
                                "required": ["title", "layout", "item_amount", "content"]
                            }
                        }
                    },
                    "required": ["template", "slides"]
                },
                "save_dir": {
                    "type": "string",
                    "description": "保存PPT文件的目录路径（可选，默认./workspace/outputs/ppt）"
                }
            },
            "required": ["config"]
        }
    
    async def execute(self, config: Dict[str, Any], save_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        执行PPT渲染
        
        Args:
            config: SlideSpeak配置
            save_dir: 保存目录
            
        Returns:
            {
                "success": True/False,
                "download_url": "https://...",
                "local_path": "/path/to/file.pptx",
                "slides_count": 10,
                "error": "错误信息（如果失败）"
            }
        """
        try:
            # 1. 创建PPT生成任务
            task_id = await self._create_presentation(config)
            
            # 2. 等待任务完成
            result = await self._wait_for_completion(task_id)
            
            if not result:
                return {
                    "success": False,
                    "error": "任务超时或失败"
                }
            
            # 3. 下载PPT文件
            download_url = result.get("url")
            if not download_url:
                return {
                    "success": False,
                    "error": "未获取到下载链接"
                }
            
            local_path = await self._download_file(
                download_url,
                save_dir or "./workspace/outputs/ppt"
            )
            
            return {
                "success": True,
                "download_url": download_url,
                "local_path": local_path,
                "slides_count": len(config.get("slides", [])),
                "presentation_id": result.get("presentation_id")
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
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
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": self.api_key
                },
                json=normalized_config,
                timeout=aiohttp.ClientTimeout(total=30)
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
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as response:
                        if response.status != 200:
                            print(f"   [{attempt+1}/{max_attempts}] ⏳ 等待中... (HTTP {response.status})")
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
                url,
                headers={"X-API-Key": self.api_key},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"获取下载链接失败: {response.status} - {error_text}")
                
                data = await response.json()
                download_url = data.get("url")
                
                if not download_url:
                    raise Exception(f"响应中未找到下载链接: {data}")
                
                return download_url
    
    async def _download_file(self, url: str, save_dir: str) -> str:
        """下载PPT文件到本地"""
        save_path = Path(save_dir)
        save_path.mkdir(parents=True, exist_ok=True)
        
        # 生成文件名
        import time
        filename = f"ppt_{int(time.time())}.pptx"
        file_path = save_path / filename
        
        # 下载文件
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as response:
                if response.status != 200:
                    raise Exception(f"下载失败: {response.status}")
                
                with open(file_path, "wb") as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)
        
        return str(file_path.absolute())


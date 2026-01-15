"""
Partition API文档解析工具

功能说明：
- 本工具通过Unstructured Partition API解析各种格式的文档（PDF、Word、PPT等）
- 支持通过URL或本地文件路径获取文档
- 自动选择最佳解析策略，也可手动指定
- 提供文档内容的结构化输出，便于大模型处理
"""

import logging
import os
import tempfile
import time
import hashlib
import json
from typing import Dict, Any, Optional, List, Union
from pathlib import Path
import aiohttp
import asyncio
from dataclasses import dataclass, asdict
from tools.base import BaseTool

logger = logging.getLogger(__name__)


@dataclass
class PartitionConfig:
    """Partition API配置"""
    api_key: str
    api_url: str = "https://api.unstructuredapp.io/general/v0/general"
    timeout_download: int = 30
    timeout_api: int = 60
    max_retries: int = 3
    default_strategy: str = "auto"
    cache_enabled: bool = False
    cache_dir: str = "./cache/partition"


class DocumentPartitionTool(BaseTool):
    """
    Partition API文档解析工具
    
    功能特性：
    - 仅支持URL输入（不支持本地文件）
    - 智能选择解析策略（fast/auto/hi_res）
    - 自动下载URL文件并缓存
    - 支持批量处理
    - 提供详细的结构化文档信息
    
    使用场景：
    - 需要从网络文档中提取结构化信息供大模型分析
    - 处理用户提供的文档URL（PDF、Word、PPT等）
    - 批量解析在线文档库中的文件
    - 将网络文档内容转为结构化数据
    """
    
    def __init__(self, **kwargs):
        """
        初始化文档解析工具
        
        依赖注入：
        - config: PartitionConfig配置对象
        - event_manager: 事件管理器（可选）
        - memory: WorkingMemory实例（可选）
        - workspace_dir: 工作目录（可选）
        """
        super().__init__()
        
        # 优先级：传入的 config > 环境变量 > 默认值
        if "config" in kwargs and kwargs["config"]:
            self.config = kwargs["config"]
        else:
            # 从环境变量构建配置
            api_key = os.getenv("UNSTRUCTURED_API_KEY", "")
            if not api_key:
                logger.warning("未配置 UNSTRUCTURED_API_KEY，工具将无法使用")
            
            self.config = PartitionConfig(
                api_key=api_key,
                api_url=os.getenv("UNSTRUCTURED_API_URL", "https://api.unstructuredapp.io/general/v0/general"),
                cache_enabled=os.getenv("PARTITION_CACHE_ENABLED", "false").lower() == "true",
                cache_dir=os.getenv("PARTITION_CACHE_DIR", "./cache/partition")
            )
        
        # 🆕 标记工具是否可用
        self.is_available = bool(self.config.api_key)
        
        self.event_manager = kwargs.get("event_manager")
        self.memory = kwargs.get("memory")
        self.workspace_dir = kwargs.get("workspace_dir")
        
        # 初始化缓存目录
        if self.config.cache_enabled:
            Path(self.config.cache_dir).mkdir(parents=True, exist_ok=True)
        
        # 创建会话
        self.session = None
    
    @property
    def name(self) -> str:
        """工具名称（唯一标识）"""
        return "document_partition_tool"
    
    @property
    def description(self) -> str:
        """
        工具描述（给LLM看的，详细说明何时使用）
        """
        return """Partition API文档解析工具 - 将各种格式的网络文档转为结构化数据（支持分段解析）

⚠️ 重要提示：mode 参数决定了返回的内容范围
- overview: 仅返回前3页的概要（用于快速了解文档结构）
- pages: 返回指定页面的完整内容（需配合 pages 参数）
- full: 返回全部内容（仅限小文档<10页）

如果用户要求"解析文档"、"读取文档"、"分析文档内容"等，通常需要使用 mode='full' 或 mode='pages'，而不是 overview！

核心功能：
1. 🆕 **分段解析**：支持三种模式，优化大文档处理
   - overview: 快速概览（3-5秒，仅返回前3页摘要和目录）⚠️ 不是完整内容
   - pages: 按需加载（解析指定页面，如 pages="1-10" 或 pages="8,12-15"）
   - full: 完整解析（返回全部内容，仅限小文档 <10页）
2. 解析多种格式：PDF、Word(.docx)、PowerPoint(.pptx)、Excel(.xlsx)、文本(.txt)等
3. 智能解析策略：auto（自动选择）、fast（快速）、hi_res（高精度含表格）
4. 仅支持URL输入（不支持本地文件路径）
5. 自动缓存结果（节省API调用成本）

使用决策树（请严格遵循）：
1. 用户要求"解析/分析/读取文档内容" → 优先使用 mode='full'
2. 如果文档>10页 → 先用 mode='overview' 查看结构，然后用 mode='pages' 读取关键章节
3. 用户明确指定"看看目录"、"文档概要" → 使用 mode='overview'
4. 用户要求"读取第X章"、"分析某个部分" → 使用 mode='pages' + 指定页码

典型场景示例：
- 场景1：用户上传PDF并说"帮我分析这个文档"
  正确做法：mode='full'（如果<10页）或 mode='overview' 然后 mode='pages'
  ❌ 错误做法：只调用 overview 就停止
  
- 场景2：用户说"这个论文讲了什么"
  正确做法：mode='full' 获取完整内容
  ❌ 错误做法：overview 返回摘要后就回答（信息不完整）
  
- 场景3：用户说"看看这个文档的目录"
  正确做法：mode='overview'

参数说明：
- source: 文档URL（必需）- HTTP/HTTPS 协议
- mode: 解析模式（⚠️ 关键参数，默认 'overview' 只返回概要）
  * 'overview': 概要模式，仅返回前3页的文档结构（不是完整内容！）
  * 'pages': 分页模式，返回指定页面的完整内容（需设置 pages 参数）
  * 'full': 完整模式，返回全部内容（<10页的文档推荐使用）
- pages: 页码范围（mode='pages'时必需），如 "5" 或 "1-10" 或 "1-5,8-10"
- strategy: 解析策略（可选，默认 'auto'）
  * 'auto': 自动选择最佳策略（推荐，处理时间约1-2分钟）
  * 'fast': 快速提取纯文本（速度快，约30-60秒）
  * 'hi_res': 高精度解析（含表格、图片，速度慢，约2-3分钟）⚠️ 需要更长等待时间
- use_cache: 是否使用缓存（可选，默认 True）

返回格式：
{
  "success": true/false,
  "mode": "overview/pages/full",
  "data": {...},  // 解析结果
  "metadata": {
    "total_pages": 20,
    "element_count": 370,
    "processing_time": 3.2
  },
  "warning": "...",  // overview模式会有警告提示
  "next_action": {...}  // 建议的下一步操作
}

性能参考（单页）：
- fast 策略：30-60秒
- auto 策略：1-2分钟
- hi_res 策略：2-3分钟（含 OCR 和表格识别）

注意：此工具仅接受URL输入，不支持本地文件路径
"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        """
        工具参数定义（JSON Schema格式）
        """
        return {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "文档URL（必需）：如 'https://example.com/doc.pdf'。仅支持HTTP/HTTPS协议的URL，不支持本地文件路径"
                },
                "mode": {
                    "type": "string",
                    "description": "⚠️ 解析模式（决定返回内容范围）：'overview'（仅返回前3页概要，不是完整内容！）、'pages'（返回指定页面完整内容，需配合pages参数）、'full'（返回全部内容，推荐用于文档解析任务）。用户要求'解析文档'时应使用'full'或'pages'，而不是'overview'",
                    "enum": ["overview", "pages", "full"],
                    "default": "overview"
                },
                "pages": {
                    "type": "string",
                    "description": "页码范围（mode='pages'时使用），支持格式：'5'（单页）、'1-10'（范围）、'1-5,8-10,15'（多段）",
                    "default": None
                },
                "strategy": {
                    "type": "string",
                    "description": "解析策略：'auto'（自动选择，约1-2分钟）、'fast'（快速提取纯文本，约30-60秒）、'hi_res'（高精度含表格，约2-3分钟）⚠️ hi_res 速度最慢但最准确",
                    "enum": ["auto", "fast", "hi_res"],
                    "default": "auto"
                },
                "use_cache": {
                    "type": "boolean",
                    "description": "是否使用缓存，重复解析相同文档时可加速",
                    "default": True
                },
                "output_format": {
                    "type": "string",
                    "description": "输出格式：'json'（结构化JSON）或 'text'（纯文本拼接）",
                    "enum": ["json", "text"],
                    "default": "json"
                }
            },
            "required": ["source"]  # 必需参数
        }
    
    async def execute(
        self,
        source: str,
        mode: str = "overview",
        pages: Optional[str] = None,
        strategy: str = "auto",
        use_cache: bool = True,
        output_format: str = "json",
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行文档解析（支持分段策略）
        
        Args:
            source: 文档URL（必须是HTTP/HTTPS协议）
            mode: 解析模式
                - overview: 概要模式（快速返回文档结构）
                - pages: 分页模式（解析指定页面）
                - full: 完整模式（解析全部内容，仅限小文档<10页）
            pages: 页码范围（mode='pages'时使用），如 "1-5" 或 "8,10,12-15"
            strategy: 解析策略（auto/fast/hi_res）
            use_cache: 是否使用缓存
            output_format: 输出格式（json/text）
            **kwargs: 框架自动注入的参数
                - user_id: 用户ID
                - conversation_id: 对话ID
                - session_id: 会话ID
        
        Returns:
            标准格式的返回字典
        """
        start_time = time.time()
        
        try:
            # 0. 检查工具是否可用
            if not self.is_available:
                return {
                    "success": False,
                    "error": "工具未配置：缺少 UNSTRUCTURED_API_KEY",
                    "message": "请在环境变量中配置 UNSTRUCTURED_API_KEY 后重试"
                }
            
            # 1. 记录日志
            logger.info(f"🔧 执行文档解析工具: source={source[:50]}..., mode={mode}, strategy={strategy}")
            
            # 2. 参数验证
            if not source:
                return {
                    "success": False,
                    "error": "source参数不能为空",
                    "message": "请提供文档URL"
                }
            
            # 验证必须是URL
            if not self._is_url(source):
                return {
                    "success": False,
                    "error": "source必须是有效的URL",
                    "message": "此工具仅支持URL输入（http:// 或 https://），不支持本地文件路径"
                }
            
            if mode not in ["overview", "pages", "full"]:
                return {
                    "success": False,
                    "error": f"无效的模式: {mode}",
                    "message": "模式必须是 overview、pages 或 full"
                }
            
            if mode == "pages" and not pages:
                return {
                    "success": False,
                    "error": "pages参数缺失",
                    "message": "mode='pages' 时必须指定 pages 参数"
                }
            
            if strategy not in ["auto", "fast", "hi_res"]:
                return {
                    "success": False,
                    "error": f"无效的策略: {strategy}",
                    "message": "策略必须是 auto、fast 或 hi_res"
                }
            
            # 3. 获取框架参数
            user_id = kwargs.get("user_id", "unknown")
            conversation_id = kwargs.get("conversation_id", "unknown")
            
            # 4. 检查缓存（基于 mode + pages + strategy）
            cache_key = None
            if use_cache and self.config.cache_enabled:
                cache_params = f"{source}_{mode}_{pages or 'none'}_{strategy}"
                cache_key = hashlib.md5(cache_params.encode()).hexdigest()
                cached_result = self._load_from_cache(cache_key)
                if cached_result:
                    logger.info(f"💾 使用缓存结果: {cache_key}")
                    if "metadata" not in cached_result:
                        cached_result["metadata"] = {}
                    cached_result["metadata"]["from_cache"] = True
                    cached_result["metadata"]["cache_key"] = cache_key
                    cached_result["metadata"]["processing_time"] = time.time() - start_time
                    cached_result["message"] = "从缓存返回结果（节省 API 调用）"
                    return cached_result
            
            # 5. 下载文档
            temp_file = await self._download_url_file(source)
            
            try:
                # 6. 快速获取文档信息（不调用 API）
                doc_info = await self._get_document_info(temp_file)
                
                # 7. 根据模式处理
                if mode == "overview":
                    # 概要模式
                    result = await self._process_overview(temp_file, doc_info, source, user_id)
                
                elif mode == "pages":
                    # 分页模式：解析指定页面
                    page_ranges = self._parse_page_ranges(pages, doc_info.get("total_pages"))
                    result = await self._process_pages(
                        temp_file, page_ranges, strategy, doc_info, source, user_id
                    )
                
                elif mode == "full":
                    # 完整模式
                    result = await self._process_full(
                        temp_file, strategy, doc_info, source, user_id
                    )
                
                # 8. 格式化输出（如果需要）
                if output_format == "text" and result.get("success") and "data" in result:
                    if "elements" in result["data"]:
                        result["data"] = self._format_as_text(result["data"])
                
                # 9. 添加处理时间
                if "metadata" in result:
                    result["metadata"]["processing_time"] = time.time() - start_time
                
                # 10. 保存到缓存
                if cache_key and self.config.cache_enabled and result.get("success"):
                    self._save_to_cache(cache_key, result)
                
                # 11. 发送事件
                if self.event_manager and result.get("success"):
                    await self._emit_processing_event(
                        user_id, conversation_id, source, result.get("metadata", {})
                    )
                
                return result
                
            finally:
                # 清理临时文件
                if temp_file and os.path.exists(temp_file):
                    try:
                        os.unlink(temp_file)
                        logger.debug(f"清理临时文件: {temp_file}")
                    except:
                        pass
            
        except ValueError as e:
            logger.error(f"参数验证失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "message": "参数验证失败"
            }
        except aiohttp.ClientError as e:
            logger.error(f"网络请求失败: {str(e)}")
            return {
                "success": False,
                "error": f"网络错误: {str(e)}",
                "message": "下载文档或调用API失败"
            }
        except Exception as e:
            logger.error(f"文档解析失败: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "message": "文档解析失败"
            }
    
    async def _process_document(
        self,
        source: str,
        strategy: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        核心文档处理逻辑
        
        步骤：
        1. 下载URL文件到临时目录
        2. 调用Partition API
        3. 解析返回结果
        4. 清理临时文件
        """
        logger.info(f"开始处理文档URL: {source}")
        
        # 临时文件路径
        temp_file = None
        
        try:
            # 下载URL文件
            logger.info(f"下载URL文件: {source}")
            temp_file = await self._download_url_file(source)
            
            # 获取文件信息
            file_size = os.path.getsize(temp_file)
            file_type = Path(temp_file).suffix.lower()
            logger.info(f"文件信息: 大小={file_size}字节, 类型={file_type}")
            
            # 调用Partition API
            logger.info(f"调用Partition API，策略: {strategy}")
            api_result = await self._call_partition_api(
                file_path=temp_file,
                strategy=strategy,
                user_id=user_id
            )
            
            # 构建结果
            return {
                "elements": api_result,
                "file_type": file_type,
                "file_size": file_size,
                "source_type": "url",
                "timestamp": time.time()
            }
            
        finally:
            # 清理临时文件
            if temp_file and os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                    logger.debug(f"清理临时文件: {temp_file}")
                except:
                    pass
    
    async def _download_url_file(self, url: str) -> str:
        """下载URL文件到临时文件"""
        temp_file = tempfile.NamedTemporaryFile(
            suffix=self._get_file_extension_from_url(url),
            delete=False
        )
        temp_path = temp_file.name
        temp_file.close()
        
        # 使用异步HTTP客户端下载
        for attempt in range(self.config.max_retries):
            try:
                timeout = aiohttp.ClientTimeout(total=self.config.timeout_download)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url) as response:
                        response.raise_for_status()
                        
                        # 流式写入文件
                        with open(temp_path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(8192):
                                f.write(chunk)
                        
                        logger.info(f"下载成功: {url} -> {temp_path}")
                        return temp_path
                        
            except Exception as e:
                if attempt == self.config.max_retries - 1:
                    raise
                logger.warning(f"下载失败，重试 {attempt + 1}/{self.config.max_retries}: {e}")
                await asyncio.sleep(2 ** attempt)  # 指数退避
    
    async def _call_partition_api(
        self,
        file_path: str,
        strategy: str,
        user_id: str,
        pages: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        调用Partition API
        
        Args:
            file_path: 文件路径
            strategy: 解析策略
            user_id: 用户ID
            pages: 页码范围（可选），如 "1-5"
        """
        for attempt in range(self.config.max_retries):
            try:
                # 准备文件
                file_name = os.path.basename(file_path)
                
                # 🆕 根据策略动态调整超时时间
                # hi_res 策略需要更长的处理时间（OCR + 表格识别）
                if strategy == "hi_res":
                    timeout_seconds = 180  # hi_res: 3分钟
                    logger.debug(f"   使用 hi_res 策略，超时时间: {timeout_seconds}秒")
                elif strategy == "auto":
                    timeout_seconds = 120  # auto: 2分钟
                else:  # fast
                    timeout_seconds = 60   # fast: 1分钟
                
                # 使用aiohttp发送multipart请求
                timeout = aiohttp.ClientTimeout(total=timeout_seconds)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    # 创建multipart表单数据
                    form_data = aiohttp.FormData()
                    form_data.add_field('strategy', strategy)
                    form_data.add_field('output_format', 'application/json')
                    
                    # 🆕 如果指定了页码范围，添加到表单
                    if pages:
                        form_data.add_field('starting_page_number', pages.split('-')[0])
                        if '-' in pages:
                            form_data.add_field('ending_page_number', pages.split('-')[1])
                        logger.debug(f"   指定页码范围: {pages}")
                    
                    with open(file_path, 'rb') as f:
                        form_data.add_field(
                            'files',
                            f.read(),
                            filename=file_name,
                            content_type=self._get_mime_type(file_path)
                        )
                    
                    # 发送请求
                    headers = {
                        "unstructured-api-key": self.config.api_key,
                        "accept": "application/json",
                        "User-Agent": f"DocumentPartitionTool/1.0 (user:{user_id})"
                    }
                    
                    async with session.post(
                        self.config.api_url,
                        data=form_data,
                        headers=headers
                    ) as response:
                        
                        if response.status == 200:
                            result = await response.json()
                            logger.info(f"API调用成功，返回{len(result)}个元素")
                            return result
                        elif response.status == 429:
                            wait_time = 10 * (attempt + 1)
                            logger.warning(f"速率限制，等待{wait_time}秒后重试")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            error_text = await response.text()
                            raise Exception(f"API错误 {response.status}: {error_text[:200]}")
                            
            except asyncio.TimeoutError:
                if attempt == self.config.max_retries - 1:
                    raise Exception(f"API调用超时（{timeout_seconds}秒，策略={strategy}）")
                logger.warning(f"超时，重试 {attempt + 1}/{self.config.max_retries}")
            except Exception as e:
                if attempt == self.config.max_retries - 1:
                    raise
                logger.warning(f"API调用失败，重试 {attempt + 1}/{self.config.max_retries}: {e}")
                await asyncio.sleep(2 ** attempt)
        
        raise Exception("API调用失败，达到最大重试次数")
    
    def _format_as_text(self, result: Dict[str, Any]) -> str:
        """将解析结果格式化为纯文本"""
        elements = result.get("elements", [])
        if not elements:
            return "文档内容为空"
        
        text_parts = []
        for elem in elements:
            elem_type = elem.get("type", "Unknown")
            elem_text = elem.get("text", "").strip()
            
            if elem_text:
                if elem_type in ["Title", "Header"]:
                    text_parts.append(f"\n# {elem_text}\n")
                elif elem_type == "Table":
                    text_parts.append(f"\n[表格开始]\n{elem_text}\n[表格结束]\n")
                else:
                    text_parts.append(elem_text + "\n")
        
        return "".join(text_parts)
    
    def _is_url(self, source: str) -> bool:
        """判断是否为URL"""
        return source.startswith(('http://', 'https://', 'ftp://'))
    
    def _get_file_extension_from_url(self, url: str) -> str:
        """从URL获取文件扩展名"""
        import re
        # 常见文档扩展名
        patterns = {
            r'\.pdf($|\?|#)': '.pdf',
            r'\.docx?($|\?|#)': '.docx',
            r'\.pptx?($|\?|#)': '.pptx',
            r'\.xlsx?($|\?|#)': '.xlsx',
            r'\.txt($|\?|#)': '.txt',
            r'\.html?($|\?|#)': '.html',
        }
        
        for pattern, ext in patterns.items():
            if re.search(pattern, url, re.IGNORECASE):
                return ext
        
        # 默认
        return '.tmp'
    
    def _get_mime_type(self, file_path: str) -> str:
        """根据文件扩展名获取MIME类型"""
        ext_map = {
            '.pdf': 'application/pdf',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.doc': 'application/msword',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            '.ppt': 'application/vnd.ms-powerpoint',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.xls': 'application/vnd.ms-excel',
            '.txt': 'text/plain',
            '.html': 'text/html',
            '.htm': 'text/html',
        }
        
        ext = Path(file_path).suffix.lower()
        return ext_map.get(ext, 'application/octet-stream')
    
    def _generate_cache_key(self, source: str, strategy: str) -> str:
        """生成缓存键"""
        content = f"{source}_{strategy}_{self.config.api_key[:8]}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def _load_from_cache(self, cache_key: str) -> Optional[Dict]:
        """从缓存加载"""
        if not self.config.cache_enabled:
            return None
        
        cache_file = Path(self.config.cache_dir) / f"{cache_key}.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 检查缓存是否过期（默认24小时）
                    cache_age = time.time() - data.get("metadata", {}).get("timestamp", 0)
                    if cache_age < 24 * 3600:
                        data["cached"] = True
                        return data
            except Exception as e:
                logger.warning(f"读取缓存失败: {e}")
        
        return None
    
    def _save_to_cache(self, cache_key: str, data: Dict):
        """保存到缓存"""
        if not self.config.cache_enabled:
            return
        
        cache_file = Path(self.config.cache_dir) / f"{cache_key}.json"
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存缓存失败: {e}")
    
    async def _emit_processing_event(
        self,
        user_id: str,
        conversation_id: str,
        source: str,
        metadata: Dict
    ):
        """发送处理完成事件"""
        if not self.event_manager:
            return
        
        event_data = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "tool": self.name,
            "source": source,
            "metadata": metadata,
            "timestamp": time.time()
        }
        
        try:
            await self.event_manager.emit(
                event_type="tool.document_parsed",
                data=event_data
            )
        except Exception as e:
            logger.warning(f"发送事件失败: {e}")
    
    # ============================================================
    # 🆕 分段解析策略相关方法
    # ============================================================
    
    async def _get_document_info(self, temp_file: str) -> Dict[str, Any]:
        """
        快速获取文档基本信息（不解析内容）
        
        使用 PyPDF2 快速读取 PDF 信息（< 1 秒）
        
        Args:
            temp_file: 临时文件路径
            
        Returns:
            文档信息字典
        """
        try:
            # 尝试使用 PyPDF2 读取 PDF 信息
            try:
                import PyPDF2
                
                with open(temp_file, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    total_pages = len(reader.pages)
                    
                    # 尝试读取元数据
                    metadata = {}
                    if reader.metadata:
                        metadata = {
                            "title": reader.metadata.get("/Title", ""),
                            "author": reader.metadata.get("/Author", ""),
                            "subject": reader.metadata.get("/Subject", "")
                        }
                
                logger.info(f"📄 文档信息: 共 {total_pages} 页")
                
                return {
                    "total_pages": total_pages,
                    "file_size": os.path.getsize(temp_file),
                    "file_type": Path(temp_file).suffix.lower(),
                    "estimated_elements": total_pages * 15,  # 估算：每页约15个元素
                    "metadata": metadata
                }
            
            except ImportError:
                # 如果没有 PyPDF2，使用基本信息
                logger.warning("PyPDF2 未安装，无法获取页数信息")
                return {
                    "total_pages": None,  # 未知页数
                    "file_size": os.path.getsize(temp_file),
                    "file_type": Path(temp_file).suffix.lower(),
                    "estimated_elements": None,
                    "metadata": {}
                }
        
        except Exception as e:
            logger.warning(f"获取文档信息失败: {e}")
            return {
                "total_pages": None,
                "file_size": os.path.getsize(temp_file),
                "file_type": Path(temp_file).suffix.lower(),
                "estimated_elements": None,
                "metadata": {}
            }
    
    def _parse_page_ranges(self, pages: str, total_pages: int) -> List[tuple]:
        """
        解析页码范围字符串
        
        支持格式：
        - "5"          → [(5, 5)]
        - "1-5"        → [(1, 5)]
        - "1,3,5"      → [(1, 1), (3, 3), (5, 5)]
        - "1-5,8-10"   → [(1, 5), (8, 10)]
        - "1-5,8,12-15" → [(1, 5), (8, 8), (12, 15)]
        
        Args:
            pages: 页码范围字符串
            total_pages: 文档总页数
            
        Returns:
            页码范围元组列表
        """
        ranges = []
        
        for part in pages.split(','):
            part = part.strip()
            
            if '-' in part:
                # 范围：1-5
                start, end = map(int, part.split('-'))
            else:
                # 单页：5
                start = end = int(part)
            
            # 验证范围
            if start < 1 or (total_pages and end > total_pages) or start > end:
                raise ValueError(
                    f"无效的页码范围: {part} "
                    f"(文档总页数: {total_pages if total_pages else '未知'})"
                )
            
            ranges.append((start, end))
        
        return ranges
    
    def _extract_outline(self, elements: List[Dict], doc_info: Dict) -> List[Dict]:
        """
        从解析结果中提取文档大纲
        
        识别标题层级：
        - Title: 主标题（H1）
        - Header: 章节标题（H2-H6）
        
        Args:
            elements: 解析结果元素列表
            doc_info: 文档信息
            
        Returns:
            大纲列表
        """
        outline = []
        
        for elem in elements:
            elem_type = elem.get("type")
            
            if elem_type in ["Title", "Header"]:
                text = elem.get("text", "").strip()
                page = elem.get("metadata", {}).get("page_number", 1)
                
                # 简单的层级识别
                level = 1 if elem_type == "Title" else 2
                
                # 识别编号（1. 2. 3.）
                import re
                if re.match(r'^\d+\.', text):
                    level = 2
                elif re.match(r'^\d+\.\d+', text):
                    level = 3
                
                outline.append({
                    "page": page,
                    "level": level,
                    "title": text[:100]  # 限制长度
                })
        
        return outline
    
    def _generate_summary(self, elements: List[Dict], max_chars: int = 500) -> str:
        """
        生成文档摘要
        
        从元素列表中提取关键信息生成简要摘要
        
        Args:
            elements: 解析结果元素列表
            max_chars: 最大字符数
            
        Returns:
            摘要文本
        """
        summary_parts = []
        current_length = 0
        
        for elem in elements[:50]:  # 只看前50个元素
            elem_type = elem.get("type")
            text = elem.get("text", "").strip()
            
            if text and elem_type in ["Title", "NarrativeText", "Header"]:
                if current_length + len(text) > max_chars:
                    # 截断并结束
                    remaining = max_chars - current_length
                    if remaining > 50:  # 至少保留50字符
                        summary_parts.append(text[:remaining] + "...")
                    break
                
                summary_parts.append(text)
                current_length += len(text) + 1
        
        return " ".join(summary_parts) if summary_parts else "文档内容为空"
    
    async def _process_overview(
        self,
        temp_file: str,
        doc_info: Dict,
        source: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        概要模式：快速返回文档结构
        
        策略：
        1. 只解析前 3 页（标题、摘要、目录）
        2. 使用 fast 策略（速度快）
        3. 提取文档大纲（标题层级）
        4. 生成简要摘要
        
        Args:
            temp_file: 临时文件路径
            doc_info: 文档信息
            source: 源URL
            user_id: 用户ID
            
        Returns:
            概要结果
        """
        logger.info("📋 生成文档概要（解析前 3 页）")
        
        # 解析前 3 页
        first_pages = await self._call_partition_api(
            file_path=temp_file,
            strategy="fast",
            user_id=user_id,
            pages="1-3"
        )
        
        # 提取大纲
        outline = self._extract_outline(first_pages, doc_info)
        
        # 生成摘要
        summary = self._generate_summary(first_pages)
        
        # 获取总页数
        total_pages = doc_info.get("total_pages")
        
        # 🆕 构建警告信息和下一步建议
        warning_message = f"⚠️ 这是文档概要（仅解析了前3页，共{total_pages}页）。这不是完整内容！"
        
        next_action = None
        if total_pages:
            if total_pages <= 10:
                # 小文档：建议直接读取全部
                next_action = {
                    "recommendation": "建议读取完整内容",
                    "reason": f"文档较小（{total_pages}页），可一次性读取",
                    "suggested_call": {
                        "tool": "document_partition_tool",
                        "parameters": {
                            "source": source,
                            "mode": "full",
                            "strategy": "auto"
                        }
                    }
                }
            else:
                # 大文档：建议分段读取
                next_action = {
                    "recommendation": "建议分段读取关键章节",
                    "reason": f"文档较大（{total_pages}页），建议根据大纲选择关键章节",
                    "suggested_call": {
                        "tool": "document_partition_tool",
                        "parameters": {
                            "source": source,
                            "mode": "pages",
                            "pages": "示例: 1-10 或根据大纲选择",
                            "strategy": "auto"
                        }
                    }
                }
        
        return {
            "success": True,
            "mode": "overview",
            "warning": warning_message,  # 🆕 醒目警告
            "message": "文档概要已生成（仅前3页）",
            "data": {
                "summary": summary,
                "outline": outline,
                "preview": first_pages[:10]  # 减少到前10个元素，避免混淆
            },
            "metadata": {
                "source": source,
                "total_pages": total_pages,
                "parsed_pages": 3,  # 🆕 明确显示只解析了3页
                "file_type": doc_info.get("file_type"),
                "file_size": doc_info.get("file_size"),
                "element_count": len(first_pages),
                "from_cache": False
            },
            "next_action": next_action,  # 🆕 智能建议
            "access_hint": {
                "message": "若需完整内容，请立即使用以下方式之一：",
                "examples": [
                    {
                        "description": "📖 读取全部内容（推荐用于小文档）",
                        "example": f"mode='full'"
                    },
                    {
                        "description": "📄 读取指定页面（推荐用于大文档）",
                        "example": f"mode='pages', pages='4-20'"
                    },
                    {
                        "description": "🔍 高精度读取（含表格结构）",
                        "example": f"mode='pages', pages='5-15', strategy='hi_res'"
                    }
                ]
            }
        }
    
    async def _process_pages(
        self,
        temp_file: str,
        page_ranges: List[tuple],
        strategy: str,
        doc_info: Dict,
        source: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        分页模式：解析指定页面范围
        
        Args:
            temp_file: 临时文件路径
            page_ranges: [(1, 5), (8, 10)] 表示解析 1-5页 和 8-10页
            strategy: 解析策略
            doc_info: 文档信息
            source: 源URL
            user_id: 用户ID
            
        Returns:
            分页结果
        """
        logger.info(f"📄 解析指定页面: {page_ranges}")
        
        all_elements = []
        processing_details = []
        
        # 逐个范围解析
        for start, end in page_ranges:
            logger.info(f"   处理第 {start}-{end} 页")
            
            try:
                # 调用 API
                result = await self._call_partition_api(
                    file_path=temp_file,
                    strategy=strategy,
                    user_id=user_id,
                    pages=f"{start}-{end}"
                )
                
                all_elements.extend(result)
                processing_details.append({
                    "pages": f"{start}-{end}",
                    "element_count": len(result),
                    "status": "success"
                })
                
            except Exception as e:
                logger.error(f"   页面 {start}-{end} 解析失败: {e}")
                processing_details.append({
                    "pages": f"{start}-{end}",
                    "status": "failed",
                    "error": str(e)
                })
        
        return {
            "success": True,
            "mode": "pages",
            "message": f"✅ 成功解析指定页面内容，共 {len(all_elements)} 个元素",
            "data": {"elements": all_elements},
            "metadata": {
                "source": source,
                "total_pages": doc_info.get("total_pages"),
                "requested_pages": sum(e - s + 1 for s, e in page_ranges),
                "parsed_pages": sum(e - s + 1 for s, e in page_ranges),  # 🆕 明确显示解析的页数
                "element_count": len(all_elements),
                "strategy": strategy,
                "file_type": doc_info.get("file_type"),
                "file_size": doc_info.get("file_size"),
                "from_cache": False,
                "processing_details": processing_details
            }
        }
    
    async def _process_full(
        self,
        temp_file: str,
        strategy: str,
        doc_info: Dict,
        source: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        完整模式：解析全部内容（仅限小文档）
        
        Args:
            temp_file: 临时文件路径
            strategy: 解析策略
            doc_info: 文档信息
            source: 源URL
            user_id: 用户ID
            
        Returns:
            完整结果
        """
        total_pages = doc_info.get("total_pages")
        
        # 检查页数限制
        if total_pages and total_pages > 10:
            return {
                "success": False,
                "error": "DOCUMENT_TOO_LARGE",
                "error_code": 413,
                "message": f"文档过大（{total_pages}页），超过完整模式限制（10页）",
                "metadata": {
                    "total_pages": total_pages,
                    "max_full_pages": 10
                },
                "suggestion": "请使用 mode='pages' 分段读取，或使用 mode='overview' 先查看概要"
            }
        
        logger.info(f"📚 完整模式：解析全部 {total_pages if total_pages else '未知'} 页")
        
        # 调用 API 解析全部内容
        all_elements = await self._call_partition_api(
            file_path=temp_file,
            strategy=strategy,
            user_id=user_id
        )
        
        return {
            "success": True,
            "mode": "full",
            "message": f"✅ 成功解析文档全部内容，共 {total_pages if total_pages else '未知'} 页，{len(all_elements)} 个元素",
            "data": {"elements": all_elements},
            "metadata": {
                "source": source,
                "total_pages": total_pages,
                "parsed_pages": total_pages,  # 🆕 明确显示解析了全部页
                "element_count": len(all_elements),
                "strategy": strategy,
                "file_type": doc_info.get("file_type"),
                "file_size": doc_info.get("file_size"),
                "from_cache": False
            }
        }


# 🆕 创建工具实例（供框架使用）
# 注意：框架会自动实例化工具，这里提供工厂函数
def create_document_partition_tool(**kwargs) -> DocumentPartitionTool:
    """
    创建文档解析工具实例
    
    Args:
        **kwargs: 配置参数
            - config: PartitionConfig 配置对象
            - event_manager: 事件管理器
            - memory: WorkingMemory 实例
            - workspace_dir: 工作目录
    
    Returns:
        DocumentPartitionTool 实例
    """
    return DocumentPartitionTool(**kwargs)


# 尝试创建默认实例（如果环境变量配置正确）
try:
    document_partition_tool = DocumentPartitionTool()
    if not document_partition_tool.is_available:
        logger.info("DocumentPartitionTool 已加载，但需要配置 UNSTRUCTURED_API_KEY 才能使用")
except Exception as e:
    logger.warning(f"无法创建默认工具实例: {e}")
    document_partition_tool = None
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
    default_strategy: str = "auto"  # 优化：使用 fast 策略避免超时，提高处理速度
    cache_enabled: bool = False
    cache_dir: str = "./cache/partition"
    # 🆕 文件大小限制配置
    recommended_size_mb: int = 20  # 建议的文件大小上限（最佳实践）
    max_size_mb: int = 50          # 硬性限制，超过将拒绝或分割
    chunk_size_mb: int = 10        # 分块下载大小
    # 🆕 分批处理配置
    pages_batch_size: int = 5      # 每批处理的最大页数（防止单次请求页数过多导致超时）


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
        
        # 🆕 文件大小常量（字节）
        self.RECOMMENDED_SIZE = self.config.recommended_size_mb * 1024 * 1024
        self.MAX_SIZE = self.config.max_size_mb * 1024 * 1024
        self.CHUNK_SIZE = self.config.chunk_size_mb * 1024 * 1024
    
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

🚨🚨🚨 **【核心规则】用户指定页码时必看！** 🚨🚨🚨

⚠️ 默认情况下，工具只返回前3页概要（overview模式）！
⚠️ 如果用户说"解析70-90页"、"读取第5页"、"分析10到20页"，你必须：

✅ **正确调用方式**（两个参数都必须传）：
```json
{
  "source": "https://...",
  "mode": "pages",        // ← 必须！告诉工具返回指定页面
  "pages": "70-90"        // ← 必须！告诉工具具体哪些页
}
```

❌ **错误调用方式**（会导致只返回前3页，不是用户要的70-90页）：
```json
{
  "source": "https://...",
  "strategy": "hi_res"
  // ❌ 没有 mode='pages' → 默认 overview → 只返回前3页
  // ❌ 没有 pages="70-90" → 无法知道要哪些页
}
```

❌ **错误示例3**：只传 mode 不传 pages
```json
{
  "source": "https://...",
  "mode": "pages"
  // ❌ 只有 mode 没有 pages → 工具不知道要哪些页，会报错
}
```

🎯 **记住**：用户说页码 = 你必须传 mode='pages' + pages 参数！

---

📋 **完整使用规则**：

1️⃣ **用户指定页码** → mode='pages' + pages="70-90"
   示例：
   - "解析70-90页" → mode='pages', pages="70-90"
   - "读取第5页" → mode='pages', pages="5"
   - "分析10-20页" → mode='pages', pages="10-20"

2️⃣ **用户要完整内容** → 根据文档大小选择
   - 小文档（<10页）→ mode='full'
   - 大文档（>10页）→ 先 overview，再 pages 分段读取

3️⃣ **用户要概要/目录** → mode='overview'
   - "这个文档讲了什么"
   - "快速浏览"

⚠️ mode 参数的作用：
- overview: 只返回前3页概要（不是完整内容！）
- pages: 返回指定页面的完整内容 ⭐ 用户指定页码时必用
- full: 返回全部内容（仅限小文档<10页）

---

核心功能：
1. 🆕 **分段解析**：支持三种模式，优化大文档处理
   - overview: 快速概览（3-5秒，仅返回前3页摘要和目录）⚠️ 不是完整内容
   - pages: 按需加载（解析指定页面，如 pages="1-10" 或 pages="8,12-15"）
   - full: 完整解析（返回全部内容，仅限小文档 <10页）
2. 解析多种格式（11种核心文档格式）：
   - 文档：PDF、Word(.doc/.docx)、TXT、RTF、ODT
   - 表格：Excel(.xls/.xlsx)、CSV
   - 演示：PowerPoint(.ppt/.pptx)
   ⚠️ 注意：不支持图片格式（PNG/JPG/TIFF），请使用模型的原生视觉能力处理图片
3. 智能解析策略：fast（快速，默认）、auto（自动选择）、hi_res（高精度含表格）
4. 🆕 **文件大小智能控制**：
   - ✅ 最佳实践：≤20MB（快速稳定）
   - ⚠️ 警告阈值：20-50MB（自动降级为 fast 策略）
   - ❌ 硬性限制：>50MB（PDF可分页处理，其他格式拒绝）
5. 仅支持URL输入（不支持本地文件路径）
6. 自动缓存结果（节省API调用成本）

🎯 智能模式选择策略（请严格遵循）：

1️⃣ **用户明确指定页码** ⭐ **最高优先级**
   示例：
   - "解析70到90页" → mode='pages', pages="70-90"
   - "读取第5页" → mode='pages', pages="5"
   - "分析10-20页和30-40页" → mode='pages', pages="10-20,30-40"
   
2️⃣ **小文档（<5页）→ 直接使用 mode='full'**
   - 用户说"解析/分析/读取文档"时，优先尝试 full 模式
   - 如果 overview 返回"文档仅有X页"，说明已是完整内容，无需再调用
   
3️⃣ **中等文档（5-10页）→ 根据需求选择**
   - 快速了解 → mode='overview'
   - 详细分析 → mode='full'
   
4️⃣ **大文档（>10页）→ 分段读取**
   - 先 mode='overview' 查看结构
   - 再 mode='pages' 读取关键章节
   
5️⃣ **特殊需求**
   - 只看目录/概要 → mode='overview'
   - 读取指定章节 → mode='pages' + 页码

⚠️ 典型错误场景（请务必避免）：
- ❌ **最常见错误**：用户说"解析70到90页"，你只传了 source 和 strategy，没传 mode 和 pages
  ✅ 正确：mode='pages', pages="70-90"
  ❌ 错误调用示例：
  ```python
  {
    "source": "...",
    "strategy": "hi_res"
    # ❌ 缺少 mode='pages'
    # ❌ 缺少 pages="70-90"
  }
  # 结果：只返回前3页（默认overview模式），不是用户要的70-90页！
  ```
  ✅ 正确调用示例：
  ```python
  {
    "source": "...",
    "mode": "pages",        # ✅ 必须指定
    "pages": "70-90",       # ✅ 必须指定
    "strategy": "hi_res"
  }
  ```

- ❌ 用户上传 1 页 Word，你调用 overview 后看到"可能不是完整内容"，然后调用 full
  ✅ 正确：overview 已返回全部内容（因为只有1页），无需再调用
  
- ❌ 用户说"分析这个论文"，你只调用 overview 就回答问题
  ✅ 正确：先 overview 判断页数，如果<10页用 full，否则 pages
  
- ❌ 看到 "共None页" 就认为文档很大
  ✅ 正确：None 表示未知页数（Word/Excel），可能实际很小，建议尝试 full

参数说明：
- source: 文档URL（必需）- HTTP/HTTPS 协议
- mode: 解析模式（⚠️ 关键参数，默认 'overview' 只返回概要）
  * 'overview': 概要模式，仅返回前3页的文档结构（不是完整内容！）
  * 'pages': 分页模式，返回指定页面的完整内容（需设置 pages 参数）⭐ **用户指定页码时必用**
  * 'full': 完整模式，返回全部内容（<10页的文档推荐使用）
- pages: 页码范围（⚠️ mode='pages'时必需！）
  * 格式示例：
    - "5" → 单页
    - "1-10" → 范围
    - "1-5,8-10" → 多个范围
    - "70-90" → 大文档的特定范围
  * ⚠️ 如果用户说"解析70到90页"，必须传 mode='pages' 和 pages="70-90"
- strategy: 解析策略（可选，默认 'fast'）
  * 'fast': 快速提取纯文本（速度快，约30-60秒）⭐ 默认策略
  * 'auto': 自动选择最佳策略（处理时间约1-2分钟）
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

📏 文件大小限制详情：
1. **≤20MB（最佳实践）**：
   - 快速处理，稳定性最佳
   - 使用原始策略（auto/fast/hi_res）
   - 推荐的文件大小范围

2. **20-50MB（警告阈值）**：
   - 仍可处理，但会有性能警告
   - 自动降级为 fast 策略（提高成功率）
   - 建议用户压缩或优化文档

3. **>50MB（硬性限制）**：
   - PDF 文档：提示使用 mode='pages' 分段读取
   - 非PDF文档：拒绝处理，返回错误
   - 建议：分割文件或压缩后再上传

⚠️ 注意事项：
- 此工具仅接受URL输入，不支持本地文件路径
- 文件大小检查通过 HEAD 请求预检（不下载文件）
- 如 HEAD 请求失败，下载后仍会检查实际大小
- 大文件自动降级策略对用户透明，但会在元数据中标注
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
                    "description": "解析模式（决定返回哪些页面）：'overview'（仅前3页概要）、'pages'（指定页面，需配合pages参数）、'full'（全部内容，限<10页）。用户说'解析第X页'时必须传 mode='pages' + pages='X'，否则只返回概要！",
                    "enum": ["overview", "pages", "full"]
                },
                "pages": {
                    "type": "string",
                    "description": "页码范围（mode='pages'时必需）。格式：'5'（单页）、'1-10'（范围）、'1-5,8-10'（多段）。用户说'解析X页'时必须传此参数，例如用户说'解析70-90页'时传 pages='70-90'。"
                },
                "strategy": {
                    "type": "string",
                    "description": "解析策略：'fast'（快速提取纯文本，约30-60秒，默认）、'auto'（自动选择，约1-2分钟）、'hi_res'（高精度含表格，约2-3分钟）⚠️ hi_res 速度最慢但最准确",
                    "enum": ["auto", "fast", "hi_res"],
                    "default": "fast"
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
    
    async def _get_file_size_from_url(self, url: str) -> Optional[int]:
        """
        通过 HEAD 请求获取文件大小（不下载文件）
        
        Args:
            url: 文件URL
            
        Returns:
            文件大小（字节），失败返回 None
        """
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.head(url, allow_redirects=True) as response:
                    if response.status == 200:
                        content_length = response.headers.get('Content-Length')
                        if content_length:
                            file_size = int(content_length)
                            logger.debug(f"文件大小（HEAD 请求）: {file_size / (1024 * 1024):.2f} MB")
                            return file_size
        except Exception as e:
            logger.warning(f"HEAD 请求获取文件大小失败: {e}，将在下载时检查")
        
        return None
    
    async def execute(
        self,
        source: str,
        mode: Optional[str] = None,
        pages: Optional[str] = None,
        strategy: str = "fast",  # 默认使用 fast 策略
        use_cache: bool = True,
        output_format: str = "json",
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行文档解析（支持分段策略）
        
        Args:
            source: 文档URL（必须是HTTP/HTTPS协议）
            mode: 解析模式（⚠️ 如果传了 pages 参数，必须明确指定 mode='pages'）
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
        # 🔧 智能默认逻辑：根据参数自动推断 mode
        if mode is None:
            if pages:
                # 传了 pages 参数，自动推断为 pages 模式
                mode = "pages"
                logger.warning(
                    f"⚠️ 检测到 pages={pages} 但未指定 mode，"
                    f"自动推断为 mode='pages'。建议显式传递 mode 参数！"
                )
            else:
                # 默认使用 overview 模式
                mode = "overview"
                logger.debug("未指定 mode，使用默认值 'overview'")
        
        # 🔧 参数验证：mode='pages' 时必须传 pages 参数
        if mode == "pages" and not pages:
            return {
                "success": False,
                "error": "INVALID_PARAMETERS",
                "message": "mode='pages' 时必须指定 pages 参数（如 pages='5' 或 pages='1-10'）",
                "hint": "如果要解析特定页面，请同时传递 mode='pages' 和 pages 参数"
            }
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
            
            # 5. 🆕 预检查文件大小（HEAD 请求）
            file_size_hint = await self._get_file_size_from_url(source)
            auto_downgrade_strategy = False  # 标记是否自动降级策略
            
            if file_size_hint:
                file_size_mb = file_size_hint / (1024 * 1024)
                
                # 5.1 超过硬性限制（50MB）
                if file_size_hint > self.MAX_SIZE:
                    # PDF 可以尝试分页处理，其他格式拒绝
                    if source.lower().endswith('.pdf'):
                        logger.warning(
                            f"⚠️ 文件过大 ({file_size_mb:.1f}MB > {self.config.max_size_mb}MB)，"
                            "将尝试 PDF 分页处理"
                        )
                        # 后续逻辑会自动触发分页处理
                    else:
                        return {
                            "success": False,
                            "error": "FILE_TOO_LARGE",
                            "error_code": 413,
                            "message": f"文件过大 ({file_size_mb:.1f}MB)，超过最大限制 ({self.config.max_size_mb}MB)",
                            "metadata": {
                                "file_size_mb": round(file_size_mb, 2),
                                "max_size_mb": self.config.max_size_mb,
                                "file_type": source.split('.')[-1].lower()
                            },
                            "suggestion": (
                                "建议：\n"
                                "1. 如果是 PDF 文件，请确保 URL 以 .pdf 结尾\n"
                                "2. 或将文件分割为多个小文件（每个 < 50MB）\n"
                                f"3. 或压缩文件（目标 < {self.config.recommended_size_mb}MB 最佳）"
                            )
                        }
                
                # 5.2 超过建议阈值（20MB）但未超过硬限制
                elif file_size_hint > self.RECOMMENDED_SIZE:
                    logger.warning(
                        f"⚠️ 文件较大 ({file_size_mb:.1f}MB > {self.config.recommended_size_mb}MB，建议小于 {self.config.recommended_size_mb}MB)，"
                        "将自动降级为 'fast' 策略以提高成功率"
                    )
                    # 自动降级策略
                    if strategy in ["auto", "hi_res"]:
                        auto_downgrade_strategy = True
                        original_strategy = strategy
                        strategy = "fast"
                        logger.info(f"   策略已从 '{original_strategy}' 降级为 'fast'")
                
                # 5.3 最佳实践范围（≤20MB）
                else:
                    logger.info(f"✅ 文件大小: {file_size_mb:.1f}MB（在最佳范围内）")
            
            # 6. 下载文档（支持分块下载）
            temp_file = await self._download_url_file(source)
            
            try:
                # 7. 快速获取文档信息（不调用 API）
                doc_info = await self._get_document_info(temp_file)
                
                # 7.1 🆕 检查实际下载的文件大小
                actual_file_size = os.path.getsize(temp_file)
                actual_file_size_mb = actual_file_size / (1024 * 1024)
                
                # 如果 HEAD 请求失败，这里是最后的防线
                if not file_size_hint and actual_file_size > self.MAX_SIZE:
                    # 清理临时文件
                    os.unlink(temp_file)
                    
                    if temp_file.lower().endswith('.pdf'):
                        logger.warning(
                            f"⚠️ 文件过大 ({actual_file_size_mb:.1f}MB > {self.config.max_size_mb}MB)，"
                            "PDF 文件可使用分页模式处理"
                        )
                    else:
                        return {
                            "success": False,
                            "error": "FILE_TOO_LARGE",
                            "error_code": 413,
                            "message": f"文件过大 ({actual_file_size_mb:.1f}MB)，超过最大限制 ({self.config.max_size_mb}MB)",
                            "metadata": {
                                "file_size_mb": round(actual_file_size_mb, 2),
                                "max_size_mb": self.config.max_size_mb
                            },
                            "suggestion": f"建议将文件压缩或分割为多个小文件（每个 < {self.config.max_size_mb}MB）"
                        }
                
                # 7.2 记录文件大小信息
                logger.debug(f"文件实际大小: {actual_file_size_mb:.2f} MB")
                
                # 8. 根据模式处理
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
                
                # 9. 格式化输出（如果需要）
                if output_format == "text" and result.get("success") and "data" in result:
                    if "elements" in result["data"]:
                        result["data"] = self._format_as_text(result["data"])
                
                # 10. 添加处理时间和文件大小信息
                if "metadata" in result:
                    result["metadata"]["processing_time"] = time.time() - start_time
                    result["metadata"]["actual_file_size_mb"] = round(actual_file_size_mb, 2)
                    
                    # 🆕 添加降级标记
                    if auto_downgrade_strategy:
                        result["metadata"]["strategy_downgraded"] = True
                        result["metadata"]["original_strategy"] = original_strategy
                        result["metadata"]["downgrade_reason"] = (
                            f"文件较大 ({actual_file_size_mb:.1f}MB > {self.config.recommended_size_mb}MB)，"
                            "自动降级为 fast 策略"
                        )
                
                # 11. 保存到缓存
                if cache_key and self.config.cache_enabled and result.get("success"):
                    self._save_to_cache(cache_key, result)
                
                # 12. 发送事件
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
        """
        下载URL文件到临时文件（支持分块下载和进度日志）
        
        Args:
            url: 文件URL
            
        Returns:
            临时文件路径
        """
        temp_file = tempfile.NamedTemporaryFile(
            suffix=self._get_file_extension_from_url(url),
            delete=False
        )
        temp_path = temp_file.name
        temp_file.close()
        
        # 使用异步HTTP客户端下载
        for attempt in range(self.config.max_retries):
            try:
                # 🆕 使用更长的超时时间处理大文件
                timeout = aiohttp.ClientTimeout(total=self.config.timeout_download * 2)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url) as response:
                        response.raise_for_status()
                        
                        # 🆕 获取文件总大小
                        total_size = response.headers.get('Content-Length')
                        if total_size:
                            total_size = int(total_size)
                            total_mb = total_size / (1024 * 1024)
                            logger.info(f"开始下载: {total_mb:.2f} MB")
                        
                        # 🆕 分块下载（使用配置的分块大小，默认 10MB）
                        chunk_size = min(self.CHUNK_SIZE, 10 * 1024 * 1024)  # 最大 10MB 每块
                        downloaded = 0
                        
                        with open(temp_path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(chunk_size):
                                f.write(chunk)
                                downloaded += len(chunk)
                                
                                # 🆕 每下载 10MB 记录一次进度
                                if total_size and downloaded % (10 * 1024 * 1024) < chunk_size:
                                    progress = (downloaded / total_size) * 100
                                    logger.debug(f"下载进度: {progress:.1f}% ({downloaded / (1024 * 1024):.1f} MB)")
                        
                        # 验证下载完整性
                        actual_size = os.path.getsize(temp_path)
                        if total_size and actual_size != total_size:
                            logger.warning(
                                f"下载大小不匹配: 预期 {total_size} bytes, 实际 {actual_size} bytes"
                            )
                        
                        logger.info(
                            f"✅ 下载成功: {actual_size / (1024 * 1024):.2f} MB -> {temp_path}"
                        )
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
        # 🆕 如果指定了页码范围且是 PDF，先提取指定页码生成临时文件
        temp_extracted_file = None
        if pages and file_path.lower().endswith('.pdf'):
            try:
                import PyPDF2
                from PyPDF2 import PdfWriter
                
                logger.debug(f"   🔧 提取 PDF 页码: {pages}")
                
                # 解析页码范围
                start_page = int(pages.split('-')[0])
                end_page = int(pages.split('-')[1]) if '-' in pages else start_page
                
                # 读取原始 PDF
                reader = PyPDF2.PdfReader(file_path)
                writer = PdfWriter()
                
                # 提取指定页码（PyPDF2 索引从 0 开始）
                for page_num in range(start_page - 1, end_page):
                    writer.add_page(reader.pages[page_num])
                
                # 生成临时文件
                temp_extracted_file = file_path.replace('.pdf', f'_pages_{pages.replace("-", "_")}.pdf')
                with open(temp_extracted_file, 'wb') as output_file:
                    writer.write(output_file)
                
                extracted_size = os.path.getsize(temp_extracted_file) / (1024 * 1024)
                logger.info(
                    f"   ✂️  已提取第 {start_page}-{end_page} 页 "
                    f"({end_page - start_page + 1} 页，{extracted_size:.2f}MB)"
                )
                
                # 使用提取后的文件替换原文件路径
                file_path = temp_extracted_file
                
                # 清空 pages 参数（因为已经提取了，不需要再传 API 参数）
                pages = None
                
            except Exception as e:
                logger.warning(f"   ⚠️ 页码提取失败，将使用 API 参数方式: {e}")
                # 提取失败，继续使用原来的方式（API 参数）
                if temp_extracted_file and os.path.exists(temp_extracted_file):
                    os.unlink(temp_extracted_file)
                temp_extracted_file = None
        
        try:
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
                        
                        # 🆕 如果还有 pages 参数（页码提取失败的情况），使用 API 参数方式
                        if pages:
                            form_data.add_field('starting_page_number', pages.split('-')[0])
                            if '-' in pages:
                                form_data.add_field('ending_page_number', pages.split('-')[1])
                            logger.debug(f"   ⚠️ 使用 API 参数方式指定页码（提取失败）: {pages}")
                        
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
        
        finally:
            # 🧹 清理提取的临时文件
            if temp_extracted_file and os.path.exists(temp_extracted_file):
                try:
                    os.unlink(temp_extracted_file)
                    logger.debug(f"   🧹 已清理提取的临时文件")
                except Exception as e:
                    logger.warning(f"   ⚠️ 清理临时文件失败: {e}")
    
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
            # 文档格式
            r'\.pdf($|\?|#)': '.pdf',
            r'\.docx($|\?|#)': '.docx',
            r'\.doc($|\?|#)': '.doc',
            r'\.txt($|\?|#)': '.txt',
            r'\.rtf($|\?|#)': '.rtf',
            r'\.odt($|\?|#)': '.odt',
            # 表格格式
            r'\.xlsx($|\?|#)': '.xlsx',
            r'\.xls($|\?|#)': '.xls',
            r'\.csv($|\?|#)': '.csv',
            # 演示格式
            r'\.pptx($|\?|#)': '.pptx',
            r'\.ppt($|\?|#)': '.ppt',
            # 网页格式
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
            # 文档格式
            '.pdf': 'application/pdf',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.doc': 'application/msword',
            '.txt': 'text/plain',
            '.rtf': 'application/rtf',
            '.odt': 'application/vnd.oasis.opendocument.text',
            
            # 表格格式
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.xls': 'application/vnd.ms-excel',
            '.csv': 'text/csv',
            
            # 演示格式
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            '.ppt': 'application/vnd.ms-powerpoint',
            
            # 网页格式
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
        
        支持多种格式：
        - PDF: 使用 PyPDF2 快速读取页数（< 1 秒）
        - Word (.docx): 使用 python-docx 估算页数
        - 其他: 返回文件基本信息
        
        Args:
            temp_file: 临时文件路径
            
        Returns:
            文档信息字典
        """
        file_type = Path(temp_file).suffix.lower()
        file_size = os.path.getsize(temp_file)
        metadata = {}
        total_pages = None
        
        try:
            # PDF 文件 - 使用 PyPDF2
            if file_type == '.pdf':
                try:
                    import PyPDF2
                    
                    with open(temp_file, 'rb') as f:
                        reader = PyPDF2.PdfReader(f)
                        total_pages = len(reader.pages)
                        
                        # 尝试读取元数据
                        if reader.metadata:
                            metadata = {
                                "title": reader.metadata.get("/Title", ""),
                                "author": reader.metadata.get("/Author", ""),
                                "subject": reader.metadata.get("/Subject", "")
                            }
                    
                    logger.info(f"📄 PDF 文档: 共 {total_pages} 页")
                
                except ImportError:
                    logger.warning("PyPDF2 未安装，无法获取 PDF 页数")
            
            # Word 文档 - 使用 python-docx
            elif file_type in ['.docx', '.doc']:
                try:
                    from docx import Document
                    
                    doc = Document(temp_file)
                    # Word 没有"页"的概念，粗略估算：
                    # - 每段约 3-5 行
                    # - A4 纸约 40 行
                    # - 估算公式：max(1, 段落数 / 8)
                    paragraph_count = len([p for p in doc.paragraphs if p.text.strip()])
                    total_pages = max(1, paragraph_count // 8)
                    
                    # 读取文档属性
                    core_props = doc.core_properties
                    if core_props:
                        metadata = {
                            "title": core_props.title or "",
                            "author": core_props.author or "",
                            "subject": core_props.subject or ""
                        }
                    
                    logger.info(f"📄 Word 文档: 估算 {total_pages} 页（{paragraph_count} 个段落）")
                
                except ImportError:
                    logger.warning("python-docx 未安装，无法获取 Word 文档信息")
                except Exception as e:
                    logger.warning(f"读取 Word 文档失败: {e}")
            
            # Excel 文件 - 使用 openpyxl
            elif file_type in ['.xlsx', '.xls']:
                try:
                    import openpyxl
                    
                    wb = openpyxl.load_workbook(temp_file, read_only=True, data_only=True)
                    total_pages = len(wb.sheetnames)  # Excel 的"页"是工作表数量
                    
                    metadata = {
                        "sheets": wb.sheetnames,
                        "sheet_count": len(wb.sheetnames)
                    }
                    
                    logger.info(f"📊 Excel 文档: {total_pages} 个工作表")
                
                except ImportError:
                    logger.warning("openpyxl 未安装，无法获取 Excel 信息")
                except Exception as e:
                    logger.warning(f"读取 Excel 文档失败: {e}")
            
            # CSV 文件 - 视为单页
            elif file_type == '.csv':
                try:
                    with open(temp_file, 'r', encoding='utf-8', errors='ignore') as f:
                        row_count = sum(1 for _ in f)
                    
                    total_pages = 1  # CSV 通常视为单页
                    metadata = {
                        "row_count": row_count,
                        "note": "CSV 文件视为单页"
                    }
                    
                    logger.info(f"📊 CSV 文档: {row_count} 行（视为1页）")
                
                except Exception as e:
                    logger.warning(f"读取 CSV 文档失败: {e}")
            
            # PowerPoint 文件 - 使用 python-pptx
            elif file_type in ['.pptx', '.ppt']:
                try:
                    from pptx import Presentation
                    
                    prs = Presentation(temp_file)
                    total_pages = len(prs.slides)  # 幻灯片数量
                    
                    metadata = {
                        "slide_count": total_pages,
                        "note": "PPT 的'页'是幻灯片数量"
                    }
                    
                    logger.info(f"📊 PowerPoint 文档: {total_pages} 张幻灯片")
                
                except ImportError:
                    logger.warning("python-pptx 未安装，无法获取 PowerPoint 信息")
                except Exception as e:
                    logger.warning(f"读取 PowerPoint 文档失败: {e}")
            
            # TXT 文件 - 估算页数（按行数）
            elif file_type == '.txt':
                try:
                    with open(temp_file, 'r', encoding='utf-8', errors='ignore') as f:
                        line_count = sum(1 for _ in f)
                    
                    # 估算：A4 纸约 40 行/页
                    total_pages = max(1, line_count // 40)
                    
                    metadata = {
                        "line_count": line_count,
                        "note": "基于40行/页估算"
                    }
                    
                    logger.info(f"📄 TXT 文档: 估算 {total_pages} 页（{line_count} 行）")
                
                except Exception as e:
                    logger.warning(f"读取 TXT 文档失败: {e}")
            
            # RTF 文件 - 估算页数（基于文件大小）
            elif file_type == '.rtf':
                # RTF 难以准确估算，使用文件大小粗略估算
                # 假设：每页约 2KB 的 RTF 内容
                total_pages = max(1, file_size // (2 * 1024))
                
                metadata = {
                    "note": "基于文件大小估算（2KB/页）"
                }
                
                logger.info(f"📄 RTF 文档: 估算 {total_pages} 页（基于文件大小）")
            
            # ODT 文件 - 使用 odfpy
            elif file_type == '.odt':
                try:
                    from odf import text, teletype
                    from odf.opendocument import load
                    
                    doc = load(temp_file)
                    # 统计段落数
                    paragraphs = doc.getElementsByType(text.P)
                    paragraph_count = len(paragraphs)
                    
                    # 估算：每 8 个段落约 1 页
                    total_pages = max(1, paragraph_count // 8)
                    
                    metadata = {
                        "paragraph_count": paragraph_count,
                        "note": "基于段落数估算（8段/页）"
                    }
                    
                    logger.info(f"📄 ODT 文档: 估算 {total_pages} 页（{paragraph_count} 个段落）")
                
                except ImportError:
                    logger.warning("odfpy 未安装，无法获取 ODT 信息")
                except Exception as e:
                    logger.warning(f"读取 ODT 文档失败: {e}")
            
            # 其他文件类型 - 返回基本信息
            else:
                logger.info(f"📄 文档类型: {file_type}, 大小: {file_size} bytes")
        
        except Exception as e:
            logger.warning(f"获取文档信息失败: {e}")
        
        return {
            "total_pages": total_pages,
            "file_size": file_size,
            "file_type": file_type,
            "estimated_elements": total_pages * 15 if total_pages else None,
            "metadata": metadata
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
    
    def _detect_heading_level(self, text: str, elem_type: str) -> int:
        """
        🆕 智能检测标题层级
        
        支持多种编号格式：
        - 数字编号：1. / 1.1 / 1.1.1 / 1.1.1.1
        - 中文编号：一、/ 二、/ （一）/ （二）
        - 英文编号：Chapter 1 / Section 1.1
        - 罗马数字：I. / II. / III.
        - 字母编号：A. / B. / (a) / (b)
        
        Args:
            text: 标题文本
            elem_type: 元素类型（Title 或 Header）
            
        Returns:
            层级（1-6）
        """
        import re
        
        # Title 类型默认为 1 级
        if elem_type == "Title":
            return 1
        
        # 数字编号识别（最常见）
        # 1.1.1.1 → level 5
        if re.match(r'^\d+\.\d+\.\d+\.\d+', text):
            return 5
        # 1.1.1 → level 4
        elif re.match(r'^\d+\.\d+\.\d+', text):
            return 4
        # 1.1 → level 3
        elif re.match(r'^\d+\.\d+', text):
            return 3
        # 1. → level 2
        elif re.match(r'^\d+\.', text):
            return 2
        
        # 中文编号识别
        # 一、二、三、四、五、六、七、八、九、十、第一章、第二节 → level 2
        if re.match(r'^[一二三四五六七八九十百千]+[、.]', text):
            return 2
        # 第一章、第二节 → level 2
        elif re.match(r'^第[一二三四五六七八九十百千]+[章节]', text):
            return 2
        # （一）、（二） → level 3
        elif re.match(r'^[（(][一二三四五六七八九十百千]+[）)]', text):
            return 3
        # 1）、2） → level 3
        elif re.match(r'^\d+[)）]', text):
            return 3
        
        # 英文编号识别
        # Chapter 1 / CHAPTER 1 → level 2
        if re.match(r'^(Chapter|CHAPTER|第)\s*\d+', text, re.IGNORECASE):
            return 2
        # Section 1.1 / SECTION 1.1 → level 3
        elif re.match(r'^(Section|SECTION|节)\s*\d+', text, re.IGNORECASE):
            return 3
        # Part I / PART I → level 1
        elif re.match(r'^(Part|PART|部分|篇)\s*[IVX]+', text, re.IGNORECASE):
            return 1
        
        # 罗马数字识别
        # I. / II. / III. → level 2
        if re.match(r'^[IVX]+\.', text):
            return 2
        # i. / ii. / iii. → level 3
        elif re.match(r'^[ivx]+\.', text):
            return 3
        
        # 字母编号识别
        # A. / B. / C. → level 3
        if re.match(r'^[A-Z]\.', text):
            return 3
        # a. / b. / c. → level 4
        elif re.match(r'^[a-z]\.', text):
            return 4
        # (a) / (b) → level 4
        elif re.match(r'^[（(][a-z][）)]', text):
            return 4
        
        # 特殊标记识别
        # ● / ○ / ■ / □ → level 4（项目符号）
        if re.match(r'^[●○■□▪▫]', text):
            return 4
        
        # 默认：Header 类型为 2 级
        return 2
    
    def _extract_outline(self, elements: List[Dict], doc_info: Dict) -> List[Dict]:
        """
        从解析结果中提取文档大纲
        
        🆕 增强功能：
        - 支持更多层级格式（1-6级）
        - 识别中英文编号
        - 识别罗马数字和字母编号
        - 记录章节页码范围
        
        Args:
            elements: 解析结果元素列表
            doc_info: 文档信息
            
        Returns:
            大纲列表
        """
        outline = []
        current_chapter = None
        
        for idx, elem in enumerate(elements):
            elem_type = elem.get("type")
            
            if elem_type in ["Title", "Header"]:
                text = elem.get("text", "").strip()
                page = elem.get("metadata", {}).get("page_number", 1)
                
                # 🆕 使用增强的层级检测
                level = self._detect_heading_level(text, elem_type)
                
                outline_item = {
                    "page": page,
                    "level": level,
                    "title": text[:100],  # 限制长度
                    "element_index": idx  # 🆕 记录元素索引
                }
                
                # 🆕 如果上一个章节存在且层级相同或更高，记录其结束页
                if current_chapter and current_chapter["level"] >= level:
                    # 当前章节结束于上一页
                    if page > current_chapter["page"]:
                        current_chapter["page_end"] = page - 1
                        current_chapter["page_range"] = f"{current_chapter['page']}-{current_chapter['page_end']}"
                
                outline.append(outline_item)
                current_chapter = outline_item
        
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
    
    def _get_smart_overview_pages(self, file_type: str, total_pages: Optional[int]) -> str:
        """
        🆕 智能选择 overview 模式解析的页数
        
        根据文档类型和总页数智能决定解析页数：
        - PDF：前5页（通常包含封面、目录、摘要）
        - Word/ODT：前2页（Word 文档通常更紧凑）
        - PowerPoint：前10张（幻灯片信息量小）
        - Excel/CSV：前3页（表格类文档）
        - 小文档（≤5页）：全部解析
        
        Args:
            file_type: 文件类型（如 '.pdf', '.docx'）
            total_pages: 文档总页数（可能为 None）
            
        Returns:
            页码范围字符串（如 "1-5"）
        """
        # 如果已知总页数且文档很小，直接全部解析
        if total_pages and total_pages <= 5:
            logger.debug(f"   小文档（{total_pages}页），解析全部")
            return f"1-{total_pages}"
        
        # 根据文件类型选择策略
        if file_type == '.pdf':
            # PDF：前5页（可能包含目录）
            pages = "1-5"
            logger.debug("   PDF 文档：解析前5页")
        
        elif file_type in ['.docx', '.doc', '.odt', '.rtf']:
            # Word/ODT：前2页（通常够了）
            pages = "1-2"
            logger.debug("   Word/ODT 文档：解析前2页")
        
        elif file_type in ['.pptx', '.ppt']:
            # PPT：前10张（幻灯片信息量小）
            if total_pages and total_pages < 10:
                pages = f"1-{total_pages}"
                logger.debug(f"   PPT 文档：解析全部 {total_pages} 张")
            else:
                pages = "1-10"
                logger.debug("   PPT 文档：解析前10张")
        
        elif file_type in ['.xlsx', '.xls', '.csv']:
            # Excel/CSV：前3页（工作表）
            pages = "1-3"
            logger.debug("   Excel/CSV 文档：解析前3页")
        
        elif file_type == '.txt':
            # TXT：前2页（纯文本）
            pages = "1-2"
            logger.debug("   TXT 文档：解析前2页")
        
        else:
            # 未知类型：默认前3页
            pages = "1-3"
            logger.debug("   未知类型：解析前3页")
        
        return pages
    
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
        1. 🆕 智能选择页数（根据文档类型和大小）
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
        # 🆕 智能页数选择逻辑
        total_pages = doc_info.get("total_pages")
        file_type = doc_info.get("file_type", "")
        
        # 根据文档类型和大小智能决定解析页数
        overview_pages = self._get_smart_overview_pages(file_type, total_pages)
        
        logger.info(f"📋 生成文档概要（智能解析第 {overview_pages} 页）")
        
        # 解析指定页数
        first_pages = await self._call_partition_api(
            file_path=temp_file,
            strategy="fast",
            user_id=user_id,
            pages=overview_pages
        )
        
        # 提取大纲
        outline = self._extract_outline(first_pages, doc_info)
        
        # 生成摘要
        summary = self._generate_summary(first_pages)
        
        # 🆕 解析实际页数范围
        parsed_page_range = overview_pages
        if '-' in overview_pages:
            start_page, end_page = overview_pages.split('-')
            parsed_page_count = int(end_page) - int(start_page) + 1
        else:
            parsed_page_count = 1
        
        # 🆕 构建智能警告信息（根据实际解析的页数）
        if total_pages:
            # 如果已知页数
            if parsed_page_count >= total_pages:
                # 已全部解析
                warning_message = f"✅ 文档仅有 {total_pages} 页，已全部解析。"
            else:
                # 部分解析：明确提示
                warning_message = (
                    f"⚠️ 这是文档概要（已解析第 {parsed_page_range} 页，共 {total_pages} 页）。"
                    f"这不是完整内容！"
                )
        else:
            # 未知页数（如 Word/Excel 等）
            if file_type in ['.docx', '.doc', '.odt', '.rtf']:
                warning_message = f"⚠️ 这是文档的部分内容（已解析第 {parsed_page_range} 页）。可能不是完整内容。"
            elif file_type in ['.xlsx', '.xls']:
                warning_message = f"⚠️ 这是 Excel 文档的部分内容（已解析第 {parsed_page_range} 个工作表）。"
            elif file_type == '.csv':
                warning_message = "⚠️ 这是 CSV 文件的部分内容。"
            elif file_type in ['.pptx', '.ppt']:
                warning_message = f"⚠️ 这是 PPT 的部分内容（已解析第 {parsed_page_range} 张）。"
            elif file_type == '.txt':
                warning_message = f"⚠️ 这是 TXT 文件的部分内容（已解析第 {parsed_page_range} 页）。"
            else:
                warning_message = f"⚠️ 这是文档概要（已解析第 {parsed_page_range} 页）。可能需要完整读取。"
        
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
            "message": f"文档概要已生成（已解析第 {parsed_page_range} 页）",  # 🆕 动态显示
            "data": {
                "summary": summary,
                "outline": outline,
                "preview": first_pages[:10]  # 减少到前10个元素，避免混淆
            },
            "metadata": {
                "source": source,
                "total_pages": total_pages,
                "parsed_pages": parsed_page_range,  # 🆕 显示实际解析的页码范围
                "parsed_page_count": parsed_page_count,  # 🆕 显示解析的页数
                "file_type": doc_info.get("file_type"),
                "file_size": doc_info.get("file_size"),
                "element_count": len(first_pages),
                "from_cache": False,
                "smart_overview": True  # 🆕 标记使用了智能页数选择
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
        
        🆕 支持自动分批处理：
        - 当单个范围页数超过 batch_size 时，自动拆分成多个批次
        - 每批独立处理，单个批次失败不影响其他批次
        - 显示批处理进度，便于追踪
        
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
        batch_size = self.config.pages_batch_size  # 默认 10 页/批
        
        # 逐个范围解析
        for range_idx, (start, end) in enumerate(page_ranges, 1):
            page_count = end - start + 1
            
            # 🆕 检查是否需要分批处理
            if page_count > batch_size:
                logger.info(f"⚠️ 页面范围较大 ({start}-{end}, 共{page_count}页)，自动分批处理（{batch_size}页/批）")
                
                # 计算批次数
                total_batches = (page_count + batch_size - 1) // batch_size
                
                # 分批处理
                for batch_idx in range(total_batches):
                    batch_start = start + batch_idx * batch_size
                    batch_end = min(batch_start + batch_size - 1, end)
                    batch_page_count = batch_end - batch_start + 1
                    
                    logger.info(f"   📦 批次 {batch_idx + 1}/{total_batches}: 第 {batch_start}-{batch_end} 页 ({batch_page_count}页)")
                    
                    try:
                        # 调用 API
                        result = await self._call_partition_api(
                            file_path=temp_file,
                            strategy=strategy,
                            user_id=user_id,
                            pages=f"{batch_start}-{batch_end}"
                        )
                        
                        all_elements.extend(result)
                        processing_details.append({
                            "pages": f"{batch_start}-{batch_end}",
                            "element_count": len(result),
                            "status": "success",
                            "batch_info": f"批次 {batch_idx + 1}/{total_batches}"
                        })
                        logger.info(f"      ✅ 成功: {len(result)} 个元素")
                        
                    except Exception as e:
                        logger.error(f"      ❌ 失败: {e}")
                        processing_details.append({
                            "pages": f"{batch_start}-{batch_end}",
                            "status": "failed",
                            "error": str(e),
                            "batch_info": f"批次 {batch_idx + 1}/{total_batches}"
                        })
            else:
                # 正常处理（不需要分批）
                logger.info(f"   处理第 {start}-{end} 页 ({page_count}页)")
                
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
                    logger.info(f"      ✅ 成功: {len(result)} 个元素")
                    
                except Exception as e:
                    logger.error(f"      ❌ 失败: {e}")
                    processing_details.append({
                        "pages": f"{start}-{end}",
                        "status": "failed",
                        "error": str(e)
                    })
        
        # 统计成功和失败的批次
        success_count = sum(1 for d in processing_details if d["status"] == "success")
        failed_count = sum(1 for d in processing_details if d["status"] == "failed")
        
        return {
            "success": True,
            "mode": "pages",
            "message": f"✅ 成功解析指定页面内容，共 {len(all_elements)} 个元素 (成功批次: {success_count}, 失败批次: {failed_count})",
            "data": {"elements": all_elements},
            "metadata": {
                "source": source,
                "total_pages": doc_info.get("total_pages"),
                "requested_pages": sum(e - s + 1 for s, e in page_ranges),
                "parsed_pages": sum(e - s + 1 for s, e in page_ranges),
                "element_count": len(all_elements),
                "strategy": strategy,
                "file_type": doc_info.get("file_type"),
                "file_size": doc_info.get("file_size"),
                "from_cache": False,
                "batch_size": batch_size,  # 🆕 记录批次大小
                "total_batches": len(processing_details),  # 🆕 总批次数
                "success_batches": success_count,  # 🆕 成功批次数
                "failed_batches": failed_count,  # 🆕 失败批次数
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
        
        # 🆕 构建友好的消息
        element_count = len(all_elements)
        file_type = doc_info.get("file_type", "")
        
        if total_pages:
            # 已知页数
            message = f"✅ 成功解析文档全部内容，共 {total_pages} 页，{element_count} 个元素"
        else:
            # 未知页数：根据文件类型给出具体说明
            if file_type in ['.docx', '.doc']:
                message = f"✅ 成功解析 Word 文档全部内容，{element_count} 个元素（Word 文档无精确页数概念）"
            elif file_type in ['.xlsx', '.xls']:
                message = f"✅ 成功解析 Excel 文档全部内容，{element_count} 个元素"
            elif file_type in ['.pptx', '.ppt']:
                message = f"✅ 成功解析 PowerPoint 文档全部内容，{element_count} 个元素"
            else:
                message = f"✅ 成功解析文档全部内容，{element_count} 个元素"
        
        # 🆕 检测可能的异常情况（元素数量过少）
        warning = None
        if element_count < 5:
            warning = (
                f"⚠️ 提醒：解析出的元素数量较少（{element_count} 个），可能的原因：\n"
                f"1. 文档本身内容较少\n"
                f"2. 文档格式特殊，API 解析能力有限\n"
                f"3. 文档文件可能损坏或不完整"
            )
        
        result = {
            "success": True,
            "mode": "full",
            "message": message,
            "data": {"elements": all_elements},
            "metadata": {
                "source": source,
                "total_pages": total_pages,
                "parsed_pages": total_pages if total_pages else "全部",
                "element_count": element_count,
                "strategy": strategy,
                "file_type": file_type,
                "file_size": doc_info.get("file_size"),
                "from_cache": False
            }
        }
        
        if warning:
            result["warning"] = warning
        
        return result


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
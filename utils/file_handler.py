"""
文件处理工具 - 支持图片和文档的编码与处理（异步版本）
用于 Claude API 的多模态输入
"""

import asyncio
import base64
import aiofiles
from logger import get_logger
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
import io

logger = get_logger(__name__)

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("PIL 未安装，图片压缩功能将不可用。运行: pip install Pillow")

try:
    import PyPDF2
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False
    logger.warning("PyPDF2 未安装，PDF 文本提取功能将不可用。运行: pip install PyPDF2")


class FileHandler:
    """文件处理工具类（异步版本）"""
    
    # 支持的图片格式
    SUPPORTED_IMAGE_FORMATS = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.webp': 'image/webp'
    }
    
    # 文件大小限制
    MAX_IMAGE_SIZE_MB = 5.0
    MAX_PDF_SIZE_MB = 30.0
    RECOMMENDED_IMAGE_SIZE_MB = 3.0
    
    def __init__(self, auto_compress: bool = True):
        """
        初始化文件处理器
        
        Args:
            auto_compress: 是否自动压缩过大的图片
        """
        self.auto_compress = auto_compress
        self._cache = {}  # 简单的编码缓存
    
    async def encode_image_to_base64(
        self,
        image_path: str,
        use_cache: bool = True
    ) -> Optional[Tuple[str, str]]:
        """
        将图片编码为 base64（异步）
        
        Args:
            image_path: 图片路径
            use_cache: 是否使用缓存
            
        Returns:
            (base64_data, media_type) 或 None（如果失败）
        """
        try:
            path = Path(image_path)
            
            # 检查缓存
            cache_key = f"image:{path.absolute()}"
            if use_cache and cache_key in self._cache:
                logger.debug(f"使用缓存的图片编码: {image_path}")
                return self._cache[cache_key]
            
            # 检查文件是否存在
            if not path.exists():
                logger.error(f"❌ 图片文件不存在: {image_path}")
                return None
            
            # 检查格式
            suffix = path.suffix.lower()
            if suffix not in self.SUPPORTED_IMAGE_FORMATS:
                logger.error(f"❌ 不支持的图片格式: {suffix}")
                return None
            
            media_type = self.SUPPORTED_IMAGE_FORMATS[suffix]
            
            # 检查文件大小
            size_mb = path.stat().st_size / (1024 * 1024)
            
            if size_mb > self.MAX_IMAGE_SIZE_MB:
                if self.auto_compress and PIL_AVAILABLE:
                    logger.warning(f"⚠️ 图片过大 ({size_mb:.2f}MB)，正在压缩...")
                    image_data = await self._compress_image(
                        image_path,
                        target_size_mb=self.MAX_IMAGE_SIZE_MB
                    )
                    compressed_mb = len(image_data) / (1024 * 1024)
                    if compressed_mb > self.MAX_IMAGE_SIZE_MB:
                        logger.error(
                            f"❌ 压缩后仍过大 ({compressed_mb:.2f}MB)，超过限制 {self.MAX_IMAGE_SIZE_MB}MB"
                        )
                        return None
                    size_mb = compressed_mb
                    media_type = 'image/jpeg'  # 压缩后统一为 JPEG
                else:
                    logger.error(f"❌ 图片过大 ({size_mb:.2f}MB)，超过限制 {self.MAX_IMAGE_SIZE_MB}MB")
                    return None
            elif size_mb > self.RECOMMENDED_IMAGE_SIZE_MB and self.auto_compress and PIL_AVAILABLE:
                logger.info(f"🔧 图片较大 ({size_mb:.2f}MB)，建议压缩以优化性能")
                image_data = await self._compress_image(
                    image_path,
                    target_size_mb=self.RECOMMENDED_IMAGE_SIZE_MB
                )
                compressed_mb = len(image_data) / (1024 * 1024)
                if compressed_mb > self.MAX_IMAGE_SIZE_MB:
                    logger.error(
                        f"❌ 压缩后仍过大 ({compressed_mb:.2f}MB)，超过限制 {self.MAX_IMAGE_SIZE_MB}MB"
                    )
                    return None
                size_mb = compressed_mb
                media_type = 'image/jpeg'
            else:
                # 异步读取文件
                async with aiofiles.open(image_path, 'rb') as f:
                    image_data = await f.read()
            
            # 编码为 base64
            encoded = base64.standard_b64encode(image_data).decode('utf-8')
            
            result = (encoded, media_type)
            
            # 缓存结果
            if use_cache:
                self._cache[cache_key] = result
            
            logger.info(f"✅ 图片编码成功: {image_path} ({size_mb:.2f}MB)")
            return result
            
        except Exception as e:
            logger.error(f"❌ 编码图片失败 ({image_path}): {e}")
            return None
    
    def _compress_image_sync(
        self,
        image_path: str,
        target_size_mb: float = None
    ) -> bytes:
        """
        同步压缩图片（CPU 密集型操作）
        
        Args:
            image_path: 图片路径
            target_size_mb: 目标大小（MB），默认为 RECOMMENDED_IMAGE_SIZE_MB
            
        Returns:
            压缩后的图片数据
        """
        if not PIL_AVAILABLE:
            raise ImportError("需要安装 Pillow 才能压缩图片")
        
        if target_size_mb is None:
            target_size_mb = self.RECOMMENDED_IMAGE_SIZE_MB
        
        img = Image.open(image_path)
        
        # 转换为 RGB（如果是 RGBA 或其他模式）
        if img.mode in ('RGBA', 'LA', 'P'):
            # 创建白色背景
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        # 如果图片太大，先调整分辨率
        max_dimension = 1568  # Claude 推荐的最大分辨率
        if max(img.size) > max_dimension:
            ratio = max_dimension / max(img.size)
            new_size = tuple(int(dim * ratio) for dim in img.size)
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            logger.info(f"   调整分辨率: {img.size}")
        
        # 逐步降低质量直到满足大小要求
        quality = 95
        buffer = io.BytesIO()
        while quality > 20:
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=quality, optimize=True)
            size_mb = buffer.tell() / (1024 * 1024)
            
            if size_mb <= target_size_mb:
                logger.info(f"   压缩完成: {size_mb:.2f}MB (质量: {quality})")
                return buffer.getvalue()
            
            quality -= 5
        
        # 如果还是太大，返回最后的结果
        logger.warning(f"   压缩后仍较大: {size_mb:.2f}MB")
        return buffer.getvalue()
    
    async def _compress_image(
        self,
        image_path: str,
        target_size_mb: float = None
    ) -> bytes:
        """
        异步压缩图片（使用线程池执行 CPU 密集型操作）
        
        Args:
            image_path: 图片路径
            target_size_mb: 目标大小（MB），默认为 RECOMMENDED_IMAGE_SIZE_MB
            
        Returns:
            压缩后的图片数据
        """
        return await asyncio.to_thread(
            self._compress_image_sync,
            image_path,
            target_size_mb
        )
    
    async def encode_pdf_to_base64(
        self,
        pdf_path: str,
        use_cache: bool = True
    ) -> Optional[str]:
        """
        将 PDF 编码为 base64（异步）
        
        Args:
            pdf_path: PDF 路径
            use_cache: 是否使用缓存
            
        Returns:
            base64_data 或 None（如果失败）
        """
        try:
            path = Path(pdf_path)
            
            # 检查缓存
            cache_key = f"pdf:{path.absolute()}"
            if use_cache and cache_key in self._cache:
                logger.debug(f"使用缓存的 PDF 编码: {pdf_path}")
                return self._cache[cache_key]
            
            # 检查文件是否存在
            if not path.exists():
                logger.error(f"❌ PDF 文件不存在: {pdf_path}")
                return None
            
            # 检查文件大小
            size_mb = path.stat().st_size / (1024 * 1024)
            if size_mb > self.MAX_PDF_SIZE_MB:
                logger.error(f"❌ PDF 过大 ({size_mb:.2f}MB)，超过限制 {self.MAX_PDF_SIZE_MB}MB")
                return None
            
            # 异步读取并编码
            async with aiofiles.open(pdf_path, 'rb') as f:
                pdf_content = await f.read()
                pdf_data = base64.standard_b64encode(pdf_content).decode('utf-8')
            
            # 缓存结果
            if use_cache:
                self._cache[cache_key] = pdf_data
            
            logger.info(f"✅ PDF 编码成功: {pdf_path} ({size_mb:.2f}MB)")
            return pdf_data
            
        except Exception as e:
            logger.error(f"❌ 编码 PDF 失败 ({pdf_path}): {e}")
            return None
    
    async def extract_text_from_pdf(self, pdf_path: str) -> Optional[str]:
        """
        从 PDF 提取纯文本（异步版本）
        
        使用 aiofiles 异步读取文件，然后用 PyPDF2 解析
        
        Args:
            pdf_path: PDF 路径
            
        Returns:
            提取的文本 或 None（如果失败）
        """
        if not PYPDF2_AVAILABLE:
            logger.error("❌ 需要安装 PyPDF2 才能提取 PDF 文本")
            return None
        
        try:
            path = Path(pdf_path)
            if not path.exists():
                logger.error(f"❌ PDF 文件不存在: {pdf_path}")
                return None
            
            # 异步读取文件内容
            async with aiofiles.open(pdf_path, 'rb') as f:
                content = await f.read()
            
            # 使用 BytesIO 传递给 PyPDF2
            reader = PyPDF2.PdfReader(io.BytesIO(content))
            num_pages = len(reader.pages)
            
            logger.info(f"📄 开始提取 PDF 文本: {pdf_path} ({num_pages} 页)")
            
            text_parts = []
            for i, page in enumerate(reader.pages):
                try:
                    page_text = page.extract_text()
                    if page_text and page_text.strip():
                        text_parts.append(f"=== 第 {i+1} 页 ===\n{page_text}\n")
                except Exception as e:
                    logger.warning(f"⚠️ 提取第 {i+1} 页失败: {e}")
            
            full_text = "\n".join(text_parts)
            logger.info(f"✅ PDF 文本提取完成: {len(full_text)} 字符")
            return full_text
                
        except Exception as e:
            logger.error(f"❌ 提取 PDF 文本失败 ({pdf_path}): {e}")
            return None
    
    async def create_image_content_block(
        self,
        image_path: str
    ) -> Optional[Dict[str, Any]]:
        """
        创建图片内容块（用于 Claude API）（异步）
        
        Args:
            image_path: 图片路径
            
        Returns:
            图片内容块字典 或 None
        """
        result = await self.encode_image_to_base64(image_path)
        if not result:
            return None
        
        image_data, media_type = result
        
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": image_data
            }
        }
    
    async def create_pdf_content_block(
        self,
        pdf_path: str
    ) -> Optional[Dict[str, Any]]:
        """
        创建 PDF 内容块（用于 Claude API）（异步）
        
        Args:
            pdf_path: PDF 路径
            
        Returns:
            PDF 内容块字典 或 None
        """
        pdf_data = await self.encode_pdf_to_base64(pdf_path)
        if not pdf_data:
            return None
        
        return {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": pdf_data
            }
        }
    
    async def create_multimodal_content(
        self,
        text: str,
        image_paths: List[str] = None,
        pdf_paths: List[str] = None
    ) -> List[Dict[str, Any]]:
        """
        创建多模态内容块列表（文本 + 图片 + PDF）（异步）
        
        Args:
            text: 文本内容
            image_paths: 图片路径列表
            pdf_paths: PDF 路径列表
            
        Returns:
            内容块列表
        """
        content_blocks = []
        
        # 添加文本
        if text:
            content_blocks.append({
                "type": "text",
                "text": text
            })
        
        # 添加 PDF（通常放在前面）
        if pdf_paths:
            for pdf_path in pdf_paths:
                block = await self.create_pdf_content_block(pdf_path)
                if block:
                    content_blocks.append(block)
        
        # 添加图片
        if image_paths:
            for image_path in image_paths:
                block = await self.create_image_content_block(image_path)
                if block:
                    content_blocks.append(block)
        
        return content_blocks
    
    async def estimate_image_tokens(self, image_path: str) -> int:
        """
        估算图片的 token 消耗（异步）
        
        Args:
            image_path: 图片路径
            
        Returns:
            估算的 token 数量
        """
        if not PIL_AVAILABLE:
            # 无法准确估算，返回平均值
            return 170
        
        try:
            # 使用线程池打开图片（I/O 操作）
            def _get_image_size():
                with Image.open(image_path) as img:
                    return img.size
            
            width, height = await asyncio.to_thread(_get_image_size)
            pixels = width * height
            
            # 粗略估算公式（基于 Claude 官方指南）
            if pixels < 500000:  # 小图片（< 500K 像素）
                return 85
            elif pixels < 1000000:  # 中等图片（< 1M 像素）
                return 170
            else:  # 大图片
                return 258
        except Exception as e:
            logger.warning(f"⚠️ 无法估算图片 token: {e}")
            return 170
    
    def clear_cache(self):
        """清除编码缓存"""
        self._cache.clear()
        logger.info("🗑️ 编码缓存已清除")


# ============================================================
# 便捷函数（异步）
# ============================================================

_default_handler = FileHandler()


async def encode_image(image_path: str) -> Optional[Tuple[str, str]]:
    """便捷函数：编码图片（异步）"""
    return await _default_handler.encode_image_to_base64(image_path)


async def encode_pdf(pdf_path: str) -> Optional[str]:
    """便捷函数：编码 PDF（异步）"""
    return await _default_handler.encode_pdf_to_base64(pdf_path)


async def create_image_block(image_path: str) -> Optional[Dict[str, Any]]:
    """便捷函数：创建图片内容块（异步）"""
    return await _default_handler.create_image_content_block(image_path)


async def create_pdf_block(pdf_path: str) -> Optional[Dict[str, Any]]:
    """便捷函数：创建 PDF 内容块（异步）"""
    return await _default_handler.create_pdf_content_block(pdf_path)


# ============================================================
# 使用示例
# ============================================================

if __name__ == "__main__":
    import logging
    
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    async def main():
        # 创建处理器
        handler = FileHandler(auto_compress=True)
        
        # 示例 1: 编码单张图片
        print("\n=== 示例 1: 编码图片 ===")
        result = await handler.encode_image_to_base64("example.jpg")
        if result:
            base64_data, media_type = result
            print(f"Media Type: {media_type}")
            print(f"Base64 长度: {len(base64_data)} 字符")
            tokens = await handler.estimate_image_tokens('example.jpg')
            print(f"估算 Token: {tokens}")
        
        # 示例 2: 创建多模态内容
        print("\n=== 示例 2: 创建多模态内容 ===")
        content = await handler.create_multimodal_content(
            text="请分析这些文件的内容",
            image_paths=["screenshot1.png", "screenshot2.png"],
            pdf_paths=["document.pdf"]
        )
        print(f"内容块数量: {len(content)}")
        for i, block in enumerate(content):
            print(f"  块 {i+1}: {block['type']}")
        
        # 示例 3: PDF 文本提取
        print("\n=== 示例 3: PDF 文本提取 ===")
        text = await handler.extract_text_from_pdf("large_document.pdf")
        if text:
            print(f"提取的文本长度: {len(text)} 字符")
            print(f"前 200 字符: {text[:200]}...")
    
    asyncio.run(main())

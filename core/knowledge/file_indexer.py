"""
文件索引器 - FileIndexer

将用户本地文件（txt/md/pdf/docx）分块索引到 FTS5 + sqlite-vec，
支持增量索引（hash check）。

使用示例：
    from core.knowledge.file_indexer import FileIndexer
    from core.knowledge.local_search import LocalKnowledgeManager

    km = LocalKnowledgeManager(semantic_enabled=True)
    indexer = FileIndexer(km)

    count = await indexer.index_directory(Path("~/Documents"), extensions=[".md", ".txt"])
    print(f"已索引 {count} 个文件")
"""

import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Set

import aiofiles

from logger import get_logger

logger = get_logger("knowledge.file_indexer")

# 默认支持的文件类型
SUPPORTED_EXTENSIONS: Set[str] = {".txt", ".md", ".pdf", ".docx"}

# 分块参数
CHUNK_SIZE = 1000  # 字符
CHUNK_OVERLAP = 100  # 重叠字符


class FileIndexer:
    """
    文件索引器

    读取文件 -> 分块 -> 生成 embedding -> 写入 FTS5 + sqlite-vec 索引。
    支持增量索引（通过 file hash 跳过未变更文件）。
    """

    def __init__(
        self,
        knowledge_manager: "LocalKnowledgeManager",
        index_dir: Optional[Path] = None,
        chunk_size: int = CHUNK_SIZE,
        chunk_overlap: int = CHUNK_OVERLAP,
    ):
        """
        Args:
            knowledge_manager: 知识管理器（FTS5 + 向量索引入口）
            index_dir: 索引元数据存储目录
            chunk_size: 分块大小（字符）
            chunk_overlap: 分块重叠（字符）
        """
        from core.knowledge.local_search import LocalKnowledgeManager

        self._km: LocalKnowledgeManager = knowledge_manager
        self._index_dir = index_dir
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._embedding_service = None
        # 内存缓存已索引文件的 hash（轻量级增量索引）
        self._indexed_hashes: Dict[str, str] = {}

    async def index_path(self, path: Path) -> bool:
        """
        索引单个文件

        Args:
            path: 文件路径

        Returns:
            是否成功索引
        """
        path = Path(path).resolve()

        if not path.exists() or not path.is_file():
            logger.warning(f"文件不存在: {path}")
            return False

        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            logger.debug(f"不支持的文件类型: {path.suffix}")
            return False

        # 增量检查：hash 未变则跳过
        file_hash = await self._compute_hash(path)
        cached_hash = self._indexed_hashes.get(str(path))
        if cached_hash == file_hash:
            logger.debug(f"文件未变更，跳过: {path.name}")
            return True

        # 读取文件内容
        content = await self._read_file(path)
        if not content or not content.strip():
            logger.debug(f"文件内容为空: {path.name}")
            return False

        # 分块
        chunks = self._split_chunks(content)
        title = path.stem  # 文件名作为标题

        # 先清除该文件的旧索引
        await self._km.remove_by_file_path(str(path))

        # 如果启用语义搜索，批量生成 embedding
        embeddings = await self._batch_embed(chunks)

        # 写入每个块
        for i, chunk in enumerate(chunks):
            doc_id = f"{path}:{i}"
            embedding = embeddings[i] if embeddings else None
            await self._km.add_document(
                doc_id=doc_id,
                title=title,
                content=chunk,
                file_path=str(path),
                file_type=path.suffix.lower(),
                chunk_index=i,
                embedding=embedding,
            )

        # 更新 hash 缓存
        self._indexed_hashes[str(path)] = file_hash

        logger.info(
            f"已索引: {path.name} ({len(chunks)} 块, "
            f"{len(content)} 字符, "
            f"向量: {'是' if embeddings else '否'})"
        )
        return True

    async def index_directory(
        self,
        directory: Path,
        extensions: Optional[List[str]] = None,
        max_file_size_mb: float = 10.0,
    ) -> int:
        """
        递归索引目录下的所有支持文件

        Args:
            directory: 目录路径
            extensions: 限定文件扩展名（默认全部支持类型）
            max_file_size_mb: 最大文件大小（MB）

        Returns:
            成功索引的文件数
        """
        directory = Path(directory).resolve()
        if not directory.exists() or not directory.is_dir():
            logger.warning(f"目录不存在: {directory}")
            return 0

        allowed_exts = set(extensions) if extensions else SUPPORTED_EXTENSIONS
        max_size = int(max_file_size_mb * 1024 * 1024)
        count = 0

        for path in directory.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in allowed_exts:
                continue
            if path.stat().st_size > max_size:
                logger.debug(
                    f"文件过大，跳过: {path.name} "
                    f"({path.stat().st_size / 1024 / 1024:.1f}MB)"
                )
                continue
            # 跳过隐藏文件和目录
            if any(part.startswith(".") for part in path.parts):
                continue

            if await self.index_path(path):
                count += 1

        logger.info(
            f"目录索引完成: {directory} ({count} 个文件)"
        )
        return count

    async def remove_path(self, path: Path) -> bool:
        """
        从索引中移除文件

        Args:
            path: 文件路径

        Returns:
            是否成功移除
        """
        path = Path(path).resolve()
        removed = await self._km.remove_by_file_path(str(path))
        self._indexed_hashes.pop(str(path), None)
        logger.info(f"已移除索引: {path.name} ({removed} 块)")
        return removed > 0

    # ==================== 文件读取 ====================

    async def _read_file(self, path: Path) -> str:
        """
        读取文件内容

        支持 txt/md（原生）、pdf/docx（可选依赖）。

        Args:
            path: 文件路径

        Returns:
            文件文本内容
        """
        suffix = path.suffix.lower()

        if suffix in {".txt", ".md"}:
            return await self._read_text(path)
        elif suffix == ".pdf":
            return await self._read_pdf(path)
        elif suffix == ".docx":
            return await self._read_docx(path)
        else:
            return ""

    async def _read_text(self, path: Path) -> str:
        """读取纯文本文件"""
        try:
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                return await f.read()
        except UnicodeDecodeError:
            # 尝试 GBK 编码
            try:
                async with aiofiles.open(path, "r", encoding="gbk") as f:
                    return await f.read()
            except Exception:
                logger.warning(f"文件编码无法识别: {path}")
                return ""

    async def _read_pdf(self, path: Path) -> str:
        """读取 PDF 文件（需要 pypdf）"""
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n\n".join(pages)
        except ImportError:
            logger.debug(
                "pypdf 未安装，跳过 PDF 索引（pip install pypdf）"
            )
            return ""
        except Exception as e:
            logger.warning(f"PDF 读取失败: {path} - {e}")
            return ""

    async def _read_docx(self, path: Path) -> str:
        """读取 DOCX 文件（需要 python-docx）"""
        try:
            from docx import Document

            doc = Document(str(path))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n\n".join(paragraphs)
        except ImportError:
            logger.debug(
                "python-docx 未安装，跳过 DOCX 索引（pip install python-docx）"
            )
            return ""
        except Exception as e:
            logger.warning(f"DOCX 读取失败: {path} - {e}")
            return ""

    # ==================== 分块 ====================

    def _split_chunks(self, content: str) -> List[str]:
        """
        将文本按固定大小分块（带重叠）

        Args:
            content: 原始文本

        Returns:
            文本块列表
        """
        if len(content) <= self._chunk_size:
            return [content]

        chunks = []
        start = 0
        while start < len(content):
            end = start + self._chunk_size
            chunk = content[start:end]

            # 尝试在段落/句子边界切分
            if end < len(content):
                # 优先找段落边界
                last_para = chunk.rfind("\n\n")
                if last_para > self._chunk_size * 0.5:
                    end = start + last_para + 2
                    chunk = content[start:end]
                else:
                    # 找句子边界
                    for sep in ["。", "！", "？", ".", "!", "?", "\n"]:
                        last_sep = chunk.rfind(sep)
                        if last_sep > self._chunk_size * 0.5:
                            end = start + last_sep + 1
                            chunk = content[start:end]
                            break

            chunks.append(chunk.strip())
            start = end - self._chunk_overlap

        return [c for c in chunks if c]

    # ==================== 向量嵌入 ====================

    async def _get_embedding_provider(self):
        """获取 embedding 提供商（通过知识管理器共享实例）"""
        return await self._km._get_embedding_provider()

    async def _batch_embed(
        self, chunks: List[str]
    ) -> Optional[List[List[float]]]:
        """
        批量生成文本块的 embedding

        使用 EmbeddingProvider 的批量接口，比逐条调用快 10-100x。
        如果知识管理器未启用语义搜索，返回 None。

        Args:
            chunks: 文本块列表

        Returns:
            向量列表（L2 归一化），或 None（未启用语义搜索）
        """
        if not self._km._semantic_enabled or not self._km._vec_initialized:
            return None

        try:
            provider = await self._get_embedding_provider()
            vectors = await provider.embed_batch(chunks)
            return [v.tolist() for v in vectors]
        except Exception as e:
            logger.warning(f"批量 embedding 失败: {e}")
            return None

    # ==================== 增量索引 ====================

    async def _compute_hash(self, path: Path) -> str:
        """计算文件 SHA256 hash"""
        hasher = hashlib.sha256()
        async with aiofiles.open(path, "rb") as f:
            while True:
                data = await f.read(8192)
                if not data:
                    break
                hasher.update(data)
        return hasher.hexdigest()

"""
工具结果压缩器

统一的工具结果压缩方案，实现"一次压缩、入库即压缩、可恢复"。

核心原则：
1. 工具执行后立即压缩（如果超过阈值）
2. 压缩格式：头部 + 本地文件引用 + 尾部
3. 完整内容存储到本地文件 + 数据库 metadata（双保险）
4. Agent 可通过文件路径自主访问完整内容
5. 入库时已是压缩格式，构建消息时不再二次压缩
"""

import hashlib
import json

from utils.app_paths import get_user_data_dir
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiofiles

from logger import get_logger

logger = get_logger("context.compaction.tool_result")

# 默认配置
DEFAULT_THRESHOLD = 1500  # 字符数阈值（对齐 config/context_compaction.yaml）
DEFAULT_HEAD_LINES = 5  # 保留开头行数
DEFAULT_TAIL_LINES = 3  # 保留结尾行数
DEFAULT_STORAGE_DIR = ""  # 空则使用 get_user_data_dir()/workspace/storage/tool_results

# 压缩标记前缀（用于识别已压缩的内容）
COMPRESSED_MARKER = "[COMPRESSED:"

# ---------- 按工具类型分流策略 ----------
# 搜索/API 类：强压缩，只保留摘要 + 文件路径
_SEARCH_TOOLS = {"web_search", "exa_search", "arxiv_search", "knowledge_search"}
# 读文件类：短文件不压缩、长文件写全文到文件 + 元信息预览
_FILE_READ_TOOLS = {"nodes"}
# 读文件时的"短文件"阈值（字符数），以下不压缩
_FILE_SHORT_THRESHOLD = 2000


class ToolResultCompressor:
    """
    统一的工具结果压缩器

    特点：
    - 一次压缩：工具执行后立即压缩
    - 可恢复：完整内容存本地文件 + 数据库 metadata
    - 格式统一：头部 + 文件引用 + 尾部

    使用示例：
        compressor = ToolResultCompressor()

        # 压缩工具结果
        text, metadata = await compressor.compress_if_needed(
            tool_name="web_search",
            tool_id="toolu_xxx",
            result=large_result
        )

        # 如果 metadata 不为 None，说明已压缩，需要存储到 message.extra_data
    """

    def __init__(
        self,
        threshold: int = DEFAULT_THRESHOLD,
        head_lines: int = DEFAULT_HEAD_LINES,
        tail_lines: int = DEFAULT_TAIL_LINES,
        storage_dir: str = DEFAULT_STORAGE_DIR,
    ):
        """
        初始化压缩器

        Args:
            threshold: 压缩阈值（字符数），超过此值则压缩
            head_lines: 保留开头行数
            tail_lines: 保留结尾行数
            storage_dir: 本地文件存储目录
        """
        self.threshold = threshold
        self.head_lines = head_lines
        self.tail_lines = tail_lines
        self.storage_dir = Path(storage_dir) if storage_dir else get_user_data_dir() / "workspace" / "storage" / "tool_results"

        # 确保存储目录存在
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # 统计信息
        self._stats = {
            "total_compressed": 0,
            "total_bytes_saved": 0,
        }

    async def compress_if_needed(
        self,
        tool_name: str,
        tool_id: str,
        result: Any,
        threshold_override: Optional[int] = None,
        preserve: bool = False,
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        If result exceeds threshold, compress according to tool type.

        Type-based strategies:
        - Search/API tools: extract top-N items + save full JSON to file.
        - File-read tools (nodes): short files (<2K) kept as-is for editing;
          long files saved to scratchpad with metadata preview.
        - Other tools: default head+tail compression.

        Args:
            tool_name: Tool name
            tool_id: Tool call ID
            result: Tool result (string or serializable object)
            threshold_override: Optional threshold override
            preserve: If True, skip compression (caller indicates this result
                      is being actively edited and must stay verbatim)

        Returns:
            (compressed_or_original_text, metadata_or_None)
        """
        # Skip compression if caller explicitly preserves (e.g., current edit target)
        if preserve:
            result_str = result if isinstance(result, str) else str(result)
            return result_str, None

        # Serialize result
        if isinstance(result, str):
            result_str = result
        else:
            try:
                result_str = json.dumps(result, ensure_ascii=False, indent=2)
            except (TypeError, ValueError):
                result_str = str(result)

        # Check threshold
        effective_threshold = threshold_override if threshold_override is not None else self.threshold
        if len(result_str) <= effective_threshold:
            return result_str, None

        # ---------- Type-based strategy selection ----------
        if tool_name in _SEARCH_TOOLS:
            return await self._compress_search_result(tool_name, tool_id, result_str)
        elif tool_name in _FILE_READ_TOOLS and len(result_str) > _FILE_SHORT_THRESHOLD:
            return await self._compress_file_read_result(tool_name, tool_id, result_str)
        else:
            return await self._compress_default(tool_name, tool_id, result_str)

    # ---------- Strategy: search / API ----------

    async def _compress_search_result(
        self, tool_name: str, tool_id: str, result_str: str,
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Save full search JSON to file; return top-N item summaries."""
        ref_id = self._generate_ref_id(tool_name, tool_id, result_str)
        file_path = await self._save_full_content(ref_id, tool_name, tool_id, result_str)

        # Try to extract structured items (JSON array of objects)
        top_n = 5
        preview_lines: List[str] = []
        try:
            data = json.loads(result_str)
            items = data if isinstance(data, list) else data.get("results", data.get("items", []))
            if isinstance(items, list):
                for i, item in enumerate(items[:top_n]):
                    title = item.get("title", item.get("name", ""))
                    url = item.get("url", item.get("link", ""))
                    snippet = item.get("snippet", item.get("abstract", item.get("summary", "")))
                    if snippet and len(snippet) > 200:
                        snippet = snippet[:200] + "..."
                    line = f"{i+1}. {title}"
                    if url:
                        line += f"  {url}"
                    if snippet:
                        line += f"\n   {snippet}"
                    preview_lines.append(line)
        except (json.JSONDecodeError, TypeError, AttributeError):
            # Fall back to head lines
            lines = result_str.split("\n")
            preview_lines = lines[:self.head_lines]

        preview = "\n".join(preview_lines) if preview_lines else result_str[:500]
        compressed_text = (
            f"{COMPRESSED_MARKER}{ref_id}] 搜索结果摘要 - {tool_name}\n"
            f"共 {len(result_str)} 字符 | Top {top_n} 条:\n\n"
            f"{preview}\n\n"
            f"完整内容: {file_path}\n"
            f"查看方式: cat {file_path}"
        )

        metadata = self._build_metadata(ref_id, file_path, result_str, tool_name, tool_id)
        self._update_stats(result_str, compressed_text, tool_name)
        return compressed_text, metadata

    # ---------- Strategy: file read (long) ----------

    async def _compress_file_read_result(
        self, tool_name: str, tool_id: str, result_str: str,
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Save full file content to scratchpad; return metadata + preview."""
        ref_id = self._generate_ref_id(tool_name, tool_id, result_str)
        file_path = await self._save_full_content(ref_id, tool_name, tool_id, result_str)

        lines = result_str.split("\n")
        total_lines = len(lines)
        preview = "\n".join(lines[:10])  # first 10 lines as preview

        compressed_text = (
            f"{COMPRESSED_MARKER}{ref_id}] 文件内容 - {tool_name}\n"
            f"总行数: {total_lines} | 总字符: {len(result_str)}\n\n"
            f"=== 前 10 行预览 ===\n{preview}\n\n"
            f"完整内容: {file_path}\n"
            f"按段读取: sed -n '起始行,结束行p' {file_path}\n"
            f"编辑时请按行范围读取需要修改的段落，不要整篇加载"
        )

        metadata = self._build_metadata(ref_id, file_path, result_str, tool_name, tool_id)
        self._update_stats(result_str, compressed_text, tool_name)
        return compressed_text, metadata

    # ---------- Strategy: default (head + tail) ----------

    async def _compress_default(
        self, tool_name: str, tool_id: str, result_str: str,
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Original head+tail compression with file backup."""
        ref_id = self._generate_ref_id(tool_name, tool_id, result_str)
        file_path = await self._save_full_content(ref_id, tool_name, tool_id, result_str)
        compressed_text = self._generate_compressed_text(tool_name, result_str, ref_id, file_path)
        metadata = self._build_metadata(ref_id, file_path, result_str, tool_name, tool_id)
        self._update_stats(result_str, compressed_text, tool_name)
        return compressed_text, metadata

    # ---------- Helpers ----------

    def _build_metadata(
        self, ref_id: str, file_path: Path, result_str: str,
        tool_name: str, tool_id: str,
    ) -> Dict[str, Any]:
        return {
            "ref_id": ref_id,
            "file_path": str(file_path),
            "original_length": len(result_str),
            "tool_name": tool_name,
            "tool_id": tool_id,
            "compressed_at": datetime.now().isoformat(),
        }

    def _update_stats(self, original: str, compressed: str, tool_name: str) -> None:
        self._stats["total_compressed"] += 1
        self._stats["total_bytes_saved"] += len(original) - len(compressed)
        logger.info(
            f"工具结果已压缩: {tool_name} "
            f"({len(original)} -> {len(compressed)} 字符, "
            f"节省 {len(original) - len(compressed)} 字符)"
        )

    def _generate_ref_id(self, tool_name: str, tool_id: str, content: str) -> str:
        """
        生成唯一的引用 ID

        Args:
            tool_name: 工具名称
            tool_id: 工具调用 ID
            content: 内容

        Returns:
            12 位十六进制引用 ID
        """
        hash_input = f"{tool_name}:{tool_id}:{len(content)}:{datetime.now().isoformat()}"
        return hashlib.md5(hash_input.encode()).hexdigest()[:12]

    async def _save_full_content(
        self, ref_id: str, tool_name: str, tool_id: str, content: str
    ) -> Path:
        """
        保存完整内容到本地文件

        Args:
            ref_id: 引用 ID
            tool_name: 工具名称
            tool_id: 工具调用 ID
            content: 完整内容

        Returns:
            文件路径
        """
        file_path = self.storage_dir / f"{ref_id}.json"

        # 构建存储对象
        storage_data = {
            "ref_id": ref_id,
            "tool_name": tool_name,
            "tool_id": tool_id,
            "created_at": datetime.now().isoformat(),
            "original_length": len(content),
            "content": content,
        }

        # 异步写入文件
        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(storage_data, ensure_ascii=False, indent=2))

        logger.debug(f"完整内容已保存: {file_path}")

        return file_path

    def _generate_compressed_text(
        self, tool_name: str, result_str: str, ref_id: str, file_path: Path
    ) -> str:
        """
        生成压缩后的文本

        格式：
        [COMPRESSED:ref_id] 工具结果摘要 - {tool_name}
        原始长度: {original_length} 字符

        === 开头 (前N行) ===
        {head_lines}

        === 完整内容 ===
        文件路径: {file_path}
        访问方式:
        - cat {file_path}
        - 或重新执行工具获取最新结果

        === 结尾 (后N行) ===
        {tail_lines}
        """
        lines = result_str.split("\n")

        # 提取开头和结尾
        head = "\n".join(lines[: self.head_lines])
        tail = "\n".join(lines[-self.tail_lines :]) if len(lines) > self.tail_lines else ""

        # 如果内容行数不多，可能开头和结尾有重叠
        if len(lines) <= self.head_lines + self.tail_lines:
            # 内容较短，只显示开头
            tail = ""

        # 构建压缩文本
        compressed_parts = [
            f"{COMPRESSED_MARKER}{ref_id}] 工具结果摘要 - {tool_name}",
            f"原始长度: {len(result_str)} 字符",
            "",
            f"=== 开头 (前{self.head_lines}行) ===",
            head,
            "",
            "=== 完整内容 ===",
            f"文件路径: {file_path}",
            "访问方式:",
            f"- cat {file_path}",
            "- 或重新执行工具获取最新结果",
        ]

        if tail:
            compressed_parts.extend(["", f"=== 结尾 (后{self.tail_lines}行) ===", tail])

        return "\n".join(compressed_parts)

    async def recover_full_content(self, ref_id: str) -> Optional[str]:
        """
        从本地文件恢复完整内容

        Args:
            ref_id: 引用 ID

        Returns:
            完整内容，如果文件不存在则返回 None
        """
        file_path = self.storage_dir / f"{ref_id}.json"

        if not file_path.exists():
            logger.warning(f"压缩内容文件不存在: {file_path}")
            return None

        try:
            async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                data = json.loads(await f.read())
                return data.get("content")
        except Exception as e:
            logger.error(f"读取压缩内容失败: {e}")
            return None

    def get_stats(self) -> Dict[str, Any]:
        """获取压缩统计信息"""
        return {
            **self._stats,
            "storage_dir": str(self.storage_dir),
            "threshold": self.threshold,
        }

    def reset_stats(self):
        """重置统计信息"""
        self._stats = {
            "total_compressed": 0,
            "total_bytes_saved": 0,
        }


def is_compressed(content: str) -> bool:
    """
    检查内容是否已被压缩

    Args:
        content: 内容字符串

    Returns:
        是否已压缩
    """
    return content.startswith(COMPRESSED_MARKER)


def extract_ref_id(content: str) -> Optional[str]:
    """
    从压缩内容中提取引用 ID

    Args:
        content: 压缩后的内容

    Returns:
        引用 ID，如果不是压缩内容则返回 None
    """
    if not is_compressed(content):
        return None

    try:
        # 格式: [COMPRESSED:ref_id] ...
        end_idx = content.index("]")
        return content[len(COMPRESSED_MARKER) : end_idx]
    except (ValueError, IndexError):
        return None


# 便捷函数
async def compress_tool_result(
    tool_name: str, tool_id: str, result: Any, threshold: int = DEFAULT_THRESHOLD
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    压缩工具结果的便捷函数

    Args:
        tool_name: 工具名称
        tool_id: 工具调用 ID
        result: 工具结果
        threshold: 压缩阈值

    Returns:
        (压缩后的文本或原文本, 压缩元数据或 None)
    """
    compressor = ToolResultCompressor(threshold=threshold)
    return await compressor.compress_if_needed(tool_name, tool_id, result)

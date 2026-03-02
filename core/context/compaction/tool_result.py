"""
工具结果压缩器

统一的工具结果压缩方案，实现"一次压缩、入库即压缩、可恢复"。

核心原则：
1. 工具自治优先：工具通过 _compression_hint 自主声明压缩策略，
   压缩器不做硬编码工具分类（不再维护 _SEARCH_TOOLS / _FILE_READ_TOOLS）
2. 工具执行后立即压缩（如果超过阈值且工具未声明 skip）
3. 压缩格式：头部 + 本地文件引用 + 尾部
4. 完整内容存储到本地文件 + 数据库 metadata（双保险）
5. Agent 可通过文件路径自主访问完整内容
6. 入库时已是压缩格式，构建消息时不再二次压缩

_compression_hint 协议（工具在返回 dict 中设置）：
- "skip"   : 不压缩（工具声明 Agent 需要完整内容）
- "normal" : 按默认阈值压缩（或不设置 hint 走默认逻辑）
- "force"  : 使用较低阈值强制压缩
- "search" : 搜索结果专用压缩（提取 top-N 条目摘要）
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
DEFAULT_HEAD_LINES = 10   # 保留开头行数
DEFAULT_TAIL_LINES = 5    # 保留结尾行数
DEFAULT_STORAGE_DIR = ""  # 空则使用 get_user_data_dir()/workspace/storage/tool_results

# 压缩标记前缀（用于识别已压缩的内容）
COMPRESSED_MARKER = "[COMPRESSED:"


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
        self.threshold = threshold
        self.head_lines = head_lines
        self.tail_lines = tail_lines
        self.storage_dir = Path(storage_dir) if storage_dir else get_user_data_dir() / "workspace" / "storage" / "tool_results"

        self.storage_dir.mkdir(parents=True, exist_ok=True)

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
        hint: Optional[str] = None,
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        If result exceeds threshold, compress using the requested strategy.

        Strategy selection (in priority order):
        1. preserve=True → never compress
        2. hint="skip"   → never compress
        3. hint="search" → search-specific compression (top-N items)
        4. hint="force"  → compress with low threshold (500 chars)
        5. Default       → head+tail compression when over threshold

        Args:
            tool_name: Tool name
            tool_id: Tool call ID
            result: Tool result (string or serializable object)
            threshold_override: Optional threshold override
            preserve: If True, skip compression
            hint: Compression hint from the tool (_compression_hint value)

        Returns:
            (compressed_or_original_text, metadata_or_None)
        """
        if preserve or hint == "skip":
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

        # Determine effective threshold
        if hint == "force":
            effective_threshold = self._get_force_threshold()
        elif threshold_override is not None:
            effective_threshold = threshold_override
        else:
            effective_threshold = self.threshold

        if len(result_str) <= effective_threshold:
            return result_str, None

        # Strategy selection based on hint
        if hint == "search":
            return await self._compress_search_result(tool_name, tool_id, result_str)
        else:
            return await self._compress_default(tool_name, tool_id, result_str)

    @staticmethod
    def _get_force_threshold() -> int:
        """Read force_threshold_chars from config, default 500."""
        try:
            import yaml
            from pathlib import Path

            for path in [
                Path("config/context_compaction.yaml"),
                Path(__file__).resolve().parents[3] / "config" / "context_compaction.yaml",
            ]:
                if path.exists():
                    with open(path, "r", encoding="utf-8") as f:
                        config = yaml.safe_load(f) or {}
                    return config.get("tool_result_compression", {}).get(
                        "force_threshold_chars", 500
                    )
        except Exception:
            pass
        return 500

    # ---------- Strategy: search / API ----------

    async def _compress_search_result(
        self, tool_name: str, tool_id: str, result_str: str,
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Save full search JSON to file; return top-N item summaries."""
        ref_id = self._generate_ref_id(tool_name, tool_id, result_str)
        file_path = await self._save_full_content(ref_id, tool_name, tool_id, result_str)

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
        hash_input = f"{tool_name}:{tool_id}:{len(content)}:{datetime.now().isoformat()}"
        return hashlib.md5(hash_input.encode()).hexdigest()[:12]

    async def _save_full_content(
        self, ref_id: str, tool_name: str, tool_id: str, content: str
    ) -> Path:
        file_path = self.storage_dir / f"{ref_id}.json"

        storage_data = {
            "ref_id": ref_id,
            "tool_name": tool_name,
            "tool_id": tool_id,
            "created_at": datetime.now().isoformat(),
            "original_length": len(content),
            "content": content,
        }

        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(storage_data, ensure_ascii=False, indent=2))

        logger.debug(f"完整内容已保存: {file_path}")

        return file_path

    def _generate_compressed_text(
        self, tool_name: str, result_str: str, ref_id: str, file_path: Path
    ) -> str:
        lines = result_str.split("\n")

        head = "\n".join(lines[: self.head_lines])
        tail = "\n".join(lines[-self.tail_lines :]) if len(lines) > self.tail_lines else ""

        if len(lines) <= self.head_lines + self.tail_lines:
            tail = ""

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
        return {
            **self._stats,
            "storage_dir": str(self.storage_dir),
            "threshold": self.threshold,
        }

    def reset_stats(self):
        self._stats = {
            "total_compressed": 0,
            "total_bytes_saved": 0,
        }


def is_compressed(content: str) -> bool:
    return content.startswith(COMPRESSED_MARKER)


def extract_ref_id(content: str) -> Optional[str]:
    if not is_compressed(content):
        return None

    try:
        end_idx = content.index("]")
        return content[len(COMPRESSED_MARKER) : end_idx]
    except (ValueError, IndexError):
        return None


async def compress_tool_result(
    tool_name: str,
    tool_id: str,
    result: Any,
    threshold: int = DEFAULT_THRESHOLD,
    hint: Optional[str] = None,
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    压缩工具结果的便捷函数

    Args:
        tool_name: 工具名称
        tool_id: 工具调用 ID
        result: 工具结果
        threshold: 压缩阈值
        hint: 压缩策略提示 ("skip"/"normal"/"force"/"search")

    Returns:
        (压缩后的文本或原文本, 压缩元数据或 None)
    """
    compressor = ToolResultCompressor(threshold=threshold)
    return await compressor.compress_if_needed(tool_name, tool_id, result, hint=hint)

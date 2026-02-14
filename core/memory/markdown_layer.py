"""
Markdown 记忆文件层 - MarkdownMemoryLayer

Layer 1：用户可见可编辑的记忆存储。

文件结构：
    base_dir/
    ├── MEMORY.md              # 全局长期记忆（用户可直接编辑）
    ├── memory/
    │   ├── 2025-02-06.md      # 每日日志（自动追加）
    │   └── 2025-02-05.md
    └── projects/
        └── {project_id}/
            └── MEMORY.md      # 项目级记忆

设计原则：
- 全部使用 aiofiles 异步 I/O
- MEMORY.md 格式遵循架构设计（## 关于你 / ## 偏好 / ## 常用工具 / ## 历史经验）
- 首次访问自动创建模板文件
- append_to_section() 通过解析 Markdown 标题定位插入
"""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import aiofiles
import aiofiles.os

from logger import get_logger

logger = get_logger("memory.markdown_layer")

# MEMORY.md 默认模板
_MEMORY_TEMPLATE = """# 小搭子的记忆

> 这是小搭子对你的了解。你可以直接编辑这个文件，小搭子会自动学习更新。

## 基本信息

- （小搭子还不了解你，多聊聊吧~）

## 关于你

## 偏好

### 写作风格

### 工作习惯

## 常用工具

## 历史经验

### 成功案例

### 需要改进

"""


@dataclass
class MemoryEntry:
    """解析后的记忆条目"""

    section: str  # 所属段落标题（如 "偏好/写作风格"）
    content: str  # 条目内容
    source: str = "MEMORY.md"  # 来源文件


@dataclass
class SectionWriteResult:
    """Result of append_to_section, enabling callers to do CRUD on indexes."""

    action: str  # "appended" | "replaced" | "skipped"
    old_content: str = ""  # replaced: the old entry content (for index delete)


class MarkdownMemoryLayer:
    """
    Layer 1: Markdown 文件层

    管理 MEMORY.md（全局记忆）和每日日志文件。
    """

    def __init__(self, base_dir: Optional[Path] = None):
        """
        Args:
            base_dir: Memory root directory (required, set by InstanceMemoryManager)
        """
        if not base_dir:
            raise ValueError(
                "base_dir is required. Caller must pass "
                "get_instance_memory_dir(instance_name)."
            )
        self._base_dir = Path(base_dir)
        self._memory_file = self._base_dir / "MEMORY.md"
        self._log_dir = self._base_dir / "memory"

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    @property
    def memory_file(self) -> Path:
        return self._memory_file

    # ==================== 全局记忆 ====================

    async def read_global_memory(self) -> str:
        """
        读取 MEMORY.md 全文

        首次访问时自动创建模板文件。

        Returns:
            MEMORY.md 的完整内容
        """
        await self._ensure_memory_file()
        async with aiofiles.open(self._memory_file, "r", encoding="utf-8") as f:
            return await f.read()

    async def write_global_memory(self, content: str) -> None:
        """
        覆写 MEMORY.md 全文

        Args:
            content: 新的完整内容
        """
        await self._ensure_dir(self._base_dir)
        async with aiofiles.open(self._memory_file, "w", encoding="utf-8") as f:
            await f.write(content)
        logger.debug("MEMORY.md 已更新")

    async def append_to_section(
        self, section: str, content: str, replace_by_key: bool = False
    ) -> SectionWriteResult:
        """
        向 MEMORY.md 的指定段落追加或替换内容。

        通过解析 Markdown 标题定位插入位置。
        如果段落不存在，在文件末尾新建段落。
        如果完全相同的内容已存在于该段落中，跳过写入。

        Args:
            section: 段落标题（如 "偏好"、"偏好/写作风格"）
            content: 要追加的内容
            replace_by_key: If True, "KEY: VALUE" entries replace existing
                entries with the same KEY prefix (last-write-wins).
                Format-level dedup rule: LLM decides what to write,
                storage layer ensures no duplicate keys within a section.

        Returns:
            SectionWriteResult with action and old_content (for CRUD on indexes).
        """
        full_text = await self.read_global_memory()
        lines = full_text.split("\n")

        # 解析 section 层级（如 "偏好/写作风格" -> 找 ## 偏好 下的 ### 写作风格）
        parts = section.split("/")
        target_title = parts[-1].strip()

        # 查找目标标题行
        insert_idx = self._find_section_end(lines, target_title)

        # Normalize entry text for comparison
        entry = content if content.startswith("-") else f"- {content}"
        entry_stripped = entry.strip()

        if insert_idx is not None:
            # Exact dedup: check if identical content already exists in section
            section_start = self._find_section_start(lines, target_title)
            if section_start is not None:
                for i in range(section_start, insert_idx):
                    if lines[i].strip() == entry_stripped:
                        logger.debug(
                            f"去重跳过 [{section}]: {content[:50]}..."
                        )
                        return SectionWriteResult(action="skipped")

            # Replace-by-key: for "KEY: VALUE" entries, replace existing
            # entries with the same key prefix (last-write-wins).
            if replace_by_key and section_start is not None:
                entry_text = entry_stripped.lstrip("- ").strip()
                if ":" in entry_text or "：" in entry_text:
                    sep = ":" if ":" in entry_text else "："
                    new_key = entry_text.split(sep)[0].strip()
                    for i in range(insert_idx - 1, section_start - 1, -1):
                        existing = lines[i].strip().lstrip("- ").strip()
                        if ":" in existing or "：" in existing:
                            esep = ":" if ":" in existing else "："
                            existing_key = existing.split(esep)[0].strip()
                            if existing_key == new_key:
                                old_content = existing
                                lines[i] = entry
                                logger.info(
                                    f"Identity 覆盖 [{section}]: "
                                    f"'{old_content}' → "
                                    f"'{entry_stripped.lstrip('- ').strip()}'"
                                )
                                new_text = "\n".join(lines)
                                await self.write_global_memory(new_text)
                                return SectionWriteResult(
                                    action="replaced",
                                    old_content=old_content,
                                )

            # Remove template placeholders in this section before inserting
            if section_start is not None:
                for i in range(insert_idx - 1, section_start - 1, -1):
                    stripped = lines[i].strip().lstrip("- ").strip()
                    if stripped.startswith("（") and stripped.endswith("）"):
                        lines.pop(i)
                        if insert_idx > i:
                            insert_idx -= 1

            lines.insert(insert_idx, entry)
        else:
            # 段落不存在，在文件末尾新建
            level = "#" * (len(parts) + 1)  # ## 顶级, ### 子级
            lines.append("")
            lines.append(f"{level} {target_title}")
            lines.append("")
            lines.append(entry)

        new_text = "\n".join(lines)
        await self.write_global_memory(new_text)
        logger.debug(f"已追加到段落 [{section}]: {content[:50]}...")
        return SectionWriteResult(action="appended")

    # ==================== 每日日志 ====================

    async def read_daily_log(self, date: Optional[str] = None) -> str:  # UNUSED: daily logs are written but never read
        """
        读取每日日志

        Args:
            date: 日期字符串（YYYY-MM-DD），默认今天

        Returns:
            日志内容，文件不存在返回空字符串
        """
        date = date or datetime.now().strftime("%Y-%m-%d")
        log_file = self._log_dir / f"{date}.md"

        if not log_file.exists():
            return ""

        async with aiofiles.open(log_file, "r", encoding="utf-8") as f:
            return await f.read()

    async def append_daily_log(
        self, entry: str, date: Optional[str] = None
    ) -> None:
        """
        向每日日志追加条目

        Args:
            entry: 日志条目内容
            date: 日期字符串（YYYY-MM-DD），默认今天
        """
        date = date or datetime.now().strftime("%Y-%m-%d")
        log_file = self._log_dir / f"{date}.md"

        await self._ensure_dir(self._log_dir)

        # 如果文件不存在，先写标题
        if not log_file.exists():
            async with aiofiles.open(log_file, "w", encoding="utf-8") as f:
                await f.write(f"# {date} 日志\n\n")

        timestamp = datetime.now().strftime("%H:%M")
        async with aiofiles.open(log_file, "a", encoding="utf-8") as f:
            await f.write(f"- [{timestamp}] {entry}\n")

        logger.debug(f"每日日志已追加: {date} - {entry[:50]}...")

    # ==================== 项目级记忆 ====================

    async def read_project_memory(self, project_id: str) -> str:  # UNUSED: project memory system not integrated
        """
        读取项目级 MEMORY.md

        Args:
            project_id: 项目标识

        Returns:
            项目记忆内容，文件不存在返回空字符串
        """
        project_memory = (
            self._base_dir / "projects" / project_id / "MEMORY.md"
        )
        if not project_memory.exists():
            return ""

        async with aiofiles.open(project_memory, "r", encoding="utf-8") as f:
            return await f.read()

    async def append_project_memory(
        self, project_id: str, section: str, content: str
    ) -> bool:
        """
        向项目级 MEMORY.md 追加内容

        Args:
            project_id: 项目标识
            section: 段落标题
            content: 要追加的内容

        Returns:
            是否成功追加
        """
        project_dir = self._base_dir / "projects" / project_id
        project_memory = project_dir / "MEMORY.md"

        await self._ensure_dir(project_dir)

        if not project_memory.exists():
            # 创建项目记忆模板
            template = (
                f"# 项目记忆: {project_id}\n\n"
                f"> 这是「{project_id}」项目的专属记忆。\n\n"
                f"## 偏好\n\n## 历史经验\n\n"
            )
            async with aiofiles.open(project_memory, "w", encoding="utf-8") as f:
                await f.write(template)

        # 复用 append_to_section 逻辑
        async with aiofiles.open(project_memory, "r", encoding="utf-8") as f:
            full_text = await f.read()

        lines = full_text.split("\n")
        target_title = section.split("/")[-1].strip()
        insert_idx = self._find_section_end(lines, target_title)

        if insert_idx is not None:
            entry = content if content.startswith("-") else f"- {content}"
            lines.insert(insert_idx, entry)
        else:
            lines.extend(["", f"## {target_title}", "", f"- {content}"])

        async with aiofiles.open(project_memory, "w", encoding="utf-8") as f:
            await f.write("\n".join(lines))

        return True

    # ==================== 批量读取 ====================

    async def read_all_memories(self) -> List[MemoryEntry]:
        """
        解析 MEMORY.md 为结构化的记忆条目列表

        Returns:
            MemoryEntry 列表
        """
        text = await self.read_global_memory()
        return self._parse_memory_entries(text, "MEMORY.md")

    # ==================== 内部方法 ====================

    def _find_section_start(
        self, lines: List[str], target_title: str
    ) -> Optional[int]:
        """
        Find the line index right after the heading of target section.

        Args:
            lines: file lines
            target_title: section heading text (without # marks)

        Returns:
            Line index of first content line in section, or None.
        """
        pattern = re.compile(
            r"^(#{1,6})\s+" + re.escape(target_title) + r"\s*$"
        )
        for i, line in enumerate(lines):
            if pattern.match(line):
                return i + 1
        return None

    def _find_section_end(
        self, lines: List[str], target_title: str
    ) -> Optional[int]:
        """
        查找目标段落的末尾行号（用于插入新内容）

        Args:
            lines: 文件行列表
            target_title: 目标段落标题文本（不含 # 标记）

        Returns:
            插入位置的行号，None 表示未找到段落
        """
        target_pattern = re.compile(
            r"^(#{1,6})\s+" + re.escape(target_title) + r"\s*$"
        )

        found = False
        found_level = 0
        insert_idx = None

        for i, line in enumerate(lines):
            if not found:
                match = target_pattern.match(line)
                if match:
                    found = True
                    found_level = len(match.group(1))
                    insert_idx = i + 1
                    continue

            if found:
                # 检查是否遇到同级或更高级标题 → 段落结束
                heading_match = re.match(r"^(#{1,6})\s+", line)
                if heading_match and len(heading_match.group(1)) <= found_level:
                    # 回退到最后一个非空行之后
                    while insert_idx > 0 and not lines[insert_idx - 1].strip():
                        insert_idx -= 1
                    return insert_idx

                # 跟踪最后一个内容行的位置
                if line.strip():
                    insert_idx = i + 1

        if found:
            return insert_idx
        return None

    def _parse_memory_entries(
        self, text: str, source: str
    ) -> List[MemoryEntry]:
        """
        解析 Markdown 为记忆条目

        提取每个段落下的列表项（- 开头）。

        Args:
            text: Markdown 文本
            source: 来源文件名

        Returns:
            MemoryEntry 列表
        """
        entries: List[MemoryEntry] = []
        lines = text.split("\n")
        current_section = ""
        section_stack: List[str] = []

        for line in lines:
            heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if heading_match:
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()

                # 维护段落栈
                while section_stack and len(section_stack) >= level:
                    section_stack.pop()
                section_stack.append(title)
                current_section = "/".join(section_stack)
                continue

            # 列表项
            item_match = re.match(r"^\s*[-*]\s+(.+)$", line)
            if item_match and current_section:
                content = item_match.group(1).strip()
                # 跳过模板占位内容
                if content.startswith("（") and content.endswith("）"):
                    continue
                entries.append(
                    MemoryEntry(
                        section=current_section,
                        content=content,
                        source=source,
                    )
                )

        return entries

    async def _ensure_memory_file(self) -> None:
        """确保 MEMORY.md 存在，不存在则创建模板"""
        if self._memory_file.exists():
            return

        await self._ensure_dir(self._base_dir)
        async with aiofiles.open(self._memory_file, "w", encoding="utf-8") as f:
            await f.write(_MEMORY_TEMPLATE)
        logger.info(f"已创建 MEMORY.md: {self._memory_file}")

    async def _ensure_dir(self, path: Path) -> None:
        """确保目录存在"""
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)

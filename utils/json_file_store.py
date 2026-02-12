"""
JSON 文件存储工具
------------------------------------------------------------
目标：
- 不引入数据库（MySQL/MongoDB/SQLite）
- 提供"并发安全"的 JSON 读写：文件锁 + 原子写入
- 适用于 user_id / conversation_id / partition_id 等轻量元数据持久化

说明：
- 采用 POSIX flock（macOS/Linux 可用）
- 写入采用临时文件 + replace，避免写一半导致文件损坏
- 🆕 V10.3: 完全异步化，删除同步方法
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, TypeVar

import aiofiles

T = TypeVar("T")


@dataclass
class JsonFileStore:
    """一个简单的 JSON 文件存储（并发安全，完全异步）。"""

    path: Path
    default_factory: Callable[[], Dict[str, Any]]

    def _ensure_parent_dir(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _lock_file(self):
        """
        打开/锁定 lock 文件。
        使用单独的 .lock 文件，避免锁住目标 JSON 文件时影响读取/替换。
        """
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self._ensure_parent_dir()
        f = open(lock_path, "a+", encoding="utf-8")
        try:
            import fcntl  # POSIX only

            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        except Exception:
            # 如果锁不可用（极少数环境），退化为无锁；试验期可接受
            pass
        return f

    async def read_async(self) -> Dict[str, Any]:
        """异步读取 JSON（不存在则返回默认结构）。"""
        self._ensure_parent_dir()

        if not self.path.exists():
            return self.default_factory()

        try:
            async with aiofiles.open(self.path, "r", encoding="utf-8") as f:
                raw = await f.read()
            if not raw.strip():
                return self.default_factory()
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
            # 非 dict 结构，统一兜底
            return self.default_factory()
        except Exception:
            # 读取/解析失败，兜底返回默认结构
            return self.default_factory()

    async def write_async(self, data: Dict[str, Any]) -> None:
        """异步原子写入 JSON。"""
        self._ensure_parent_dir()

        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        async with aiofiles.open(tmp_path, "w", encoding="utf-8") as f:
            await f.write(payload)
        await asyncio.to_thread(os.replace, tmp_path, self.path)

    async def update_async(self, mutator: Callable[[Dict[str, Any]], T]) -> T:
        """
        异步读-改-写（带文件锁 + 原子写），并返回 mutator 的返回值。

        mutator：
        - 入参是 dict（当前数据）
        - 你可以直接原地修改
        - 返回值会原样返回

        注意：文件锁操作仍然是同步的，通过 asyncio.to_thread 包装
        """
        lock_f = await asyncio.to_thread(self._lock_file)
        try:
            data = await self.read_async()
            result = mutator(data)
            await self.write_async(data)
            return result
        finally:
            try:
                import fcntl

                await asyncio.to_thread(fcntl.flock, lock_f.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            lock_f.close()


def create_default_knowledge_store_dict() -> Dict[str, Any]:
    """Knowledge Store 默认结构（可随时扩展字段）。"""
    return {
        "version": 1,
        "users": {},  # user_id -> {created_at, metadata...}
        "conversations": {},  # conversation_id -> {user_id, created_at, last_seen_at, session_id?}
    }

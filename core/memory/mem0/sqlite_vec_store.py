"""
SQLite-Vec 向量存储适配器

将 sqlite-vec（SQLite 向量搜索扩展）适配为 Mem0 VectorStore 接口。
100% 本地运行，零外部服务依赖。

安装依赖：
    pip install sqlite-vec
"""

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from mem0.vector_stores.base import VectorStoreBase

from logger import get_logger

logger = get_logger("memory.mem0.sqlite_vec_store")


class OutputData:
    """搜索结果数据结构（与 Mem0 VectorStore 接口兼容）"""

    def __init__(self, id: str, score: float, payload: Dict) -> None:
        self.id = id
        self.score = score
        self.payload = payload or {}


class SqliteVecVectorStore(VectorStoreBase):
    """
    基于 sqlite-vec 的向量存储

    实现 Mem0 VectorStoreBase 接口，使用 SQLite + sqlite-vec 扩展。
    数据完全存储在本地 SQLite 文件中，无需任何外部服务。

    Args:
        collection_name: 集合名称（对应虚拟表名）
        embedding_model_dims: 向量维度（默认 1536，OpenAI text-embedding-3-small）
        db_path: SQLite 数据库文件路径（默认 data/local_store/mem0_vectors.db）
    """

    def __init__(
        self,
        collection_name: str = "mem0_memories",
        embedding_model_dims: int = 1536,
        db_path: Optional[str] = None,
    ):
        self.collection_name = collection_name
        self.embedding_model_dims = embedding_model_dims

        if not db_path:
            raise ValueError(
                "db_path is required. Use Mem0Config.db_path for "
                "instance-scoped path."
            )
        self._db_path = db_path

        # Single connection with check_same_thread=False.
        # Mem0 internally uses thread pools for add/search — the default
        # check_same_thread=True would raise "SQLite objects created in a
        # thread can only be used in that same thread".
        # WAL mode + single-writer semantics (Mem0 serializes operations)
        # makes this safe.
        self._conn = self._create_connection()
        self._ensure_table()

        logger.info(
            f"[SqliteVec] 初始化完成: db={self._db_path}, "
            f"collection={collection_name}, dims={embedding_model_dims}"
        )

    def _create_connection(self) -> sqlite3.Connection:
        """Create SQLite connection with sqlite-vec extension (cross-thread safe)."""
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")

        # 加载 sqlite-vec 扩展
        try:
            import sqlite_vec

            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
        except ImportError:
            # fallback: 尝试直接加载系统扩展
            try:
                conn.enable_load_extension(True)
                conn.load_extension("vec0")
                conn.enable_load_extension(False)
            except Exception as e:
                raise RuntimeError(
                    f"sqlite-vec 扩展不可用，请安装: pip install sqlite-vec\n错误: {e}"
                ) from e

        return conn

    def _ensure_table(self) -> None:
        """Ensure vector and metadata tables exist."""
        self._conn.execute(
            f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS [{self.collection_name}] USING vec0(
                id TEXT PRIMARY KEY,
                embedding FLOAT[{self.embedding_model_dims}]
            )
            """
        )
        self._conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS [{self.collection_name}_meta] (
                id TEXT PRIMARY KEY,
                payload TEXT DEFAULT '{{}}'
            )
            """
        )
        self._conn.commit()

    # ==================== Mem0 VectorStoreBase 接口实现 ====================

    def create_col(self, name: str, vector_size: int, distance: str) -> None:
        """创建集合（虚拟表 + 元数据表）"""
        self._conn.execute(
            f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS [{name}] USING vec0(
                id TEXT PRIMARY KEY,
                embedding FLOAT[{vector_size}]
            )
            """
        )
        self._conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS [{name}_meta] (
                id TEXT PRIMARY KEY,
                payload TEXT DEFAULT '{{}}'
            )
            """
        )
        self._conn.commit()
        logger.info(f"[SqliteVec] 集合创建成功: {name}")

    def insert(
        self,
        vectors: List[List[float]],
        payloads: Optional[List[Dict]] = None,
        ids: Optional[List[str]] = None,
    ):
        """插入向量"""
        if not ids:
            ids = [str(uuid.uuid4()) for _ in vectors]
        if not payloads:
            payloads = [{}] * len(vectors)

        for vec_id, vector, payload in zip(ids, vectors, payloads):
            embedding_json = json.dumps(vector)
            payload_json = json.dumps(payload, ensure_ascii=False)

            # 先删除再插入（幂等 upsert）
            self._conn.execute(
                f"DELETE FROM [{self.collection_name}] WHERE id = ?", (vec_id,)
            )
            self._conn.execute(
                f"INSERT INTO [{self.collection_name}](id, embedding) VALUES (?, ?)",
                (vec_id, embedding_json),
            )
            # 元数据
            self._conn.execute(
                f"INSERT OR REPLACE INTO [{self.collection_name}_meta](id, payload) "
                f"VALUES (?, ?)",
                (vec_id, payload_json),
            )

        self._conn.commit()
        logger.debug(f"[SqliteVec] 插入成功: {len(vectors)} 条")

    def search(
        self,
        query: str,
        vectors: List[List[float]],
        limit: int = 5,
        filters: Optional[Dict] = None,
    ) -> List[OutputData]:
        """搜索相似向量"""
        try:
            if not vectors:
                return []

            # 兼容单个向量（一维）和向量列表（二维）
            query_vector = (
                vectors[0] if vectors and isinstance(vectors[0], list) else vectors
            )
            query_json = json.dumps(query_vector)

            # sqlite-vec v0.1.6+ requires 'k = ?' constraint
            # instead of SQL LIMIT for vec0 KNN queries.
            cursor = self._conn.execute(
                f"""
                SELECT v.id, v.distance, m.payload
                FROM [{self.collection_name}] v
                LEFT JOIN [{self.collection_name}_meta] m ON v.id = m.id
                WHERE v.embedding MATCH ? AND k = ?
                ORDER BY v.distance
                """,
                (query_json, limit),
            )

            results = []
            for row in cursor.fetchall():
                vec_id, distance, payload_str = row
                try:
                    payload = json.loads(payload_str) if payload_str else {}
                except json.JSONDecodeError:
                    payload = {}

                # sqlite-vec 返回距离（越小越相似），转换为分数（越大越相似）
                score = 1.0 / (1.0 + distance) if distance >= 0 else 0.0
                results.append(
                    OutputData(id=vec_id, score=score, payload=payload)
                )

            logger.debug(f"[SqliteVec] 搜索完成: {len(results)} 条结果")
            return results

        except Exception as e:
            logger.error(f"[SqliteVec] 搜索失败: {e}")
            return []

    def delete(self, vector_id: str) -> None:
        """删除向量"""
        self._conn.execute(
            f"DELETE FROM [{self.collection_name}] WHERE id = ?", (vector_id,)
        )
        self._conn.execute(
            f"DELETE FROM [{self.collection_name}_meta] WHERE id = ?", (vector_id,)
        )
        self._conn.commit()
        logger.debug(f"[SqliteVec] 删除成功: {vector_id}")

    def update(
        self,
        vector_id: str,
        vector: Optional[List[float]] = None,
        payload: Optional[Dict] = None,
    ):
        """更新向量"""
        if vector is not None:
            embedding_json = json.dumps(vector)
            self._conn.execute(
                f"DELETE FROM [{self.collection_name}] WHERE id = ?", (vector_id,)
            )
            self._conn.execute(
                f"INSERT INTO [{self.collection_name}](id, embedding) VALUES (?, ?)",
                (vector_id, embedding_json),
            )

        if payload is not None:
            payload_json = json.dumps(payload, ensure_ascii=False)
            self._conn.execute(
                f"INSERT OR REPLACE INTO [{self.collection_name}_meta](id, payload) "
                f"VALUES (?, ?)",
                (vector_id, payload_json),
            )

        self._conn.commit()
        logger.debug(f"[SqliteVec] 更新成功: {vector_id}")

    def get(self, vector_id: str) -> Optional[OutputData]:
        """根据 ID 获取向量"""
        try:
            cursor = self._conn.execute(
                f"SELECT payload FROM [{self.collection_name}_meta] WHERE id = ?",
                (vector_id,),
            )
            row = cursor.fetchone()
            if row:
                try:
                    payload = json.loads(row[0]) if row[0] else {}
                except json.JSONDecodeError:
                    payload = {}
                return OutputData(id=vector_id, score=1.0, payload=payload)
            return None
        except Exception as e:
            logger.error(f"[SqliteVec] 获取失败: {e}")
            return None

    def list(
        self, filters: Optional[Dict] = None, limit: Optional[int] = None
    ) -> list:
        """
        List all memories.

        Returns:
            [results_list, total_count] — Mem0 expects list()[0] to
            be the results list (see Memory.delete_all).
        """
        try:
            # Filter by user_id if specified in filters
            where_clauses = []
            params: list = []

            if filters:
                # Mem0 passes {"user_id": "xxx"} — filter via payload JSON
                for key, value in filters.items():
                    where_clauses.append(
                        f"json_extract(payload, '$.{key}') = ?"
                    )
                    params.append(value)

            sql = f"SELECT id, payload FROM [{self.collection_name}_meta]"
            if where_clauses:
                sql += " WHERE " + " AND ".join(where_clauses)
            if limit:
                sql += " LIMIT ?"
                params.append(limit)

            cursor = self._conn.execute(sql, params)
            results = []
            for row in cursor.fetchall():
                vec_id, payload_str = row
                try:
                    payload = json.loads(payload_str) if payload_str else {}
                except json.JSONDecodeError:
                    payload = {}
                results.append(OutputData(id=vec_id, score=1.0, payload=payload))

            logger.debug(f"[SqliteVec] 列出记忆: {len(results)} 条")
            # Mem0 expects [results, count] tuple-like list
            return [results, len(results)]

        except Exception as e:
            logger.error(f"[SqliteVec] 列出记忆失败: {e}")
            return [[], 0]

    # ==================== 集合管理接口 ====================

    def list_cols(self) -> List[str]:
        """列出所有集合"""
        try:
            cursor = self._conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name LIKE '%_meta'"
            )
            return [row[0].replace("_meta", "") for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"[SqliteVec] 列出集合失败: {e}")
            return []

    def delete_col(self) -> None:
        """删除当前集合"""
        try:
            self._conn.execute(f"DROP TABLE IF EXISTS [{self.collection_name}]")
            self._conn.execute(
                f"DROP TABLE IF EXISTS [{self.collection_name}_meta]"
            )
            self._conn.commit()
            logger.info(f"[SqliteVec] 删除集合成功: {self.collection_name}")
        except Exception as e:
            logger.error(f"[SqliteVec] 删除集合失败: {e}")

    def col_info(self) -> Dict[str, Any]:
        """获取集合信息"""
        try:
            cursor = self._conn.execute(
                f"SELECT COUNT(*) FROM [{self.collection_name}_meta]"
            )
            count = cursor.fetchone()[0]
            return {
                "name": self.collection_name,
                "document_count": count,
                "dimensions": self.embedding_model_dims,
                "backend": "sqlite-vec",
            }
        except Exception as e:
            return {"name": self.collection_name, "error": str(e)}

    def reset(self) -> None:
        """重置集合（删除后重建）"""
        logger.info(f"[SqliteVec] 重置集合: {self.collection_name}")
        self.delete_col()
        self._ensure_table()

    def close(self) -> None:
        """关闭数据库连接"""
        if self._conn:
            self._conn.close()
            logger.info("[SqliteVec] 连接已关闭")

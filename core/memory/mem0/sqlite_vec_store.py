"""
SQLite-Vec 向量存储适配器

将 sqlite-vec（SQLite 向量搜索扩展）适配为 Mem0 VectorStore 接口。
100% 本地运行，零外部服务依赖。

功能：
- 向量搜索（sqlite-vec KNN）
- 关键词搜索（SQLite FTS5）— 从 payload.memory 自动建立全文索引
- 混合搜索支持：由 pool.py 在上层编排向量 + 关键词并行搜索

FTS5 方案设计（参考 https://www.sqlite.org/fts5.html）：
- 使用普通 FTS5 表（非 contentless），支持标准 DELETE FROM 语句
- 记忆数据量小（百~千级），存储冗余可忽略
- BM25 排序 + 归一化到 [0, 1]，与向量 score 可直接加权合并

安装依赖：
    pip install sqlite-vec
"""

import json
import math
import re
import sqlite3
import threading
import uuid
from typing import Any, Dict, List, Optional

from mem0.vector_stores.base import VectorStoreBase  # type: ignore[import-untyped]

from logger import get_logger

logger = get_logger("memory.mem0.sqlite_vec_store")


# ==================== 混合搜索参数 ====================

# BM25 归一化：abs(rank) / (1 + abs(rank))
# 与 knowledge/local_search.py 使用相同公式
DEFAULT_VECTOR_WEIGHT = 0.6
DEFAULT_TEXT_WEIGHT = 0.4
DEFAULT_MIN_SCORE = 0.35  # Mem0 记忆最低分阈值（方向 C）

# CJK 统一表意文字范围（覆盖中日韩常用汉字）
_CJK_RE = re.compile(
    r"([\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff])"
)


def _cjk_segmenter(text: str) -> str:
    """
    CJK 单字分词预处理。

    在每个 CJK 字符前后插入空格，让 FTS5 unicode61 tokenizer
    将每个汉字作为独立 token 索引。英文和数字保持原样（由 unicode61 处理）。

    示例:
        "老张是永辉项目负责人" → "老 张 是 永 辉 项 目 负 责 人"
        "用户偏好Python编程"  → "用 户 偏 好 Python 编 程"
        "FastAPI框架"         → "FastAPI 框 架"
    """
    if not text:
        return text
    return _CJK_RE.sub(r" \1 ", text).strip()


class OutputData:
    """搜索结果数据结构（与 Mem0 VectorStore 接口兼容）"""

    def __init__(self, id: str, score: float, payload: Dict) -> None:
        self.id = id
        self.score = score
        self.payload = payload or {}


class SqliteVecVectorStore(VectorStoreBase):
    """
    基于 sqlite-vec 的向量存储 + FTS5 关键词索引

    实现 Mem0 VectorStoreBase 接口，使用 SQLite + sqlite-vec 扩展。
    数据完全存储在本地 SQLite 文件中，无需任何外部服务。

    FTS5 全文索引与向量表同库同步，支持混合搜索：
    - 向量搜索（sqlite-vec KNN）：语义相似度
    - 关键词搜索（FTS5 BM25）：精确关键词匹配

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

        # Write-lock: Mem0 internally uses thread pools for add/search.
        # Multiple threads sharing one SQLite connection without
        # serialization causes "disk I/O error" under WAL mode.
        # All write methods (insert/update/delete) acquire this lock.
        self._write_lock = threading.Lock()

        # Single connection with check_same_thread=False.
        # Reads are safe without the lock; writes are serialized above.
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
        conn.execute("PRAGMA busy_timeout=5000")

        # 加载 sqlite-vec 扩展
        try:
            import sqlite_vec

            conn.enable_load_extension(True)
            # 使用 loadable_path() 获取扩展的绝对路径，避免系统路径找不到
            vec_path = sqlite_vec.loadable_path()
            conn.load_extension(vec_path)
            conn.enable_load_extension(False)
        except ImportError:
            raise RuntimeError(
                "sqlite-vec 未安装，请执行: pip install sqlite-vec"
            )
        except Exception as e:
            raise RuntimeError(
                f"sqlite-vec 扩展加载失败: {e}\n"
                f"请确认 sqlite-vec 已正确安装: pip install sqlite-vec"
            ) from e

        return conn

    @property
    def _fts_table_name(self) -> str:
        """FTS5 全文索引虚拟表名"""
        return f"{self.collection_name}_fts"

    def _ensure_table(self) -> None:
        """Ensure vector, metadata, and FTS5 tables exist."""
        # 1. sqlite-vec 向量表
        self._conn.execute(
            f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS [{self.collection_name}] USING vec0(
                id TEXT PRIMARY KEY,
                embedding FLOAT[{self.embedding_model_dims}]
            )
            """
        )
        # 2. 元数据表（Mem0 payload JSON）
        self._conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS [{self.collection_name}_meta] (
                id TEXT PRIMARY KEY,
                payload TEXT DEFAULT '{{}}'
            )
            """
        )
        # 3. FTS5 全文索引表
        #    普通 FTS5 表（非 contentless），支持标准 DELETE FROM 语句
        #    参考: https://www.sqlite.org/fts5.html#fts5_table_creation_and_initialization
        #    - id: UNINDEXED，仅存储不索引（用于 JOIN 回 _meta 表）
        #    - memory: 全文索引列（记忆文本）
        #    - user_id: UNINDEXED，用于按用户过滤
        #
        #    使用默认 unicode61 tokenizer + 应用层 CJK 单字分词预处理
        #    参考: https://www.sqlite.org/fts5.html#unicode61_tokenizer
        #    中文文本在写入前经过 _cjk_segmenter() 预处理（每字加空格），
        #    使 unicode61 能将每个汉字作为独立 token 索引。
        #    英文由 unicode61 原生处理（按空格/标点分词）。
        #    不使用 trigram（2 字中文词搜不到）或外部分词扩展（部署复杂）。
        self._conn.execute(
            f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS [{self._fts_table_name}]
            USING fts5(id UNINDEXED, memory, user_id UNINDEXED)
            """
        )
        self._conn.commit()

    # ==================== FTS5 同步方法 ====================

    def _sync_fts(self, vec_id: str, memory_text: str, user_id: str) -> None:
        """
        同步 FTS5 索引（先删后插，幂等 upsert）。

        写入前对文本做 CJK 单字分词预处理（_cjk_segmenter），
        确保中文字符被 unicode61 tokenizer 正确拆分为独立 token。

        必须在 _write_lock 内调用。
        参考: https://www.sqlite.org/fts5.html
        """
        try:
            # 先删除旧条目（FTS5 普通表支持标准 DELETE）
            self._conn.execute(
                f"DELETE FROM [{self._fts_table_name}] WHERE id = ?",
                (vec_id,),
            )
            # 插入新条目（CJK 预处理后写入）
            if memory_text and memory_text.strip():
                segmented = _cjk_segmenter(memory_text.strip())
                self._conn.execute(
                    f"INSERT INTO [{self._fts_table_name}](id, memory, user_id) "
                    f"VALUES (?, ?, ?)",
                    (vec_id, segmented, user_id),
                )
        except Exception as e:
            # FTS 同步失败不影响主流程（向量搜索仍可用）
            logger.debug(f"[SqliteVec] FTS5 同步失败 (non-fatal): {e}")

    # ==================== 关键词搜索 ====================

    def keyword_search(
        self,
        query: str,
        user_id: str,
        limit: int = 10,
    ) -> List[OutputData]:
        """
        FTS5 关键词搜索（BM25 排序）。

        泛化搜索策略：
        对查询做 CJK 单字分词后，提取所有 token，
        用隐式 AND 拼接（FTS5 默认行为：空格分隔 = AND）。
        BM25 自然排序——包含更多 token 的文档得分更高。

        参考:
        - https://www.sqlite.org/fts5.html#fts5_boolean_operators
          "implicit AND operators" — 空格分隔的 token 之间是隐式 AND
        - https://www.sqlite.org/fts5.html#the_bm25_function

        示例（CJK 预处理后）：
        - "老张" → "老 张" → MATCH '老 张'       → 匹配同时含"老"和"张"的记忆
        - "Python 编程" → "Python 编 程" → MATCH  → 匹配含 python + 编 + 程
        - "帮我写健身房文章" → 逐字 token          → 匹配含大部分字的记忆

        当 AND 无结果时，自动降级为 OR（扩大召回），
        BM25 排序保证包含更多 token 的结果排在前面。

        Args:
            query: 搜索关键词（原始文本，内部自动做 CJK 预处理）
            user_id: 用户 ID（过滤条件）
            limit: 返回数量

        Returns:
            OutputData 列表（score 已归一化到 [0, 1]）
        """
        if not query or not query.strip():
            return []

        try:
            # CJK 单字分词 + 转义
            segmented = _cjk_segmenter(query.strip())
            tokens = [t for t in segmented.split() if t.strip()]
            if not tokens:
                return []

            # 构建 FTS5 查询：token 之间空格分隔 = 隐式 AND
            # 参考: https://www.sqlite.org/fts5.html#fts5_boolean_operators
            fts_query = " ".join(t.replace('"', '""') for t in tokens)

            results = self._execute_fts_query(fts_query, user_id, limit)

            # AND 无结果 → 降级为 OR（扩大召回）
            if not results and len(tokens) > 1:
                or_query = " OR ".join(t.replace('"', '""') for t in tokens)
                results = self._execute_fts_query(or_query, user_id, limit)

            if results:
                logger.debug(
                    f"[SqliteVec] FTS5 搜索完成: query={query[:30]}, "
                    f"user_id={user_id}, 结果数={len(results)}"
                )
            return results

        except Exception as e:
            logger.debug(f"[SqliteVec] FTS5 搜索失败 (non-fatal): {e}")
            return []

    def _execute_fts_query(
        self, fts_query: str, user_id: str, limit: int
    ) -> List[OutputData]:
        """
        执行单次 FTS5 查询并返回结果。

        抽取为独立方法，避免 AND/OR 两种策略重复 SQL 代码。
        """
        cursor = self._conn.execute(
            f"""
            SELECT f.id, f.rank, m.payload
            FROM [{self._fts_table_name}] f
            LEFT JOIN [{self.collection_name}_meta] m ON f.id = m.id
            WHERE [{self._fts_table_name}] MATCH ?
              AND f.user_id = ?
            ORDER BY f.rank
            LIMIT ?
            """,
            (fts_query, user_id, limit),
        )

        results = []
        for row in cursor.fetchall():
            vec_id, rank, payload_str = row
            try:
                payload = json.loads(payload_str) if payload_str else {}
            except json.JSONDecodeError:
                payload = {}
            score = self._bm25_rank_to_score(rank)
            results.append(OutputData(id=vec_id, score=score, payload=payload))
        return results

    def rebuild_fts_index(self) -> int:
        """
        从 _meta 表重建 FTS5 索引。

        用于首次升级或索引损坏时的数据修复。
        参考: https://www.sqlite.org/fts5.html#the_rebuild_command

        Returns:
            重建的记录数
        """
        count = 0
        try:
            with self._write_lock:
                # 清空 FTS5 普通表：使用标准 DELETE FROM
                # 注: 'delete-all' 仅适用于 contentless/external content 表
                # 参考: https://www.sqlite.org/fts5.html#the_delete_all_command
                self._conn.execute(
                    f"DELETE FROM [{self._fts_table_name}]"
                )
                # 从 _meta 表重建
                cursor = self._conn.execute(
                    f"SELECT id, payload FROM [{self.collection_name}_meta]"
                )
                for row in cursor.fetchall():
                    vec_id, payload_str = row
                    try:
                        payload = json.loads(payload_str) if payload_str else {}
                    except json.JSONDecodeError:
                        continue
                    memory_text = payload.get("data", payload.get("memory", ""))
                    user_id = payload.get("user_id", "")
                    if memory_text and memory_text.strip():
                        segmented = _cjk_segmenter(memory_text.strip())
                        self._conn.execute(
                            f"INSERT INTO [{self._fts_table_name}](id, memory, user_id) "
                            f"VALUES (?, ?, ?)",
                            (vec_id, segmented, user_id),
                        )
                        count += 1
                self._conn.commit()
            logger.info(f"[SqliteVec] FTS5 索引重建完成: {count} 条记忆")
        except Exception as e:
            logger.error(f"[SqliteVec] FTS5 索引重建失败: {e}")
        return count

    # ==================== 工具方法 ====================

    @staticmethod
    def _bm25_rank_to_score(rank: float) -> float:
        """
        BM25 rank → 归一化分数 [0, 1]

        FTS5 bm25() 返回负数 rank（越小越相关）。
        公式：abs(rank) / (1 + abs(rank))
        - rank=-10 → 0.909（高相关）
        - rank=-5  → 0.833
        - rank=-1  → 0.500
        - rank=-0.1 → 0.091（低相关）
        - rank=0   → 0.000

        与 knowledge/local_search.py 使用相同公式，保证分数可比性。
        参考: https://www.sqlite.org/fts5.html#the_bm25_function
        """
        if rank is None or not math.isfinite(rank):
            return 0.0
        a = abs(rank)
        return a / (1.0 + a)

    # ==================== Mem0 VectorStoreBase 接口实现 ====================

    def create_col(self, name: str, vector_size: int, distance: str) -> None:
        """创建集合（虚拟表 + 元数据表，线程安全）"""
        with self._write_lock:
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
        """插入向量 + FTS5 索引（线程安全）"""
        if not ids:
            ids = [str(uuid.uuid4()) for _ in vectors]
        if not payloads:
            payloads = [{}] * len(vectors)

        with self._write_lock:
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
                # 同步 FTS5 索引
                memory_text = payload.get("data", payload.get("memory", ""))
                user_id = payload.get("user_id", "")
                self._sync_fts(vec_id, memory_text, user_id)

            self._conn.commit()
        logger.debug(f"[SqliteVec] 插入成功: {len(vectors)} 条")

    def search(
        self,
        query: str,
        vectors: List[List[float]],
        limit: int = 5,
        filters: Optional[Dict] = None,
    ) -> List[OutputData]:
        """搜索相似向量（支持 user_id 过滤）

        sqlite-vec KNN 查询（vec0 MATCH）不支持额外 WHERE 条件，
        因此采用"多取后过滤"策略：取 limit * 3 条候选，在应用层按
        payload.user_id 过滤，最终返回 limit 条。

        filters 支持:
        - {"user_id": "xxx"} — 按 user_id 过滤
        - {"metadata.key": "val"} — 按 metadata 字段过滤（json_extract）
        """
        try:
            if not vectors:
                return []

            # 兼容单个向量（一维）和向量列表（二维）
            query_vector = (
                vectors[0] if vectors and isinstance(vectors[0], list) else vectors
            )
            query_json = json.dumps(query_vector)

            # Extract user_id filter (if present) for post-KNN filtering
            filter_user_id = None
            if filters:
                filter_user_id = filters.get("user_id")

            # Over-fetch to compensate for post-KNN user_id filtering
            fetch_limit = limit * 3 if filter_user_id else limit

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
                (query_json, fetch_limit),
            )

            results = []
            for row in cursor.fetchall():
                vec_id, distance, payload_str = row
                try:
                    payload = json.loads(payload_str) if payload_str else {}
                except json.JSONDecodeError:
                    payload = {}

                # Post-KNN user_id filtering
                if filter_user_id:
                    record_user_id = payload.get("user_id", "")
                    if record_user_id != filter_user_id:
                        continue

                # sqlite-vec 返回距离（越小越相似），转换为分数（越大越相似）
                score = 1.0 / (1.0 + distance) if distance >= 0 else 0.0
                results.append(
                    OutputData(id=vec_id, score=score, payload=payload)
                )

                if len(results) >= limit:
                    break

            logger.debug(
                f"[SqliteVec] 搜索完成: {len(results)} 条结果"
                f"{f' (user_id={filter_user_id})' if filter_user_id else ''}"
            )
            return results

        except Exception as e:
            logger.error(f"[SqliteVec] 搜索失败: {e}")
            return []

    def delete(self, vector_id: str) -> None:
        """删除向量 + FTS5 索引（线程安全）"""
        with self._write_lock:
            self._conn.execute(
                f"DELETE FROM [{self.collection_name}] WHERE id = ?", (vector_id,)
            )
            self._conn.execute(
                f"DELETE FROM [{self.collection_name}_meta] WHERE id = ?", (vector_id,)
            )
            # FTS5 普通表：标准 DELETE FROM 语句
            try:
                self._conn.execute(
                    f"DELETE FROM [{self._fts_table_name}] WHERE id = ?",
                    (vector_id,),
                )
            except Exception:
                pass  # FTS 删除失败不影响主流程
            self._conn.commit()
        logger.debug(f"[SqliteVec] 删除成功: {vector_id}")

    def update(
        self,
        vector_id: str,
        vector: Optional[List[float]] = None,
        payload: Optional[Dict] = None,
    ):
        """更新向量 + FTS5 索引（线程安全）"""
        with self._write_lock:
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
                # 同步 FTS5 索引
                memory_text = payload.get("data", payload.get("memory", ""))
                user_id = payload.get("user_id", "")
                self._sync_fts(vector_id, memory_text, user_id)

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
        """删除当前集合（线程安全）"""
        try:
            with self._write_lock:
                self._conn.execute(f"DROP TABLE IF EXISTS [{self.collection_name}]")
                self._conn.execute(
                    f"DROP TABLE IF EXISTS [{self.collection_name}_meta]"
                )
                self._conn.execute(
                    f"DROP TABLE IF EXISTS [{self._fts_table_name}]"
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

            # FTS5 索引条数
            fts_count = 0
            try:
                fts_cursor = self._conn.execute(
                    f"SELECT COUNT(*) FROM [{self._fts_table_name}]"
                )
                fts_count = fts_cursor.fetchone()[0]
            except Exception:
                pass

            return {
                "name": self.collection_name,
                "document_count": count,
                "fts_count": fts_count,
                "dimensions": self.embedding_model_dims,
                "backend": "sqlite-vec + fts5",
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

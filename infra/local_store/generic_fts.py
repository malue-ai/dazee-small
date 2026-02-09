"""
通用 FTS5 全文搜索引擎

不绑定特定模型，支持任意表名和字段，供知识检索和记忆索引共用。

特性：
- 表名、字段名完全可配置
- BM25 排序
- snippet() 匹配片段高亮
- 幂等 upsert（先删后插）
- 异步操作（复用 infra/local_store/engine.py）

使用示例：
    from infra.local_store.generic_fts import GenericFTS5, FTS5TableConfig

    config = FTS5TableConfig(table_name="knowledge_fts")
    fts = GenericFTS5()

    async with get_local_session() as session:
        await fts.ensure_table(session, config)
        await fts.upsert(session, config, doc_id="d1", title="标题", content="正文")
        hits = await fts.search(session, config, query="关键词")
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from logger import get_logger

logger = get_logger("local_store.generic_fts")


@dataclass
class FTS5TableConfig:
    """FTS5 表配置"""

    table_name: str = "generic_fts"
    id_column: str = "doc_id"
    title_column: str = "title"
    content_column: str = "content"
    # 不索引但存储的附加列（UNINDEXED）
    extra_columns: List[str] = field(
        default_factory=lambda: ["source", "category"]
    )
    tokenizer: str = "unicode61 remove_diacritics 2"


@dataclass
class FTS5Hit:
    """FTS5 搜索命中结果"""

    doc_id: str
    title: str
    content: str
    rank: float  # BM25 得分（负数，越小越相关）
    snippet: str = ""  # 匹配片段（带高亮标记）
    extra: Dict[str, Any] = field(default_factory=dict)


class GenericFTS5:
    """
    通用 FTS5 全文搜索引擎

    不绑定任何特定模型，通过 FTS5TableConfig 配置表结构。
    """

    async def ensure_table(
        self, engine: AsyncEngine, config: FTS5TableConfig
    ) -> None:
        """
        创建 FTS5 虚拟表（如果不存在）

        Args:
            engine: SQLAlchemy AsyncEngine
            config: 表配置
        """
        # 组装 FTS5 建表 SQL
        columns = [
            f"{config.id_column} UNINDEXED",
            config.title_column,
            config.content_column,
        ]
        for col in config.extra_columns:
            columns.append(f"{col} UNINDEXED")

        cols_sql = ", ".join(columns)
        create_sql = (
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {config.table_name} "
            f"USING fts5({cols_sql}, tokenize='{config.tokenizer}')"
        )

        async with engine.begin() as conn:
            await conn.execute(sa_text(create_sql))

            # FTS5 官方推荐（文档 6.1）：设置 automerge 自动后台合并索引段
            # 减少索引碎片，避免搜索性能随写入量劣化
            try:
                await conn.execute(
                    sa_text(
                        f"INSERT INTO {config.table_name}({config.table_name}, rank) "
                        f"VALUES('automerge', 8)"
                    )
                )
            except Exception:
                pass  # 首次创建表时可能失败，不影响功能

        logger.info(
            f"FTS5 表已就绪: {config.table_name} "
            f"(索引列: {config.title_column}, {config.content_column}, "
            f"automerge=8)"
        )

    async def upsert(
        self,
        session: AsyncSession,
        config: FTS5TableConfig,
        doc_id: str,
        title: str,
        content: str,
        **extra: Any,
    ) -> None:
        """
        插入或更新文档（幂等：先删后插）

        Args:
            session: 数据库会话
            config: 表配置
            doc_id: 文档唯一标识
            title: 文档标题（参与索引）
            content: 文档内容（参与索引）
            **extra: 附加列值（不参与索引，仅存储）
        """
        if not content or not content.strip():
            return

        # CJK 字符级分割：让每个汉字独立成 token，解决 unicode61 将连续中文
        # 当作一个超长 token 导致子串搜索失败的问题。
        # 例："喜欢毒舌" → "喜 欢 毒 舌"，搜索 "喜 欢" 即可匹配。
        title = self._cjk_aware_split(title or "")
        content = self._cjk_aware_split(content)

        # 先删除旧记录（幂等）
        await session.execute(
            sa_text(
                f"DELETE FROM {config.table_name} "
                f"WHERE {config.id_column} = :doc_id"
            ),
            {"doc_id": doc_id},
        )

        # 构建插入 SQL
        all_columns = [
            config.id_column,
            config.title_column,
            config.content_column,
        ] + config.extra_columns

        placeholders = [":doc_id", ":title", ":content"] + [
            f":{col}" for col in config.extra_columns
        ]

        cols_sql = ", ".join(all_columns)
        vals_sql = ", ".join(placeholders)

        params: Dict[str, Any] = {
            "doc_id": doc_id,
            "title": title or "",
            "content": content,
        }
        for col in config.extra_columns:
            params[col] = extra.get(col, "")

        await session.execute(
            sa_text(
                f"INSERT INTO {config.table_name}({cols_sql}) "
                f"VALUES ({vals_sql})"
            ),
            params,
        )

    async def delete(
        self,
        session: AsyncSession,
        config: FTS5TableConfig,
        doc_id: str,
    ) -> None:
        """
        删除文档

        Args:
            session: 数据库会话
            config: 表配置
            doc_id: 文档唯一标识
        """
        await session.execute(
            sa_text(
                f"DELETE FROM {config.table_name} "
                f"WHERE {config.id_column} = :doc_id"
            ),
            {"doc_id": doc_id},
        )

    async def search(
        self,
        session: AsyncSession,
        config: FTS5TableConfig,
        query: str,
        limit: int = 20,
        offset: int = 0,
        where: Optional[Dict[str, str]] = None,
    ) -> List[FTS5Hit]:
        """
        全文搜索

        支持 FTS5 查询语法：
        - 普通搜索: "天气预报"
        - 短语搜索: '"今天天气"'
        - 前缀搜索: "天气*"
        - 布尔搜索: "天气 AND 上海"

        Args:
            session: 数据库会话
            config: 表配置
            query: FTS5 搜索查询
            limit: 返回数量
            offset: 偏移量
            where: 附加过滤条件 {"category": "preference"}

        Returns:
            FTS5Hit 列表（按 BM25 得分排序）
        """
        if not query or not query.strip():
            return []

        # 预处理查询：多词用 OR 连接（提高中英文混合召回率）
        sanitized_query = self._sanitize_query(query)

        # SQL 只做 MATCH 召回，UNINDEXED 列的过滤在 Python 层完成。
        # 原因：FTS5 UNINDEXED 列在 WHERE 中的行为因 SQLite 版本而异，
        # 后过滤兼容所有平台（macOS/Windows/Linux 内置 SQLite 版本各异）。
        # 对桌面端个人数据量（<10万条）后过滤性能开销 <1ms。
        fetch_limit = limit if not where else limit * 5  # 有过滤时多召回

        params: Dict[str, Any] = {
            "query": sanitized_query,
            "limit": fetch_limit,
            "offset": offset,
        }

        # 构建 extra 列选择
        extra_select = ""
        if config.extra_columns:
            extra_select = ", " + ", ".join(config.extra_columns)

        sql = f"""
            SELECT
                {config.id_column},
                {config.title_column},
                snippet({config.table_name}, 2, '<b>', '</b>', '...', 32),
                rank
                {extra_select}
            FROM {config.table_name}
            WHERE {config.table_name} MATCH :query
            ORDER BY rank
            LIMIT :limit OFFSET :offset
        """

        try:
            result = await session.execute(sa_text(sql), params)
        except Exception as e:
            error_msg = str(e).lower()
            if "fts5" in error_msg or "corrupt" in error_msg:
                # FTS5 索引损坏时自动重建（面向小白用户的容错）
                logger.warning(
                    f"FTS5 索引可能损坏，尝试自动重建: {e}"
                )
                try:
                    await self.rebuild(session, config)
                    result = await session.execute(sa_text(sql), params)
                except Exception:
                    logger.error("FTS5 自动重建失败", exc_info=True)
                    return []
            else:
                logger.error(f"FTS5 搜索失败: {e}", exc_info=True)
                return []

        rows = result.fetchall()

        hits = []
        for row in rows:
            extra_data = {}
            for i, col in enumerate(config.extra_columns):
                extra_data[col] = row[4 + i] if (4 + i) < len(row) else ""

            hits.append(
                FTS5Hit(
                    doc_id=row[0],
                    title=self._cjk_restore(row[1] or ""),
                    snippet=self._cjk_restore(row[2] or ""),
                    rank=row[3],
                    content="",  # snippet 已包含关键片段，不返回全文（节省内存）
                    extra=extra_data,
                )
            )

        # Python 层后过滤 UNINDEXED 列（兼容所有 SQLite 版本）
        if where:
            hits = [
                h for h in hits
                if all(h.extra.get(col) == val for col, val in where.items())
            ]

        return hits[:limit]

    async def count(
        self,
        session: AsyncSession,
        config: FTS5TableConfig,
        query: str,
        where: Optional[Dict[str, str]] = None,
    ) -> int:
        """
        获取搜索结果总数

        Args:
            session: 数据库会话
            config: 表配置
            query: FTS5 搜索查询
            where: 附加过滤条件

        Returns:
            匹配的文档数量
        """
        if not query or not query.strip():
            return 0

        # 无 UNINDEXED 过滤时直接 SQL COUNT
        if not where:
            sanitized_query = self._sanitize_query(query)
            sql = (
                f"SELECT COUNT(*) FROM {config.table_name} "
                f"WHERE {config.table_name} MATCH :query"
            )
            result = await session.execute(
                sa_text(sql), {"query": sanitized_query}
            )
            return result.scalar() or 0

        # 有 UNINDEXED 列过滤时走 search() + len()（Python 后过滤兼容性）
        hits = await self.search(
            session, config, query, limit=10000, where=where
        )
        return len(hits)

    async def get_full_content(
        self,
        session: AsyncSession,
        config: FTS5TableConfig,
        doc_id: str,
    ) -> Optional[str]:
        """
        获取文档完整内容（搜索只返回 snippet，此方法返回全文）

        Args:
            session: 数据库会话
            config: 表配置
            doc_id: 文档唯一标识

        Returns:
            文档内容，不存在则返回 None
        """
        result = await session.execute(
            sa_text(
                f"SELECT {config.content_column} FROM {config.table_name} "
                f"WHERE {config.id_column} = :doc_id"
            ),
            {"doc_id": doc_id},
        )
        row = result.fetchone()
        return self._cjk_restore(row[0]) if row else None

    async def rebuild(
        self,
        session: AsyncSession,
        config: FTS5TableConfig,
    ) -> None:
        """
        重建 FTS5 索引（修复损坏或优化性能）

        Args:
            session: 数据库会话
            config: 表配置
        """
        await session.execute(
            sa_text(
                f"INSERT INTO {config.table_name}({config.table_name}) "
                f"VALUES('rebuild')"
            )
        )
        logger.info(f"FTS5 索引已重建: {config.table_name}")

    async def integrity_check(
        self,
        session: AsyncSession,
        config: FTS5TableConfig,
    ) -> bool:
        """
        FTS5 索引完整性检查（SQLite 官方文档 6.7）

        比猜测异常消息更可靠的损坏检测方式。
        适合在应用启动时执行。

        Args:
            session: 数据库会话
            config: 表配置

        Returns:
            索引是否完整（True = 正常）
        """
        try:
            await session.execute(
                sa_text(
                    f"INSERT INTO {config.table_name}({config.table_name}) "
                    f"VALUES('integrity-check')"
                )
            )
            logger.debug(f"FTS5 完整性检查通过: {config.table_name}")
            return True
        except Exception as e:
            logger.warning(
                f"FTS5 完整性检查失败: {config.table_name} - {e}"
            )
            return False

    async def optimize(
        self,
        session: AsyncSession,
        config: FTS5TableConfig,
    ) -> None:
        """
        优化 FTS5 索引（SQLite 官方推荐定期执行）

        合并 b-tree 段，减少磁盘碎片，提升搜索性能。
        适合在应用空闲时或启动时执行。

        Args:
            session: 数据库会话
            config: 表配置
        """
        await session.execute(
            sa_text(
                f"INSERT INTO {config.table_name}({config.table_name}) "
                f"VALUES('optimize')"
            )
        )
        logger.info(f"FTS5 索引已优化: {config.table_name}")

    async def get_stats(
        self,
        session: AsyncSession,
        config: FTS5TableConfig,
    ) -> Dict[str, Any]:
        """
        获取索引统计信息

        Returns:
            {"total_docs": int, "table_name": str}
        """
        result = await session.execute(
            sa_text(f"SELECT COUNT(*) FROM {config.table_name}")
        )
        total = result.scalar() or 0
        return {
            "table_name": config.table_name,
            "total_docs": total,
        }

    @staticmethod
    def _sanitize_query(query: str) -> str:
        """
        预处理 FTS5 查询字符串（面向非技术用户的安全处理）

        SQLite FTS5 特殊字符（* ^ ( ) : "）如果被用户误输入会导致查询报错，
        对于面向小白用户的桌面应用需要主动防御。

        策略：
        1. CJK 字符级分割（与索引时一致）
        2. 移除 FTS5 特殊字符
        3. 保留用户显式使用的 AND/OR/NOT
        4. 多词用 OR 连接（提高召回率）

        Args:
            query: 原始查询（用户输入的自然语言）

        Returns:
            FTS5 安全查询字符串
        """
        import re

        query = query.strip()
        if not query:
            return query

        # 如果用户使用了引号短语搜索，保留原样
        if '"' in query and query.count('"') % 2 == 0:
            return query

        # 检测用户是否显式使用了 FTS5 布尔操作符
        has_bool_op = any(
            op in query.upper()
            for op in (" AND ", " OR ", " NOT ")
        )

        # 移除 FTS5 特殊字符
        # - * ^ ( ) [ ] { } : " + \ 是 FTS5 查询语法的保留字符
        # - `-` 在 FTS5 中等价于 NOT，必须移除
        # - `/` 不是 FTS5 语法字符但会产生无意义 token（如 Asia/Shanghai → Asia Shanghai）
        # - `.` 在 FTS5 中用于列过滤/隐式短语语法，会导致 syntax error
        #   （如时间戳 30.725Z → "fts5: syntax error near '.'"）
        query = re.sub(r'[*^()\[\]{}:"+\\/<>\-.]', " ", query)

        # 如果用户用了布尔操作符，清洗特殊字符后直接返回
        if has_bool_op:
            return re.sub(r"\s+", " ", query).strip()

        # CJK 字符级分割（与索引时一致，确保匹配）
        query = GenericFTS5._cjk_aware_split(query)

        # 合并连续空格
        query = re.sub(r"\s+", " ", query).strip()

        if not query:
            return ""

        # 按空格分词，过滤无效 token 后用 OR 连接
        # 无效 token：空字符串、纯标点、纯空白
        terms = [t for t in query.split() if t and re.search(r"\w", t)]
        if not terms:
            return ""
        if len(terms) == 1:
            return terms[0]

        return " OR ".join(terms)

    @staticmethod
    def _cjk_aware_split(text: str) -> str:
        """
        CJK 字符级分割

        SQLite FTS5 的 unicode61 tokenizer 将连续 CJK 字符视为一个 token，
        导致 "喜欢" 无法匹配 "喜欢毒舌但有干货的写作风格"（后者是一个完整 token）。

        解决方案：在每个 CJK 字符之间插入空格，使每个汉字独立成 token。
        英文单词保持不变。

        例：
        - "喜欢毒舌" → "喜 欢 毒 舌"
        - "Python 编程语言" → "Python 编 程 语 言"
        - "hello world" → "hello world"（不变）

        Args:
            text: 原始文本

        Returns:
            CJK 字符已分割的文本
        """
        import re

        if not text:
            return text

        # CJK 统一表意文字范围：U+4E00-U+9FFF（基本区）
        # 加上 U+3400-U+4DBF（扩展A）和 U+F900-U+FAFF（兼容区）
        # 在每个 CJK 字符前后插入空格
        result = re.sub(
            r"([\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF])",
            r" \1 ",
            text,
        )

        # 合并连续空格
        return re.sub(r"\s+", " ", result).strip()

    @staticmethod
    def _cjk_restore(text: str) -> str:
        """
        CJK 逆向合并：移除 CJK 字符之间被插入的空格

        与 _cjk_aware_split 互逆，用于还原搜索结果的展示文本。
        例："喜 欢 毒 舌" → "喜欢毒舌"
        英文单词间的空格保持不变："Python 编 程" → "Python 编程"

        Args:
            text: 经过 CJK 分割的文本

        Returns:
            还原后的自然文本
        """
        import re

        if not text:
            return text

        # 移除两个 CJK 字符之间的空格
        result = re.sub(
            r"([\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF])"
            r"\s+"
            r"([\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF])",
            r"\1\2",
            text,
        )
        # 需要多次执行（因为正则不重叠匹配，"喜 欢 毒" 第一次只合并 "喜欢 毒"）
        prev = None
        while prev != result:
            prev = result
            result = re.sub(
                r"([\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF])"
                r"\s+"
                r"([\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF])",
                r"\1\2",
                result,
            )

        return result.strip()

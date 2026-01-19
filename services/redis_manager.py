"""
Redis 会话管理器（异步版本）

负责 Session 的 Redis 存储和管理：
- Session 状态（status, progress, heartbeat）
- 事件缓冲（events buffer）
- 用户活跃 Sessions 列表

设计说明：
- 使用 redis.asyncio 实现真正的异步操作
- 所有方法都是异步的，避免阻塞事件循环
"""

import json
import asyncio
import redis.asyncio as redis
from typing import Dict, Any, List, Optional
from datetime import datetime
from logger import get_logger

logger = get_logger("redis_manager")


class RedisSessionManager:
    """Redis Session 管理器（异步版本）"""
    
    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
        redis_password: Optional[str] = None
    ):
        """
        初始化 Redis 连接
        
        Args:
            redis_host: Redis 主机
            redis_port: Redis 端口
            redis_db: Redis 数据库编号
            redis_password: Redis 密码（可选）
        """
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis_db = redis_db
        self.redis_password = redis_password
        self._client: Optional[redis.Redis] = None
    
    async def _get_client(self) -> redis.Redis:
        """
        获取或创建 Redis 客户端（懒加载）
        """
        if self._client is None:
            self._client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                db=self.redis_db,
                password=self.redis_password,
            decode_responses=True  # 自动解码为字符串
        )
        try:
            await self._client.ping()
        except Exception as e:
            logger.error(f"❌ Redis 连接失败: {str(e)}")
            self._client = None
            raise
        return self._client
    
    @property
    def client(self) -> redis.Redis:
        """
        获取客户端（同步访问，用于兼容旧代码的过渡期）
        注意：这会阻塞，请尽快迁移到异步方法
        """
        if self._client is None:
            # 同步创建连接（仅用于兼容）
            import redis as sync_redis
            sync_client = sync_redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                db=self.redis_db,
                password=self.redis_password,
                decode_responses=True
            )
            sync_client.ping()
            logger.warning("⚠️ 使用同步 Redis 客户端，建议迁移到异步方法")
            # 创建异步客户端以供后续使用
            self._client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                db=self.redis_db,
                password=self.redis_password,
                decode_responses=True
            )
        return self._client
    
    # ==================== Session 状态管理 ====================
    
    async def create_session(
        self,
        session_id: str,
        user_id: str,
        conversation_id: Optional[str] = None,
        message_id: Optional[str] = None,
        message_preview: str = ""
    ) -> None:
        """
        创建新的 Session
        
        Args:
            session_id: Session ID
            user_id: 用户 ID
            conversation_id: 对话 ID（可选）
            message_id: 消息 ID（可选）
            message_preview: 消息预览
        """
        client = await self._get_client()
        
        session_status = {
            "session_id": session_id,
            "user_id": user_id,
            "conversation_id": conversation_id or "",
            "message_id": message_id or "",
            "status": "running",
            "last_event_seq": "0",
            "start_time": datetime.now().isoformat(),
            "last_heartbeat": datetime.now().isoformat(),
            "progress": "0.0",
            "total_turns": "0",
            "message_preview": message_preview[:100]
        }
        
        # 保存 Session 状态
        await client.hset(
            f"session:{session_id}:status",
            mapping=session_status
        )
        
        # 添加到用户的活跃 sessions
        await client.sadd(f"user:{user_id}:sessions", session_id)
        await client.expire(f"user:{user_id}:sessions", 3600)
        
        # 初始化心跳
        await self.update_heartbeat(session_id)
        
        logger.info(f"✅ Session 已创建: {session_id}")
    
    async def get_session_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        获取 Session 状态
        
        Args:
            session_id: Session ID
            
        Returns:
            Session 状态字典，不存在则返回 None
        """
        client = await self._get_client()
        status = await client.hgetall(f"session:{session_id}:status")
        
        if not status:
            return None
        
        # 转换数字类型
        if "last_event_seq" in status:
            try:
                val = status["last_event_seq"]
                if val and val != 'None':
                    status["last_event_seq"] = int(val)
                else:
                    status["last_event_seq"] = 0
            except (ValueError, TypeError):
                status["last_event_seq"] = 0
        elif "last_event_id" in status:
            try:
                val = status["last_event_id"]
                if val and val != 'None':
                    status["last_event_seq"] = int(val)
                    status["last_event_id"] = int(val)
                else:
                    status["last_event_seq"] = 0
                    status["last_event_id"] = 0
            except (ValueError, TypeError):
                status["last_event_seq"] = 0
                status["last_event_id"] = 0
        
        if "progress" in status:
            try:
                val = status["progress"]
                if val and val != 'None':
                    status["progress"] = float(val)
                else:
                    status["progress"] = 0.0
            except (ValueError, TypeError):
                status["progress"] = 0.0
        
        if "total_turns" in status:
            try:
                val = status["total_turns"]
                if val and val != 'None':
                    status["total_turns"] = int(val)
                else:
                    status["total_turns"] = 0
            except (ValueError, TypeError):
                status["total_turns"] = 0
        
        return status
    
    async def update_session_status(
        self,
        session_id: str,
        **fields
    ) -> None:
        """
        更新 Session 状态
        
        Args:
            session_id: Session ID
            **fields: 要更新的字段
        """
        if not fields:
            return
        
        client = await self._get_client()
        
        # 转换为字符串，排除 None 值
        str_fields = {}
        for k, v in fields.items():
            if v is not None:
                str_fields[k] = str(v)
            else:
                if k in ["last_event_id", "last_event_seq"]:
                    str_fields[k] = "0"
                elif k == "progress":
                    str_fields[k] = "0.0"
                elif k == "total_turns":
                    str_fields[k] = "0"
                else:
                    str_fields[k] = ""
        
        await client.hset(
            f"session:{session_id}:status",
            mapping=str_fields
        )
    
    async def complete_session(
        self,
        session_id: str,
        status: str = "completed"
    ) -> None:
        """
        Session 完成（设置状态并添加过期时间）
        
        Args:
            session_id: Session ID
            status: 最终状态（completed/failed/timeout）
        """
        client = await self._get_client()
        
        # 更新状态
        await self.update_session_status(
            session_id,
            status=status,
            last_heartbeat=datetime.now().isoformat()
        )
        
        # 设置 TTL = 60 秒
        await client.expire(f"session:{session_id}:status", 60)
        await client.expire(f"session:{session_id}:events", 60)
        await client.expire(f"session:{session_id}:heartbeat", 60)
        
        # 从用户活跃列表移除
        status_data = await self.get_session_status(session_id)
        if status_data:
            user_id = status_data.get("user_id")
            if user_id:
                await client.srem(f"user:{user_id}:sessions", session_id)
        
        logger.info(f"✅ Session 已完成: {session_id}, status={status}")
    
    async def update_heartbeat(self, session_id: str) -> None:
        """
        更新心跳
        
        Args:
            session_id: Session ID
        """
        client = await self._get_client()
        now = datetime.now().isoformat()
        
        # 更新心跳时间戳（60秒 TTL）
        await client.set(
            f"session:{session_id}:heartbeat",
            now,
            ex=60
        )
        
        # 同步更新 status 中的 last_heartbeat
        await self.update_session_status(session_id, last_heartbeat=now)
    
    # ==================== 事件缓冲管理 ====================
    
    async def generate_session_seq(self, session_id: str) -> int:
        """
        生成 session 内的事件序号（从 1 开始递增）
        
        Args:
            session_id: Session ID
            
        Returns:
            Session 内的事件序号（1, 2, 3...）
        """
        client = await self._get_client()
        return await client.incr(f"session:{session_id}:seq_counter")
    
    async def get_session_context(self, session_id: str) -> Dict[str, Any]:
        """
        获取 session 上下文信息
        """
        status_data = await self.get_session_status(session_id)
        if not status_data:
            return {}
        
        return {
            "conversation_id": status_data.get("conversation_id"),
            "user_id": status_data.get("user_id")
        }
    
    async def buffer_event(
        self,
        session_id: str,
        event_data: Dict[str, Any] = None,
        event_id: int = None,
        event_type: str = None,
        timestamp: str = None,
        output_format: str = "zenflux",
        adapter=None
    ) -> Dict[str, Any]:
        """
        缓冲事件到 Redis 并通过 Pub/Sub 发布（统一入口）
        
        处理流程：
        1. 格式转换（如果 output_format != "zenflux"）
        2. 生成 seq（Redis INCR，原子操作）
        3. 存入 Redis List
        4. 通过 Pub/Sub 发布
        
        Args:
            session_id: Session ID
            event_data: 完整的事件字典（推荐）
            event_id: 事件 ID（可选，向后兼容）
            event_type: 事件类型（可选）
            timestamp: 时间戳（可选）
            output_format: 输出格式（zenflux/zeno），默认 zenflux
            adapter: 格式转换适配器（可选，用于 zeno 格式）
            
        Returns:
            添加了 seq 的完整事件
        """
        client = await self._get_client()
        
        # 方式1：传入完整事件字典
        if event_data is not None and isinstance(event_data, dict):
            event = event_data.copy()  # 不修改原对象
        # 方式2：分别传入字段（向后兼容）
        else:
            event = {
                "id": event_id,
                "type": event_type,
                "data": event_data,
                "timestamp": timestamp
            }
        
        # 1. 格式转换（如果需要）
        if output_format == "zeno" and adapter is not None:
            transformed = adapter.transform(event)
            if transformed is None:
                # 事件被适配器过滤，不需要存储
                return None
            event = transformed
        
        # 2. 生成 seq（Redis INCR，原子操作）
        # 只有当事件没有 seq 时才生成
        if "seq" not in event or event.get("seq") is None:
            seq_key = f"session:{session_id}:seq"
            seq = await client.incr(seq_key)
            
            # 首次创建设置 TTL（1小时）
            if seq == 1:
                await client.expire(seq_key, 3600)
            
            event["seq"] = seq
        
        # 3. 存入 Redis
        event_json = json.dumps(event, ensure_ascii=False)
        
        # 左进（LPUSH），保持最新的在前面
        await client.lpush(
            f"session:{session_id}:events",
            event_json
        )
        
        # 🔧 Agent 运行期间保留所有事件（不做 LTRIM）
        # 只在 Session 完成后由 complete_session() 设置 TTL 自动过期
        # 如果事件数量超过安全阈值（10000），才进行截断防止内存爆炸
        events_count = await client.llen(f"session:{session_id}:events")
        if events_count > 10000:
            logger.warning(f"⚠️ 事件数量超过阈值: session_id={session_id}, count={events_count}")
            await client.ltrim(f"session:{session_id}:events", 0, 9999)
        
        # 4. 通过 Pub/Sub 发布事件（实时推送）
        channel = f"session:{session_id}:stream"
        await client.publish(channel, event_json)
        
        # 更新 last_event_seq
        await self.update_session_status(session_id, last_event_seq=event["seq"])
        
        return event
    
    async def get_events(
        self,
        session_id: str,
        after_id: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取事件列表
        
        Args:
            session_id: Session ID
            after_id: 从哪个 event_id 之后开始（可选）
            limit: 最多返回多少个事件
            
        Returns:
            事件列表
        """
        client = await self._get_client()
        
        # 读取所有缓冲的事件
        events_json = await client.lrange(
            f"session:{session_id}:events",
            0,
            -1
        )
        
        if not events_json:
            return []
        
        # 解析并反转（LPUSH 是倒序的）
        events = []
        for event_json in reversed(events_json):
            try:
                event = json.loads(event_json)
                events.append(event)
            except json.JSONDecodeError:
                logger.warning(f"⚠️ 无法解析事件: {event_json}")
        
        # 过滤 after_id
        if after_id is not None:
            events = [
                e for e in events 
                if e.get("seq", e.get("id", 0) if isinstance(e.get("id"), int) else 0) > after_id
            ]
        
        # 限制数量
        if limit and len(events) > limit:
            events = events[:limit]
        
        return events
    
    async def stream_events(
        self,
        session_id: str,
        after_id: Optional[int] = None,
        timeout: int = 60
    ):
        """
        实时流式读取事件（用于 SSE）- 使用轮询作为备选
        
        Args:
            session_id: Session ID
            after_id: 从哪个 event_id 之后开始（可选）
            timeout: 超时时间（秒）
            
        Yields:
            事件字典
        """
        last_id = after_id or 0
        start_time = datetime.now()
        
        while True:
            # 检查超时
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed > timeout:
                logger.debug(f"⏱️ 流式读取超时: session_id={session_id}")
                break
            
            # 读取新事件
            events = await self.get_events(
                session_id=session_id,
                after_id=last_id,
                limit=10
            )
            
            # 发送新事件
            for event in events:
                yield event
                event_seq = event.get("seq", event.get("id", 0) if isinstance(event.get("id"), int) else 0)
                last_id = max(last_id, event_seq)
            
            # 检查 session 是否结束
            session_data = await self.get_session_status(session_id)
            if session_data and session_data.get("status") in ["completed", "failed", "stopped"]:
                logger.debug(f"✅ Session 已结束: session_id={session_id}")
                break
            
            # 没有新事件，等待一小段时间
            if not events:
                await asyncio.sleep(0.1)
            else:
                await asyncio.sleep(0.01)
    
    async def subscribe_events(
        self,
        session_id: str,
        after_id: Optional[int] = None,
        timeout: int = 300
    ):
        """
        使用 Pub/Sub 订阅实时事件流（推荐）
        
        相比轮询的优势：
        - 延迟更低（毫秒级 vs 100ms）
        - 资源消耗更少（无空轮询）
        
        Args:
            session_id: Session ID
            after_id: 从哪个 event_id 之后开始（可选，用于补偿丢失的事件）
            timeout: 超时时间（秒）
            
        Yields:
            事件字典
        """
        client = await self._get_client()
        channel = f"session:{session_id}:stream"
        last_id = after_id or 0
        
        # 1. 先读取积压的事件（断线补偿）
        if after_id is not None:
            backlog_events = await self.get_events(
                session_id=session_id,
                after_id=after_id,
                limit=1000
            )
            for event in backlog_events:
                yield event
                event_seq = event.get("seq", event.get("id", 0) if isinstance(event.get("id"), int) else 0)
                last_id = max(last_id, event_seq)
        
        # 2. 订阅 Pub/Sub 频道
        pubsub = client.pubsub()
        await pubsub.subscribe(channel)
        
        try:
            start_time = datetime.now()
            
            while True:
                # 检查超时
                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed > timeout:
                    logger.debug(f"⏱️ Pub/Sub 超时: session_id={session_id}")
                    break
                
                # 读取 Pub/Sub 消息（非阻塞，带超时）
                try:
                    message = await asyncio.wait_for(
                        pubsub.get_message(ignore_subscribe_messages=True),
                        timeout=1.0  # 1秒超时，允许检查 session 状态
                    )
                except asyncio.TimeoutError:
                    message = None
                
                if message and message["type"] == "message":
                    try:
                        event = json.loads(message["data"])
                        event_seq = event.get("seq", event.get("id", 0) if isinstance(event.get("id"), int) else 0)
                        
                        # 过滤已处理的事件
                        if event_seq > last_id:
                            yield event
                            last_id = event_seq
                    except json.JSONDecodeError:
                        logger.warning(f"⚠️ 无法解析 Pub/Sub 消息: {message['data']}")
                
                # 检查 session 是否结束
                session_data = await self.get_session_status(session_id)
                
                # 🔧 修复1：Session 状态不存在（已过期）也认为是已结束
                if session_data is None:
                    logger.info(f"⚠️ Session 状态已过期，视为已结束: session_id={session_id}")
                    break
                
                # 🔧 修复2：检查心跳超时（超过 2 分钟没有心跳，认为 Agent 已死）
                last_heartbeat = session_data.get("last_heartbeat")
                if last_heartbeat:
                    try:
                        heartbeat_time = datetime.fromisoformat(last_heartbeat)
                        heartbeat_age = (datetime.now() - heartbeat_time).total_seconds()
                        if heartbeat_age > 1200:  # 20 分钟超时
                            logger.warning(
                                f"⚠️ Session 心跳超时 ({heartbeat_age:.0f}s)，视为已结束: "
                                f"session_id={session_id}"
                            )
                            break
                    except (ValueError, TypeError):
                        pass  # 忽略解析错误
                
                if session_data.get("status") in ["completed", "failed", "stopped"]:
                    # 读取最后可能遗漏的事件
                    final_events = await self.get_events(
                        session_id=session_id,
                        after_id=last_id,
                        limit=100
                    )
                    for event in final_events:
                        yield event
                    
                    logger.debug(f"✅ Session 已结束: session_id={session_id}")
                    break
        
        finally:
            # 清理订阅（在 CancelledError 时也要尽量清理）
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()
            except asyncio.CancelledError:
                # 连接已取消，忽略清理错误
                logger.debug(f"🔌 Pub/Sub 清理被取消: session_id={session_id}")
            except Exception as e:
                logger.warning(f"⚠️ Pub/Sub 清理失败: {e}")
    
    # ==================== 用户 Session 列表 ====================
    
    async def get_user_sessions(self, user_id: str) -> List[str]:
        """
        获取用户的所有活跃 Session
        
        Args:
            user_id: 用户 ID
            
        Returns:
            Session ID 列表
        """
        client = await self._get_client()
        sessions = await client.smembers(f"user:{user_id}:sessions")
        return list(sessions) if sessions else []
    
    async def get_user_sessions_detail(self, user_id: str) -> List[Dict[str, Any]]:
        """
        获取用户的所有活跃 Session（包含详细信息）
        
        Args:
            user_id: 用户 ID
            
        Returns:
            Session 详情列表
        """
        session_ids = await self.get_user_sessions(user_id)
        
        sessions_detail = []
        for session_id in session_ids:
            status = await self.get_session_status(session_id)
            if status:
                sessions_detail.append(status)
        
        return sessions_detail
    
    # ==================== 停止控制 ====================
    
    async def set_stop_flag(self, session_id: str) -> None:
        """
        设置停止标志（用户主动中断）
        
        Args:
            session_id: Session ID
        """
        client = await self._get_client()
        
        # 设置停止标志（60秒 TTL，防止泄漏）
        await client.set(
            f"session:{session_id}:stop_flag",
            "1",
            ex=60
        )
        logger.info(f"🛑 已设置停止标志: session_id={session_id}")
    
    async def is_stopped(self, session_id: str) -> bool:
        """
        检查 Session 是否被停止
        
        Args:
            session_id: Session ID
            
        Returns:
            是否已停止
        """
        client = await self._get_client()
        flag = await client.get(f"session:{session_id}:stop_flag")
        return flag == "1"
    
    async def clear_stop_flag(self, session_id: str) -> None:
        """
        清除停止标志
        
        Args:
            session_id: Session ID
        """
        client = await self._get_client()
        await client.delete(f"session:{session_id}:stop_flag")
    
    # ==================== 清理和维护 ====================
    
    async def cleanup_timeout_sessions(self) -> int:
        """
        清理超时的 Session
        
        Returns:
            清理的数量
        """
        client = await self._get_client()
        cleaned = 0
        
        # 获取所有用户的 sessions keys
        user_keys = []
        async for key in client.scan_iter("user:*:sessions"):
            user_keys.append(key)
        
        for user_key in user_keys:
            session_ids = await client.smembers(user_key)
            
            for session_id in session_ids:
                # 检查心跳是否存在
                heartbeat = await client.get(f"session:{session_id}:heartbeat")
                
                if not heartbeat:
                    # 心跳已过期（超过 60 秒）
                    logger.warning(f"⚠️ Session 超时: {session_id}")
                    
                    # 标记为 timeout
                    await self.complete_session(session_id, status="timeout")
                    cleaned += 1
        
        if cleaned > 0:
            logger.info(f"🧹 清理了 {cleaned} 个超时的 Session")
        
        return cleaned
    
    # ==================== 分布式锁（用于清理任务防重入） ====================
    
    async def acquire_cleanup_lock(self, lock_timeout: int = 300) -> bool:
        """
        获取清理任务的分布式锁
        
        Args:
            lock_timeout: 锁超时时间（秒），默认 5 分钟
            
        Returns:
            是否成功获取锁
        """
        client = await self._get_client()
        lock_key = "lock:cleanup_sessions"
        # NX: 只在 key 不存在时设置
        # EX: 设置过期时间，防止死锁
        acquired = await client.set(lock_key, "1", nx=True, ex=lock_timeout)
        if acquired:
            logger.debug("🔒 获取清理任务锁成功")
        return bool(acquired)
    
    async def release_cleanup_lock(self) -> None:
        """
        释放清理任务的分布式锁
        """
        client = await self._get_client()
        lock_key = "lock:cleanup_sessions"
        await client.delete(lock_key)
        logger.debug("🔓 释放清理任务锁")
    
    async def cleanup_with_lock(self) -> int:
        """
        带分布式锁的清理（防止多实例并发清理）
        
        Returns:
            清理的数量，-1 表示未获取到锁
        """
        # 尝试获取锁
        if not await self.acquire_cleanup_lock():
            logger.debug("⏭️ 清理任务已在运行中，跳过")
            return -1
        
        try:
            return await self.cleanup_timeout_sessions()
        finally:
            await self.release_cleanup_lock()
    
    async def close(self) -> None:
        """
        关闭 Redis 连接
        """
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("🔌 Redis 连接已关闭")


# ==================== 便捷函数 ====================

_default_redis_manager: Optional[RedisSessionManager] = None


def get_redis_manager(
    redis_host: Optional[str] = None,
    redis_port: Optional[int] = None,
    redis_db: int = 0,
    redis_password: Optional[str] = None
) -> RedisSessionManager:
    """
    获取默认 Redis 管理器单例
    
    优先从环境变量读取配置：
    - REDIS_HOST: Redis 主机地址
    - REDIS_PORT: Redis 端口
    - REDIS_PASSWORD: Redis 密码（可选）
    """
    import os
    
    global _default_redis_manager
    if _default_redis_manager is None:
        # 从环境变量读取配置，参数覆盖环境变量
        host = redis_host or os.getenv("REDIS_HOST", "localhost")
        port = redis_port or int(os.getenv("REDIS_PORT", "6379"))
        password = redis_password or os.getenv("REDIS_PASSWORD")
        
        _default_redis_manager = RedisSessionManager(
            redis_host=host,
            redis_port=port,
            redis_db=redis_db,
            redis_password=password
        )
    return _default_redis_manager

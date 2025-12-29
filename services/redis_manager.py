"""
Redis 会话管理器

负责 Session 的 Redis 存储和管理：
- Session 状态（status, progress, heartbeat）
- 事件缓冲（events buffer）
- 用户活跃 Sessions 列表
"""

import json
import redis
from typing import Dict, Any, List, Optional
from datetime import datetime
from logger import get_logger

logger = get_logger("redis_manager")


class RedisSessionManager:
    """Redis Session 管理器"""
    
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
        self.client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
            decode_responses=True  # 自动解码为字符串
        )
        
        try:
            self.client.ping()
            logger.info(f"✅ Redis 连接成功: {redis_host}:{redis_port}")
        except Exception as e:
            logger.error(f"❌ Redis 连接失败: {str(e)}")
            raise
    
    # ==================== Session 状态管理 ====================
    
    def create_session(
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
        session_status = {
            "session_id": session_id,
            "user_id": user_id,
            "conversation_id": conversation_id or "",
            "message_id": message_id or "",
            "status": "running",
            "last_event_seq": "0",  # 使用 seq（session 内序号）而不是全局 ID
            "start_time": datetime.now().isoformat(),
            "last_heartbeat": datetime.now().isoformat(),
            "progress": "0.0",
            "total_turns": "0",
            "message_preview": message_preview[:100]
        }
        
        # 保存 Session 状态
        self.client.hset(
            f"session:{session_id}:status",
            mapping=session_status
        )
        # 运行中不设置 TTL
        
        # 添加到用户的活跃 sessions
        self.client.sadd(f"user:{user_id}:sessions", session_id)
        self.client.expire(f"user:{user_id}:sessions", 3600)
        
        # 初始化心跳
        self.update_heartbeat(session_id)
        
        logger.info(f"✅ Session 已创建: {session_id}")
    
    def get_session_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        获取 Session 状态
        
        Args:
            session_id: Session ID
            
        Returns:
            Session 状态字典，不存在则返回 None
        """
        status = self.client.hgetall(f"session:{session_id}:status")
        
        if not status:
            return None
        
        # 转换数字类型（安全转换，处理 None 和无效值）
        # 支持 last_event_id（旧字段）和 last_event_seq（新字段）
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
            # 向后兼容：如果有 last_event_id，转换并复制到 last_event_seq
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
    
    def update_session_status(
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
        
        # 转换为字符串，但排除 None 值（避免存储字符串 'None'）
        str_fields = {}
        for k, v in fields.items():
            if v is not None:
                str_fields[k] = str(v)
            else:
                # None 值使用默认值
                if k in ["last_event_id", "last_event_seq"]:
                    str_fields[k] = "0"
                elif k == "progress":
                    str_fields[k] = "0.0"
                elif k == "total_turns":
                    str_fields[k] = "0"
                else:
                    str_fields[k] = ""
        
        self.client.hset(
            f"session:{session_id}:status",
            mapping=str_fields
        )
    
    def complete_session(
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
        # 更新状态
        self.update_session_status(
            session_id,
            status=status,
            last_heartbeat=datetime.now().isoformat()
        )
        
        # 设置 TTL = 60 秒
        self.client.expire(f"session:{session_id}:status", 60)
        self.client.expire(f"session:{session_id}:events", 60)
        self.client.expire(f"session:{session_id}:heartbeat", 60)
        
        # 从用户活跃列表移除
        status_data = self.get_session_status(session_id)
        if status_data:
            user_id = status_data.get("user_id")
            if user_id:
                self.client.srem(f"user:{user_id}:sessions", session_id)
        
        logger.info(f"✅ Session 已完成: {session_id}, status={status}")
    
    def update_heartbeat(self, session_id: str) -> None:
        """
        更新心跳
        
        Args:
            session_id: Session ID
        """
        now = datetime.now().isoformat()
        
        # 更新心跳时间戳（60秒 TTL）
        self.client.set(
            f"session:{session_id}:heartbeat",
            now,
            ex=60
        )
        
        # 同步更新 status 中的 last_heartbeat
        self.update_session_status(session_id, last_heartbeat=now)
    
    # ==================== 事件缓冲管理 ====================
    
    def generate_session_seq(self, session_id: str) -> int:
        """
        生成 session 内的事件序号（从 1 开始递增）
        
        Args:
            session_id: Session ID
            
        Returns:
            Session 内的事件序号（1, 2, 3...）
        """
        return self.client.incr(f"session:{session_id}:seq_counter")
    
    def get_session_context(self, session_id: str) -> Dict[str, Any]:
        """
        获取 session 上下文信息
        
        Args:
            session_id: Session ID
            
        Returns:
            {
                "conversation_id": str,
                "user_id": str,
                ...
            }
        """
        status_data = self.get_session_status(session_id)
        if not status_data:
            return {}
        
        return {
            "conversation_id": status_data.get("conversation_id"),
            "user_id": status_data.get("user_id")
        }
    
    def buffer_event(
        self,
        session_id: str,
        event_data: Dict[str, Any] = None,
        event_id: int = None,
        event_type: str = None,
        timestamp: str = None
    ) -> None:
        """
        缓冲事件到 Redis
        
        支持两种调用方式：
        1. 传入完整的 event_data 字典（包含 event_uuid, seq, type, data, timestamp）
        2. 分别传入各个字段（向后兼容）
        
        Args:
            session_id: Session ID
            event_data: 完整的事件字典（推荐）
            event_id: 事件 ID（可选，向后兼容）
            event_type: 事件类型（可选，向后兼容）
            timestamp: 时间戳（可选，向后兼容）
        """
        # 方式1：传入完整事件字典
        if event_data is not None and ("event_uuid" in event_data or "id" in event_data):
            event = event_data
        # 方式2：分别传入字段（向后兼容）
        else:
            event = {
                "id": event_id,
                "type": event_type,
                "data": event_data,
                "timestamp": timestamp
            }
        
        # 左进（LPUSH），保持最新的在前面
        self.client.lpush(
            f"session:{session_id}:events",
            json.dumps(event, ensure_ascii=False)
        )
        
        # 只保留最近 1000 个事件
        self.client.ltrim(
            f"session:{session_id}:events",
            0,
            999
        )
        
        # 更新 last_event_seq（使用 seq 字段，如果有的话）
        # seq 是 session 内的递增序号，适合用于断线重连
        if "seq" in event:
            self.update_session_status(session_id, last_event_seq=event["seq"])
        elif "id" in event and event["id"] is not None:
            # 向后兼容：如果 id 存在且不是 None
            self.update_session_status(session_id, last_event_seq=event["id"])
    
    def get_events(
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
        # 读取所有缓冲的事件
        events_json = self.client.lrange(
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
        
        # 过滤 after_id（使用 seq 字段）
        if after_id is not None:
            # 优先使用 seq 字段（新），fallback 到 id 字段（旧，如果是数字的话）
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
        实时流式读取事件（用于 SSE）
        
        特点：
        - 实时读取新事件
        - 使用轮询（Redis 不支持真正的 pub/sub stream）
        - 当没有新事件时等待
        - 检测 session 结束
        
        Args:
            session_id: Session ID
            after_id: 从哪个 event_id 之后开始（可选）
            timeout: 超时时间（秒）
            
        Yields:
            事件字典
        """
        import asyncio
        
        last_id = after_id or 0
        start_time = datetime.now()
        
        while True:
            # 检查超时
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed > timeout:
                logger.debug(f"⏱️ 流式读取超时: session_id={session_id}")
                break
            
            # 读取新事件
            events = self.get_events(
                session_id=session_id,
                after_id=last_id,
                limit=10  # 每次最多10个
            )
            
            # 发送新事件
            for event in events:
                yield event
                # 使用 seq 字段更新 last_id
                event_seq = event.get("seq", event.get("id", 0) if isinstance(event.get("id"), int) else 0)
                last_id = max(last_id, event_seq)
            
            # 检查 session 是否结束
            session_data = self.get_session_status(session_id)
            if session_data and session_data.get("status") in ["completed", "failed"]:
                logger.debug(f"✅ Session 已结束: session_id={session_id}")
                break
            
            # 没有新事件，等待一小段时间
            if not events:
                await asyncio.sleep(0.1)  # 100ms
            else:
                # 有事件，立即检查下一批
                await asyncio.sleep(0.01)  # 10ms
    
    # ==================== 用户 Session 列表 ====================
    
    def get_user_sessions(self, user_id: str) -> List[str]:
        """
        获取用户的所有活跃 Session
        
        Args:
            user_id: 用户 ID
            
        Returns:
            Session ID 列表
        """
        sessions = self.client.smembers(f"user:{user_id}:sessions")
        return list(sessions) if sessions else []
    
    def get_user_sessions_detail(self, user_id: str) -> List[Dict[str, Any]]:
        """
        获取用户的所有活跃 Session（包含详细信息）
        
        Args:
            user_id: 用户 ID
            
        Returns:
            Session 详情列表
        """
        session_ids = self.get_user_sessions(user_id)
        
        sessions_detail = []
        for session_id in session_ids:
            status = self.get_session_status(session_id)
            if status:
                sessions_detail.append(status)
        
        return sessions_detail
    
    # ==================== 停止控制 ====================
    
    def set_stop_flag(self, session_id: str) -> None:
        """
        设置停止标志（用户主动中断）
        
        Args:
            session_id: Session ID
        """
        # 设置停止标志（60秒 TTL，防止泄漏）
        self.client.set(
            f"session:{session_id}:stop_flag",
            "1",
            ex=60
        )
        logger.info(f"🛑 已设置停止标志: session_id={session_id}")
    
    def is_stopped(self, session_id: str) -> bool:
        """
        检查 Session 是否被停止
        
        Args:
            session_id: Session ID
            
        Returns:
            是否已停止
        """
        flag = self.client.get(f"session:{session_id}:stop_flag")
        return flag == "1"
    
    def clear_stop_flag(self, session_id: str) -> None:
        """
        清除停止标志
        
        Args:
            session_id: Session ID
        """
        self.client.delete(f"session:{session_id}:stop_flag")
    
    # ==================== 清理和维护 ====================
    
    def cleanup_timeout_sessions(self) -> int:
        """
        清理超时的 Session
        
        Returns:
            清理的数量
        """
        cleaned = 0
        
        # 获取所有用户的 sessions keys
        user_keys = self.client.keys("user:*:sessions")
        
        for user_key in user_keys:
            session_ids = self.client.smembers(user_key)
            
            for session_id in session_ids:
                # 检查心跳是否存在
                heartbeat = self.client.get(f"session:{session_id}:heartbeat")
                
                if not heartbeat:
                    # 心跳已过期（超过 60 秒）
                    logger.warning(f"⚠️ Session 超时: {session_id}")
                    
                    # 标记为 timeout
                    self.complete_session(session_id, status="timeout")
                    cleaned += 1
        
        if cleaned > 0:
            logger.info(f"🧹 清理了 {cleaned} 个超时的 Session")
        
        return cleaned


# ==================== 便捷函数 ====================

_default_redis_manager: Optional[RedisSessionManager] = None


def get_redis_manager(
    redis_host: str = "localhost",
    redis_port: int = 6379,
    redis_db: int = 0,
    redis_password: Optional[str] = None
) -> RedisSessionManager:
    """获取默认 Redis 管理器单例"""
    global _default_redis_manager
    if _default_redis_manager is None:
        _default_redis_manager = RedisSessionManager(
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
            redis_password=redis_password
        )
    return _default_redis_manager


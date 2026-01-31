"""
确认服务层

提供 HITL (Human-in-the-Loop) 确认请求的业务逻辑封装：
- 获取待处理请求
- 提交确认响应
- 取消请求
- 统计信息
"""

from typing import Optional, Dict, Any, List, Union

from logger import get_logger
from core.confirmation_manager import (
    get_confirmation_manager,
    ConfirmationManager,
    ConfirmationRequest,
)

logger = get_logger("confirmation_service")


# ============================================================
# 异常定义
# ============================================================

class ConfirmationServiceError(Exception):
    """确认服务基础异常"""
    pass


class ConfirmationNotFoundError(ConfirmationServiceError):
    """确认请求不存在"""
    pass


class ConfirmationExpiredError(ConfirmationServiceError):
    """确认请求已过期"""
    pass


class ConfirmationResponseError(ConfirmationServiceError):
    """设置响应失败"""
    pass


# ============================================================
# 确认服务
# ============================================================

class ConfirmationService:
    """
    确认服务
    
    职责：
    - 封装 ConfirmationManager 的操作
    - 提供业务级别的错误处理
    - 统一日志记录
    """
    
    def __init__(self):
        self._manager: ConfirmationManager = get_confirmation_manager()
    
    def get_request(self, request_id: str) -> ConfirmationRequest:
        """
        获取确认请求
        
        Args:
            request_id: 请求 ID
            
        Returns:
            确认请求对象
            
        Raises:
            ConfirmationNotFoundError: 请求不存在
        """
        request = self._manager.get_request(request_id)
        if not request:
            logger.warning(f"确认请求不存在: request_id={request_id}")
            raise ConfirmationNotFoundError(f"确认请求 {request_id} 不存在")
        return request
    
    def get_pending_requests(
        self,
        session_id: Optional[str] = None
    ) -> List[ConfirmationRequest]:
        """
        获取待处理的确认请求
        
        Args:
            session_id: 可选，按会话 ID 过滤
            
        Returns:
            待处理请求列表
        """
        requests = self._manager.get_pending_requests(session_id)
        logger.debug(f"获取待处理请求: count={len(requests)}, session_id={session_id}")
        return requests
    
    def submit_response(
        self,
        request_id: str,
        response: Union[str, List[str], Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        提交确认响应
        
        Args:
            request_id: 请求 ID
            response: 用户响应
            metadata: 额外元数据
            
        Returns:
            提交结果
            
        Raises:
            ConfirmationNotFoundError: 请求不存在
            ConfirmationExpiredError: 请求已过期
            ConfirmationResponseError: 设置响应失败
        """
        logger.info(f"收到确认响应: request_id={request_id}, response={response}")
        
        # 获取请求
        request = self._manager.get_request(request_id)
        if not request:
            logger.warning(f"确认请求不存在: request_id={request_id}")
            raise ConfirmationNotFoundError(f"确认请求 {request_id} 不存在或已过期")
        
        # 检查是否过期
        if request.is_expired():
            logger.warning(f"确认请求已过期: request_id={request_id}")
            raise ConfirmationExpiredError(f"确认请求 {request_id} 已过期")
        
        # 设置响应，唤醒等待的工具
        success = self._manager.set_response(request_id, response, metadata)
        
        if not success:
            logger.error(f"设置响应失败: request_id={request_id}")
            raise ConfirmationResponseError("设置响应失败")
        
        logger.info(f"确认响应已提交: request_id={request_id}")
        
        return {
            "request_id": request_id,
            "response": response
        }
    
    def cancel_request(self, request_id: str) -> bool:
        """
        取消确认请求
        
        Args:
            request_id: 请求 ID
            
        Returns:
            是否成功取消
            
        Raises:
            ConfirmationNotFoundError: 请求不存在
        """
        success = self._manager.cancel_request(request_id)
        
        if not success:
            logger.warning(f"取消请求失败: request_id={request_id}")
            raise ConfirmationNotFoundError(f"确认请求 {request_id} 不存在")
        
        logger.info(f"确认请求已取消: request_id={request_id}")
        return True
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            统计信息字典
        """
        return self._manager.stats()


# ============================================================
# 单例管理
# ============================================================

_confirmation_service: Optional[ConfirmationService] = None


def get_confirmation_service() -> ConfirmationService:
    """获取确认服务单例"""
    global _confirmation_service
    if _confirmation_service is None:
        _confirmation_service = ConfirmationService()
    return _confirmation_service


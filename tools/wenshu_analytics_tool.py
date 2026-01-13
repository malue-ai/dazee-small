"""
问数平台工具 - 调用问数平台 V3 提问接口进行数据分析

功能说明：
- 自动判断 task_id 是否存在
- 不存在则创建对话（包括用户、任务、数据源、对话、仪表板）
- 已存在且提供 files 参数时，追加文件到数据源
- 等待文件解析完成（超时 120 秒）
- 执行问答处理，返回 JSON 响应

V3 特性（面向系统集成，简化参数）：
✅ JSON 响应（非 SSE 流式）
✅ 整合创建和提问
✅ 支持文件追加
✅ 包含 report 字段（结构化数据）
✅ 文件解析等待机制
✅ task_id == chat_id == conversation_id
"""

import os
import aiohttp
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from logger import get_logger
from tools.base import BaseTool

logger = get_logger("wenshu_analytics_tool")


# 问数平台 API 基础 URL（从环境变量读取）
WENSHU_API_BASE_URL = os.getenv("WENSHU_API_BASE_URL", "http://localhost:8080")


@dataclass
class WenshuFile:
    """问数平台文件定义"""
    file_name: str
    file_url: str


class WenshuAnalyticsTool(BaseTool):
    """
    问数平台数据分析工具
    
    调用问数平台 V3 提问接口，实现数据分析和问答功能。
    task_id 和 user_id 都使用 conversation_id，实现一个对话一个数据分析任务。
    """
    
    @property
    def name(self) -> str:
        return "wenshu_analytics"
    
    @property
    def description(self) -> str:
        return """问数平台数据分析工具 - 用于数据查询、分析和可视化。

功能：
1. 自动创建或复用数据分析会话
2. 上传和追加数据文件（Excel、CSV 等）
3. 自然语言查询数据
4. 返回 SQL、图表、分析报告

使用场景：
- "2024年销售额是多少？"
- "帮我分析这份数据的趋势"
- "对比各季度的销售情况"
- "生成销售数据的饼图"

参数：
- question: 用户的数据分析问题（必需）
- files: 要分析的文件列表（可选，首次提问时上传）
- lg_code: 语言代码（可选，默认 zh-CN）
- conversation_id: 对话 ID（框架自动注入，作为 task_id）
- user_id: 用户 ID（框架自动注入）

返回：
- report: 分析报告（title + content）
- sql: 生成的 SQL 语句
- chart: 图表配置
- data: 查询结果数据
"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "用户的数据分析问题，如 '2024年销售额是多少？'"
                },
                "files": {
                    "type": "array",
                    "description": "要分析的文件列表（可选，首次提问时上传）",
                    "items": {
                        "type": "object",
                        "properties": {
                            "file_name": {
                                "type": "string",
                                "description": "文件名，如 '2024年销售数据.xlsx'"
                            },
                            "file_url": {
                                "type": "string",
                                "description": "文件 URL，如 'https://example.com/data.xlsx'"
                            }
                        },
                        "required": ["file_name", "file_url"]
                    }
                },
                "lg_code": {
                    "type": "string",
                    "description": "语言代码（默认 zh-CN）"
                },
                "conversation_id": {
                    "type": "string",
                    "description": "对话 ID（框架自动注入，作为问数平台的 task_id）"
                },
                "user_id": {
                    "type": "string",
                    "description": "用户 ID（框架自动注入）"
                }
            },
            "required": ["question", "conversation_id", "user_id"]
        }
    
    async def execute(
        self,
        question: str,
        files: Optional[List[Dict[str, str]]] = None,
        lg_code: str = "zh-CN",
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行问数平台数据分析查询
        
        Args:
            question: 用户的数据分析问题
            files: 要分析的文件列表（可选）
            lg_code: 语言代码
            conversation_id: 对话 ID（由框架自动注入，作为 task_id）
            user_id: 用户 ID（由框架自动注入）
            
        Returns:
            分析结果，包含 report、sql、chart、data 等
        """
        # user_id 由框架注入，conversation_id 作为 task_id
        # 这样一个对话对应一个数据分析会话
        effective_user_id = user_id or "default_user"
        effective_task_id = conversation_id or "default_task"
        
        logger.info(
            f"📊 调用问数平台: question='{question[:50]}...', "
            f"task_id={effective_task_id}, files={len(files) if files else 0}个"
        )
        
        try:
            # 构建请求体
            request_body = {
                "user_id": effective_user_id,
                "task_id": effective_task_id,
                "question": question,
                "lg_code": lg_code
            }
            
            # 如果有文件，添加到请求体
            if files:
                request_body["files"] = files
                logger.info(f"📁 附带文件: {[f.get('file_name') for f in files]}")
            
            # 调用问数平台 V3 API
            api_url = f"{WENSHU_API_BASE_URL}/api/v3/ask"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url,
                    json=request_body,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=180)  # 180秒超时（含文件解析）
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return self._format_response(result)
                    elif response.status == 422:
                        error_detail = await response.json()
                        logger.error(f"❌ 参数验证失败: {error_detail}")
                        return {
                            "success": False,
                            "error": "参数验证失败",
                            "error_detail": error_detail
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ API 错误 (HTTP {response.status}): {error_text}")
                        return {
                            "success": False,
                            "error": f"API 请求失败: HTTP {response.status}",
                            "error_detail": error_text
                        }
        
        except aiohttp.ClientTimeout:
            logger.error("❌ 请求超时（可能是文件解析耗时较长）")
            return {
                "success": False,
                "error": "请求超时，请稍后重试"
            }
        except Exception as e:
            logger.error(f"❌ 问数平台调用失败: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": f"调用失败: {str(e)}"
            }
    
    def _format_response(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        格式化问数平台响应
        
        Args:
            result: 问数平台原始响应
            
        Returns:
            格式化后的响应
        """
        success = result.get("success", False)
        
        if success:
            logger.info(
                f"✅ 问数平台返回成功: intent={result.get('intent_name')}, "
                f"有报告={bool(result.get('report'))}, 有图表={bool(result.get('chart'))}"
            )
            
            return {
                "success": True,
                "message_id": result.get("message_id"),
                "conversation_id": result.get("conversation_id"),
                "dashboard_id": result.get("dashboard_id"),
                "intent": result.get("intent"),
                "intent_name": result.get("intent_name"),
                "report": result.get("report"),  # {title, content}
                "sql": result.get("sql"),
                "chart": result.get("chart"),  # {chart_type, ...}
                "data": result.get("data"),  # {columns, rows}
            }
        else:
            error = result.get("error", {})
            logger.warning(f"⚠️ 问数平台返回失败: {error}")
            
            return {
                "success": False,
                "error": error.get("message", "未知错误"),
                "error_code": error.get("code"),
                "error_detail": error
            }


# 工具实例（供 Agent 使用）
wenshu_analytics_tool = WenshuAnalyticsTool()


async def execute_wenshu_analytics(
    question: str,
    files: Optional[List[Dict[str, str]]] = None,
    lg_code: str = "zh-CN",
    conversation_id: Optional[str] = None,
    user_id: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    问数平台数据分析查询（函数式接口）
    
    这是 WenshuAnalyticsTool.execute 的快捷方式
    """
    return await wenshu_analytics_tool.execute(
        question=question,
        files=files,
        lg_code=lg_code,
        conversation_id=conversation_id,
        user_id=user_id,
        **kwargs
    )


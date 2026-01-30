"""
HITL 工具 (Human-in-the-Loop)

用于在 Agent 执行过程中请求用户输入或收集偏好。

═══════════════════════════════════════════════════════════════════════════════
                              表单模式 (form)
═══════════════════════════════════════════════════════════════════════════════

参数：
┌────────────────────────┬────────────────────────────────────────────────────────────┐
│ title                  │ 表单标题（必需）                                            │
│ description            │ 表单描述                                                    │
│ questions              │ 问题数组（必需）                                            │
│ timeout                │ 超时时间（秒），默认 120                                    │
│ use_default_on_timeout │ 超时时是否使用默认值，默认 True                             │
└────────────────────────┴────────────────────────────────────────────────────────────┘

questions 中的问题类型：
- single_choice: 单选（包括 yes/no，options 文本可自定义）
- multiple_choice: 多选
# - text_input: 文本输入（暂未支持）

SSE 输出的 content 结构：
{
  "type": "form",           # 🆕 HITL 类型（目前只有 form）
  "status": "pending",      # pending（等待响应）或无此字段（已响应）
  "title": "...",
  "description": "...",
  "questions": [...],
  "timeout": 120,           # 仅 pending 状态有
  "success": true/false,    # 仅响应后有
  "timed_out": true/false,  # 仅响应后有
  "response": {...}         # 仅响应后有
}

调用示例：
hitl(
  title="确认操作",
  description="请确认以下操作",
  questions=[
    {
      "id": "confirm", 
      "label": "确定要删除这些文件吗？", 
      "type": "single_choice", 
      "options": ["是的，删除", "不，取消"]
    }
  ]
)

hitl(
  title="收集用户偏好",
  description="请选择您的偏好以生成更符合需求的内容",
  questions=[
    {"id": "style", "label": "选择风格", "type": "single_choice", 
     "options": ["商务专业", "科技未来感", "简约清新"], "default": "商务专业"},
    {"id": "focus", "label": "内容重点", "type": "multiple_choice", 
     "options": ["政策法规", "产业动态", "技术突破"]}
    # {"id": "notes", "label": "补充说明", "type": "text_input", 
    #  "hint": "可选", "required": false}  # 暂未支持
  ]
)

═══════════════════════════════════════════════════════════════════════════════

工作流程：
1. Agent 调用此工具 → 创建 ConfirmationRequest
2. 通过 tool_use SSE 事件 → 前端渲染表单界面
3. 异步等待用户响应（不阻塞事件循环）
4. 用户提交 → HTTP POST 唤醒等待
5. 返回结果给 Agent → 继续执行

参考文档: docs/HITL-SSE-CONFIRMATION-DESIGN.md
"""

import json
from logger import get_logger
from typing import Dict, Any, Optional, List, Callable, Awaitable, Union

from core.tool.base import BaseTool, ToolContext
from models.hitl import ConfirmationType
from services.confirmation_service import get_confirmation_manager

logger = get_logger(__name__)


# ==================== 常量定义 ====================

DEFAULT_TIMEOUT = 60        # 默认超时时间
FORM_TIMEOUT = 120          # 表单默认超时（给更多时间）


# ==================== 问题类型定义 ====================

class QuestionType:
    """
    form 中的问题类型常量
    
    - SINGLE_CHOICE: 单选题（包含 yes/no 确认场景）
    - MULTIPLE_CHOICE: 多选题
    # - TEXT_INPUT: 文本输入（暂未支持）
    """
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    # TEXT_INPUT = "text_input"  # 暂未支持


# ==================== 工具类 ====================

class HITLTool(BaseTool):
    """
    HITL (Human-in-the-Loop) 工具
    
    统一表单模式，通过 questions 数组支持：
    - single_choice: 单选（包括 yes/no，options 文本可自定义）
    - multiple_choice: 多选
    # - text_input: 文本输入（暂未支持）
    """
    
    name = "hitl"
    
    async def execute(
        self,
        params: Dict[str, Any],
        context: ToolContext
    ) -> Dict[str, Any]:
        """
        执行用户输入请求（表单模式）
        
        Args:
            params: 工具输入参数
                - title: 表单标题（必需）
                - description: 表单描述
                - questions: 问题数组（必需），每个问题包含：
                    - id: 问题唯一标识
                    - label: 问题标签
                    - type: single_choice / multiple_choice
                    - options: 选项列表（单选/多选时必需）
                    - default: 默认值
                    - required: 是否必填
                - timeout: 超时时间（秒），默认 120
            context: 工具执行上下文
            
        Returns:
            {
                "success": True,
                "response": {"question_id": "用户选择/输入", ...},
                "timed_out": False
            }
        """
        # 提取参数
        title = params.get("title", "")
        if not title:
            return {"success": False, "error": "缺少必需参数: title"}
        
        questions = params.get("questions")
        if not questions:
            return {"success": False, "error": "缺少必需参数: questions"}
        
        description = params.get("description", "")
        # 🆕 AI 可以传 timeout 参数，但代码暂不启用超时逻辑
        # timeout = params.get("timeout", FORM_TIMEOUT)
        timeout = None  # 暂时禁用超时，无限等待用户响应
        # 🆕 超时时是否使用默认值（默认 True）- 暂不使用
        use_default_on_timeout = params.get("use_default_on_timeout", True)
        
        # 从 context 获取 session_id
        session_id = context.session_id or ""
        
        # 构建表单元数据
        form_metadata = {
            "type": "form",
            "description": description,
            "questions": questions
        }
        
        logger.info(f"HITL 表单请求: title={title[:50]}..., questions={len(questions)}")
        
        # 获取确认管理器
        manager = get_confirmation_manager()
        
        # 创建确认请求
        request = manager.create_request(
            question=title,
            options=None,
            timeout=timeout,
            confirmation_type=ConfirmationType.FORM,
            session_id=session_id,
            metadata=form_metadata
        )
        
        logger.info(f"输入请求已创建: request_id={request.request_id}")
        
        # 前端会通过 tool_use 事件自动显示表单
        logger.debug("等待用户通过前端界面响应...")
        
        # 异步等待用户响应
        result = await manager.wait_for_response(request.request_id, timeout)
        
        # 处理并返回结果
        return self._process_response(result, timeout, questions, use_default_on_timeout)
    
    # ==================== 私有方法 ====================
    
    def _process_response(
        self,
        result: Dict[str, Any],
        timeout: int,
        questions: List[Dict[str, Any]],
        use_default_on_timeout: bool = True
    ) -> Dict[str, Any]:
        """
        处理用户响应
        
        Args:
            result: 等待响应的结果
            timeout: 超时时间
            questions: 问题列表（用于提取默认值）
            use_default_on_timeout: 超时时是否使用默认值
        """
        # 超时处理
        if result.get("timed_out"):
            logger.warning(f"用户响应超时 ({timeout}s)")
            
            # 🆕 超时时使用默认值
            if use_default_on_timeout:
                default_response = self._extract_default_values(questions)
                if default_response:
                    logger.info(f"⏱️ 超时，使用默认值: {default_response}")
                    return {
                        "success": True,  # 使用默认值视为成功
                        "timed_out": True,
                        "used_default": True,
                        "response": default_response,
                        "message": f"用户未在 {timeout} 秒内响应，已使用默认值"
                    }
            
            # 没有默认值或不使用默认值
            return {
                "success": False,
                "timed_out": True,
                "response": None,
                "message": f"用户未在 {timeout} 秒内响应"
            }
        
        response = result.get("response")
        
        # 尝试解析 JSON（前端可能返回 JSON 字符串）
        if isinstance(response, str):
            try:
                response = json.loads(response)
            except json.JSONDecodeError:
                pass  # 保持原始字符串
        
        logger.info(f"用户已响应: {type(response).__name__}")
        
        return {
            "success": True,
            "timed_out": False,
            "response": response,
            "metadata": result.get("metadata", {})
        }
    
    def _extract_default_values(self, questions: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        从问题列表中提取默认值
        
        Args:
            questions: 问题列表
            
        Returns:
            默认值字典 {question_id: default_value}，如果任何必填问题没有默认值则返回 None
        """
        defaults = {}
        
        for question in questions:
            q_id = question.get("id")
            if not q_id:
                continue
            
            default = question.get("default")
            required = question.get("required", True)  # 默认必填
            
            if default is not None:
                defaults[q_id] = default
            elif required:
                # 必填问题没有默认值，无法使用默认响应
                logger.debug(f"问题 '{q_id}' 是必填项但没有默认值，无法使用默认响应")
                return None
            # 非必填且无默认值的问题，跳过
        
        return defaults if defaults else None


# ==================== 便捷函数 ====================

def create_hitl_tool() -> HITLTool:
    """
    创建 HITLTool 实例
    
    Returns:
        HITLTool 实例
    """
    return HITLTool()

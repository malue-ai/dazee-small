"""
HITL 工具 (Human-in-the-Loop)

用于在 Agent 执行过程中请求用户输入或收集偏好。

🎯 最佳实践：
- 当需要用户做选择时，立即调用此工具，而不是在回复中询问用户
- 例如："画一张图"、"做个思维导图"等模糊需求，应该先用 HITL 收集具体要求
- ❌ 错误：在回复中问"您想要什么风格？1. 商务 2. 科技"
- ✅ 正确：调用 hitl 工具让用户通过表单选择

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

⚠️ 限制：
- 每个问题的 label（问题文本）不能超过 20 字
- 每个问题的选项数量不能超过 3 个
- 每个选项的文本不能超过 10 字
- 未设置 default 时，会默认选中第一个选项

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

典型场景示例：

📝 description（副标题）使用指南：
- 复杂操作、危险操作 → 添加 description 说明背景或警告
- 简单选择、清晰问题 → 省略 description 保持简洁

场景1：用户说"画一张图"（需求不明确，添加 description 说明目的）
hitl(
  title="图片生成配置",
  description="请告诉我您想要的图片类型和风格",
  questions=[
    {"id": "type", "label": "图片类型", "type": "single_choice",
     "options": ["风景照片", "数据图表", "流程示意图"]},  # 未设置 default，会默认选中"风景照片"
    {"id": "style", "label": "风格偏好", "type": "single_choice", 
     "options": ["写实风格", "卡通风格", "抽象艺术"], "default": "写实风格"}
  ]
)

场景2：用户说"做个思维导图"
hitl(
  title="思维导图需求确认",
  description="请选择您需要的功能",
  questions=[
    {"id": "action", "label": "具体需求", "type": "single_choice", 
     "options": ["创建编辑工具", "生成特定主题", "其他需求"]}
  ]
)

场景3：危险操作确认
hitl(
  title="确认删除操作",
  description="即将删除所有日志文件，此操作不可撤销",
  questions=[
    {"id": "confirm", "label": "确定要删除吗？", "type": "single_choice", 
     "options": ["是的，删除", "取消操作"]}
  ]
)

场景4：收集多个配置参数
hitl(
  title="PPT 生成配置",
  description="请配置 PPT 的基本信息",
  questions=[
    {"id": "theme", "label": "选择主题", "type": "single_choice", 
     "options": ["商务专业", "科技未来", "简约清新"], "default": "商务专业"},
    {"id": "language", "label": "语言", "type": "single_choice", 
     "options": ["中文", "英文", "双语"], "default": "中文"}
  ]
)

场景5：简单选择（问题清晰，省略 description）
hitl(
  title="选择主题",
  # 不需要 description，问题已经很清楚
  questions=[
    {"id": "theme", "label": "选择界面主题", "type": "single_choice", 
     "options": ["浅色", "深色", "自动"]}
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
        timeout = 0  # 暂时禁用超时，无限等待用户响应 (0 = 无限)
        # 🆕 超时时是否使用默认值（默认 True）- 暂不使用
        use_default_on_timeout = params.get("use_default_on_timeout", True)
        
        # 从 context 获取 session_id
        session_id = context.session_id or ""
        
        # 过滤掉 questions 中的 hint 字段（已废弃）
        filtered_questions = []
        for q in questions:
            filtered_q = {k: v for k, v in q.items() if k != "hint"}
            filtered_questions.append(filtered_q)
        
        # 构建表单元数据
        form_metadata = {
            "type": "form",
            "description": description,
            "questions": filtered_questions
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
        
        # 处理并返回结果（使用过滤后的 questions）
        return self._process_response(result, timeout, filtered_questions, use_default_on_timeout)
    
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

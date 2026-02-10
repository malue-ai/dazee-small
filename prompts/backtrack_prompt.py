"""
Backtrack decision prompt template.

Used by BacktrackManager._llm_decide() to ask the LLM how to recover
from a business-logic error during agent execution.
"""

BACKTRACK_DECISION_PROMPT = """你是一个智能体执行恢复专家。当前执行遇到了业务逻辑层错误，需要决定如何恢复。

## 错误信息
- 错误类型: {error_type}
- 错误消息: {error_message}
- 错误类别: {error_category}
- 建议的回溯类型: {suggested_backtrack_type}

## 执行上下文
- 当前轮次: {turn}/{max_turns}
- 已回溯次数: {backtrack_count}/{max_backtracks}
- 当前步骤: {current_step}
- 失败的工具: {failed_tools}
- 失败的策略: {failed_strategies}

## 执行历史
{execution_history}

## 可选决策
1. CONTINUE - 继续执行（错误已自动恢复或不影响主流程）
2. BACKTRACK - 需要回溯，请选择回溯类型：
   - PLAN_REPLAN: 重新规划任务分解
   - TOOL_REPLACE: 使用替代工具
   - PARAM_ADJUST: 调整参数重试
   - CONTEXT_ENRICH: 补充上下文信息
   - INTENT_CLARIFY: 请求用户澄清意图
3. FAIL_GRACEFULLY - 优雅失败（已尝试多次回溯仍失败）
4. ESCALATE - 升级处理（需要人工介入）

请以 JSON 格式返回你的决策：
```json
{{
    "decision": "CONTINUE|BACKTRACK|FAIL_GRACEFULLY|ESCALATE",
    "backtrack_type": "PLAN_REPLAN|TOOL_REPLACE|PARAM_ADJUST|CONTEXT_ENRICH|INTENT_CLARIFY|NO_BACKTRACK",
    "action": {{
        // 具体操作，根据 backtrack_type 不同而不同
        // PLAN_REPLAN: {{"new_plan_hint": "建议的新规划方向"}}
        // TOOL_REPLACE: {{"alternative_tool": "建议的替代工具", "reason": "原因"}}
        // PARAM_ADJUST: {{"adjusted_params": {{}}, "reason": "调整原因"}}
        // CONTEXT_ENRICH: {{"needed_context": "需要补充的上下文"}}
        // INTENT_CLARIFY: {{"clarification_question": "需要向用户询问的问题"}}
    }},
    "reason": "决策理由",
    "confidence": 0.0-1.0
}}
```
"""

BACKTRACK_SYSTEM_PROMPT = (
    "你是一个智能体执行恢复专家，帮助决定如何从错误中恢复。"
    "请严格按照 JSON 格式返回决策。"
)

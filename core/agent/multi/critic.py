"""
Critic Agent - 评审顾问智能体

V7.2 新增：负责评估执行结果并提供改进建议

设计原则：
1. **顾问而非裁判**：提供观察和建议，不做最终决策
2. **人机协同**：关键决策由人或上层系统做出
3. **不硬编码评分**：基于具体任务分析，不是通用评分规则
4. **承认不确定性**：无法判断时主动请求人工介入
"""

# 1. 标准库
import json
import re
from pathlib import Path
from typing import List, Optional

# 2. 第三方库
import aiofiles

# 3. 本地模块
from core.agent.multi.models import (
    CriticResult,
    CriticAction,
    CriticConfidence,
    CriticConfig,
    PlanAdjustmentHint,
)
from core.planning.protocol import PlanStep
from core.llm import create_claude_service, Message
from logger import get_logger

logger = get_logger(__name__)


class CriticAgent:
    """
    评审顾问智能体（人机协同版本）
    
    职责：
    1. 观察：客观描述执行结果
    2. 对比：与预期进行对比
    3. 分析：深入分析问题根因
    4. 建议：提供具体改进建议
    5. 推荐：建议下一步行动（但不强制）
    
    核心原则：
    - 你是顾问，不是裁判
    - 提供建议，不做决策
    - 承认不确定性
    
    使用方式：
        critic = CriticAgent(model="claude-sonnet-4-5-20250929")
        await critic.initialize()  # 必须调用以加载提示词
    """
    
    def __init__(
        self,
        model: str = "claude-sonnet-4-5-20250929",
        enable_thinking: bool = True,
        config: Optional[CriticConfig] = None,
    ):
        """
        初始化 Critic Agent
        
        Args:
            model: 使用的模型（默认 Sonnet 4.5）
            enable_thinking: 是否启用扩展思考
            config: Critic 配置（可选）
        """
        self.model = model
        self.enable_thinking = enable_thinking
        self.config = config or CriticConfig()
        
        # 创建 LLM 服务
        self.llm = create_claude_service(
            model=model,
            enable_thinking=enable_thinking,
        )
        
        # 系统提示词（需要调用 initialize() 加载）
        self.system_prompt: str = self._get_default_prompt()
        self._initialized: bool = False
    
    async def initialize(self) -> None:
        """
        异步初始化：加载系统提示词
        
        使用方式：
            critic = CriticAgent(...)
            await critic.initialize()
        """
        if self._initialized:
            return
        
        self.system_prompt = await self._load_system_prompt_async()
        self._initialized = True
        
        logger.info(
            f"✅ CriticAgent 初始化完成: model={self.model}, "
            f"enable_thinking={self.enable_thinking}, "
            f"max_retries={self.config.max_retries}"
        )
    
    async def _load_system_prompt_async(self) -> str:
        """异步加载系统提示词"""
        prompt_path = Path(__file__).parent.parent.parent.parent / "prompts" / "multi_agent" / "critic_prompt.md"
        
        if not prompt_path.exists():
            logger.warning(f"⚠️ 提示词文件不存在: {prompt_path}，使用默认提示词")
            return self._get_default_prompt()
        
        try:
            async with aiofiles.open(prompt_path, "r", encoding="utf-8") as f:
                return await f.read()
        except Exception as e:
            logger.error(f"❌ 加载提示词失败: {e}，使用默认提示词")
            return self._get_default_prompt()
    
    def _get_default_prompt(self) -> str:
        """获取默认提示词（fallback）"""
        return """你是一个专业的 Critic（评审顾问），负责帮助评估执行结果并提供改进建议。

核心原则：你是顾问，不是裁判。

输出格式（必须是 JSON）：
{
  "observations": ["对结果的客观观察"],
  "gaps": ["与预期的差距"],
  "root_cause": "问题根因",
  "suggestions": ["具体的改进建议"],
  "recommended_action": "pass/retry/replan/ask_human",
  "reasoning": "推荐理由",
  "confidence": "high/medium/low"
}

当你无法判断时，使用 ask_human 并设置 confidence 为 low。
"""
    
    async def critique(
        self,
        executor_output: str,
        plan_step: PlanStep,
        success_criteria: Optional[List[str]] = None,
        retry_count: int = 0,
        max_retries: Optional[int] = None,
        original_task: Optional[str] = None,
    ) -> CriticResult:
        """
        评估执行结果，返回建议
        
        Args:
            executor_output: 执行结果
            plan_step: Plan 步骤（包含任务描述）
            success_criteria: 成功标准列表
            retry_count: 当前重试次数
            max_retries: 最大重试次数
            original_task: 原始任务描述（可选，用于更好的上下文）
            
        Returns:
            CriticResult: 评估结果和建议
        """
        # 获取成功标准
        if success_criteria is None:
            success_criteria = plan_step.metadata.get("success_criteria", [])
        
        if max_retries is None:
            max_retries = self.config.max_retries
        
        # 构建用户消息
        user_message = self._build_critique_message(
            executor_output=executor_output,
            task_description=original_task or plan_step.description,
            success_criteria=success_criteria,
            retry_count=retry_count,
            max_retries=max_retries,
        )
        
        # 调用 LLM 评估
        messages = [Message(role="user", content=user_message)]
        
        try:
            llm_response = await self.llm.create_message_async(
                messages=messages,
                system=self.system_prompt,
                temperature=0.3,
            )
            
            # 提取响应文本
            response_text = llm_response.content if hasattr(llm_response, 'content') else str(llm_response)
            
            # 解析 JSON 响应
            result = self._parse_critique_response(response_text)
            
            # 确保 result 不为 None
            if result is None:
                logger.error(f"❌ Critic 响应解析返回 None, response_text={response_text[:500]}")
                result = CriticResult(
                    observations=["Critic 响应解析失败"],
                    gaps=[],
                    root_cause="解析返回 None",
                    suggestions=["人工检查执行结果"],
                    recommended_action=CriticAction.ASK_HUMAN,
                    reasoning="Critic 响应解析失败，需要人工介入",
                    confidence=CriticConfidence.LOW,
                )
            
            logger.info(
                f"✅ Critic 评估完成: step_id={plan_step.id}, "
                f"action={result.recommended_action.value}, "
                f"confidence={result.confidence.value}"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Critic 评估失败: {e}", exc_info=True)
            # 返回 ask_human（无法判断时请求人工）
            return CriticResult(
                observations=[f"Critic 评估过程出错: {str(e)}"],
                gaps=[],
                root_cause="评估过程异常",
                suggestions=["人工检查执行结果"],
                recommended_action=CriticAction.ASK_HUMAN,
                reasoning=f"Critic 评估过程出错，需要人工介入: {str(e)}",
                confidence=CriticConfidence.LOW,
            )
    
    def _build_critique_message(
        self,
        executor_output: str,
        task_description: str,
        success_criteria: List[str],
        retry_count: int,
        max_retries: int,
    ) -> str:
        """构建评估消息"""
        criteria_text = "\n".join(f"- {c}" for c in success_criteria) if success_criteria else "（未指定明确的成功标准）"
        
        return f"""请评估以下执行结果：

## 原始任务
{task_description}

## 成功标准
{criteria_text}

## 执行结果
{executor_output}

## 上下文
- 当前重试次数: {retry_count}
- 最大重试次数: {max_retries}

请根据提示词中的指导原则，输出 JSON 格式的评估结果。

注意：
1. 如果成功标准不明确，可以建议 ask_human 获取澄清
2. 如果你无法判断结果好坏，诚实地设置 confidence 为 low
3. 建议必须具体可执行"""
    
    def _parse_critique_response(self, response_text: str) -> CriticResult:
        """解析 LLM 响应为 CriticResult（健壮版本）"""
        # 尝试多种方式提取 JSON
        json_text = response_text.strip()
        
        # 方法 1: 提取 markdown 代码块中的 JSON
        json_block_match = re.search(r'```json\s*([\s\S]*?)\s*```', json_text)
        if json_block_match:
            json_text = json_block_match.group(1).strip()
        else:
            # 方法 2: 提取第一个 { ... } 块（贪婪匹配到最后一个 }）
            brace_match = re.search(r'\{[\s\S]*\}', json_text)
            if brace_match:
                json_text = brace_match.group(0)
            else:
                # 方法 3: 移除简单的代码块标记
                if json_text.startswith("```json"):
                    json_text = json_text[7:]
                elif json_text.startswith("```"):
                    json_text = json_text[3:]
                if json_text.endswith("```"):
                    json_text = json_text[:-3]
                json_text = json_text.strip()
        
        # 尝试解析，如果失败则尝试截断到第一个完整 JSON 对象
        data = None
        try:
            data = json.loads(json_text)
        except json.JSONDecodeError:
            # 尝试找到第一个完整的 JSON 对象（通过括号匹配）
            depth = 0
            end_pos = 0
            for i, char in enumerate(json_text):
                if char == '{':
                    depth += 1
                elif char == '}':
                    depth -= 1
                    if depth == 0:
                        end_pos = i + 1
                        break
            
            if end_pos > 0:
                json_text = json_text[:end_pos]
                try:
                    data = json.loads(json_text)
                except json.JSONDecodeError as e:
                    logger.error(f"❌ JSON 解析失败（截断后）: {e}, response_text={response_text[:200]}")
        
        # 如果解析失败，返回 ask_human
        if data is None:
            logger.error(f"❌ 无法解析 Critic 响应, response_text={response_text[:300]}")
            return CriticResult(
                observations=["无法解析 Critic 响应"],
                gaps=[],
                root_cause="JSON 解析失败",
                suggestions=["人工检查执行结果"],
                recommended_action=CriticAction.ASK_HUMAN,
                reasoning="无法解析 LLM 响应为 JSON，需要人工介入",
                confidence=CriticConfidence.LOW,
            )
        
        # 解析 recommended_action
        action_str = data.get("recommended_action", "ask_human").lower()
        try:
            action = CriticAction(action_str)
        except ValueError:
            logger.warning(f"⚠️ 未知的 action: {action_str}，使用 ask_human")
            action = CriticAction.ASK_HUMAN
        
        # 解析 confidence
        confidence_str = data.get("confidence", "medium").lower()
        try:
            confidence = CriticConfidence(confidence_str)
        except ValueError:
            logger.warning(f"⚠️ 未知的 confidence: {confidence_str}，使用 medium")
            confidence = CriticConfidence.MEDIUM
        
        # 解析 plan_adjustment
        plan_adjustment = None
        if data.get("plan_adjustment"):
            adj_data = data["plan_adjustment"]
            plan_adjustment = PlanAdjustmentHint(
                action=adj_data.get("action", "modify"),
                reason=adj_data.get("reason", ""),
                new_step=adj_data.get("new_step"),
                context_for_replan=adj_data.get("context_for_replan"),
            )
        
        return CriticResult(
            observations=data.get("observations", []),
            gaps=data.get("gaps", []),
            root_cause=data.get("root_cause"),
            suggestions=data.get("suggestions", []),
            recommended_action=action,
            reasoning=data.get("reasoning", ""),
            confidence=confidence,
            plan_adjustment=plan_adjustment,
        )
    
    def should_auto_execute(self, result: CriticResult) -> bool:
        """
        判断是否可以自动执行推荐行动
        
        Args:
            result: Critic 评估结果
            
        Returns:
            bool: 是否可以自动执行
        """
        # 高信心 + 配置允许自动通过
        if result.confidence == CriticConfidence.HIGH and self.config.auto_pass_on_high_confidence:
            return True
        
        # 低信心 + 配置要求人工介入
        if result.confidence == CriticConfidence.LOW and self.config.require_human_on_low_confidence:
            return False
        
        # 中等信心，默认需要确认
        return False

"""
线索生成工具 - 分析对话内容并生成操作建议

当 AI 判断当前对话需要给用户提供后续操作建议时，主动调用此工具。

使用场景：
- 完成了用户的主要任务后，提供延伸操作建议
- 对话中存在需要用户确认、回复或上传文件的情况
- 助手给出了可转发/分享的内容时
- 用户的问题需要后续跟进操作

操作类型（act）：
- reply: 需要用户回复确认的问题
- forward: 可以转发/分享的内容
- confirm: 需要用户确认的配置或操作
- upload: 需要用户上传文件
"""

from typing import Dict, Any, Optional, List

from core.tool.base import BaseTool, ToolContext
from logger import get_logger
from utils.json_utils import extract_json

logger = get_logger(__name__)

# 线索生成提示词
CLUE_GENERATION_PROMPT = """基于以下对话内容，分析用户可能需要执行的后续操作，生成操作线索列表。

操作类型说明：
- reply: 需要用户回复确认的问题
- forward: 可以转发/分享的内容
- confirm: 需要用户确认的配置或操作
- upload: 需要用户上传文件

生成规则：
1. 每个线索应该具体、可操作
2. 线索文本不超过 30 个字
3. 最多生成 4 个线索
4. 优先生成与当前任务相关的线索
5. 如果助手已完成某项任务，生成后续延伸类线索
6. 不要生成已经完成的操作

对话内容：
用户：{user_message}
助手：{assistant_response}

返回格式（只返回 JSON，不要其他内容）：
{{
    "tasks": [
        {{
            "id": "clue_1",
            "text": "线索描述",
            "act": "reply|forward|confirm|upload",
            "payload": {{}}
        }}
    ]
}}

如果没有合适的线索，返回：
{{"tasks": []}}
"""


class ClueGenerationTool(BaseTool):
    """
    线索生成工具
    
    当 AI 判断当前对话需要给用户提供后续操作建议时调用。
    分析对话内容，生成可操作的线索列表。
    
    注意：clue delta 由 ZenOAdapter.enhance_tool_result 统一生成和发送，
    工具只负责返回结果数据。
    """
    
    name = "clue_generation"
    
    async def execute(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        """
        执行线索生成
        
        Args:
            params: 工具输入参数
                - user_message: 用户消息内容
                - assistant_response: 助手回复内容
            context: 工具执行上下文
            
        Returns:
            生成的线索数据
        """
        user_message = params.get("user_message", "")
        assistant_response = params.get("assistant_response", "")
        
        if not user_message and not assistant_response:
            return {
                "success": False,
                "error": "缺少对话内容（user_message 或 assistant_response）"
            }
        
        logger.info(f"🔍 开始生成线索: session_id={context.session_id}")
        
        try:
            # 1. 截取内容（避免过长）
            user_preview = user_message[:500] if len(user_message) > 500 else user_message
            assistant_preview = assistant_response[:800] if len(assistant_response) > 800 else assistant_response
            
            # 2. 使用 LLM 生成线索
            clue_data = await self._generate_clues_with_llm(
                user_preview, 
                assistant_preview,
                context
            )
            
            if not clue_data or not clue_data.get("tasks"):
                logger.info("○ 未生成线索（无合适的操作建议）")
                return {
                    "success": True,
                    "message": "无需生成线索",
                    "tasks": []
                }
            
            tasks = clue_data.get("tasks", [])
            logger.info(f"✅ 线索已生成: {len(tasks)} 个")
            
            # 注意：clue delta 由 ZenOAdapter.enhance_tool_result 统一处理
            # 不在工具内部直接发送，避免重复
            
            return {
                "success": True,
                "message": f"成功生成 {len(tasks)} 个操作建议",
                "tasks": tasks
            }
        
        except Exception as e:
            logger.warning(f"⚠️ 生成线索失败: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": f"生成线索失败: {str(e)}"
            }
    
    async def _generate_clues_with_llm(
        self,
        user_message: str,
        assistant_response: str,
        context: ToolContext
    ) -> Optional[Dict[str, Any]]:
        """使用 LLM 生成操作线索"""
        try:
            from core.llm.base import Message
            from core.llm import create_llm_service
            
            # 创建轻量级 LLM 实例用于线索生成
            llm = create_llm_service(
                model="claude-3-5-haiku-latest",
                max_tokens=512
            )
            
            prompt = CLUE_GENERATION_PROMPT.format(
                user_message=user_message,
                assistant_response=assistant_response
            )
            
            response = await llm.create_message_async(
                messages=[Message(role="user", content=prompt)],
            )
            
            if response and hasattr(response, 'content') and response.content:
                content = response.content
                
                # 提取原始文本
                raw_text = None
                if isinstance(content, str):
                    raw_text = content.strip()
                elif isinstance(content, list):
                    for block in content:
                        if hasattr(block, 'text'):
                            raw_text = block.text.strip()
                            break
                
                if raw_text:
                    logger.debug(f"📝 LLM 线索返回: {raw_text[:500]}...")
                    
                    # 解析 JSON
                    parsed = extract_json(raw_text)
                    
                    if parsed and isinstance(parsed, dict):
                        tasks = parsed.get("tasks", [])
                        
                        # 验证和清理 tasks
                        valid_tasks = self._validate_tasks(tasks)
                        
                        if valid_tasks:
                            return {"tasks": valid_tasks}
            
            return None
        
        except Exception as e:
            logger.error(f"❌ LLM 生成线索失败: {str(e)}", exc_info=True)
            return None
    
    def _validate_tasks(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """验证和清理 tasks"""
        valid_tasks = []
        valid_acts = {"reply", "forward", "confirm", "upload"}
        
        for i, task in enumerate(tasks[:4]):  # 最多 4 个
            if not isinstance(task, dict):
                continue
            
            text = task.get("text", "").strip()
            act = task.get("act", "reply")
            
            if not text:
                continue
            
            # 验证 act 类型
            if act not in valid_acts:
                act = "reply"  # 默认回退
            
            # 截断过长的文本
            if len(text) > 30:
                text = text[:27] + "..."
            
            valid_task = {
                "id": task.get("id") or f"clue_{i + 1}",
                "text": text,
                "act": act
            }
            
            # 添加可选字段
            if task.get("payload"):
                valid_task["payload"] = task["payload"]
            if task.get("status"):
                valid_task["status"] = task["status"]
            if task.get("metadata"):
                valid_task["metadata"] = task["metadata"]
            
            valid_tasks.append(valid_task)
        
        return valid_tasks


# 工具实例（用于 ToolExecutor 加载）
clue_generation_tool = ClueGenerationTool()

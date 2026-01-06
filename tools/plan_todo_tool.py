"""
Plan/Todo Tool - 任务规划工具（智能版本）

设计原则：
1. 工具封装闭环：内部调用 Claude + Extended Thinking 生成智能计划
2. Agent 无需特殊逻辑，只负责编排
3. Tool 不持有状态，Plan 数据由上层管理
4. 返回纯 JSON，前端自己渲染 UI

架构关系：
```
┌─────────────────────────────────────────────────────────────┐
│  Frontend                                                    │
│  └── 接收 JSON，自己渲染 UI（进度条/看板/时间线）             │
└─────────────────────────────────────────────────────────────┘
                              ↑ plan_json (纯数据)
┌─────────────────────────────────────────────────────────────┐
│  Service 层 (ChatService)                                    │
│  ├── 接收 Tool 输出                                          │
│  ├── 更新 Conversation.metadata.plan                         │
│  └── 持久化到数据库                                          │
└─────────────────────────────────────────────────────────────┘
                              ↑ tool_result (智能生成结果)
┌─────────────────────────────────────────────────────────────┐
│  plan_todo_tool (智能工具)                                   │
│  ├── create_plan: 调用 Claude + Extended Thinking 生成计划   │
│  ├── update_step: 纯计算更新                                 │
│  └── add_step: 纯计算添加                                    │
└─────────────────────────────────────────────────────────────┘
```
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import json
import logging

from core.llm import create_claude_service, Message

logger = logging.getLogger(__name__)


# ===== 计划生成 Prompt =====
PLAN_GENERATION_PROMPT = """你是一个专业的任务规划专家。请根据用户的需求，生成一个详细且可执行的任务计划。

## 输入信息
- 用户需求: {user_query}
- 可用能力: {capabilities}

## 输出格式要求
请以 JSON 格式输出计划，严格遵循以下结构：

```json
{{
    "goal": "任务目标的简洁描述",
    "information_gaps": ["缺失的信息1", "缺失的信息2"],
    "steps": [
        {{
            "action": "具体要执行的动作描述",
            "capability": "所需的能力分类（从可用能力中选择）",
            "purpose": "这一步的目的",
            "expected_output": "预期产出"
        }}
    ]
}}
```

## 规划原则
1. 步骤要具体、可执行
2. 每个步骤只做一件事
3. 步骤之间要有逻辑顺序
4. 选择最合适的能力来执行每个步骤
5. 如果信息不足，在 information_gaps 中列出

请直接输出 JSON，不要添加其他说明。"""


class PlanTodoTool:
    """
    Plan/Todo 工具 - 智能版本
    
    关键设计：
    1. create_plan 调用 Claude + Extended Thinking 生成智能计划
    2. update_step/add_step 保持纯计算
    3. 不持有状态：所有操作都是纯函数
    4. 接收 current_plan 作为参数
    """
    
    name = "plan_todo"
    description = """任务规划工具 - 智能版本。

操作类型:
- create_plan: 创建智能任务计划（内部调用 Claude + Extended Thinking）
  data 格式: {
    "user_query": "用户的原始需求（必需）"
  }
  ⚠️ 工具会自动调用 Claude 生成最优计划！

- update_step: 更新步骤状态
  data 格式: {"step_index": 0, "status": "completed|failed|in_progress", "result": "结果"}

- add_step: 动态添加步骤
  data 格式: {"action": "动作", "purpose": "目的"}

- replan: 重新生成计划（保留已完成步骤）🆕
  data 格式: {
    "reason": "重新规划的原因（必需）",
    "strategy": "full（全量重规划）| incremental（保留已完成步骤，默认）"
  }
  ⚠️ 当发现以下情况时应该调用 replan:
    1. 多个步骤连续失败
    2. 发现原计划遗漏关键信息
    3. 用户需求发生变化
    4. 执行过程中发现更优方案

- get_plan: 获取当前计划状态（无需 data）

返回格式:
- status: success/error
- plan: 更新后的计划 JSON（由调用方存储）
- replan_count: 重新规划次数（replan 时返回）

注意：此工具不持有状态，plan 由调用方管理。
"""
    
    def __init__(self, registry=None):
        """
        初始化工具
        
        Args:
            registry: CapabilityRegistry 实例（用于动态生成 Schema）
        """
        self._registry = registry
        
        # 🆕 创建专用 LLM Service（启用 Extended Thinking）
        self._llm = create_claude_service(
            model="claude-sonnet-4-5-20250929",
            enable_thinking=True,
            enable_caching=False
        )
        logger.info("✅ PlanTodoTool 初始化完成（智能版本，启用 Extended Thinking）")
    
    def get_input_schema(self) -> Dict:
        """
        动态生成 input_schema
        
        Returns:
            Tool 的 input_schema（Claude API 格式）
        """
        # 从 Registry 动态获取分类 ID
        capability_enum = []
        if self._registry and hasattr(self._registry, 'get_category_ids'):
            capability_enum = self._registry.get_category_ids()
        
        if not capability_enum:
            capability_enum = [
                "web_search", "ppt_generation", "document_creation",
                "data_analysis", "file_operations", "code_execution",
                "api_calling", "task_planning"
            ]
        
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "description": "操作类型",
                    "enum": ["create_plan", "update_step", "add_step", "replan"]
                },
                "data": {
                    "type": "object",
                    "description": "操作数据",
                    "properties": {
                        "user_query": {
                            "type": "string",
                            "description": "用户的原始需求（create_plan 时必需）"
                        },
                        "goal": {
                            "type": "string",
                            "description": "任务目标（可选，create_plan 时会自动生成）"
                        },
                        "steps": {
                            "type": "array",
                            "description": "步骤列表（可选，create_plan 时会自动生成）",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "action": {
                                        "type": "string",
                                        "description": "步骤动作描述"
                                    },
                                    "capability": {
                                        "type": "string",
                                        "description": "所需能力分类",
                                        "enum": capability_enum
                                    },
                                    "purpose": {
                                        "type": "string",
                                        "description": "步骤目的"
                                    }
                                },
                                "required": ["action"]
                            }
                        },
                        "step_index": {
                            "type": "integer",
                            "description": "步骤索引（update_step 时必需）"
                        },
                        "status": {
                            "type": "string",
                            "description": "步骤状态（update_step 时必需）",
                            "enum": ["pending", "in_progress", "completed", "failed"]
                        },
                        "result": {
                            "type": "string",
                            "description": "步骤结果（update_step 时可选）"
                        },
                        "reason": {
                            "type": "string",
                            "description": "重新规划的原因（replan 时必需）"
                        },
                        "strategy": {
                            "type": "string",
                            "description": "重新规划策略（replan 时可选）",
                            "enum": ["full", "incremental"],
                            "default": "incremental"
                        }
                    }
                }
            },
            "required": ["operation"]
        }
    
    async def execute(
        self,
        operation: str,
        data: Dict[str, Any] = None,
        current_plan: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        执行工具操作
        
        Args:
            operation: 操作类型
            data: 操作数据
            current_plan: 当前计划（从 Conversation.metadata 传入）
            
        Returns:
            {
                "status": "success/error",
                "plan": {...},  # 新的计划 JSON
                "message": "..."
            }
        """
        data = data or {}
        
        try:
            if operation == "create_plan":
                # 🆕 智能计划生成（调用 Claude + Extended Thinking）
                return await self._create_plan_smart(data)
            elif operation == "update_step":
                return self._update_step(data, current_plan)
            elif operation == "add_step":
                return self._add_step(data, current_plan)
            elif operation == "replan":
                # 🆕 重新规划（保留已完成步骤或全量重规划）
                return await self._replan(data, current_plan)
            else:
                return {
                    "status": "error",
                    "message": f"Unknown operation: {operation}",
                    "available": ["create_plan", "update_step", "add_step", "replan"]
                }
        except Exception as e:
            logger.error(f"❌ PlanTodoTool 执行失败: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}
    
    async def _create_plan_smart(self, data: Dict) -> Dict:
        """
        智能创建任务计划（调用 Claude + Extended Thinking）
        
        Args:
            data: {user_query, goal?, steps?}
            
        Returns:
            {status, plan, message}
        """
        user_query = data.get('user_query', '')
        
        # 如果已提供完整的 goal 和 steps，直接使用（向后兼容）
        if data.get('goal') and data.get('steps'):
            logger.info("📋 使用提供的计划结构（向后兼容模式）")
            return self._create_plan_from_data(data)
        
        if not user_query:
            return {"status": "error", "message": "user_query is required for smart plan generation"}
        
        # 获取可用能力列表
        capabilities = []
        if self._registry and hasattr(self._registry, 'get_category_ids'):
            capabilities = self._registry.get_category_ids()
        if not capabilities:
            capabilities = [
                "web_search", "ppt_generation", "document_creation",
                "data_analysis", "file_operations", "code_execution",
                "code_sandbox", "app_generation", "api_calling", "task_planning"
            ]
        
        # 构建 Prompt
        prompt = PLAN_GENERATION_PROMPT.format(
            user_query=user_query,
            capabilities=", ".join(capabilities)
        )
        
        logger.info(f"🧠 调用 Claude + Extended Thinking 生成计划...")
        logger.info(f"   用户需求: {user_query[:100]}...")
        
        try:
            # 调用 Claude（启用 Extended Thinking）
            response = await self._llm.create_message_async(
                messages=[Message(role="user", content=prompt)],
                system="你是一个专业的任务规划专家，擅长将复杂任务分解为可执行的步骤。"
            )
            
            # 解析 JSON 响应
            content = response.content.strip()
            
            # 移除可能的 markdown 代码块标记
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            plan_data = json.loads(content)
            
            logger.info(f"✅ Claude 生成计划成功: {plan_data.get('goal', '')[:50]}...")
            
            # 使用生成的数据创建计划
            return self._create_plan_from_data({
                "goal": plan_data.get("goal", user_query),
                "steps": plan_data.get("steps", []),
                "information_gaps": plan_data.get("information_gaps", []),
                "user_query": user_query
            })
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON 解析失败: {e}")
            logger.error(f"   响应内容: {content[:200]}...")
            # 降级：使用简单的默认计划
            return self._create_plan_from_data({
                "goal": user_query,
                "steps": [{"action": user_query, "capability": "task_planning"}],
                "user_query": user_query
            })
        except Exception as e:
            logger.error(f"❌ Claude 调用失败: {e}", exc_info=True)
            return {"status": "error", "message": f"Plan generation failed: {str(e)}"}
    
    def _create_plan_from_data(self, data: Dict) -> Dict:
        """
        从数据创建计划结构（纯计算）
        
        Args:
            data: {goal, steps, information_gaps, user_query}
            
        Returns:
            {status, plan, message}
        """
        goal = data.get('goal', '')
        steps = data.get('steps', [])
        information_gaps = data.get('information_gaps', [])
        user_query = data.get('user_query', '')
        
        if not goal:
            return {"status": "error", "message": "Goal is required"}
        
        created_at = datetime.now().isoformat()
        task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # 构建 plan 结构
        plan = {
            "task_id": task_id,
            "goal": goal,
            "user_query": user_query,
            "created_at": created_at,
            "updated_at": created_at,
            "information_gaps": information_gaps,
            "status": "executing",
            "current_step": 0,
            "total_steps": len(steps),
            "completed_steps": 0,
            "failed_steps": 0,
            "retry_count": 0,
            "steps": []
        }
        
        for i, step in enumerate(steps):
            # 兼容字符串和字典两种格式
            if isinstance(step, str):
                step_data = {
                    "action": step,
                    "capability": "",
                    "query": "",
                    "purpose": "",
                    "expected_output": ""
                }
            else:
                step_data = step
            
            plan["steps"].append({
                "step_id": i + 1,
                "index": i,
                "action": step_data.get('action', ''),
                "capability": step_data.get('capability', ''),
                "query": step_data.get('query', ''),
                "purpose": step_data.get('purpose', ''),
                "expected_output": step_data.get('expected_output', ''),
                "status": "pending" if i > 0 else "in_progress",
                "result": None,
                "retry_count": 0,
                "started_at": None,
                "completed_at": None
            })
        
        return {
            "status": "success",
            "message": f"Plan created: {goal}",
            "plan": plan
        }
    
    def _update_step(self, data: Dict, current_plan: Optional[Dict]) -> Dict:
        """
        更新步骤状态（纯计算）
        
        Args:
            data: {step_index, status, result}
            current_plan: 当前计划
            
        Returns:
            {status, plan, message}
        """
        if not current_plan:
            return {"status": "error", "message": "No active plan"}
        
        step_index = data.get('step_index')
        status = data.get('status', 'completed')
        result = data.get('result', '')
        
        if step_index is None:
            return {"status": "error", "message": "step_index is required"}
        
        if step_index >= len(current_plan.get('steps', [])):
            return {"status": "error", "message": f"Invalid step_index: {step_index}"}
        
        # 复制 plan（不修改原对象）
        plan = self._deep_copy_plan(current_plan)
        now = datetime.now().isoformat()
        plan["updated_at"] = now
        
        # 更新步骤
        step = plan['steps'][step_index]
        old_status = step['status']
        step['status'] = status
        step['result'] = result
        
        if status == 'in_progress' and not step.get('started_at'):
            step['started_at'] = now
        elif status in ['completed', 'failed']:
            step['completed_at'] = now
        
        # 处理重试
        if status == 'failed' and old_status != 'failed':
            step['retry_count'] = step.get('retry_count', 0) + 1
            plan['retry_count'] = plan.get('retry_count', 0) + 1
        
        # 统计
        plan['completed_steps'] = sum(1 for s in plan['steps'] if s['status'] == 'completed')
        plan['failed_steps'] = sum(1 for s in plan['steps'] if s['status'] == 'failed')
        
        # 自动推进 current_step
        if status == 'completed' and step_index == plan['current_step']:
            plan['current_step'] = min(step_index + 1, len(plan['steps']))
            # 标记下一步为 in_progress
            if plan['current_step'] < len(plan['steps']):
                plan['steps'][plan['current_step']]['status'] = 'in_progress'
                plan['steps'][plan['current_step']]['started_at'] = now
        
        # 检查是否全部完成
        all_done = all(s['status'] in ['completed', 'failed'] for s in plan['steps'])
        if all_done:
            if plan['completed_steps'] == len(plan['steps']):
                plan['status'] = 'completed'
            elif plan['failed_steps'] > 0:
                plan['status'] = 'partial'
        
        return {
            "status": "success",
            "message": f"Step {step_index + 1} → {status}",
            "plan": plan
        }
    
    def _add_step(self, data: Dict, current_plan: Optional[Dict]) -> Dict:
        """
        动态添加步骤（纯计算）
        
        Args:
            data: {action, capability, purpose}
            current_plan: 当前计划
            
        Returns:
            {status, plan, message}
        """
        if not current_plan:
            return {"status": "error", "message": "No active plan"}
        
        action = data.get('action', '')
        capability = data.get('capability', '')
        purpose = data.get('purpose', '')
        
        if not action:
            return {"status": "error", "message": "action is required"}
        
        # 复制 plan
        plan = self._deep_copy_plan(current_plan)
        now = datetime.now().isoformat()
        plan["updated_at"] = now
        
        new_index = len(plan['steps'])
        plan['steps'].append({
            "step_id": new_index + 1,
            "index": new_index,
            "action": action,
            "capability": capability,
            "purpose": purpose,
            "status": "pending",
            "result": None,
            "retry_count": 0,
            "started_at": None,
            "completed_at": None
        })
        plan['total_steps'] = len(plan['steps'])
        
        return {
            "status": "success",
            "message": f"Step {new_index + 1} added",
            "plan": plan
        }
    
    async def _replan(self, data: Dict, current_plan: Optional[Dict]) -> Dict:
        """
        重新生成计划（调用 Claude + Extended Thinking）
        
        策略：
        - incremental（默认）：保留已完成的步骤，只重新生成剩余步骤
        - full：全量重新生成计划（忽略已完成步骤）
        
        Args:
            data: {reason, strategy}
            current_plan: 当前计划
            
        Returns:
            {status, plan, message, replan_count}
        """
        reason = data.get('reason', '')
        strategy = data.get('strategy', 'incremental')
        
        if not reason:
            return {"status": "error", "message": "reason is required for replan"}
        
        if not current_plan:
            return {"status": "error", "message": "No active plan to replan"}
        
        # 检查重规划次数限制
        replan_count = current_plan.get('replan_count', 0) + 1
        max_replan = 3  # 默认最大重规划次数
        if replan_count > max_replan:
            return {
                "status": "error",
                "message": f"已达到最大重规划次数 ({max_replan})，请尝试其他方法",
                "replan_count": replan_count - 1
            }
        
        logger.info(f"🔄 开始重新规划 (第 {replan_count} 次)...")
        logger.info(f"   原因: {reason}")
        logger.info(f"   策略: {strategy}")
        
        # 获取原始用户需求
        user_query = current_plan.get('user_query', current_plan.get('goal', ''))
        
        # 收集执行上下文
        completed_steps = []
        failed_steps = []
        pending_steps = []
        
        for step in current_plan.get('steps', []):
            if step['status'] == 'completed':
                completed_steps.append({
                    'action': step['action'],
                    'result': step.get('result', '')
                })
            elif step['status'] == 'failed':
                failed_steps.append({
                    'action': step['action'],
                    'result': step.get('result', '')
                })
            else:
                pending_steps.append(step['action'])
        
        # 构建重规划 Prompt
        replan_prompt = self._build_replan_prompt(
            user_query=user_query,
            reason=reason,
            strategy=strategy,
            completed_steps=completed_steps,
            failed_steps=failed_steps,
            pending_steps=pending_steps,
            original_goal=current_plan.get('goal', '')
        )
        
        try:
            # 调用 Claude 重新规划
            response = await self._llm.create_message_async(
                messages=[Message(role="user", content=replan_prompt)],
                system="你是一个专业的任务规划专家。请根据执行情况重新规划任务，确保能够成功完成用户目标。"
            )
            
            # 解析响应
            content = response.content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            new_plan_data = json.loads(content)
            
            # 构建新计划
            now = datetime.now().isoformat()
            
            if strategy == "incremental":
                # 增量策略：保留已完成步骤
                new_plan = self._deep_copy_plan(current_plan)
                new_plan["updated_at"] = now
                new_plan["replan_count"] = replan_count
                new_plan["replan_reason"] = reason
                new_plan["status"] = "executing"
                
                # 移除未完成的步骤
                new_plan["steps"] = [s for s in new_plan["steps"] if s["status"] == "completed"]
                
                # 添加新生成的步骤
                new_steps = new_plan_data.get('steps', [])
                for i, step in enumerate(new_steps):
                    if isinstance(step, str):
                        step_data = {"action": step, "capability": "", "purpose": ""}
                    else:
                        step_data = step
                    
                    new_index = len(new_plan["steps"])
                    new_plan["steps"].append({
                        "step_id": new_index + 1,
                        "index": new_index,
                        "action": step_data.get('action', ''),
                        "capability": step_data.get('capability', ''),
                        "purpose": step_data.get('purpose', ''),
                        "expected_output": step_data.get('expected_output', ''),
                        "status": "in_progress" if new_index == len(new_plan["steps"]) else "pending",
                        "result": None,
                        "retry_count": 0,
                        "started_at": now if new_index == len(new_plan["steps"]) - 1 else None,
                        "completed_at": None
                    })
                
                # 更新计划元数据
                new_plan["total_steps"] = len(new_plan["steps"])
                new_plan["current_step"] = len(completed_steps)
                
            else:
                # 全量策略：完全重新生成
                result = self._create_plan_from_data({
                    "goal": new_plan_data.get("goal", current_plan.get("goal")),
                    "steps": new_plan_data.get("steps", []),
                    "information_gaps": new_plan_data.get("information_gaps", []),
                    "user_query": user_query
                })
                
                if result["status"] != "success":
                    return result
                
                new_plan = result["plan"]
                new_plan["replan_count"] = replan_count
                new_plan["replan_reason"] = reason
                new_plan["previous_completed_steps"] = completed_steps  # 保存历史记录
            
            logger.info(f"✅ 重新规划完成: {len(new_plan['steps'])} 个步骤")
            
            return {
                "status": "success",
                "message": f"Plan regenerated ({strategy}): {reason}",
                "plan": new_plan,
                "replan_count": replan_count
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ 重规划 JSON 解析失败: {e}")
            return {"status": "error", "message": f"Replan JSON parse error: {str(e)}"}
        except Exception as e:
            logger.error(f"❌ 重规划失败: {e}", exc_info=True)
            return {"status": "error", "message": f"Replan failed: {str(e)}"}
    
    def _build_replan_prompt(
        self,
        user_query: str,
        reason: str,
        strategy: str,
        completed_steps: List[Dict],
        failed_steps: List[Dict],
        pending_steps: List[str],
        original_goal: str
    ) -> str:
        """构建重规划 Prompt"""
        
        # 已完成步骤摘要
        completed_summary = ""
        if completed_steps:
            completed_summary = "\n".join([
                f"  ✅ {s['action']}: {s['result'][:100]}..." if len(s.get('result', '')) > 100 else f"  ✅ {s['action']}: {s.get('result', '无结果')}"
                for s in completed_steps
            ])
        else:
            completed_summary = "  （无）"
        
        # 失败步骤摘要
        failed_summary = ""
        if failed_steps:
            failed_summary = "\n".join([
                f"  ❌ {s['action']}: {s['result'][:100]}..." if len(s.get('result', '')) > 100 else f"  ❌ {s['action']}: {s.get('result', '未知错误')}"
                for s in failed_steps
            ])
        else:
            failed_summary = "  （无）"
        
        # 待执行步骤
        pending_summary = "\n".join([f"  ⏳ {s}" for s in pending_steps]) if pending_steps else "  （无）"
        
        # 获取可用能力
        capabilities = []
        if self._registry and hasattr(self._registry, 'get_category_ids'):
            capabilities = self._registry.get_category_ids()
        if not capabilities:
            capabilities = ["web_search", "code_execution", "code_sandbox", "file_operations", "api_calling"]
        
        prompt = f"""# 任务重规划请求

## 原始用户需求
{user_query}

## 原始目标
{original_goal}

## 重规划原因
{reason}

## 执行情况

### 已完成步骤
{completed_summary}

### 失败步骤
{failed_summary}

### 待执行步骤（将被替换）
{pending_summary}

## 重规划策略
- **{strategy}**: {'保留已完成步骤，只生成新的剩余步骤' if strategy == 'incremental' else '完全重新生成计划'}

## 可用能力
{', '.join(capabilities)}

## 输出要求
请生成新的任务计划，格式如下：

```json
{{
    "goal": "更新后的目标描述",
    "steps": [
        {{
            "action": "具体动作",
            "capability": "所需能力",
            "purpose": "目的"
        }}
    ],
    "information_gaps": ["如果有缺失信息"]
}}
```

{'注意：只需要生成**剩余步骤**，已完成的步骤会被保留。' if strategy == 'incremental' else '注意：生成完整的新计划。'}

请直接输出 JSON，不要添加其他说明。"""
        
        return prompt
    
    def _deep_copy_plan(self, plan: Dict) -> Dict:
        """深拷贝 plan 对象"""
        import copy
        return copy.deepcopy(plan)
    
    # ==================== 辅助方法（静态，供外部使用）====================
    
    @staticmethod
    def get_progress(plan: Optional[Dict]) -> Dict[str, Any]:
        """
        获取计划进度信息
        
        Args:
            plan: 计划对象
            
        Returns:
            {
                "has_plan": bool,
                "total": int,
                "completed": int,
                "failed": int,
                "progress": float (0-1),
                "current_step": int,
                "status": str
            }
        """
        if not plan:
            return {
                "has_plan": False,
                "total": 0,
                "completed": 0,
                "failed": 0,
                "progress": 0.0,
                "current_step": 0,
                "status": "none"
            }
        
        total = plan.get('total_steps', len(plan.get('steps', [])))
        completed = plan.get('completed_steps', 0)
        failed = plan.get('failed_steps', 0)
        
        return {
            "has_plan": True,
            "total": total,
            "completed": completed,
            "failed": failed,
            "progress": completed / total if total > 0 else 0.0,
            "current_step": plan.get('current_step', 0),
            "status": plan.get('status', 'executing'),
            "goal": plan.get('goal', '')
        }
    
    @staticmethod
    def get_current_step(plan: Optional[Dict]) -> Optional[Dict]:
        """获取当前步骤"""
        if not plan:
            return None
        idx = plan.get('current_step', 0)
        steps = plan.get('steps', [])
        if 0 <= idx < len(steps):
            return steps[idx]
        return None
    
    @staticmethod
    def get_context_for_llm(plan: Optional[Dict]) -> str:
        """
        获取精简的 Plan 上下文给 LLM
        
        减少 tokens 消耗
        """
        if not plan:
            return "[Plan] No active plan"
        
        total = plan.get('total_steps', 0)
        current_idx = plan.get('current_step', 0)
        completed = plan.get('completed_steps', 0)
        status = plan.get('status', 'executing')
        
        current_step = None
        steps = plan.get('steps', [])
        if 0 <= current_idx < len(steps):
            current_step = steps[current_idx]
        
        lines = [
            f"[Plan] {plan.get('goal', '')}",
            f"Status: {status} | Progress: {completed}/{total}"
        ]
        
        if current_step:
            lines.append(f"Current: {current_step.get('action', '')} → {current_step.get('purpose', '')}")
        
        return "\n".join(lines)


# 工具 Schema（用于 Claude API 注册）
PLAN_TODO_TOOL_SCHEMA = {
    "name": "plan_todo",
    "description": """智能任务规划工具。

操作：
- create_plan: 智能创建计划 {"user_query": "用户需求"}（自动调用 Claude + Extended Thinking）
- update_step: 更新步骤 {"step_index": 0, "status": "completed|failed|in_progress", "result": "..."}
- add_step: 添加步骤 {"action": "...", "purpose": "..."}

返回新的 plan JSON，由调用方决定如何存储。""",
    "input_schema": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "description": "操作类型",
                "enum": ["create_plan", "update_step", "add_step"]
            },
            "data": {
                "type": "object",
                "description": "操作数据"
            }
        },
        "required": ["operation"]
    }
}


def create_plan_todo_tool(registry=None) -> PlanTodoTool:
    """
    创建 Plan/Todo 工具实例
    
    Args:
        registry: CapabilityRegistry 实例（用于动态生成 Schema）
    
    Returns:
        PlanTodoTool 实例
    """
    return PlanTodoTool(registry=registry)

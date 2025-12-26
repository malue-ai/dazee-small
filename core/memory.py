"""
Memory Layer - 记忆管理层

职责：
1. Working Memory：当前会话的短期记忆（消息历史、工具调用）
2. Episodic Memory：长期任务历史（历史会话、经验教训）
3. Skill Memory：已加载的Skills缓存

设计原则：
- 框架层：只负责存储和检索，不包含业务逻辑
- 状态管理：提供统一的内存接口
- 可扩展：支持多种存储后端（内存、文件、数据库）
"""

import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
from logger import get_logger

logger = get_logger("memory")

class WorkingMemory:
    """
    工作记忆 - 当前会话的短期记忆
    
    存储内容：
    - 消息历史（messages）
    - 工具调用记录（tool_calls）
    - 当前任务状态（task_phase, metadata）
    - plan.json（内部 RVR 调度）- 🆕
    - todo.md（用户进度展示 + 状态追踪）- 🆕
    
    设计原则：
    - plan.json 和 todo.md 存储在 Short Memory，避免多轮 LLM tokens 消耗
    - LLM 通过 plan_todo 工具来 CRUD 计划，不需要每次都传递完整计划
    """
    
    def __init__(self):
        self.messages: List[Dict[str, Any]] = []
        self.tool_calls: List[Dict[str, Any]] = []
        self.metadata: Dict[str, Any] = {}
        
        # 🆕 Plan/Todo 存储（会话级短期记忆）
        self.plan_json: Optional[Dict[str, Any]] = None  # 内部 RVR 调度
        self.todo_md: Optional[str] = None  # 用户进度展示
        
    def add_message(self, role: str, content: Any):
        """添加消息"""
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        
        # 🔍 输出消息添加日志
        content_preview = str(content)[:80] + '...' if len(str(content)) > 80 else str(content)
        logger.debug(f"💾 添加消息到WorkingMemory: role={role}, 当前消息总数={len(self.messages)}, 内容={content_preview}")
    
    def add_tool_call(self, tool_name: str, tool_input: Dict[str, Any], result: Any = None):
        """记录工具调用"""
        self.tool_calls.append({
            "tool": tool_name,
            "input": tool_input,
            "result": result,
            "timestamp": datetime.now().isoformat()
        })
    
    def update_metadata(self, key: str, value: Any):
        """更新元数据"""
        self.metadata[key] = value
    
    def get_messages(self, last_n: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取消息历史"""
        if last_n:
            return self.messages[-last_n:]
        return self.messages
    
    def get_tool_history(self) -> List[Dict[str, Any]]:
        """获取工具调用历史"""
        return self.tool_calls
    
    def clear(self):
        """清空工作记忆"""
        self.messages.clear()
        self.tool_calls.clear()
        self.metadata.clear()
        self.plan_json = None
        self.todo_md = None
    
    # ==================== Plan/Todo CRUD ====================
    
    def set_plan(self, plan_json: Dict[str, Any], todo_md: str):
        """
        设置 Plan 和 Todo（Create/Update）
        
        Args:
            plan_json: plan.json 结构（内部 RVR 调度）
            todo_md: todo.md 内容（用户进度展示）
        """
        self.plan_json = plan_json
        self.todo_md = todo_md
        self.update_metadata("plan_updated_at", datetime.now().isoformat())
    
    def get_plan(self) -> Optional[Dict[str, Any]]:
        """获取 plan.json（Read）"""
        return self.plan_json
    
    def get_todo(self) -> Optional[str]:
        """获取 todo.md（Read）"""
        return self.todo_md
    
    def has_plan(self) -> bool:
        """是否有活跃计划"""
        return self.plan_json is not None
    
    def update_plan_step(self, step_index: int, status: str, result: str = None):
        """
        更新计划步骤状态（Update）
        
        Args:
            step_index: 步骤索引（0-based）
            status: 状态（pending|in_progress|completed|failed）
            result: 步骤结果
        """
        if not self.plan_json or "steps" not in self.plan_json:
            return
        
        if 0 <= step_index < len(self.plan_json["steps"]):
            step = self.plan_json["steps"][step_index]
            old_status = step.get("status", "pending")
            step["status"] = status
            if result:
                step["result"] = result
            step["updated_at"] = datetime.now().isoformat()
            
            # 更新 current_step
            if status == "completed" and step_index == self.plan_json.get("current_step", 0):
                self.plan_json["current_step"] = min(
                    step_index + 1, 
                    len(self.plan_json["steps"]) - 1
                )
                # 标记下一步为 in_progress
                next_idx = self.plan_json["current_step"]
                if next_idx < len(self.plan_json["steps"]):
                    self.plan_json["steps"][next_idx]["status"] = "in_progress"
            
            # 检查是否全部完成
            all_done = all(
                s.get("status") in ["completed", "failed"] 
                for s in self.plan_json["steps"]
            )
            if all_done:
                completed = sum(
                    1 for s in self.plan_json["steps"] 
                    if s.get("status") == "completed"
                )
                if completed == len(self.plan_json["steps"]):
                    self.plan_json["status"] = "completed"
                else:
                    self.plan_json["status"] = "partial"
            
            # 重新生成 todo.md
            self._regenerate_todo_md()
    
    def _regenerate_todo_md(self):
        """根据 plan.json 重新生成 todo.md"""
        if not self.plan_json:
            self.todo_md = None
            return
        
        plan = self.plan_json
        total = len(plan.get("steps", []))
        current = plan.get("current_step", 0)
        retry = plan.get("retry_count", 0)
        status = plan.get("status", "executing")
        completed = sum(
            1 for s in plan.get("steps", []) 
            if s.get("status") == "completed"
        )
        
        # 状态元数据（首行注释）
        meta_line = f"<!-- Status: {status} | Step: {current + 1}/{total} | Retry: {retry} -->"
        
        lines = [
            meta_line,
            "",
            "# 📋 任务进度",
            "",
            f"🎯 **目标**: {plan.get('goal', '')}",
            "",
            "## To-do List",
            ""
        ]
        
        # 步骤列表
        for step in plan.get("steps", []):
            step_status = step.get("status", "pending")
            result = step.get("result", "")
            
            # 状态图标和复选框
            if step_status == "completed":
                icon = "✅"
                checkbox = "[x]"
                suffix = f" - {result}" if result else ""
            elif step_status == "in_progress":
                icon = "🔄"
                checkbox = "[ ]"
                suffix = " - 执行中..."
            elif step_status == "failed":
                icon = "❌"
                checkbox = "[ ]"
                suffix = f" - 失败: {result}" if result else " - 失败"
            else:  # pending
                icon = "○"
                checkbox = "[ ]"
                suffix = ""
            
            # 显示文本
            action = step.get("action", "")
            purpose = step.get("purpose", "")
            display_text = f"{action}" if action else purpose
            if purpose and action:
                display_text = f"{action} → {purpose}"
            
            step_num = step.get("step_id", step.get("index", 0) + 1)
            lines.append(f"- {checkbox} {icon} Step {step_num}: {display_text}{suffix}")
        
        # 进度条
        progress = completed / total if total > 0 else 0
        bar_width = 20
        filled = int(bar_width * progress)
        bar = "█" * filled + "░" * (bar_width - filled)
        
        lines.extend([
            "",
            "---",
            f"**进度**: [{bar}] {progress*100:.0f}% ({completed}/{total})",
            f"**阶段**: {status}"
        ])
        
        self.todo_md = "\n".join(lines)
    
    def clear_plan(self):
        """清除计划（Delete）"""
        self.plan_json = None
        self.todo_md = None
    
    def get_plan_context_for_llm(self) -> str:
        """
        获取 Plan 上下文给 LLM（精简版，避免 token 浪费）
        
        返回格式：
        [Plan Context]
        Status: executing | Step: 2/5
        Current: web_search → 收集信息
        """
        if not self.plan_json:
            return "[Plan Context] No active plan"
        
        plan = self.plan_json
        total = len(plan.get("steps", []))
        current_idx = plan.get("current_step", 0)
        status = plan.get("status", "executing")
        
        current_step = None
        if 0 <= current_idx < total:
            current_step = plan["steps"][current_idx]
        
        lines = [
            f"[Plan Context]",
            f"Goal: {plan.get('goal', '')}",
            f"Status: {status} | Step: {current_idx + 1}/{total}"
        ]
        
        if current_step:
            action = current_step.get("action", "")
            purpose = current_step.get("purpose", "")
            lines.append(f"Current: {action} → {purpose}")
        
        return "\n".join(lines)


class EpisodicMemory:
    """
    情节记忆 - 长期任务历史
    
    存储内容：
    - 历史会话记录
    - 成功/失败的经验
    - 质量评估数据
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = Path(storage_path) if storage_path else None
        self.episodes: List[Dict[str, Any]] = []
        
        # 如果有存储路径，加载历史
        if self.storage_path and self.storage_path.exists():
            self._load()
    
    def add_episode(
        self,
        session_id: str,
        user_intent: str,
        result: Any,
        quality_score: float,
        metadata: Dict[str, Any] = None
    ):
        """添加一个历史情节"""
        episode = {
            "session_id": session_id,
            "user_intent": user_intent,
            "result": result,
            "quality_score": quality_score,
            "metadata": metadata or {},
            "timestamp": datetime.now().isoformat()
        }
        self.episodes.append(episode)
        
        # 自动持久化
        if self.storage_path:
            self._save()
    
    def get_episodes(
        self,
        last_n: Optional[int] = None,
        min_quality: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """获取历史情节"""
        episodes = self.episodes
        
        # 过滤质量阈值
        if min_quality is not None:
            episodes = [e for e in episodes if e["quality_score"] >= min_quality]
        
        # 返回最近N个
        if last_n:
            return episodes[-last_n:]
        return episodes
    
    def get_similar_episodes(self, user_intent: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        获取相似的历史情节（简单实现：基于关键词匹配）
        
        未来可以使用embedding进行语义相似度检索
        """
        # 简单的关键词匹配
        scored_episodes = []
        intent_words = set(user_intent.lower().split())
        
        for episode in self.episodes:
            episode_words = set(episode["user_intent"].lower().split())
            overlap = len(intent_words & episode_words)
            if overlap > 0:
                scored_episodes.append((overlap, episode))
        
        # 按相似度排序
        scored_episodes.sort(reverse=True, key=lambda x: x[0])
        return [e[1] for e in scored_episodes[:top_k]]
    
    def _save(self):
        """持久化到文件"""
        if not self.storage_path:
            return
        
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump(self.episodes, f, ensure_ascii=False, indent=2)
    
    def _load(self):
        """从文件加载"""
        if not self.storage_path or not self.storage_path.exists():
            return
        
        with open(self.storage_path, 'r', encoding='utf-8') as f:
            self.episodes = json.load(f)


class SkillMemory:
    """
    Skill记忆 - 已加载的Skills缓存
    
    存储内容：
    - Skill元数据（名称、描述、路径）
    - Skill资源（SKILL.md内容、scripts路径）
    """
    
    def __init__(self):
        self.skills: Dict[str, Dict[str, Any]] = {}
    
    def register_skill(
        self,
        skill_name: str,
        skill_path: str,
        description: str = "",
        metadata: Dict[str, Any] = None
    ):
        """注册一个Skill"""
        self.skills[skill_name] = {
            "name": skill_name,
            "path": skill_path,
            "description": description,
            "metadata": metadata or {},
            "loaded_at": datetime.now().isoformat()
        }
    
    def get_skill(self, skill_name: str) -> Optional[Dict[str, Any]]:
        """获取Skill信息"""
        return self.skills.get(skill_name)
    
    def list_skills(self) -> List[str]:
        """列出所有已注册的Skills"""
        return list(self.skills.keys())
    
    def get_skill_path(self, skill_name: str) -> Optional[str]:
        """获取Skill的文件路径"""
        skill = self.get_skill(skill_name)
        return skill["path"] if skill else None


class MemoryManager:
    """
    记忆管理器 - 统一的内存接口
    
    整合三层记忆：
    - Working Memory（短期）
    - Episodic Memory（长期）
    - Skill Memory（技能）
    """
    
    def __init__(self, episodic_storage_path: Optional[str] = None):
        self.working = WorkingMemory()
        self.episodic = EpisodicMemory(episodic_storage_path)
        self.skills = SkillMemory()
    
    def start_session(self, session_id: str, user_intent: str):
        """开始新会话"""
        self.working.clear()
        self.working.update_metadata("session_id", session_id)
        self.working.update_metadata("user_intent", user_intent)
        self.working.update_metadata("start_time", datetime.now().isoformat())
    
    def end_session(self, result: Any, metadata: Dict[str, Any] = None):
        """结束会话，保存到长期记忆"""
        session_id = self.working.metadata.get("session_id", "unknown")
        user_intent = self.working.metadata.get("user_intent", "")
        
        # 保存到情节记忆
        self.episodic.add_episode(
            session_id=session_id,
            user_intent=user_intent,
            result=result,
            quality_score=None,  # 不再自动评分，由用户决定
            metadata=self.working.metadata
        )
    
    def get_context_for_llm(self, include_history: bool = True) -> Dict[str, Any]:
        """
        为LLM准备上下文
        
        Returns:
            {
                "messages": [...],
                "tool_history": [...],
                "relevant_episodes": [...]  # 可选：相关历史经验
            }
        """
        context = {
            "messages": self.working.get_messages(),
            "tool_history": self.working.get_tool_history(),
            "metadata": self.working.metadata
        }
        
        if include_history:
            # 获取相似的历史情节作为参考
            user_intent = self.working.metadata.get("user_intent", "")
            if user_intent:
                similar_episodes = self.episodic.get_similar_episodes(user_intent, top_k=2)
                context["relevant_episodes"] = similar_episodes
        
        return context


# 便捷函数
def create_memory_manager(workspace_dir: Optional[str] = None) -> MemoryManager:
    """
    创建记忆管理器
    
    Args:
        workspace_dir: 工作目录（用于持久化episodic memory）
        
    Returns:
        配置好的MemoryManager实例
    """
    if workspace_dir:
        episodic_path = str(Path(workspace_dir) / "memory" / "episodic_memory.json")
    else:
        episodic_path = None
    
    return MemoryManager(episodic_storage_path=episodic_path)


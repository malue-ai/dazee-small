"""
Plan Memory - 任务计划持久化记忆

职责：
- 跨 Session 持久化任务计划
- 存储步骤完成状态
- 生成 Session 进度摘要

设计原则：
- 步骤只能标记 passes: true，永不删除
- 自动生成进度摘要用于 Prompt 注入
- 对用户透明，框架自动处理

存储位置：storage/users/{user_id}/plans/{task_id}.json

参考：
- Anthropic Blog: https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- 示例格式: feature_list.json + progress.txt
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles

from logger import get_logger

from ..base import BaseScopedMemory, MemoryConfig, MemoryScope, StorageBackend

logger = get_logger("memory.user.plan")


class PlanMemory(BaseScopedMemory):
    """
    任务计划持久化记忆

    存储结构（单个计划）：
    {
        "task_id": "task_xxx",
        "goal": "生成产品PPT",
        "user_query": "帮我做一个产品介绍PPT",
        "steps": [
            {
                "index": 0,
                "action": "搜索产品资料",
                "passes": false,
                "verified_at": null,
                "result": null
            },
            ...
        ],
        "session_summaries": [
            {
                "session": 1,
                "completed": ["搜索资料"],
                "timestamp": "2026-01-07T14:00:00Z",
                "next_hint": "使用 PPT Skill + api_calling 生成"
            }
        ],
        "created_at": "...",
        "updated_at": "...",
        "completion_rate": "1/2"
    }

    核心规则：
    1. 步骤只能标记 passes: true，永不删除
    2. session_summaries 记录跨 session 的进度
    3. 自动生成进度摘要用于 Prompt 注入
    """

    def __init__(self, user_id: Optional[str] = None, storage_dir: Optional[str] = None):
        """
        初始化 PlanMemory

        Args:
            user_id: 用户 ID（用于隔离数据）
            storage_dir: 存储目录（自动生成子目录 plans/）
        """
        config = MemoryConfig(
            scope=MemoryScope.USER,
            backend=StorageBackend.FILE if storage_dir else StorageBackend.MEMORY,
            storage_path=storage_dir,
        )
        super().__init__(scope_id=user_id, config=config)

        self.user_id = user_id
        self.storage_dir = Path(storage_dir) if storage_dir else None

        # 计划存储目录
        if self.storage_dir:
            if user_id:
                self.plans_dir = self.storage_dir / "users" / user_id / "plans"
            else:
                self.plans_dir = self.storage_dir / "plans"
            self.plans_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.plans_dir = None

        # 内存缓存（用于快速访问）
        self._plans_cache: Dict[str, Dict] = {}

        logger.debug(f"[PlanMemory] 初始化: user_id={user_id}, storage_dir={storage_dir}")

    # ==================== 核心 CRUD 操作 ====================

    async def save_plan(
        self,
        task_id: str,
        goal: str,
        steps: List[Dict],
        user_query: str = "",
        metadata: Optional[Dict] = None,
    ) -> bool:
        """
        保存新计划（首次 Session 调用）（异步版本）

        Args:
            task_id: 任务 ID
            goal: 任务目标
            steps: 步骤列表（从 plan_todo 传入）
            user_query: 用户原始查询
            metadata: 额外元数据（如 recommended_skill）

        Returns:
            是否保存成功
        """
        now = datetime.now().isoformat()

        # 构建持久化结构
        plan_data = {
            "task_id": task_id,
            "goal": goal,
            "user_query": user_query,
            "steps": self._normalize_steps(steps),
            "session_summaries": [],
            "metadata": metadata or {},
            "created_at": now,
            "updated_at": now,
            "completion_rate": self._calculate_completion_rate([]),
        }

        # 保存到缓存
        self._plans_cache[task_id] = plan_data

        # 持久化到文件
        if self.plans_dir:
            await self._save_to_file(task_id, plan_data)

        logger.info(f"[PlanMemory] 保存计划: task_id={task_id}, goal={goal[:50]}...")
        return True

    async def load_plan(self, task_id: str) -> Optional[Dict]:
        """
        加载计划（后续 Session 恢复时调用）（异步版本）

        Args:
            task_id: 任务 ID

        Returns:
            计划数据，不存在则返回 None
        """
        # 先从缓存读取
        if task_id in self._plans_cache:
            return self._plans_cache[task_id]

        # 从文件读取
        if self.plans_dir:
            plan_data = await self._load_from_file(task_id)
            if plan_data:
                self._plans_cache[task_id] = plan_data
                return plan_data

        return None

    async def update_step_status(
        self, task_id: str, step_index: int, passes: bool, result: Optional[str] = None
    ) -> bool:
        """
        更新步骤状态（只能标记 passes: true，永不删除）（异步版本）

        核心规则：
        - 步骤只能标记 passes: true
        - 永不删除或修改步骤描述
        - 添加 verified_at 时间戳

        Args:
            task_id: 任务 ID
            step_index: 步骤索引
            passes: 是否通过
            result: 执行结果（可选）

        Returns:
            是否更新成功
        """
        plan_data = await self.load_plan(task_id)
        if not plan_data:
            logger.warning(f"[PlanMemory] 更新步骤失败: 计划不存在 task_id={task_id}")
            return False

        steps = plan_data.get("steps", [])
        if step_index >= len(steps):
            logger.warning(f"[PlanMemory] 更新步骤失败: 索引越界 step_index={step_index}")
            return False

        now = datetime.now().isoformat()
        step = steps[step_index]

        # 只能标记为 true（核心规则：只增不删）
        if passes and not step.get("passes"):
            step["passes"] = True
            step["verified_at"] = now

        if result:
            step["result"] = result

        plan_data["updated_at"] = now
        plan_data["completion_rate"] = self._calculate_completion_rate(steps)

        # 保存
        self._plans_cache[task_id] = plan_data
        if self.plans_dir:
            await self._save_to_file(task_id, plan_data)

        logger.debug(
            f"[PlanMemory] 更新步骤: task_id={task_id}, step={step_index}, passes={passes}"
        )
        return True

    async def add_session_summary(
        self, task_id: str, completed_steps: List[str], next_step_hint: str = ""
    ) -> bool:
        """
        添加 Session 进度摘要（每个 Session 结束时调用）（异步版本）

        Args:
            task_id: 任务 ID
            completed_steps: 本次 Session 完成的步骤描述
            next_step_hint: 下一步建议

        Returns:
            是否添加成功
        """
        plan_data = await self.load_plan(task_id)
        if not plan_data:
            return False

        summaries = plan_data.get("session_summaries", [])
        session_num = len(summaries) + 1

        summaries.append(
            {
                "session": session_num,
                "completed": completed_steps,
                "timestamp": datetime.now().isoformat(),
                "next_hint": next_step_hint,
            }
        )

        plan_data["session_summaries"] = summaries
        plan_data["updated_at"] = datetime.now().isoformat()

        # 保存
        self._plans_cache[task_id] = plan_data
        if self.plans_dir:
            await self._save_to_file(task_id, plan_data)

        logger.info(f"[PlanMemory] 添加 Session 摘要: task_id={task_id}, session={session_num}")
        return True

    # ==================== 进度摘要生成（用于 Prompt 注入）====================

    async def get_session_summary(self, task_id: str) -> str:
        """
        生成 Session 进度摘要（用于注入到 System Prompt）（异步版本）

        这是框架自动处理的核心功能，用户无感知。

        Args:
            task_id: 任务 ID

        Returns:
            格式化的进度摘要（Markdown 格式）
        """
        plan_data = await self.load_plan(task_id)
        if not plan_data:
            return ""

        goal = plan_data.get("goal", "")
        steps = plan_data.get("steps", [])
        summaries = plan_data.get("session_summaries", [])

        # 统计进度
        total = len(steps)
        completed = sum(1 for s in steps if s.get("passes"))
        pending = total - completed

        # 生成步骤列表
        step_list = []
        for step in steps:
            status = "[x]" if step.get("passes") else "[ ]"
            step_list.append(f"- {status} {step.get('action', '')}")

        # 获取上次建议
        last_hint = ""
        if summaries:
            last_hint = summaries[-1].get("next_hint", "")

        # 构建摘要
        summary = f"""
---
## 🔄 任务进度恢复（框架自动注入）

**目标**: {goal}

**进度**: {completed}/{total} ({int(completed/total*100) if total > 0 else 0}%)

**步骤状态**:
{chr(10).join(step_list)}
"""

        if last_hint:
            summary += f"""
**上次建议**: {last_hint}
"""

        summary += """
**恢复协议**:
1. 继续处理第一个未完成的步骤
2. 完成后使用 plan_todo.update_step 更新状态
3. 每次只处理一个步骤，避免一次性完成太多
---
"""
        return summary

    # ==================== 查询方法 ====================

    def has_persistent_plan(self, task_id: str) -> bool:
        """
        检查是否有持久化的计划（用于判断是首次还是恢复）

        Args:
            task_id: 任务 ID

        Returns:
            是否存在持久化计划
        """
        # 先检查缓存
        if task_id in self._plans_cache:
            return True

        # 检查文件
        if self.plans_dir:
            file_path = self.plans_dir / f"{task_id}.json"
            return file_path.exists()

        return False

    async def get_incomplete_steps(self, task_id: str) -> List[Dict]:
        """
        获取未完成的步骤（异步版本）

        Args:
            task_id: 任务 ID

        Returns:
            未完成步骤列表
        """
        plan_data = await self.load_plan(task_id)
        if not plan_data:
            return []

        return [step for step in plan_data.get("steps", []) if not step.get("passes")]

    async def get_next_step(self, task_id: str) -> Optional[Dict]:
        """
        获取下一个待执行步骤（异步版本）

        Args:
            task_id: 任务 ID

        Returns:
            下一个待执行步骤，无则返回 None
        """
        incomplete = await self.get_incomplete_steps(task_id)
        return incomplete[0] if incomplete else None

    async def list_plans(self, limit: int = 10) -> List[Dict]:
        """
        列出所有计划（按更新时间倒序）（异步版本）

        Args:
            limit: 返回数量限制

        Returns:
            计划摘要列表
        """
        plans = []

        # 从文件读取
        if self.plans_dir and self.plans_dir.exists():
            # 使用 asyncio.to_thread 包装同步的 glob 操作
            file_paths = await asyncio.to_thread(list, self.plans_dir.glob("*.json"))
            for file_path in file_paths:
                try:
                    async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                        content = await f.read()
                        plan_data = json.loads(content)
                        plans.append(
                            {
                                "task_id": plan_data.get("task_id"),
                                "goal": plan_data.get("goal"),
                                "completion_rate": plan_data.get("completion_rate"),
                                "updated_at": plan_data.get("updated_at"),
                            }
                        )
                except Exception as e:
                    logger.warning(f"[PlanMemory] 读取计划失败: {file_path}, error={e}")

        # 按更新时间排序
        plans.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return plans[:limit]

    # ==================== 清理方法 ====================

    async def clear(self) -> None:
        """清空所有计划（异步版本）"""
        self._plans_cache.clear()

        if self.plans_dir and self.plans_dir.exists():
            # 使用 asyncio.to_thread 包装同步的 glob 操作
            file_paths = await asyncio.to_thread(list, self.plans_dir.glob("*.json"))
            for file_path in file_paths:
                try:
                    await asyncio.to_thread(file_path.unlink)
                except Exception as e:
                    logger.warning(f"[PlanMemory] 删除文件失败: {file_path}, error={e}")

        logger.info("[PlanMemory] 清空所有计划")

    async def delete_plan(self, task_id: str) -> bool:
        """
        删除指定计划（异步版本）

        Args:
            task_id: 任务 ID

        Returns:
            是否删除成功
        """
        # 从缓存删除
        self._plans_cache.pop(task_id, None)

        # 从文件删除
        if self.plans_dir:
            file_path = self.plans_dir / f"{task_id}.json"
            if file_path.exists():
                try:
                    await asyncio.to_thread(file_path.unlink)
                    logger.info(f"[PlanMemory] 删除计划: task_id={task_id}")
                    return True
                except Exception as e:
                    logger.error(f"[PlanMemory] 删除失败: {e}")
                    return False

        return False

    # ==================== 私有方法 ====================

    def _normalize_steps(self, steps: List[Dict]) -> List[Dict]:
        """
        规范化步骤格式

        将 plan_todo 的步骤格式转换为持久化格式
        """
        normalized = []
        for i, step in enumerate(steps):
            normalized.append(
                {
                    "index": i,
                    "action": step.get("action", ""),
                    "capability": step.get("capability", ""),
                    "purpose": step.get("purpose", ""),
                    "skill_hint": step.get("skill_hint", ""),
                    "passes": False,
                    "verified_at": None,
                    "result": step.get("result"),
                }
            )
        return normalized

    def _calculate_completion_rate(self, steps: List[Dict]) -> str:
        """计算完成率字符串"""
        if not steps:
            return "0/0"
        completed = sum(1 for s in steps if s.get("passes"))
        return f"{completed}/{len(steps)}"

    async def _save_to_file(self, task_id: str, plan_data: Dict) -> None:
        """异步保存到文件"""
        if not self.plans_dir:
            return

        file_path = self.plans_dir / f"{task_id}.json"
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(plan_data, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.error(f"[PlanMemory] 保存文件失败: {e}")

    async def _load_from_file(self, task_id: str) -> Optional[Dict]:
        """异步从文件加载"""
        if not self.plans_dir:
            return None

        file_path = self.plans_dir / f"{task_id}.json"
        if not file_path.exists():
            return None

        try:
            async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                content = await f.read()
                return json.loads(content)
        except Exception as e:
            logger.error(f"[PlanMemory] 加载文件失败: {e}")
            return None

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        base = super().to_dict()
        base.update(
            {
                "user_id": self.user_id,
                "plans_count": len(self._plans_cache),
                "storage_dir": str(self.plans_dir) if self.plans_dir else None,
            }
        )
        return base


# ==================== 工厂函数 ====================


def create_plan_memory(
    user_id: Optional[str] = None, storage_dir: Optional[str] = None
) -> PlanMemory:
    """
    创建 PlanMemory 实例

    Args:
        user_id: 用户 ID（用于隔离数据）
        storage_dir: 存储目录（自动生成 plans/ 子目录）

    Returns:
        PlanMemory 实例
    """
    return PlanMemory(user_id=user_id, storage_dir=storage_dir)

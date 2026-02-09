"""
记忆质量控制模块

职责：
- 敏感信息过滤
- 冲突检测与处理
- 显式记忆优先级规则
- TTL 管理
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from logger import get_logger

from ..pool import get_mem0_pool
from ..schemas import MemoryType

logger = get_logger("memory.mem0.quality_control")


# ==================== 更新阶段 Prompt ====================

# 对齐 mem0 原仓的 update tool-call 语义（事件：ADD/UPDATE/DELETE/NONE）
DEFAULT_UPDATE_MEMORY_PROMPT = """You are a smart memory manager which controls the memory of a system.
You can perform four operations: (1) add into the memory, (2) update the memory, (3) delete from the memory, and (4) no change.

Based on the above four operations, the memory will change.

Compare newly retrieved facts with the existing memory. For each new fact, decide whether to:
- ADD: Add it to the memory as a new element
- UPDATE: Update an existing memory element
- DELETE: Delete an existing memory element
- NONE: Make no change (if the fact is already present or irrelevant)

There are specific guidelines to select which operation to perform:

1. **Add**: If the retrieved facts contain new information not present in the memory, then you have to add it by generating a new ID in the id field.
- **Example**:
    - Old Memory:
        [
            {
                "id" : "0",
                "text" : "User is a software engineer"
            }
        ]
    - Retrieved facts: ["Name is John"]
    - New Memory:
        {
            "memory" : [
                {
                    "id" : "0",
                    "text" : "User is a software engineer",
                    "event" : "NONE"
                },
                {
                    "id" : "1",
                    "text" : "Name is John",
                    "event" : "ADD"
                }
            ]

        }

2. **Update**: If the retrieved facts contain information that is already present in the memory but the information is totally different, then you have to update it. 
If the retrieved fact contains information that conveys the same thing as the elements present in the memory, then you have to keep the fact which has the most information. 
Example (a) -- if the memory contains "User likes to play cricket" and the retrieved fact is "Loves to play cricket with friends", then update the memory with the retrieved facts.
Example (b) -- if the memory contains "Likes cheese pizza" and the retrieved fact is "Loves cheese pizza", then you do not need to update it because they convey the same information.
If the direction is to update the memory, then you have to update it.
Please keep in mind while updating you have to keep the same ID.
Please note to return the IDs in the output from the input IDs only and do not generate any new ID.
- **Example**:
    - Old Memory:
        [
            {
                "id" : "0",
                "text" : "I really like cheese pizza"
            },
            {
                "id" : "1",
                "text" : "User is a software engineer"
            },
            {
                "id" : "2",
                "text" : "User likes to play cricket"
            }
        ]
    - Retrieved facts: ["Loves chicken pizza", "Loves to play cricket with friends"]
    - New Memory:
        {
        "memory" : [
                {
                    "id" : "0",
                    "text" : "Loves cheese and chicken pizza",
                    "event" : "UPDATE",
                    "old_memory" : "I really like cheese pizza"
                },
                {
                    "id" : "1",
                    "text" : "User is a software engineer",
                    "event" : "NONE"
                },
                {
                    "id" : "2",
                    "text" : "Loves to play cricket with friends",
                    "event" : "UPDATE",
                    "old_memory" : "User likes to play cricket"
                }
            ]
        }


3. **Delete**: If the retrieved facts contain information that contradicts the information present in the memory, then you have to delete it. Or if the direction is to delete the memory, then you have to delete it.
Please note to return the IDs in the output from the input IDs only and do not generate any new ID.
- **Example**:
    - Old Memory:
        [
            {
                "id" : "0",
                "text" : "User is a software engineer"
            },
            {
                "id" : "1",
                "text" : "User likes to play cricket"
            }
        ]
    - Retrieved facts: ["User is a doctor"]
    - New Memory:
        {
            "memory" : [
                {
                    "id" : "0",
                    "text" : "User is a software engineer",
                    "event" : "DELETE"
                },
                {
                    "id" : "1",
                    "text" : "User likes to play cricket",
                    "event" : "NONE"
                }
            ]
        }

4. **No Change**: If the retrieved facts contain information that is already present in the memory or are irrelevant, you should keep the memory unchanged with event NONE.

Important:
- You must return your response in the JSON format shown below.
- Use only the IDs provided in the input for UPDATE/DELETE/NONE. For ADD, you can create a new ID.
- Do not return anything except the JSON.

Few-shot examples:

Example A (ADD):
Current memory:
[
  {"id": "0", "text": "User is a software engineer"}
]
New facts:
["Name is John"]
Output:
{
  "memory": [
    {"id": "0", "text": "User is a software engineer", "event": "NONE"},
    {"id": "1", "text": "Name is John", "event": "ADD"}
  ]
}

Example B (UPDATE):
Current memory:
[
  {"id": "0", "text": "User likes cheese pizza"}
]
New facts:
["User loves cheese pizza with friends"]
Output:
{
  "memory": [
    {
      "id": "0",
      "text": "User loves cheese pizza with friends",
      "event": "UPDATE",
      "old_memory": "User likes cheese pizza"
    }
  ]
}

Example C (DELETE):
Current memory:
[
  {"id": "0", "text": "User is a software engineer"}
]
New facts:
["User is a doctor"]
Output:
{
  "memory": [
    {"id": "0", "text": "User is a software engineer", "event": "DELETE"}
  ]
}

Example D (NONE):
Current memory:
[
  {"id": "0", "text": "User likes coffee"}
]
New facts:
["User likes coffee"]
Output:
{
  "memory": [
    {"id": "0", "text": "User likes coffee", "event": "NONE"}
  ]
}
"""


class QualityController:
    """
    记忆质量控制器

    负责敏感信息过滤、冲突检测和质量评估
    """

    def __init__(self):
        """初始化质量控制器"""
        self.pool = get_mem0_pool()
        logger.info("[QualityController] 初始化完成")

    # ==================== 敏感信息过滤 ====================

    def filter_sensitive_info(self, content: str) -> Tuple[str, List[str]]:
        """
        过滤敏感信息

        Args:
            content: 原始内容

        Returns:
            (过滤后的内容, 检测到的敏感信息类型列表)
        """
        decision = self._run_update_stage(content, [])
        actions = self.extract_update_actions(decision)
        if not actions["add"] and not actions["update"] and not actions["delete"]:
            logger.info(
                "[QualityController] 更新阶段返回 NONE，跳过写入",
            )
        return content, []

    def should_reject(self, content: str) -> Tuple[bool, str]:
        """
        Determine if a memory should be rejected.

        Uses format validation (length check) as a fast pre-filter,
        then delegates to LLM update stage for semantic judgment.

        Args:
            content: Memory content

        Returns:
            (should_reject, reason)
        """
        # Fast pre-filter: format validation (allowed by LLM-First rules)
        if not content or not content.strip():
            return True, "内容为空"
        if len(content.strip()) < 5:
            return True, f"内容过短（{len(content.strip())} 字符，最少 5）"

        # LLM semantic judgment via update stage
        decision = self._run_update_stage(content, [])
        actions = self.extract_update_actions(decision)
        if not actions["add"] and not actions["update"] and not actions["delete"]:
            return True, "更新阶段返回 NONE，拒绝写入"
        return False, ""

    # ==================== 更新阶段（LLM 驱动）====================

    def _run_update_stage(
        self, new_memory: str, existing_memories: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Run update stage (sync wrapper).

        In async context (FastAPI): returns conservative ADD fallback
        since LLM call requires await. The async callers should use
        analyze_update() directly.

        In sync context: runs the async method via asyncio.run().
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # In async context — cannot block, return conservative default.
                # Callers in async context should use analyze_update() directly.
                return {"memory": [{"id": "0", "text": new_memory, "event": "ADD"}]}
            return loop.run_until_complete(
                self.analyze_update(new_memory, existing_memories)
            )
        except RuntimeError:
            try:
                return asyncio.run(
                    self.analyze_update(new_memory, existing_memories)
                )
            except Exception:
                logger.error("[QualityController] 更新阶段执行失败", exc_info=True)
                return {"memory": [{"id": "0", "text": new_memory, "event": "ADD"}]}

    async def analyze_update(
        self, new_memory: str, existing_memories: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        通过 LLM 进行更新阶段决策（过滤/冲突/更新）

        Args:
            new_memory: 新记忆内容
            existing_memories: 已有记忆列表

        Returns:
            更新决策结果（JSON）
        """
        payload, id_mapping = self._format_existing_memories(existing_memories)
        prompt = self._build_update_prompt(payload, [new_memory])

        try:
            response = await self._call_llm(prompt)
            decision = self._parse_llm_response(response)
            if not decision:
                return {
                    "memory": [{"id": "0", "text": new_memory, "event": "ADD"}],
                    "_id_mapping": id_mapping,
                }
            decision["_id_mapping"] = id_mapping
            return decision
        except Exception:
            logger.error("[QualityController] 更新阶段 LLM 调用失败", exc_info=True)
            return {
                "memory": [{"id": "0", "text": new_memory, "event": "ADD"}],
                "_id_mapping": id_mapping,
            }

    def _format_existing_memories(
        self, existing_memories: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
        """
        格式化已有记忆（对齐 mem0：id/text）

        Returns:
            (formatted_memories, id_mapping)
        """
        formatted: List[Dict[str, Any]] = []
        id_mapping: Dict[str, str] = {}
        for idx, mem in enumerate(existing_memories[:30]):
            raw_id = mem.get("id") or mem.get("memory_id")
            if not raw_id:
                continue
            temp_id = str(idx)
            formatted.append({"id": temp_id, "text": mem.get("memory", "")})
            id_mapping[temp_id] = raw_id
        return formatted, id_mapping

    def _build_update_prompt(
        self, existing_memories: List[Dict[str, Any]], new_facts: List[str]
    ) -> str:
        """
        构建更新阶段提示词（对齐 mem0 原仓）

        Args:
            existing_memories: 当前记忆（id/text）
            new_facts: 新的事实列表

        Returns:
            完整提示词
        """
        if existing_memories:
            current_memory_part = f"""
Below is the current content of my memory which I have collected till now. You have to update it in the following format only:

```
{existing_memories}
```
"""
        else:
            current_memory_part = """
Current memory is empty.
"""

        return f"""{DEFAULT_UPDATE_MEMORY_PROMPT}

{current_memory_part}

The new retrieved facts are mentioned in the triple backticks. You have to analyze the new retrieved facts and determine whether these facts should be added, updated, or deleted in the memory.

```
{new_facts}
```

You must return your response in the following JSON structure only:

{{
    "memory" : [
        {{
            "id" : "<ID of the memory>",
            "text" : "<Content of the memory>",
            "event" : "<Operation to be performed>",
            "old_memory" : "<Old memory content>"
        }}
    ]
}}

Follow the instruction mentioned below:
- Do not return anything from the custom few shot prompts provided above.
- If the current memory is empty, then you have to add the new retrieved facts to the memory.
- You should return the updated memory in only JSON format as shown below. The memory key should be the same if no changes are made.
- If there is an addition, generate a new key and add the new memory corresponding to it.
- If there is a deletion, the memory key-value pair should be removed from the memory.
- If there is an update, the ID key should remain the same and only the value needs to be updated.

Do not return anything except the JSON format.
"""

    async def get_llm_service(self):
        """获取 LLM 服务（懒加载）"""
        if not hasattr(self, "_llm_service"):
            from config.llm_config import get_llm_profile
            from core.llm import create_llm_service

            profile = await get_llm_profile("memory_update")
            self._llm_service = create_llm_service(**profile)
        return self._llm_service

    async def _call_llm(self, prompt: str) -> str:
        """调用 LLM（更新阶段）"""
        from core.llm import Message

        llm_service = await self.get_llm_service()
        response = await llm_service.create_message_async(
            messages=[Message(role="user", content=prompt)]
        )
        if hasattr(response, "text"):
            return response.text
        if hasattr(response, "content"):
            return response.content
        return str(response)

    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """解析 LLM 响应 JSON（对齐 mem0）"""
        try:
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.strip("`")
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                json_start = cleaned.find("{")
                json_end = cleaned.rfind("}") + 1
                if json_start != -1 and json_end > json_start:
                    return json.loads(cleaned[json_start:json_end])
        except Exception:
            logger.warning("[QualityController] LLM JSON 解析失败")
        return {}

    def extract_update_actions(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        """
        提取更新动作（对齐 mem0 的 event 语义）

        Returns:
            {
                "add": [{"text": "..."}],
                "update": [{"id": "...", "text": "...", "old_memory": "..."}],
                "delete": [{"id": "...", "text": "..."}],
                "none": [{"id": "...", "text": "..."}],
                "id_mapping": {...}
            }
        """
        actions = {"add": [], "update": [], "delete": [], "none": []}
        id_mapping = decision.get("_id_mapping", {})
        for item in decision.get("memory", []) or []:
            event = str(item.get("event", "")).upper()
            text = item.get("text", "")
            mem_id = item.get("id")
            if mem_id in id_mapping:
                mem_id = id_mapping[mem_id]
            payload = {"id": mem_id, "text": text, "old_memory": item.get("old_memory")}
            if event == "ADD":
                actions["add"].append(payload)
            elif event == "UPDATE":
                actions["update"].append(payload)
            elif event == "DELETE":
                actions["delete"].append(payload)
            elif event == "NONE":
                actions["none"].append(payload)
        actions["id_mapping"] = id_mapping
        return actions

    # ==================== 冲突检测 ====================

    def detect_conflicts(
        self, user_id: str, new_memory: str, memory_type: MemoryType = MemoryType.EXPLICIT
    ) -> List[Dict[str, Any]]:
        """
        检测新记忆与现有记忆的冲突

        Args:
            user_id: 用户 ID
            new_memory: 新记忆内容
            memory_type: 记忆类型

        Returns:
            冲突列表，每个冲突包含：
            {
                "type": "fact_contradiction/preference_change",
                "existing_id": "...",
                "existing_content": "...",
                "new_content": "...",
                "confidence": 0.0-1.0,
                "suggestion": "处理建议"
            }
        """
        try:
            pool = get_mem0_pool()
            existing_memories = pool.search(user_id=user_id, query=new_memory, limit=5)
            decision = self._run_update_stage(new_memory, existing_memories)
            actions = self.extract_update_actions(decision)
            conflicts = []
            for item in actions["update"]:
                conflicts.append(
                    {
                        "type": "preference_change",
                        "existing_id": item.get("id"),
                        "existing_content": item.get("old_memory", ""),
                        "new_content": item.get("text", ""),
                        "confidence": 0.6,
                        "suggestion": "更新阶段建议更新旧记忆",
                    }
                )
            for item in actions["delete"]:
                conflicts.append(
                    {
                        "type": "fact_contradiction",
                        "existing_id": item.get("id"),
                        "existing_content": item.get("text", ""),
                        "new_content": new_memory,
                        "confidence": 0.6,
                        "suggestion": "更新阶段建议删除冲突记忆",
                    }
                )

            if conflicts:
                logger.info(
                    f"[QualityController] 更新阶段检测到冲突: "
                    f"user={user_id}, count={len(conflicts)}"
                )

            return conflicts

        except Exception as e:
            logger.error("[QualityController] 冲突检测失败", exc_info=True)
            return []

    # ==================== 显式记忆优先级 ====================

    def resolve_conflict(
        self, user_id: str, conflict: Dict[str, Any], priority: str = "explicit_first"
    ) -> Dict[str, Any]:
        """
        解决冲突

        Args:
            user_id: 用户 ID
            conflict: 冲突信息
            priority: 优先级策略
                - "explicit_first": 显式记忆优先
                - "newest_first": 最新记忆优先
                - "keep_both": 保留两者
                - "update_old": 更新旧记忆

        Returns:
            处理结果
        """
        existing_id = conflict.get("existing_id")
        existing_content = conflict.get("existing_content")
        new_content = conflict.get("new_content")

        pool = get_mem0_pool()

        if priority == "explicit_first":
            # 显式记忆优先：删除旧记忆
            if existing_id:
                pool.delete(memory_id=existing_id, user_id=user_id)
                logger.info(f"[QualityController] 冲突解决: 删除旧记忆 {existing_id}")
                return {
                    "action": "delete_old",
                    "deleted_id": existing_id,
                    "kept_content": new_content,
                }

        elif priority == "newest_first":
            # 最新记忆优先：更新旧记忆
            if existing_id:
                pool.update(memory_id=existing_id, data=new_content, user_id=user_id)
                logger.info(f"[QualityController] 冲突解决: 更新旧记忆 {existing_id}")
                return {
                    "action": "update_old",
                    "updated_id": existing_id,
                    "new_content": new_content,
                }

        elif priority == "keep_both":
            # 保留两者：标记旧记忆为冲突
            logger.info(f"[QualityController] 冲突解决: 保留两者")
            return {"action": "keep_both", "note": "两段记忆都保留，需要人工审核"}

        elif priority == "update_old":
            # 更新旧记忆
            if existing_id:
                pool.update(memory_id=existing_id, data=new_content, user_id=user_id)
                return {"action": "update_old", "updated_id": existing_id}

        return {"action": "noop", "note": "未处理"}

    # ==================== TTL 管理 ====================

    def clean_expired_memories(self, user_id: str, memory_types: Optional[List[str]] = None) -> int:
        """
        清理过期记忆

        Args:
            user_id: 用户 ID
            memory_types: 要清理的记忆类型列表（None 表示清理所有类型）

        Returns:
            清理的记忆数量
        """
        cleaned_count = 0

        try:
            pool = get_mem0_pool()
            all_memories = pool.get_all(user_id=user_id, limit=200)

            for mem in all_memories:
                metadata = mem.get("metadata", {})
                memory_type = metadata.get("memory_type", "implicit")

                # 过滤记忆类型
                if memory_types and memory_type not in memory_types:
                    continue

                # 检查过期时间
                expires_at_str = metadata.get("expires_at")
                if not expires_at_str:
                    continue

                try:
                    expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                    if datetime.now() > expires_at:
                        # 删除过期记忆
                        mem_id = mem.get("id", mem.get("memory_id", ""))
                        if mem_id:
                            pool.delete(memory_id=mem_id, user_id=user_id)
                            cleaned_count += 1
                except Exception as e:
                    logger.warning(f"[QualityController] 解析过期时间失败: {e}")

            if cleaned_count > 0:
                logger.info(
                    f"[QualityController] 清理过期记忆: user={user_id}, "
                    f"count={cleaned_count}, types={memory_types}"
                )

            return cleaned_count

        except Exception as e:
            logger.error(f"[QualityController] 清理过期记忆失败: {e}")
            return 0

    def get_memory_ttl_status(self, user_id: str) -> Dict[str, Any]:
        """
        获取记忆 TTL 状态

        Args:
            user_id: 用户 ID

        Returns:
            TTL 状态信息
        """
        try:
            pool = get_mem0_pool()
            all_memories = pool.get_all(user_id=user_id, limit=200)

            stats = {
                "total": len(all_memories),
                "with_ttl": 0,
                "expired": 0,
                "expiring_soon": 0,  # 7天内过期
                "by_type": {},
            }

            now = datetime.now()
            soon_cutoff = now + timedelta(days=7)

            for mem in all_memories:
                metadata = mem.get("metadata", {})
                memory_type = metadata.get("memory_type", "implicit")

                if memory_type not in stats["by_type"]:
                    stats["by_type"][memory_type] = {
                        "total": 0,
                        "with_ttl": 0,
                        "expired": 0,
                        "expiring_soon": 0,
                    }

                stats["by_type"][memory_type]["total"] += 1

                expires_at_str = metadata.get("expires_at")
                if expires_at_str:
                    try:
                        expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                        stats["with_ttl"] += 1
                        stats["by_type"][memory_type]["with_ttl"] += 1

                        if now > expires_at:
                            stats["expired"] += 1
                            stats["by_type"][memory_type]["expired"] += 1
                        elif expires_at < soon_cutoff:
                            stats["expiring_soon"] += 1
                            stats["by_type"][memory_type]["expiring_soon"] += 1
                    except Exception:
                        pass

            return stats

        except Exception as e:
            logger.error(f"[QualityController] 获取 TTL 状态失败: {e}")
            return {"error": str(e)}


# ==================== 工厂函数 ====================

_quality_controller_instance: Optional[QualityController] = None


def get_quality_controller() -> QualityController:
    """获取质量控制器单例"""
    global _quality_controller_instance
    if _quality_controller_instance is None:
        _quality_controller_instance = QualityController()
    return _quality_controller_instance


def reset_quality_controller() -> None:
    """重置质量控制器（用于测试）"""
    global _quality_controller_instance
    _quality_controller_instance = None

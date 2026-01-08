"""
Mem0 格式化模块

职责：
- 将 Mem0 搜索结果格式化为 System Prompt 片段
- 提供多种格式化模板
- 支持自定义格式化逻辑

设计原则：
- 格式化与存储分离
- 可读性优先
- 支持国际化
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from logger import get_logger

logger = get_logger("memory.mem0.formatter")


# ==================== 格式化模板 ====================

USER_PROFILE_HEADER_ZH = """# 用户画像（基于历史交互）

以下是与当前问题相关的用户信息，请据此提供个性化回答：
"""

USER_PROFILE_HEADER_EN = """# User Profile (Based on Historical Interactions)

The following user information is relevant to the current query. Please provide personalized responses accordingly:
"""

MEMORY_ITEM_TEMPLATE_ZH = "- {memory}"
MEMORY_ITEM_TEMPLATE_EN = "- {memory}"

NO_RELEVANT_MEMORIES_ZH = "(暂无相关用户记忆)"
NO_RELEVANT_MEMORIES_EN = "(No relevant user memories available)"


# ==================== 核心格式化函数 ====================

def format_memories_for_prompt(
    memories: List[Dict[str, Any]],
    language: str = "zh",
    max_memories: int = 10,
    include_metadata: bool = False,
    min_score: float = 0.0
) -> Optional[str]:
    """
    将 Mem0 搜索结果格式化为 System Prompt 片段
    
    Args:
        memories: Mem0 搜索返回的记忆列表
            每个记忆包含：
            - id: 记忆 ID
            - memory: 记忆内容（核心字段）
            - score: 相关性分数
            - user_id: 用户 ID
            - created_at: 创建时间
            - metadata: 元数据
        language: 语言（"zh" 或 "en"）
        max_memories: 最大返回记忆数
        include_metadata: 是否包含元数据（时间、来源等）
        min_score: 最低相关性分数阈值
        
    Returns:
        格式化后的字符串，或 None（如果没有有效记忆）
        
    示例输出：
        # 用户画像（基于历史交互）
        
        以下是与当前问题相关的用户信息，请据此提供个性化回答：
        
        - 用户偏好使用 Python 进行开发
        - 用户是前端工程师，熟悉 React
        - 用户喜欢简洁的代码风格
    """
    if not memories:
        return None
    
    # 筛选有效记忆
    valid_memories = [
        m for m in memories
        if m.get("memory") and (m.get("score", 1.0) >= min_score)
    ]
    
    if not valid_memories:
        return None
    
    # 限制数量
    valid_memories = valid_memories[:max_memories]
    
    # 选择模板
    if language == "zh":
        header = USER_PROFILE_HEADER_ZH
        item_template = MEMORY_ITEM_TEMPLATE_ZH
    else:
        header = USER_PROFILE_HEADER_EN
        item_template = MEMORY_ITEM_TEMPLATE_EN
    
    # 构建输出
    lines = [header]
    
    for mem in valid_memories:
        memory_text = mem.get("memory", "")
        
        if include_metadata:
            # 包含元数据
            score = mem.get("score", 0)
            created_at = mem.get("created_at", "")
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    created_str = dt.strftime("%Y-%m-%d")
                except:
                    created_str = created_at[:10] if len(created_at) >= 10 else ""
                line = f"- {memory_text} (相关度: {score:.2f}, 来源: {created_str})"
            else:
                line = f"- {memory_text} (相关度: {score:.2f})"
        else:
            line = item_template.format(memory=memory_text)
        
        lines.append(line)
    
    result = "\n".join(lines)
    
    logger.debug(
        f"[Mem0Formatter] 格式化完成: "
        f"输入={len(memories)}, 有效={len(valid_memories)}, 语言={language}"
    )
    
    return result


def format_memories_as_context(
    memories: List[Dict[str, Any]],
    max_memories: int = 5
) -> str:
    """
    将记忆格式化为简洁的上下文字符串（用于非 Prompt 场景）
    
    Args:
        memories: 记忆列表
        max_memories: 最大数量
        
    Returns:
        简洁的上下文字符串
    """
    if not memories:
        return ""
    
    valid_memories = [m for m in memories if m.get("memory")][:max_memories]
    
    if not valid_memories:
        return ""
    
    return " | ".join([m["memory"] for m in valid_memories])


def format_single_memory(
    memory: Dict[str, Any],
    include_score: bool = True
) -> str:
    """
    格式化单条记忆
    
    Args:
        memory: 单条记忆
        include_score: 是否包含分数
        
    Returns:
        格式化的字符串
    """
    text = memory.get("memory", "")
    if not text:
        return ""
    
    if include_score:
        score = memory.get("score", 0)
        return f"{text} (score: {score:.2f})"
    
    return text


# ==================== 高级格式化函数 ====================

def format_memories_by_category(
    memories: List[Dict[str, Any]],
    categories: Optional[Dict[str, List[str]]] = None
) -> str:
    """
    按类别格式化记忆
    
    Args:
        memories: 记忆列表
        categories: 类别定义，如 {"偏好": ["喜欢", "偏好"], "技能": ["会", "熟悉"]}
        
    Returns:
        分类格式化的字符串
    """
    if not memories:
        return ""
    
    # 默认类别
    if categories is None:
        categories = {
            "用户偏好": ["喜欢", "偏好", "prefer", "like"],
            "技术技能": ["会", "熟悉", "擅长", "know", "familiar", "expert"],
            "工作相关": ["工作", "职业", "role", "job", "work"],
            "其他": []  # 兜底类别
        }
    
    # 分类记忆
    categorized: Dict[str, List[str]] = {cat: [] for cat in categories}
    
    for mem in memories:
        text = mem.get("memory", "")
        if not text:
            continue
        
        placed = False
        for cat, keywords in categories.items():
            if cat == "其他":
                continue
            if any(kw.lower() in text.lower() for kw in keywords):
                categorized[cat].append(text)
                placed = True
                break
        
        if not placed:
            categorized["其他"].append(text)
    
    # 构建输出
    lines = ["# 用户画像\n"]
    
    for cat, items in categorized.items():
        if items:
            lines.append(f"## {cat}")
            for item in items[:5]:  # 每类最多5条
                lines.append(f"- {item}")
            lines.append("")
    
    return "\n".join(lines)


def create_user_profile_section(
    memories: List[Dict[str, Any]],
    user_query: str = "",
    style: str = "concise"
) -> Optional[str]:
    """
    创建用户画像 Section（用于 System Prompt 注入）
    
    Args:
        memories: 相关记忆列表
        user_query: 用户当前问题（可选，用于上下文）
        style: 风格 ("concise" 简洁, "detailed" 详细, "structured" 结构化)
        
    Returns:
        格式化的用户画像 Section
    """
    if not memories:
        return None
    
    if style == "concise":
        return format_memories_for_prompt(
            memories,
            language="zh",
            max_memories=5,
            include_metadata=False
        )
    
    elif style == "detailed":
        return format_memories_for_prompt(
            memories,
            language="zh",
            max_memories=10,
            include_metadata=True
        )
    
    elif style == "structured":
        return format_memories_by_category(memories)
    
    else:
        return format_memories_for_prompt(memories)


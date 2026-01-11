"""
Dazee E2E 测试数据

合成销售人员"小李"的一周工作对话数据
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any
from dataclasses import dataclass


@dataclass
class ConversationItem:
    """对话项"""
    day: int                    # 第几天 (1-5)
    time: str                   # 时间 HH:MM
    scenario: str               # 场景描述
    message: str                # 用户消息
    expected_task: str          # 预期任务类型
    expected_emotion: str       # 预期情绪
    expected_relations: List[str]  # 预期提到的人
    expected_todo: str = None   # 预期待办（如有）
    notes: str = ""            # 备注


# ==================== 合成对话数据 ====================

def get_base_date() -> datetime:
    """获取基准日期（本周一）"""
    today = datetime.now()
    # 回溯到本周一
    monday = today - timedelta(days=today.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


def get_test_conversations() -> List[ConversationItem]:
    """
    获取测试对话数据
    
    模拟销售人员"小李"的一周工作（周一到周五）
    """
    return [
        # ==================== Day 1: 周一 ====================
        ConversationItem(
            day=1,
            time="09:30",
            scenario="晨会后，接到老板任务",
            message="老板说这周要把永辉的合同签了，有点紧",
            expected_task="合同签署",
            expected_emotion="stressed",
            expected_relations=["老板"],
            expected_todo="签永辉合同",
            notes="包含任务、压力、上级、截止时间"
        ),
        ConversationItem(
            day=1,
            time="14:00",
            scenario="客户拜访后反馈",
            message="刚和永辉采购老张聊完，他们要再对比下价格",
            expected_task="客户拜访",
            expected_emotion="neutral",
            expected_relations=["老张", "永辉"],
            expected_todo=None,
            notes="包含客户、阻碍、关系"
        ),
        
        # ==================== Day 2: 周二 ====================
        ConversationItem(
            day=2,
            time="10:00",
            scenario="准备报价单",
            message="得赶紧把报价单改一下，老张要的急",
            expected_task="报价",
            expected_emotion="stressed",
            expected_relations=["老张"],
            expected_todo="修改报价单",
            notes="包含待办、紧急"
        ),
        ConversationItem(
            day=2,
            time="16:00",
            scenario="客户放鸽子",
            message="又被客户放鸽子了，烦死了",
            expected_task="客户跟进",
            expected_emotion="frustrated",
            expected_relations=[],
            expected_todo=None,
            notes="包含情绪、挫折"
        ),
        
        # ==================== Day 3: 周三 ====================
        ConversationItem(
            day=3,
            time="09:00",
            scenario="周三例行周报",
            message="每周三都要写周报，又是这个时候",
            expected_task="周报",
            expected_emotion="neutral",
            expected_relations=[],
            expected_todo="写周报",
            notes="包含习惯、时间模式"
        ),
        ConversationItem(
            day=3,
            time="15:00",
            scenario="永辉合同有进展",
            message="永辉那边有眉目了！老张说下周可以签",
            expected_task="合同跟进",
            expected_emotion="positive",
            expected_relations=["老张", "永辉"],
            expected_todo=None,
            notes="包含积极情绪、进展"
        ),
        
        # ==================== Day 4: 周四 ====================
        ConversationItem(
            day=4,
            time="11:00",
            scenario="拜访新客户",
            message="今天要去拜访美团的采购，第一次见面",
            expected_task="客户拜访",
            expected_emotion="neutral",
            expected_relations=["美团"],
            expected_todo="拜访美团采购",
            notes="包含新任务、客户"
        ),
        ConversationItem(
            day=4,
            time="17:00",
            scenario="老板询问业绩",
            message="老板问业绩进度，压力山大",
            expected_task="业绩汇报",
            expected_emotion="stressed",
            expected_relations=["老板"],
            expected_todo=None,
            notes="包含压力、上级、KPI"
        ),
        
        # ==================== Day 5: 周五 ====================
        ConversationItem(
            day=5,
            time="10:00",
            scenario="准备合同材料",
            message="下周要准备合同模板，还要跟法务确认条款",
            expected_task="合同准备",
            expected_emotion="neutral",
            expected_relations=["法务"],
            expected_todo="准备合同模板",
            notes="包含待办、协作"
        ),
        ConversationItem(
            day=5,
            time="16:00",
            scenario="周五下班前",
            message="总算熬到周五了，这周太累了",
            expected_task="general",
            expected_emotion="fatigue",
            expected_relations=[],
            expected_todo=None,
            notes="包含疲惫、情绪"
        ),
    ]


def format_conversations_for_test() -> List[Dict[str, Any]]:
    """
    格式化对话数据为测试格式
    
    Returns:
        包含 timestamp 和 content 的字典列表
    """
    base_date = get_base_date()
    conversations = get_test_conversations()
    
    formatted = []
    for conv in conversations:
        # 计算具体时间戳
        day_offset = conv.day - 1
        hour, minute = map(int, conv.time.split(":"))
        timestamp = base_date + timedelta(days=day_offset, hours=hour, minutes=minute)
        
        formatted.append({
            "timestamp": timestamp,
            "content": conv.message,
            "scenario": conv.scenario,
            # 预期结果（用于验证）
            "expected": {
                "task": conv.expected_task,
                "emotion": conv.expected_emotion,
                "relations": conv.expected_relations,
                "todo": conv.expected_todo
            },
            "notes": conv.notes
        })
    
    return formatted


def get_conversations_by_day(day: int) -> List[Dict[str, Any]]:
    """
    获取指定天的对话
    
    Args:
        day: 第几天 (1-5)
        
    Returns:
        该天的对话列表
    """
    all_convs = format_conversations_for_test()
    base_date = get_base_date()
    target_date = base_date + timedelta(days=day - 1)
    
    return [
        conv for conv in all_convs
        if conv["timestamp"].date() == target_date.date()
    ]


def get_weekly_conversations() -> List[Dict[str, Any]]:
    """获取整周的对话数据"""
    return format_conversations_for_test()


# ==================== 预期验证结果 ====================

def get_expected_behavior_pattern() -> Dict[str, Any]:
    """
    获取预期的行为模式分析结果
    
    用于验证 BehaviorAnalyzer 输出
    """
    return {
        "inferred_role": "sales",
        "role_confidence_min": 0.6,  # 至少 60% 置信度
        "what": {
            "min_routine_tasks": 3,
            "expected_tasks": ["客户拜访", "报价", "合同跟进", "周报"],
        },
        "when": {
            "min_patterns": 1,
            "expected_patterns": ["周三写周报"],
        },
        "who": {
            "min_collaborators": 2,
            "expected_people": ["老板", "老张", "法务"],
        },
        "why": {
            "min_motivations": 1,
            "expected_keywords": ["业绩", "签单", "合同"],
        },
        "how": {
            "expected_work_style": "deadline_driven",
        }
    }


def get_expected_plans() -> List[Dict[str, Any]]:
    """
    获取预期的计划识别结果
    
    用于验证 PDCAManager 输出
    """
    return [
        {
            "title_keywords": ["永辉", "合同", "签"],
            "priority": ["high", "urgent"],
            "deadline_within_days": 7,
            "has_blockers": True,
            "blocker_keywords": ["价格", "对比"],
        }
    ]


def get_expected_reminders() -> List[Dict[str, Any]]:
    """
    获取预期的提醒创建结果
    
    用于验证 Reminder 输出
    """
    return [
        {
            "type": "deadline",
            "related_to": "永辉合同",
            "advance_hours_min": 12,
            "advance_hours_max": 48,
        }
    ]


# ==================== 测试元数据 ====================

TEST_USER_ID = "test_sales_user_001"
TEST_USER_NAME = "小李"
TEST_SESSION_ID_PREFIX = "test_session_"


def get_test_metadata() -> Dict[str, Any]:
    """获取测试元数据"""
    return {
        "user_id": TEST_USER_ID,
        "user_name": TEST_USER_NAME,
        "role": "sales",
        "test_period": {
            "start": get_base_date(),
            "end": get_base_date() + timedelta(days=4, hours=23, minutes=59),
            "duration_days": 5
        },
        "total_conversations": len(get_test_conversations()),
        "llm_calls_expected": {
            "fragment_extraction": 10,  # 每条对话一次
            "behavior_analysis": 1,     # 整周分析一次
            "plan_analysis": 10,        # 每条对话尝试识别计划
        }
    }


if __name__ == "__main__":
    # 测试数据生成
    print("=== Dazee E2E 测试数据 ===\n")
    
    metadata = get_test_metadata()
    print(f"用户: {metadata['user_name']} ({metadata['role']})")
    print(f"测试周期: {metadata['test_period']['duration_days']} 天")
    print(f"对话数量: {metadata['total_conversations']} 条\n")
    
    conversations = get_weekly_conversations()
    for i, conv in enumerate(conversations, 1):
        print(f"{i}. [{conv['timestamp'].strftime('%m-%d %H:%M')}] {conv['scenario']}")
        print(f"   消息: {conv['content']}")
        print(f"   预期: 任务={conv['expected']['task']}, "
              f"情绪={conv['expected']['emotion']}, "
              f"提及={conv['expected']['relations']}")
        print()

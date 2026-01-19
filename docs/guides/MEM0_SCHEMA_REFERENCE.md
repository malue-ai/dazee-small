# Mem0 字段定义参考文档

> 📅 **最后更新**: 2026-01-13  
> 📌 **代码位置**: `core/memory/mem0/schemas/`  
> 🎯 **版本**: Dazee Mem0 增强版

---

## 📚 目录

- [1. 碎片记忆 (Fragment Memory)](#1-碎片记忆-fragment-memory)
- [2. 行为模式 (Behavior Pattern)](#2-行为模式-behavior-pattern)
- [3. PDCA 工作计划 (Work Plan)](#3-pdca-工作计划-work-plan)
- [4. 情绪状态 (Emotion State)](#4-情绪状态-emotion-state)
- [5. 用户画像 (User Persona)](#5-用户画像-user-persona)

---

## 1. 碎片记忆 (Fragment Memory)

从单次对话中提取的碎片级记忆，包含任务、时间、情绪、关系等线索。

### 1.1 枚举类型

#### TimeSlot（时间段）
```python
class TimeSlot(str, Enum):
    MORNING = "morning"      # 06:00-12:00
    AFTERNOON = "afternoon"  # 12:00-18:00
    EVENING = "evening"      # 18:00-22:00
    NIGHT = "night"          # 22:00-06:00
```

#### DayOfWeek（星期）
```python
class DayOfWeek(str, Enum):
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"
```

### 1.2 数据结构

#### TaskHint（任务线索）
| 字段 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `content` | `str` | 任务内容，如"客户反馈处理" | - |
| `category` | `str` | 任务类别，如"customer_support" | - |
| `confidence` | `float` | 推断置信度 0.0-1.0 | `0.0` |

#### TimeHint（时间规律线索）
| 字段 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `pattern` | `str` | 时间模式，如"early_morning_routine" | - |
| `inferred_schedule` | `Optional[str]` | 推断的时间段，如"09:00-10:00" | `None` |
| `confidence` | `float` | 置信度 0.0-1.0 | `0.0` |

#### EmotionHint（情绪线索）
| 字段 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `signal` | `str` | 情绪信号：neutral/positive/stressed/frustrated | - |
| `stress_level` | `float` | 压力水平 0.0-1.0 | `0.0` |
| `keywords_detected` | `List[str]` | 检测到的情绪关键词 | `[]` |

#### RelationHint（关系线索）
| 字段 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `mentioned` | `List[str]` | 提到的人，如["客户A", "老板"] | `[]` |
| `relationship_type` | `Optional[str]` | 关系类型：colleague/supervisor/client | `None` |

#### TodoHint（待办线索）
| 字段 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `content` | `str` | 待办内容 | - |
| `deadline` | `Optional[datetime]` | 截止时间 | `None` |
| `priority` | `str` | 优先级：low/medium/high | `"medium"` |
| `confidence` | `float` | 置信度 0.0-1.0 | `0.0` |

#### FragmentMemory（碎片记忆）
| 字段 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `id` | `str` | 唯一标识符 | - |
| `user_id` | `str` | 用户 ID | - |
| `session_id` | `str` | 会话 ID | - |
| `message` | `str` | 原始消息内容 | - |
| `timestamp` | `datetime` | 时间戳 | - |
| `time_slot` | `TimeSlot` | 时间段枚举 | - |
| `day_of_week` | `DayOfWeek` | 星期枚举 | - |
| `task_hint` | `Optional[TaskHint]` | 任务线索 | `None` |
| `time_hint` | `Optional[TimeHint]` | 时间线索 | `None` |
| `emotion_hint` | `Optional[EmotionHint]` | 情绪线索 | `None` |
| `relation_hint` | `Optional[RelationHint]` | 关系线索 | `None` |
| `todo_hint` | `Optional[TodoHint]` | 待办线索 | `None` |
| `confidence` | `float` | 整体提取置信度 0.0-1.0 | `0.0` |
| `created_at` | `datetime` | 创建时间 | `datetime.now()` |

---

## 2. 行为模式 (Behavior Pattern)

从碎片记忆中聚合推断的用户行为模式（5W1H）。

### 2.1 数据结构

#### DateRange（日期范围）
| 字段 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `start` | `datetime` | 开始时间 | - |
| `end` | `datetime` | 结束时间 | - |

#### RoutineTask（常规任务 - What）
| 字段 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `name` | `str` | 任务名称，如"客户反馈处理" | - |
| `category` | `str` | 类别 | `"general"` |
| `frequency` | `str` | 频率：daily/weekly/monthly/ad_hoc | `"ad_hoc"` |
| `avg_duration_hours` | `Optional[float]` | 平均耗时（小时） | `None` |
| `confidence` | `float` | 置信度 0.0-1.0 | `0.5` |

#### TimePattern（时间模式 - When）
| 字段 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `work_start` | `Optional[str]` | 通常开始工作时间，如"09:00" | `None` |
| `work_end` | `Optional[str]` | 通常结束工作时间，如"18:00" | `None` |
| `peak_hours` | `List[str]` | 高效工作时段 | `[]` |
| `meeting_slots` | `List[str]` | 常见会议时段 | `[]` |
| `preferred_deep_work_time` | `Optional[str]` | 偏好的深度工作时间 | `None` |

#### WorkContext（工作场景 - Where）
| 字段 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `primary_context` | `str` | 主要场景：office/remote/hybrid/unknown | `"unknown"` |
| `tools_mentioned` | `List[str]` | 提到的工具/平台 | `[]` |

#### Collaborator（协作者 - Who）
| 字段 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `name` | `str` | 名称或称呼，如"老板"、"客户A" | - |
| `relationship` | `str` | 关系：supervisor/colleague/client/external | `"colleague"` |
| `interaction_frequency` | `str` | 互动频率：daily/weekly/occasionally | `"occasionally"` |

#### Motivation（动机/目标 - Why）
| 字段 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `primary_goals` | `List[str]` | 主要工作目标 | `[]` |
| `motivations` | `List[str]` | 工作动力/驱动因素 | `[]` |
| `pain_points` | `List[str]` | 工作痛点/困扰 | `[]` |

#### WorkStyle（工作风格 - How）
| 字段 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `work_style` | `str` | 工作风格：structured/flexible/deadline_driven | `"flexible"` |
| `communication_preference` | `str` | 沟通偏好：async/sync/mixed | `"mixed"` |
| `decision_style` | `str` | 决策风格：data_driven/intuitive/collaborative | `"collaborative"` |
| `response_format_preference` | `str` | 响应格式偏好：detailed/concise/structured | `"concise"` |

#### BehaviorPattern（5W1H 行为模式）
| 字段 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `id` | `str` | 唯一标识符 | - |
| `user_id` | `str` | 用户 ID | - |
| `analysis_period` | `DateRange` | 分析时间段 | - |
| `fragment_count` | `int` | 基于多少碎片推断 | `0` |
| `routine_tasks` | `List[RoutineTask]` | 常规任务列表（What） | `[]` |
| `main_work_focus` | `str` | 主要工作重点 | `""` |
| `time_pattern` | `Optional[TimePattern]` | 时间模式（When） | `None` |
| `work_context` | `Optional[WorkContext]` | 工作场景（Where） | `None` |
| `collaborators` | `List[Collaborator]` | 协作者列表（Who） | `[]` |
| `reporting_to` | `Optional[str]` | 汇报对象 | `None` |
| `motivation` | `Optional[Motivation]` | 动机/目标（Why） | `None` |
| `work_style` | `Optional[WorkStyle]` | 工作风格（How） | `None` |
| `inferred_role` | `str` | 推断角色：product_manager/developer/sales/operations/designer/analyst/unknown | `"unknown"` |
| `role_confidence` | `float` | 角色推断置信度 0.0-1.0 | `0.0` |
| `created_at` | `datetime` | 创建时间 | `datetime.now()` |
| `updated_at` | `datetime` | 更新时间 | `datetime.now()` |

---

## 3. PDCA 工作计划 (Work Plan)

支持从对话中识别待办，并进行 Plan-Do-Check-Act 循环管理。

### 3.1 枚举类型

#### Priority（优先级）
```python
class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"
```

#### TodoStatus（待办状态）
```python
class TodoStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
```

#### PlanStatus（计划状态）
```python
class PlanStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ON_HOLD = "on_hold"
    BLOCKED = "blocked"
    AT_RISK = "at_risk"
```

#### PDCAPhase（PDCA 阶段）
```python
class PDCAPhase(str, Enum):
    PLAN = "plan"
    DO = "do"
    CHECK = "check"
    ACT = "act"
```

#### ReminderType（提醒类型）
```python
class ReminderType(str, Enum):
    DEADLINE = "deadline"           # 截止日期提醒
    PROGRESS_CHECK = "progress"     # 进度检查提醒
    HABIT = "habit"                 # 习惯性提醒
    BLOCKER_FOLLOWUP = "blocker"    # 阻碍跟进提醒
    CUSTOM = "custom"               # 自定义提醒
```

### 3.2 数据结构

#### TodoItem（待办事项）
| 字段 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `id` | `str` | 唯一标识符 | - |
| `title` | `str` | 待办标题 | - |
| `status` | `TodoStatus` | 待办状态枚举 | `TodoStatus.PENDING` |
| `started_at` | `Optional[datetime]` | 开始时间 | `None` |
| `completed_at` | `Optional[datetime]` | 完成时间 | `None` |
| `depends_on` | `List[str]` | 依赖的其他 todo id | `[]` |

#### Checkpoint（检查点）
| 字段 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `date` | `datetime` | 检查日期 | - |
| `expected_progress` | `float` | 预期进度 0.0-1.0 | - |
| `actual_progress` | `Optional[float]` | 实际进度 0.0-1.0 | `None` |
| `status` | `str` | 状态：pending/passed/failed | `"pending"` |

#### Blocker（阻碍项）
| 字段 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `id` | `str` | 唯一标识符 | - |
| `description` | `str` | 阻碍描述 | - |
| `owner` | `Optional[str]` | 负责人 | `None` |
| `status` | `str` | 状态：waiting/resolved/escalated | `"waiting"` |
| `reported_at` | `datetime` | 报告时间 | `datetime.now()` |
| `resolved_at` | `Optional[datetime]` | 解决时间 | `None` |

#### ReminderItem（提醒项）
| 字段 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `id` | `str` | 唯一标识符 | - |
| `user_id` | `str` | 用户 ID | - |
| `content` | `str` | 提醒内容 | - |
| `reminder_type` | `ReminderType` | 提醒类型枚举 | `ReminderType.CUSTOM` |
| `time` | `datetime` | 提醒时间 | `datetime.now()` |
| `related_plan_id` | `Optional[str]` | 关联计划 ID | `None` |
| `repeat` | `Optional[str]` | 重复模式：daily/weekly/monthly | `None` |
| `priority` | `str` | 优先级 | `"medium"` |
| `status` | `str` | 状态：pending/triggered/dismissed | `"pending"` |
| `created_at` | `datetime` | 创建时间 | `datetime.now()` |
| `triggered_at` | `Optional[datetime]` | 触发时间 | `None` |
| `snooze_count` | `int` | 延迟次数 | `0` |

#### Reminder（提醒 - 兼容旧版本）
| 字段 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `id` | `str` | 唯一标识符 | - |
| `type` | `str` | 类型：deadline_approaching/blocker_followup/checkpoint/custom | - |
| `trigger_time` | `datetime` | 触发时间 | - |
| `message` | `str` | 提醒消息 | - |
| `status` | `str` | 状态：scheduled/sent/cancelled | `"scheduled"` |
| `sent_at` | `Optional[datetime]` | 发送时间 | `None` |

#### CheckResult（Check 阶段检查结果）
| 字段 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `plan_id` | `str` | 计划 ID | - |
| `checked_at` | `datetime` | 检查时间 | - |
| `completion_rate` | `float` | 完成率 0.0-1.0 | - |
| `actual_result` | `str` | 实际结果描述 | - |
| `gaps` | `List[str]` | 差距列表 | `[]` |
| `lessons_learned` | `List[str]` | 经验教训 | `[]` |

#### ActionItem（Act 阶段行动项）
| 字段 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `plan_id` | `str` | 计划 ID | - |
| `decision` | `str` | 决策：continue/adjust/close/restart | - |
| `action_taken` | `str` | 采取的行动 | - |
| `created_at` | `datetime` | 创建时间 | `datetime.now()` |

#### WorkPlan（PDCA 工作计划）
| 字段 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `id` | `str` | 唯一标识符 | - |
| `user_id` | `str` | 用户 ID | - |
| `created_from` | `str` | 创建来源：conversation/manual | `"conversation"` |
| `title` | `str` | 计划标题 | `""` |
| `description` | `str` | 计划描述 | `""` |
| `deadline` | `Optional[datetime]` | 截止日期 | `None` |
| `priority` | `str` | 优先级：low/medium/high/urgent | `"medium"` |
| `source_message` | `str` | 来源对话内容 | `""` |
| `source_timestamp` | `Optional[datetime]` | 来源对话时间 | `None` |
| `category` | `str` | 类别：report/ppt/code/meeting/general | `"general"` |
| `tags` | `List[str]` | 标签列表 | `[]` |
| `estimated_hours` | `Optional[float]` | 预估耗时（小时） | `None` |
| `todos` | `List[TodoItem]` | 待办事项列表（Do） | `[]` |
| `sub_tasks` | `List[str]` | 子任务列表 | `[]` |
| `completed_tasks` | `List[str]` | 已完成任务列表 | `[]` |
| `progress` | `float` | 进度 0.0-1.0（Do） | `0.0` |
| `current_step` | `Optional[str]` | 当前步骤 | `None` |
| `phase` | `PDCAPhase` | PDCA 阶段枚举 | `PDCAPhase.PLAN` |
| `started_at` | `Optional[datetime]` | 开始时间 | `None` |
| `checkpoints` | `List[Checkpoint]` | 检查点列表（Check） | `[]` |
| `blockers` | `List[str]` | 阻碍项 ID 列表 | `[]` |
| `blocker_items` | `List[Blocker]` | 阻碍项对象列表（Check） | `[]` |
| `risks` | `List[dict]` | 风险列表：{description, probability, impact} | `[]` |
| `check_results` | `List[CheckResult]` | 检查结果列表（Check） | `[]` |
| `reminders` | `List[Reminder]` | 提醒列表（Act） | `[]` |
| `actions_taken` | `List[dict]` | 行动历史：{action, timestamp, result} | `[]` |
| `action_history` | `List[ActionItem]` | 行动项历史（Act） | `[]` |
| `lessons_learned` | `List[str]` | 经验教训（Act） | `[]` |
| `status` | `str` | 计划状态：active/completed/blocked/at_risk/cancelled | `"active"` |
| `created_at` | `datetime` | 创建时间 | `datetime.now()` |
| `updated_at` | `datetime` | 更新时间 | `datetime.now()` |
| `completed_at` | `Optional[datetime]` | 完成时间 | `None` |

---

## 4. 情绪状态 (Emotion State)

追踪用户的情绪变化和心理状态。

### 4.1 数据结构

#### EmotionSignal（单次情绪信号）
| 字段 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `timestamp` | `datetime` | 时间戳 | - |
| `message_snippet` | `str` | 消息片段 | - |
| `detected_emotion` | `str` | 检测到的情绪：neutral/positive/fatigue/frustration/stressed | - |
| `keywords` | `List[str]` | 情绪关键词 | `[]` |
| `stress_delta` | `float` | 压力变化量 | `0.0` |

#### EmotionTrend（情绪趋势）
| 字段 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `period` | `str` | 时间段：7_days/14_days/30_days | - |
| `average_stress` | `float` | 平均压力水平 0.0-1.0 | - |
| `trend_direction` | `str` | 趋势：increasing/decreasing/stable | - |
| `peak_stress_day` | `Optional[date]` | 压力最高日 | `None` |
| `main_stressors` | `List[str]` | 主要压力源 | `[]` |

#### EmotionState（情绪状态）
| 字段 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `user_id` | `str` | 用户 ID | - |
| `date` | `date` | 日期 | - |
| `current_mood` | `str` | 当前情绪：neutral/positive/slightly_stressed/stressed/frustrated | `"neutral"` |
| `stress_level` | `float` | 压力水平 0.0-1.0 | `0.0` |
| `energy_level` | `float` | 能量水平 0.0-1.0 | `0.5` |
| `last_updated` | `datetime` | 最后更新时间 | `datetime.now()` |
| `signals` | `List[EmotionSignal]` | 检测到的信号列表 | `[]` |
| `trend` | `Optional[EmotionTrend]` | 趋势分析 | `None` |
| `support_needed` | `bool` | 是否需要支持 | `False` |
| `support_reason` | `Optional[str]` | 支持原因 | `None` |
| `suggested_action` | `str` | 建议行动：none/proactive_care/resource_recommendation | `"none"` |

---

## 5. 用户画像 (User Persona)

汇总所有分析结果，生成综合用户画像，用于 Prompt 注入。

### 5.1 数据结构

#### PlanSummary（计划摘要）
| 字段 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `title` | `str` | 计划标题 | - |
| `deadline` | `Optional[datetime]` | 截止日期 | `None` |
| `progress` | `float` | 进度 0.0-1.0 | - |
| `status` | `str` | 状态：active/at_risk/completed | - |
| `blockers` | `List[str]` | 阻碍项列表 | `[]` |

#### ReminderSummary（提醒摘要）
| 字段 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `time` | `datetime` | 提醒时间 | - |
| `content` | `str` | 提醒内容 | - |
| `type` | `str` | 类型：deadline/blocker/checkpoint | - |

#### UserPersona（用户画像）
| 字段 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `user_id` | `str` | 用户 ID | - |
| `generated_at` | `datetime` | 生成时间 | `datetime.now()` |
| `inferred_role` | `str` | 推断角色：product_manager/developer/sales/operations/designer/analyst/unknown | `"unknown"` |
| `role_confidence` | `float` | 角色推断置信度 0.0-1.0 | `0.0` |
| `work_domain` | `str` | 工作领域 | `"general"` |
| `routine_overview` | `str` | 工作规律概述 | `""` |
| `work_style` | `str` | 工作风格 | `""` |
| `time_management` | `str` | 时间管理方式 | `""` |
| `mood` | `str` | 情绪状态：neutral/positive/slightly_stressed/stressed/frustrated | `"neutral"` |
| `stress_level` | `float` | 压力水平 0.0-1.0 | `0.0` |
| `main_concerns` | `List[str]` | 主要关注点 | `[]` |
| `support_flag` | `bool` | 是否需要关怀 | `False` |
| `active_plans` | `List[PlanSummary]` | 活跃计划列表 | `[]` |
| `upcoming_reminders` | `List[ReminderSummary]` | 即将到来的提醒列表 | `[]` |
| `greeting_style` | `str` | 问候风格：professional/casual/warm | `"professional"` |
| `response_format` | `str` | 响应格式：structured/concise/detailed | `"structured"` |
| `proactive_level` | `str` | 主动程度：low/medium/high | `"medium"` |
| `emotional_support` | `bool` | 是否启用情感支持 | `True` |
| `prompt_injection_enabled` | `bool` | 是否启用 Prompt 注入 | `True` |
| `prompt_sections` | `List[str]` | Prompt 注入的段落列表 | `["identity", "current_state", "active_plans", "personalization"]` |
| `max_prompt_tokens` | `int` | 最大 Prompt Token 数 | `500` |
| `source_fragments` | `int` | 基于多少碎片 | `0` |
| `last_behavior_analysis` | `Optional[datetime]` | 最后一次行为分析时间 | `None` |
| `last_emotion_analysis` | `Optional[datetime]` | 最后一次情绪分析时间 | `None` |
| `ttl_minutes` | `int` | 缓存 TTL（分钟） | `60` |

---

## 📝 使用示例

### 示例 1: 创建碎片记忆

```python
from core.memory.mem0.schemas import FragmentMemory, TaskHint, TimeSlot, DayOfWeek
from datetime import datetime

fragment = FragmentMemory(
    id="frag_001",
    user_id="user_123",
    session_id="session_456",
    message="我需要在下周一早上处理客户反馈",
    timestamp=datetime.now(),
    time_slot=TimeSlot.MORNING,
    day_of_week=DayOfWeek.MONDAY,
    task_hint=TaskHint(
        content="处理客户反馈",
        category="customer_support",
        confidence=0.9
    ),
    confidence=0.85
)
```

### 示例 2: 创建工作计划

```python
from core.memory.mem0.schemas import WorkPlan, TodoItem, TodoStatus, PDCAPhase
from datetime import datetime, timedelta

plan = WorkPlan(
    id="plan_001",
    user_id="user_123",
    title="完成季度报告",
    description="准备 Q4 季度业务报告",
    deadline=datetime.now() + timedelta(days=7),
    priority="high",
    category="report",
    todos=[
        TodoItem(
            id="todo_001",
            title="收集数据",
            status=TodoStatus.PENDING
        ),
        TodoItem(
            id="todo_002",
            title="撰写报告",
            status=TodoStatus.PENDING,
            depends_on=["todo_001"]
        )
    ],
    phase=PDCAPhase.PLAN
)
```

### 示例 3: 创建用户画像

```python
from core.memory.mem0.schemas import UserPersona, PlanSummary
from datetime import datetime, timedelta

persona = UserPersona(
    user_id="user_123",
    inferred_role="product_manager",
    role_confidence=0.85,
    work_domain="SaaS",
    routine_overview="工作日通常 9:00-18:00，高效时段在上午",
    work_style="structured",
    mood="positive",
    stress_level=0.3,
    active_plans=[
        PlanSummary(
            title="完成季度报告",
            deadline=datetime.now() + timedelta(days=7),
            progress=0.4,
            status="active"
        )
    ],
    response_format="structured",
    proactive_level="high"
)
```

---

## 🔗 相关文档

- [Mem0 设置指南](./MEM0_SETUP_GUIDE.md)
- [Mem0 Embedding 配置指南](./MEM0_EMBEDDING_GUIDE.md)
- [代码实现](../../core/memory/mem0/schemas/)

---

## 📌 注意事项

1. **字段类型**: 所有枚举类型使用 `str` 类型，便于 JSON 序列化
2. **时间格式**: `datetime` 类型在序列化时使用 ISO 格式（`isoformat()`）
3. **可选字段**: 使用 `Optional[T]` 类型，默认值为 `None`
4. **列表字段**: 使用 `field(default_factory=list)` 避免可变默认值问题
5. **置信度字段**: 范围统一为 0.0-1.0
6. **状态字段**: 使用枚举类型确保值的一致性

---

**最后更新**: 2026-01-13  
**维护者**: Dazee Team

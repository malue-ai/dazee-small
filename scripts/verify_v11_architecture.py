"""
V11 架构完整性验证脚本

验证小搭子实例代码框架实施计划的所有 Phase 是否正确实现。
运行方式：
    python3 scripts/verify_v11_architecture.py
"""

import importlib
import inspect
import os
import sys
from pathlib import Path

# 确保项目根目录在 sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

passed = 0
failed = 0
warnings = 0


def check(description: str, condition: bool, warn_only: bool = False):
    """断言检查"""
    global passed, failed, warnings
    if condition:
        print(f"  ✅ {description}")
        passed += 1
    elif warn_only:
        print(f"  ⚠️ {description}")
        warnings += 1
    else:
        print(f"  ❌ {description}")
        failed += 1


def check_file_exists(path: str, should_exist: bool = True):
    """检查文件是否存在/不存在"""
    exists = (ROOT / path).exists()
    if should_exist:
        check(f"文件存在: {path}", exists)
    else:
        check(f"文件已删除: {path}", not exists)


def check_module_importable(module_name: str):
    """检查模块是否可导入"""
    try:
        importlib.import_module(module_name)
        check(f"模块可导入: {module_name}", True)
    except Exception as e:
        check(f"模块可导入: {module_name} ({e})", False)


def check_class_has_method(cls, method_name: str):
    """检查类是否有某个方法"""
    has = hasattr(cls, method_name) and callable(getattr(cls, method_name))
    check(f"{cls.__name__}.{method_name}() 存在", has)


def check_class_has_attr(cls, attr_name: str):
    """检查类是否有某个属性（含 dataclass 字段）"""
    has = hasattr(cls, attr_name)
    # dataclass 必填字段不会挂在类上，需要检查 __dataclass_fields__
    if not has and hasattr(cls, "__dataclass_fields__"):
        has = attr_name in cls.__dataclass_fields__
    check(f"{cls.__name__}.{attr_name} 存在", has)


# ========== Phase 0: 架构清理 ==========
print("\n" + "=" * 60)
print("Phase 0: 架构清理验证")
print("=" * 60)

# 应删除的目录/文件
phase0_deleted = [
    "core/agent/execution/_multi/",
    "core/agent/execution/multi.py",
    "core/multi_agent/",
    "core/agent/components/critic.py",
    "core/agent/components/lead_agent.py",
    "config/multi_agent_config.yaml",
    "prompts/multi_agent/",
    "evaluation/suites/multi_agent/",
    "services/knowledge_service.py",
    "utils/knowledge_store.py",
    "tools/knowledge_search.py",
    "routers/knowledge.py",
    "models/knowledge.py",
    "core/context/providers/knowledge.py",
    "core/context/injectors/phase2/knowledge.py",
    "tools/tavily_search.py",
    "tools/exa_search.py",
    "tools/slidespeak.py",
    "tools/ppt_generator.py",
    "tools/nano_banana_image.py",
    "tools/partition.py",
    "core/llm/moa/",
    "services/health_probe_service.py",
]
for path in phase0_deleted:
    check_file_exists(path, should_exist=False)

# 应保留的文件
# checkpoint.py: 计划原要求保留，但分析后确认应删除：
# 1. 依赖已删除的多智能体模型（OrchestratorState, TaskAssignment）
# 2. 记录多智能体流水线状态，不适用于 RVR-B 单智能体
# 3. 功能已被 core/state/ 模块替代（Phase 4）
check_file_exists("core/agent/components/checkpoint.py", should_exist=False)
check_file_exists("core/events/adapters/dingtalk.py", should_exist=True)
check_file_exists("core/events/dispatcher.py", should_exist=True)
check_file_exists("models/database.py", should_exist=True)  # Pydantic 响应模型，活跃使用

# main.py 可导入
check_module_importable("main")

# ========== Phase 1: 实例骨架 ==========
print("\n" + "=" * 60)
print("Phase 1: 实例骨架验证")
print("=" * 60)

check_file_exists("instances/xiaodazi/config.yaml")
check_file_exists("instances/xiaodazi/prompt.md")
check_file_exists("instances/xiaodazi/skills/skill_registry.yaml")

# InstanceConfig 新增字段
from utils.instance_loader import InstanceConfig

for field_name in ["termination", "state_consistency"]:
    check(
        f"InstanceConfig.{field_name} 字段存在",
        field_name in InstanceConfig.__dataclass_fields__
        if hasattr(InstanceConfig, "__dataclass_fields__")
        else hasattr(InstanceConfig, field_name),
    )

# IntentAnalyzer 配置扩展
from core.routing.intent_analyzer import IntentAnalyzer

check(
    "IntentAnalyzer 支持 fast_mode",
    "fast_mode" in inspect.signature(IntentAnalyzer.__init__).parameters
    or hasattr(IntentAnalyzer, "fast_mode"),
)

# ========== Phase 2: 自适应终止策略 ==========
print("\n" + "=" * 60)
print("Phase 2: 自适应终止策略验证")
print("=" * 60)

check_file_exists("core/termination/__init__.py")
check_file_exists("core/termination/protocol.py")
check_file_exists("core/termination/adaptive.py")

from core.termination.protocol import BaseTerminator, TerminationAction, TerminationDecision

check("TerminationDecision 有 should_stop 字段", "should_stop" in TerminationDecision.__dataclass_fields__)
check("TerminationDecision 有 reason 字段", "reason" in TerminationDecision.__dataclass_fields__)
check("TerminationDecision 有 action 字段", "action" in TerminationDecision.__dataclass_fields__)
check("TerminationAction 有 STOP", hasattr(TerminationAction, "STOP"))
check("TerminationAction 有 ASK_USER", hasattr(TerminationAction, "ASK_USER"))

from core.termination.adaptive import AdaptiveTerminator, AdaptiveTerminatorConfig

check_class_has_method(AdaptiveTerminator, "evaluate")

# AdaptiveTerminatorConfig 四维度配置
for field in ["max_turns", "max_duration_seconds", "idle_timeout_seconds",
              "consecutive_failure_limit", "long_running_confirm_after_turns"]:
    check(f"AdaptiveTerminatorConfig.{field}", hasattr(AdaptiveTerminatorConfig, field))

# RuntimeContext 新增属性
from core.context.runtime import RuntimeContext

check("RuntimeContext.consecutive_failures 字段", "consecutive_failures" in RuntimeContext.__dataclass_fields__)
check(
    "RuntimeContext.duration_seconds 属性",
    isinstance(inspect.getattr_static(RuntimeContext, "duration_seconds", None), property),
)

# ExecutorConfig.terminator 字段
from core.agent.execution.protocol import ExecutorConfig

check("ExecutorConfig.terminator 字段", "terminator" in ExecutorConfig.__dataclass_fields__)

# ========== Phase 3: Skills 二维分类 ==========
print("\n" + "=" * 60)
print("Phase 3: Skills 二维分类验证")
print("=" * 60)

check_file_exists("core/skill/os_skill_merger.py")
check_file_exists("core/skill/os_compatibility.py")

from core.skill.os_skill_merger import OSSkillMerger

check_class_has_method(OSSkillMerger, "get_enabled_skills")
check_class_has_method(OSSkillMerger, "get_unavailable_skills")

from core.skill.os_compatibility import OSCompatibilityChecker, CompatibilityResult, CompatibilityStatus

check_class_has_method(OSCompatibilityChecker, "check_skill")
check("CompatibilityStatus 有 READY", hasattr(CompatibilityStatus, "READY"))
check("CompatibilityStatus 有 NEED_AUTH", hasattr(CompatibilityStatus, "NEED_AUTH"))
check("CompatibilityStatus 有 NEED_SETUP", hasattr(CompatibilityStatus, "NEED_SETUP"))
check("CompatibilityStatus 有 UNAVAILABLE", hasattr(CompatibilityStatus, "UNAVAILABLE"))

# DynamicSkillLoader 集成 OSSkillMerger
from core.skill.dynamic_loader import DynamicSkillLoader

init_params = inspect.signature(DynamicSkillLoader.__init__).parameters
check("DynamicSkillLoader.__init__ 接受 os_skill_merger", "os_skill_merger" in init_params)
check_class_has_method(DynamicSkillLoader, "get_eligible_skills")

# RuntimeContextBuilder.build_skill_status_prompt
from core.prompt.runtime_context_builder import RuntimeContextBuilder

check_class_has_method(RuntimeContextBuilder, "build_skill_status_prompt")

# ========== Phase 4: 状态一致性管理 ==========
print("\n" + "=" * 60)
print("Phase 4: 状态一致性管理验证")
print("=" * 60)

check_file_exists("core/state/__init__.py")
check_file_exists("core/state/operation_log.py")
check_file_exists("core/state/consistency_manager.py")

from core.state.operation_log import OperationRecord, OperationLog

for field_name in ["operation_id", "action", "target", "before_state", "after_state",
              "rollback_action", "timestamp"]:
    check(f"OperationRecord.{field_name}", field_name in OperationRecord.__dataclass_fields__)

check_class_has_method(OperationLog, "append")
check_class_has_method(OperationLog, "rollback_all")

from core.state.consistency_manager import StateConsistencyManager, Snapshot

check_class_has_method(StateConsistencyManager, "create_snapshot")
check_class_has_method(StateConsistencyManager, "record_operation")
check_class_has_method(StateConsistencyManager, "rollback")
check_class_has_method(StateConsistencyManager, "commit")
check_class_has_method(StateConsistencyManager, "get_rollback_options")

# 回滚事件（EventBroadcaster）
from core.events.broadcaster import EventBroadcaster

check_class_has_method(EventBroadcaster, "emit_rollback_options")
check_class_has_method(EventBroadcaster, "emit_rollback_result")

# Agent.get_rollback_options
from core.agent.base import Agent

check_class_has_method(Agent, "get_rollback_options")

# ========== Phase 5: 记忆 / 知识 / 发现 ==========
print("\n" + "=" * 60)
print("Phase 5: 记忆/知识/发现模块验证")
print("=" * 60)

check_file_exists("core/knowledge/__init__.py")
check_file_exists("core/knowledge/local_search.py")
check_file_exists("core/knowledge/file_indexer.py")
check_file_exists("core/discovery/__init__.py")
check_file_exists("core/discovery/app_scanner.py")
check_file_exists("core/memory/instance_memory.py")
check_file_exists("core/planning/progress_transformer.py")
check_file_exists("core/project/__init__.py")
check_file_exists("core/project/manager.py")

from core.knowledge.local_search import LocalKnowledgeManager

check_class_has_method(LocalKnowledgeManager, "search")

from core.knowledge.file_indexer import FileIndexer

check_class_has_method(FileIndexer, "index_directory")

from core.discovery.app_scanner import AppScanner

check_class_has_method(AppScanner, "scan")
check_class_has_method(AppScanner, "get_capabilities")
check_class_has_method(AppScanner, "find_app_for_task")

from core.memory.instance_memory import InstanceMemoryManager

check_class_has_method(InstanceMemoryManager, "recall")
check_class_has_method(InstanceMemoryManager, "remember")
check_class_has_method(InstanceMemoryManager, "flush")

from core.planning.progress_transformer import ProgressTransformer, ProgressUpdate

check_class_has_method(ProgressTransformer, "transform")
check_class_has_method(ProgressTransformer, "transform_and_emit")
check(
    "ProgressTransformer.__init__ 接受 broadcaster",
    "broadcaster" in inspect.signature(ProgressTransformer.__init__).parameters,
)

# 进度事件
check_class_has_method(EventBroadcaster, "emit_progress_update")

# ========== 代码质量检查 ==========
print("\n" + "=" * 60)
print("代码质量验证")
print("=" * 60)

# AdaptiveTerminator.evaluate 不使用 getattr 访问 RuntimeContext 的确定字段
source = inspect.getsource(AdaptiveTerminator.evaluate)
check(
    "evaluate 使用 ctx.duration_seconds（非 getattr）",
    "ctx.duration_seconds" in source
    and "getattr(ctx, \"duration_seconds\"" not in source
    and "getattr(ctx, 'duration_seconds'" not in source,
)
check(
    "evaluate 使用 ctx.consecutive_failures（非 getattr）",
    "ctx.consecutive_failures" in source
    and "getattr(ctx, \"consecutive_failures\"" not in source
    and "getattr(ctx, 'consecutive_failures'" not in source,
)

# ASK_USER 在 long_running_confirm 时 should_stop=True
check(
    "long_running_confirm 时 should_stop=True（确保执行器会暂停）",
    "should_stop=True" in source and "long_running_confirm" in source,
)

# terminator 类型标注不是 Any
exec_config_source = inspect.getsource(ExecutorConfig)
check(
    "ExecutorConfig.terminator 类型不是 Optional[Any]",
    'Optional[Any]' not in exec_config_source or 'terminator' not in exec_config_source.split('Optional[Any]')[0].split('\n')[-1],
)

# base.py 中 state_consistency 有 try-except
agent_exec_source = inspect.getsource(Agent.execute)
check(
    "Agent.execute 中 create_snapshot 有异常处理",
    "create_snapshot" in agent_exec_source and "except" in agent_exec_source,
)
check(
    "Agent.execute 中有回滚处理逻辑",
    "rollback" in agent_exec_source.lower(),
)

# ========== 汇总 ==========
print("\n" + "=" * 60)
total = passed + failed + warnings
print(f"验证完成: {passed}/{total} 通过, {failed} 失败, {warnings} 警告")
print("=" * 60)

sys.exit(1 if failed > 0 else 0)

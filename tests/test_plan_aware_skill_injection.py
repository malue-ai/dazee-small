"""
Plan-Aware Skill Injection Tests (V12.1)

验证 intent.relevant_skill_groups 与 plan.required_skills 的合并逻辑。

核心原则：
- Intent（Haiku）负责"当前轮需要什么"
- Plan（主模型）负责"整体任务需要什么"
- 两者 union 合并，最大化召回率
- 宁多勿漏：多选无害，漏选致命

Run:
    python -m pytest tests/test_plan_aware_skill_injection.py -v
"""

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

# ======================================================================
# 隔离导入：使用 importlib.util 直接加载目标 .py 文件，
# 完全绕开 core/__init__.py → Agent → LLM → ... 的重依赖链。
# ======================================================================

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _load_module(name: str, filepath: Path):
    """
    从指定文件加载模块，不触发任何 __init__.py。
    如果目标模块 import 了尚未加载的父包，先注册空壳。
    """
    # 确保父包名在 sys.modules 中（空壳），防止 import 链
    parts = name.rsplit(".", 1)
    if len(parts) == 2:
        parent = parts[0]
        for i, seg in enumerate(parent.split(".")):
            pkg = ".".join(parent.split(".")[:i + 1])
            if pkg not in sys.modules:
                sys.modules[pkg] = type(sys)("__fake__")

    spec = importlib.util.spec_from_file_location(name, str(filepath))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# 1) logger（group_registry 依赖它）
_logger_mod = _load_module("logger", _ROOT / "logger.py")

# 2) SkillGroupRegistry（纯数据类，只依赖 logger）
_gr_mod = _load_module(
    "core.skill.group_registry",
    _ROOT / "core" / "skill" / "group_registry.py",
)
SkillGroupRegistry = _gr_mod.SkillGroupRegistry

# 3) InjectionContext（纯 dataclass，TYPE_CHECKING 下的 import 不执行）
_ctx_mod = _load_module(
    "core.context.injectors.context",
    _ROOT / "core" / "context" / "injectors" / "context.py",
)
InjectionContext = _ctx_mod.InjectionContext

# 4) ToolSystemRoleProvider._merge_plan_skills（需要 BaseInjector 壳）
# 先注册 base 的空壳依赖
_base_stub = type(sys)("base_stub")
_base_stub.BaseInjector = type("BaseInjector", (), {})
_base_stub.CacheStrategy = MagicMock()
_base_stub.InjectionPhase = MagicMock()
_base_stub.InjectionResult = MagicMock()
sys.modules["core.context.injectors.base"] = _base_stub
# 把刚加载的 context 也注册为 ..context 可达
sys.modules["core.context.injectors.context"] = _ctx_mod

_tp_mod = _load_module(
    "core.context.injectors.phase1.tool_provider",
    _ROOT / "core" / "context" / "injectors" / "phase1" / "tool_provider.py",
)
_merge_plan_skills = _tp_mod.ToolSystemRoleProvider._merge_plan_skills


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture
def sample_skill_groups_config():
    """模拟 skills.yaml 中的 skill_groups 配置"""
    return {
        "writing": {
            "description": "写作、润色、改写",
            "skills": ["writing-assistant", "style-learner", "humanizer", "elegant-reports"],
        },
        "data_analysis": {
            "description": "Excel/CSV 数据分析",
            "skills": ["excel-analyzer", "excel-fixer", "invoice-organizer"],
        },
        "file_operation": {
            "description": "文件管理、PDF、Word",
            "skills": ["file-manager", "word-processor", "nano-pdf", "pdf-toolkit"],
        },
        "research": {
            "description": "论文搜索、调研",
            "skills": ["literature-reviewer", "paper-search", "deep-research"],
        },
        "translation": {
            "description": "多语言翻译",
            "skills": ["translator", "locale-aware-formatter"],
        },
        "productivity": {
            "description": "笔记、邮件、日历",
            "skills": ["notion", "smart-email-assistant", "apple-calendar"],
        },
        "meeting": {
            "description": "会议记录分析",
            "skills": ["meeting-insights-analyzer", "meeting-notes-to-action-items"],
        },
        "media": {
            "description": "音视频处理",
            "skills": ["openai-whisper", "video-frames"],
        },
        "content_creation": {
            "description": "社交媒体创作",
            "skills": ["social-media-creator", "newsletter-writer"],
        },
        "_always": {
            "description": "始终注入",
            "skills": ["local-search", "weather"],
        },
    }


@pytest.fixture
def registry(sample_skill_groups_config):
    return SkillGroupRegistry(sample_skill_groups_config)


def _make_context(plan=None):
    metadata = {"plan": plan} if plan is not None else {}
    return InjectionContext(metadata=metadata)


def _make_plan(required_skills=None, name="测试计划"):
    plan = {
        "name": name,
        "todos": [{"id": "1", "title": "步骤1", "status": "pending"}],
    }
    if required_skills is not None:
        plan["required_skills"] = required_skills
    return plan


# ======================================================================
# T1: 基本合并 — intent 漏了的分组由 plan 补上
# ======================================================================


class TestBasicMerge:
    def test_plan_supplements_missing_groups(self, registry):
        """plan 的 smart-email-assistant 补上 productivity 分组"""
        intent_groups = ["data_analysis", "writing"]
        plan = _make_plan(required_skills=["excel-analyzer", "writing-assistant", "smart-email-assistant"])
        context = _make_context(plan=plan)

        result = _merge_plan_skills(intent_groups, context, registry)

        assert result is not None
        assert set(result) == {"data_analysis", "writing", "productivity"}

    def test_merge_is_union_not_replace(self, registry):
        """合并是 union，不会丢失 intent 原有的分组"""
        intent_groups = ["writing"]
        plan = _make_plan(required_skills=["deep-research"])
        context = _make_context(plan=plan)

        result = _merge_plan_skills(intent_groups, context, registry)

        assert "writing" in result
        assert "research" in result


# ======================================================================
# T2: 无 plan — Turn 1 场景，intent 独扛
# ======================================================================


class TestNoPlan:
    def test_no_plan_returns_intent_unchanged(self, registry):
        context = _make_context(plan=None)
        result = _merge_plan_skills(["data_analysis", "writing"], context, registry)
        assert result == ["data_analysis", "writing"]

    def test_empty_metadata_returns_intent_unchanged(self, registry):
        context = InjectionContext(metadata={})
        result = _merge_plan_skills(["writing"], context, registry)
        assert result == ["writing"]


# ======================================================================
# T3: plan 存在但 LLM 未填 required_skills
# ======================================================================


class TestPlanWithoutRequiredSkills:
    def test_plan_without_required_skills(self, registry):
        plan = _make_plan(required_skills=None)
        context = _make_context(plan=plan)
        result = _merge_plan_skills(["writing"], context, registry)
        assert result == ["writing"]

    def test_plan_with_empty_required_skills(self, registry):
        plan = _make_plan(required_skills=[])
        context = _make_context(plan=plan)
        result = _merge_plan_skills(["writing"], context, registry)
        assert result == ["writing"]


# ======================================================================
# T4: intent 为 None（全量 Fallback）— 不合并
# ======================================================================


class TestIntentNoneFallback:
    def test_none_intent_returns_none(self, registry):
        plan = _make_plan(required_skills=["excel-analyzer"])
        context = _make_context(plan=plan)
        result = _merge_plan_skills(None, context, registry)
        assert result is None

    def test_none_intent_without_plan(self, registry):
        context = _make_context(plan=None)
        result = _merge_plan_skills(None, context, registry)
        assert result is None


# ======================================================================
# T5: intent 为空列表 — plan 补偿生效
# ======================================================================


class TestEmptyIntentGroups:
    def test_empty_intent_gets_plan_groups(self, registry):
        plan = _make_plan(required_skills=["writing-assistant", "excel-analyzer"])
        context = _make_context(plan=plan)
        result = _merge_plan_skills([], context, registry)
        assert set(result) == {"writing", "data_analysis"}


# ======================================================================
# T6: plan 中有未知 skill — 安全忽略
# ======================================================================


class TestUnknownSkills:
    def test_unknown_skill_ignored(self, registry):
        plan = _make_plan(required_skills=["nonexistent-skill", "writing-assistant"])
        context = _make_context(plan=plan)
        result = _merge_plan_skills(["data_analysis"], context, registry)
        assert set(result) == {"data_analysis", "writing"}

    def test_all_unknown_skills_no_change(self, registry):
        plan = _make_plan(required_skills=["foo", "bar", "baz"])
        context = _make_context(plan=plan)
        result = _merge_plan_skills(["writing"], context, registry)
        assert result == ["writing"]


# ======================================================================
# T7: plan 和 intent 完全重叠 — 无变化
# ======================================================================


class TestFullOverlap:
    def test_no_new_groups_added(self, registry):
        plan = _make_plan(required_skills=["writing-assistant", "style-learner"])
        context = _make_context(plan=plan)
        result = _merge_plan_skills(["writing"], context, registry)
        assert result == ["writing"]


# ======================================================================
# T8: 无 group_registry — 安全降级
# ======================================================================


class TestNoGroupRegistry:
    def test_none_registry_returns_intent(self):
        plan = _make_plan(required_skills=["writing-assistant"])
        context = _make_context(plan=plan)
        result = _merge_plan_skills(["data_analysis"], context, None)
        assert result == ["data_analysis"]

    def test_registry_without_method_returns_intent(self):
        fake_registry = MagicMock(spec=[])
        plan = _make_plan(required_skills=["writing-assistant"])
        context = _make_context(plan=plan)
        result = _merge_plan_skills(["data_analysis"], context, fake_registry)
        assert result == ["data_analysis"]


# ======================================================================
# T9: 复杂多 skill 合并 — 多个 skill 映射到多个 group
# ======================================================================


class TestComplexMultiSkillMerge:
    def test_multi_skill_multi_group_merge(self, registry):
        """intent=media+writing, plan 补上 translation+content_creation"""
        intent_groups = ["media", "writing"]
        plan = _make_plan(
            required_skills=[
                "openai-whisper",        # → media (已有)
                "translator",            # → translation (新增)
                "writing-assistant",     # → writing (已有)
                "social-media-creator",  # → content_creation (新增)
            ]
        )
        context = _make_context(plan=plan)
        result = _merge_plan_skills(intent_groups, context, registry)
        assert set(result) == {"media", "writing", "translation", "content_creation"}

    def test_single_skill_maps_to_one_group(self, registry):
        plan = _make_plan(required_skills=["meeting-insights-analyzer"])
        context = _make_context(plan=plan)
        result = _merge_plan_skills(["writing"], context, registry)
        assert set(result) == {"writing", "meeting"}


# ======================================================================
# T10: plan 包含 _always 组 skill — 不重复注入
# ======================================================================


class TestAlwaysGroupFiltered:
    def test_always_group_filtered_out(self, registry):
        plan = _make_plan(required_skills=["local-search", "weather", "writing-assistant"])
        context = _make_context(plan=plan)
        result = _merge_plan_skills(["data_analysis"], context, registry)
        assert set(result) == {"data_analysis", "writing"}
        assert "_always" not in result


# ======================================================================
# T11: 边界输入 — 各种异常值不应崩溃
# ======================================================================


class TestEdgeCases:
    def test_plan_is_not_dict(self, registry):
        context = _make_context(plan="invalid")
        result = _merge_plan_skills(["writing"], context, registry)
        assert result == ["writing"]

    def test_required_skills_is_not_list(self, registry):
        plan = {"name": "test", "todos": [], "required_skills": "not-a-list"}
        context = _make_context(plan=plan)
        result = _merge_plan_skills(["writing"], context, registry)
        assert result == ["writing"]

    def test_required_skills_contains_non_string(self, registry):
        plan = _make_plan(required_skills=["writing-assistant", 123, None, True])
        context = _make_context(plan=plan)
        result = _merge_plan_skills(["data_analysis"], context, registry)
        assert set(result) == {"data_analysis", "writing"}

    def test_empty_plan_dict(self, registry):
        context = _make_context(plan={})
        result = _merge_plan_skills(["writing"], context, registry)
        assert result == ["writing"]


# ======================================================================
# T12: SkillGroupRegistry 反查验证
# ======================================================================


class TestRegistryReverseLookup:
    def test_known_skill_returns_group(self, registry):
        assert "writing" in registry.get_groups_for_skill("writing-assistant")

    def test_unknown_skill_returns_empty(self, registry):
        assert registry.get_groups_for_skill("nonexistent") == []

    def test_always_skill_returns_always_group(self, registry):
        assert "_always" in registry.get_groups_for_skill("local-search")

    def test_multi_group_skill(self, sample_skill_groups_config):
        config = dict(sample_skill_groups_config)
        config["writing"] = dict(config["writing"])
        config["writing"]["skills"] = list(config["writing"]["skills"]) + ["translator"]
        reg = SkillGroupRegistry(config)
        groups = reg.get_groups_for_skill("translator")
        assert "writing" in groups
        assert "translation" in groups


# ======================================================================
# T13: 端到端模拟 — 完整注入流程
# ======================================================================


class TestEndToEndFlow:
    def test_turn1_no_plan_intent_only(self, registry):
        """Turn 1: 无 plan，intent 独扛"""
        context = _make_context(plan=None)
        merged = _merge_plan_skills(["data_analysis", "writing"], context, registry)
        assert merged == ["data_analysis", "writing"]

    def test_turn2_plan_supplements(self, registry):
        """Turn 2: plan 补偿 intent 遗漏"""
        plan = _make_plan(
            required_skills=["excel-analyzer", "writing-assistant", "smart-email-assistant"]
        )
        context = _make_context(plan=plan)
        merged = _merge_plan_skills(["data_analysis"], context, registry)
        assert set(merged) == {"data_analysis", "writing", "productivity"}

    def test_turn2_follow_up_new_need(self, registry):
        """Turn 2 追问: intent 捕获新需求 + plan 保留旧需求"""
        plan = _make_plan(required_skills=["excel-analyzer", "writing-assistant"])
        context = _make_context(plan=plan)
        merged = _merge_plan_skills(["translation"], context, registry)
        assert set(merged) == {"translation", "data_analysis", "writing"}

    def test_conservative_default_not_affected(self, registry):
        """保守默认值（intent=None）不受 plan 影响"""
        plan = _make_plan(required_skills=["excel-analyzer"])
        context = _make_context(plan=plan)
        merged = _merge_plan_skills(None, context, registry)
        assert merged is None

"""
Plan Tool 语义 Upsert 端到端测试

验证三个核心场景：
A. 新对话新任务 → create 直接成功
B. 旧对话新任务 (is_follow_up=false) → create 覆盖旧 plan
C. 追问 (is_follow_up=true) → create 被拒绝，保护现有 plan
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.tool.types import ToolContext, create_tool_context
from tools.plan_todo_tool import PlanTool


@pytest.fixture
def plan_tool():
    return PlanTool()


@pytest.fixture
def sample_params():
    return {
        "action": "create",
        "name": "构建人力资源管理系统",
        "overview": "利用云端智能体构建完整的现代化人力资源管理系统",
        "todos": [
            {"id": "1", "title": "员工信息管理"},
            {"id": "2", "title": "考勤管理"},
            {"id": "3", "title": "薪资管理"},
        ],
    }


@pytest.fixture
def existing_plan():
    return {
        "name": "构建贪吃蛇游戏",
        "overview": "构建网页版贪吃蛇小游戏",
        "todos": [
            {"id": "1", "title": "创建 HTML 结构", "status": "completed"},
            {"id": "2", "title": "编写游戏逻辑", "status": "completed"},
        ],
        "created_at": "2026-03-01T10:00:00",
    }


def _make_context(is_follow_up: bool = False) -> ToolContext:
    ctx = create_tool_context(
        session_id="test-session",
        conversation_id="test-conv-001",
        user_id="test-user",
    )
    ctx.set("is_follow_up", is_follow_up)
    return ctx


class TestPlanUpsert:
    """Plan Tool 语义 Upsert 测试"""

    @pytest.mark.asyncio
    async def test_scenario_a_new_conversation_new_task(self, plan_tool, sample_params):
        """场景 A: 新对话新任务 → create 直接成功"""
        context = _make_context(is_follow_up=False)

        with patch.object(plan_tool, "_load", new_callable=AsyncMock, return_value=None), \
             patch.object(plan_tool, "_save", new_callable=AsyncMock):

            result = await plan_tool.execute(sample_params, context)

        assert result["success"] is True
        assert result["plan"]["name"] == "构建人力资源管理系统"
        assert len(result["plan"]["todos"]) == 3
        assert result.get("replaced_old") is False

    @pytest.mark.asyncio
    async def test_scenario_b_old_conversation_new_task(
        self, plan_tool, sample_params, existing_plan
    ):
        """场景 B: 旧对话新任务 (is_follow_up=false) → create 覆盖旧 plan，一次成功"""
        context = _make_context(is_follow_up=False)

        with patch.object(plan_tool, "_load", new_callable=AsyncMock, return_value=existing_plan), \
             patch.object(plan_tool, "_save", new_callable=AsyncMock) as mock_save:

            result = await plan_tool.execute(sample_params, context)

        assert result["success"] is True
        assert result["plan"]["name"] == "构建人力资源管理系统"
        assert result["replaced_old"] is True
        # 保留旧 plan 的 created_at
        assert result["plan"]["created_at"] == "2026-03-01T10:00:00"
        mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_scenario_c_follow_up_protects_plan(
        self, plan_tool, sample_params, existing_plan
    ):
        """场景 C: 追问 (is_follow_up=true) → create 被拒绝，保护现有 plan"""
        context = _make_context(is_follow_up=True)

        with patch.object(plan_tool, "_load", new_callable=AsyncMock, return_value=existing_plan), \
             patch.object(plan_tool, "_save", new_callable=AsyncMock) as mock_save:

            result = await plan_tool.execute(sample_params, context)

        assert result["success"] is False
        assert "追问" in result["error"]
        assert result["current_plan_name"] == "构建贪吃蛇游戏"
        mock_save.assert_not_called()

    @pytest.mark.asyncio
    async def test_rewrite_same_as_create(self, plan_tool, existing_plan):
        """rewrite 和 create 行为一致：追问时同样被拒绝"""
        context = _make_context(is_follow_up=True)
        params = {
            "action": "rewrite",
            "name": "调整后的贪吃蛇游戏",
            "todos": [{"id": "1", "title": "重新设计 UI"}],
        }

        with patch.object(plan_tool, "_load", new_callable=AsyncMock, return_value=existing_plan), \
             patch.object(plan_tool, "_save", new_callable=AsyncMock) as mock_save:

            result = await plan_tool.execute(params, context)

        assert result["success"] is False
        assert "追问" in result["error"]
        mock_save.assert_not_called()

    @pytest.mark.asyncio
    async def test_rewrite_new_task_succeeds(self, plan_tool, existing_plan):
        """rewrite 在新任务 (is_follow_up=false) 时正常覆盖"""
        context = _make_context(is_follow_up=False)
        params = {
            "action": "rewrite",
            "name": "调整后的贪吃蛇游戏",
            "todos": [{"id": "1", "title": "重新设计 UI"}],
        }

        with patch.object(plan_tool, "_load", new_callable=AsyncMock, return_value=existing_plan), \
             patch.object(plan_tool, "_save", new_callable=AsyncMock) as mock_save:

            result = await plan_tool.execute(params, context)

        assert result["success"] is True
        assert result["plan"]["name"] == "调整后的贪吃蛇游戏"
        assert result["replaced_old"] is True
        mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_still_works(self, plan_tool, existing_plan):
        """update action 不受影响"""
        context = _make_context(is_follow_up=True)
        params = {
            "action": "update",
            "todo_id": "1",
            "status": "completed",
            "result": "完成",
        }

        with patch.object(plan_tool, "_load", new_callable=AsyncMock, return_value=existing_plan), \
             patch.object(plan_tool, "_save", new_callable=AsyncMock):

            result = await plan_tool.execute(params, context)

        assert result["success"] is True


class TestToolContextSignalFlow:
    """验证 is_follow_up 信号在 ToolContext 中的传递"""

    def test_extra_dict_persists_across_update_context(self):
        """update_context 不会清除 extra 中已有的信号"""
        from core.tool.executor import ToolExecutor

        executor = ToolExecutor(registry=MagicMock())

        # 第一次设置 is_follow_up
        executor.update_context(is_follow_up=True)
        assert executor.tool_context.get("is_follow_up") is True

        # 后续 update_context 只传 session_id，不应清除 is_follow_up
        executor.update_context(
            session_id="new-session",
            conversation_id="new-conv",
            user_id="new-user",
        )
        assert executor.tool_context.get("is_follow_up") is True

    def test_is_follow_up_default_false(self):
        """未设置 is_follow_up 时默认为 False"""
        ctx = create_tool_context(session_id="s1", conversation_id="c1")
        assert ctx.get("is_follow_up", False) is False

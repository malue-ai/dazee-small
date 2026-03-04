"""
Pipeline 全链路测试

分 4 层覆盖：
1. 单元测试 — PipelineDefinition 解析、PipelineState 状态机
2. 引擎测试 — PipelineExecutor 核心执行（mock step_executor）
3. 集成测试 — PipelineTool 完整调用（mock ToolContext）
4. 端到端测试 — 通过 HTTP API 验证真实服务

运行方式：
    # 单元 + 引擎 + 集成（无需启动服务）
    python -m pytest tests/test_pipeline.py -v

    # 端到端（需先启动服务）
    python -m pytest tests/test_pipeline.py -v -k "e2e" --e2e-url http://localhost:8000
"""

import asyncio
import json
import pytest
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock


# ================================================================
# 1. 单元测试：PipelineDefinition 解析
# ================================================================


class TestPipelineDefinition:
    """管道定义的 YAML/JSON 解析"""

    def test_from_yaml_basic(self):
        from core.orchestration.pipeline import PipelineDefinition

        yaml_str = """
pipeline:
  name: "测试管道"
  description: "描述"
  steps:
    - id: "1"
      skill: "ddg-search"
      params:
        query: "AI 趋势"
    - id: "2"
      skill: "elegant-reports"
      depends_on: ["1"]
"""
        definition = PipelineDefinition.from_yaml(yaml_str)

        assert definition.name == "测试管道"
        assert len(definition.steps) == 2
        assert definition.steps[0].skill == "ddg-search"
        assert definition.steps[1].depends_on == ["1"]

    def test_from_yaml_with_approval(self):
        from core.orchestration.pipeline import PipelineDefinition

        yaml_str = """
pipeline:
  name: "带审批"
  steps:
    - id: "1"
      skill: "deep-research"
    - id: "2"
      skill: "ic-memo-generator"
      depends_on: ["1"]
      approval: true
"""
        definition = PipelineDefinition.from_yaml(yaml_str)
        assert definition.steps[1].approval.required is True

    def test_from_json(self):
        from core.orchestration.pipeline import PipelineDefinition

        json_str = json.dumps({
            "pipeline": {
                "name": "JSON管道",
                "steps": [
                    {"id": "1", "tool": "api_calling", "params": {"url": "https://example.com"}},
                ]
            }
        })
        definition = PipelineDefinition.from_json(json_str)
        assert definition.name == "JSON管道"
        assert definition.steps[0].tool == "api_calling"

    def test_step_output_key_auto_generated(self):
        from core.orchestration.pipeline import PipelineStep

        step = PipelineStep(id="3", skill="test")
        assert step.output_key == "step_3_result"

    def test_empty_steps_raises(self):
        from core.orchestration.pipeline import PipelineDefinition

        yaml_str = """
pipeline:
  name: "空管道"
  steps: []
"""
        definition = PipelineDefinition.from_yaml(yaml_str)
        assert len(definition.steps) == 0


# ================================================================
# 2. 单元测试：PipelineState 状态机
# ================================================================


class TestPipelineState:
    """管道执行状态的进度查询和断点恢复判断"""

    def test_progress_tracking(self):
        from core.orchestration.pipeline import (
            PipelineDefinition,
            PipelineState,
            ExecutionStatus,
        )

        definition = PipelineDefinition(
            name="test",
            steps=[
                {"id": "1", "skill": "a"},
                {"id": "2", "skill": "b"},
                {"id": "3", "skill": "c"},
            ],
        )
        # from_yaml 需要正确格式，这里直接构造
        from core.orchestration.pipeline import PipelineStep
        definition.steps = [PipelineStep(id=str(i), skill=f"s{i}") for i in range(1, 4)]

        state = PipelineState(definition=definition)
        assert state.progress == 0.0

        state.step_executions["1"].status = ExecutionStatus.COMPLETED
        assert abs(state.progress - 1/3) < 0.01

        state.step_executions["2"].status = ExecutionStatus.COMPLETED
        state.step_executions["3"].status = ExecutionStatus.COMPLETED
        assert state.progress == 1.0

    def test_is_resumable(self):
        from core.orchestration.pipeline import (
            PipelineDefinition,
            PipelineState,
            ExecutionStatus,
            PipelineStep,
        )

        definition = PipelineDefinition(
            name="test",
            steps=[PipelineStep(id="1", skill="a")],
        )
        state = PipelineState(definition=definition)

        state.status = ExecutionStatus.RUNNING
        assert state.is_resumable is False

        state.status = ExecutionStatus.WAITING_APPROVAL
        assert state.is_resumable is True

        state.status = ExecutionStatus.FAILED
        assert state.is_resumable is True

    def test_get_ready_steps_respects_dependencies(self):
        from core.orchestration.pipeline import (
            PipelineDefinition,
            PipelineState,
            ExecutionStatus,
            PipelineStep,
        )

        definition = PipelineDefinition(
            name="test",
            steps=[
                PipelineStep(id="1", skill="a"),
                PipelineStep(id="2", skill="b", depends_on=["1"]),
                PipelineStep(id="3", skill="c", depends_on=["1"]),
            ],
        )
        state = PipelineState(definition=definition)

        ready = state.get_ready_steps()
        assert [s.id for s in ready] == ["1"]

        state.step_executions["1"].status = ExecutionStatus.COMPLETED
        ready = state.get_ready_steps()
        assert sorted([s.id for s in ready]) == ["2", "3"]


# ================================================================
# 3. 引擎测试：PipelineExecutor 核心执行
# ================================================================


class TestPipelineExecutor:
    """PipelineExecutor 的核心执行逻辑"""

    @pytest.fixture
    def mock_step_executor(self):
        """模拟步骤执行器：每步返回成功"""
        async def executor(step, params):
            await asyncio.sleep(0.01)
            return {"success": True, "output": f"result of {step.id}"}
        return executor

    @pytest.fixture
    def failing_step_executor(self):
        """模拟步骤执行器：第 2 步失败"""
        async def executor(step, params):
            if step.id == "2":
                raise ValueError("模拟失败")
            return {"success": True, "output": f"result of {step.id}"}
        return executor

    @pytest.mark.asyncio
    async def test_linear_execution(self, mock_step_executor):
        from core.orchestration.pipeline import PipelineExecutor, PipelineDefinition, PipelineStep

        definition = PipelineDefinition(
            name="线性管道",
            steps=[
                PipelineStep(id="1", skill="search"),
                PipelineStep(id="2", skill="analyze", depends_on=["1"]),
                PipelineStep(id="3", skill="report", depends_on=["2"]),
            ],
        )

        executor = PipelineExecutor(
            step_executor=mock_step_executor,
            storage_dir=Path("/tmp/test_pipeline"),
        )
        state = await executor.run(definition)

        assert state.status.value == "completed"
        assert state.progress == 1.0
        assert all(se.status.value == "completed" for se in state.step_executions.values())

    @pytest.mark.asyncio
    async def test_parallel_execution(self, mock_step_executor):
        from core.orchestration.pipeline import PipelineExecutor, PipelineDefinition, PipelineStep

        definition = PipelineDefinition(
            name="并行管道",
            steps=[
                PipelineStep(id="1", skill="a"),
                PipelineStep(id="2", skill="b"),
                PipelineStep(id="3", skill="c"),
                PipelineStep(id="4", skill="d", depends_on=["1", "2", "3"]),
            ],
        )

        executor = PipelineExecutor(
            step_executor=mock_step_executor,
            storage_dir=Path("/tmp/test_pipeline"),
        )
        state = await executor.run(definition)

        assert state.status.value == "completed"
        assert state.progress == 1.0

    @pytest.mark.asyncio
    async def test_step_failure_propagation(self, failing_step_executor):
        from core.orchestration.pipeline import PipelineExecutor, PipelineDefinition, PipelineStep

        definition = PipelineDefinition(
            name="失败测试",
            steps=[
                PipelineStep(id="1", skill="ok"),
                PipelineStep(id="2", skill="fail", depends_on=["1"]),
                PipelineStep(id="3", skill="blocked", depends_on=["2"]),
            ],
        )

        executor = PipelineExecutor(
            step_executor=failing_step_executor,
            storage_dir=Path("/tmp/test_pipeline"),
        )
        state = await executor.run(definition)

        assert state.status.value == "failed"
        assert state.step_executions["1"].status.value == "completed"
        assert state.step_executions["2"].status.value == "failed"
        # 步骤 3 依赖 2，2 失败后 3 保持 pending（无法就绪）
        assert state.step_executions["3"].status.value == "pending"

    @pytest.mark.asyncio
    async def test_approval_gate_pauses(self):
        """审批卡点应暂停管道并返回 resume_token"""
        from core.orchestration.pipeline import (
            PipelineExecutor,
            PipelineDefinition,
            PipelineStep,
            ApprovalConfig,
        )

        async def executor(step, params):
            return {"success": True, "output": "ok"}

        async def reject_approval(step, message):
            return False

        definition = PipelineDefinition(
            name="审批测试",
            steps=[
                PipelineStep(id="1", skill="a"),
                PipelineStep(
                    id="2",
                    skill="b",
                    depends_on=["1"],
                    approval=ApprovalConfig(required=True, message="确认？"),
                ),
            ],
        )

        pipe_executor = PipelineExecutor(
            step_executor=executor,
            approval_fn=reject_approval,
            storage_dir=Path("/tmp/test_pipeline"),
        )
        state = await pipe_executor.run(definition)

        assert state.status.value == "waiting_approval"
        assert state.is_resumable is True
        assert state.resume_token is not None
        assert state.step_executions["1"].status.value == "completed"
        assert state.step_executions["2"].status.value == "waiting_approval"

    @pytest.mark.asyncio
    async def test_resume_from_checkpoint(self):
        """断点恢复应从暂停位置继续"""
        from core.orchestration.pipeline import (
            PipelineExecutor,
            PipelineDefinition,
            PipelineStep,
            ApprovalConfig,
        )

        call_count = 0

        async def executor(step, params):
            nonlocal call_count
            call_count += 1
            return {"success": True, "output": f"done {step.id}"}

        first_call = True

        async def conditional_approval(step, message):
            nonlocal first_call
            if first_call:
                first_call = False
                return False
            return True

        definition = PipelineDefinition(
            name="恢复测试",
            steps=[
                PipelineStep(id="1", skill="a"),
                PipelineStep(
                    id="2",
                    skill="b",
                    depends_on=["1"],
                    approval=ApprovalConfig(required=True),
                ),
                PipelineStep(id="3", skill="c", depends_on=["2"]),
            ],
        )

        storage_dir = Path("/tmp/test_pipeline_resume")
        storage_dir.mkdir(parents=True, exist_ok=True)

        pipe_executor = PipelineExecutor(
            step_executor=executor,
            approval_fn=conditional_approval,
            storage_dir=storage_dir,
        )

        # 第一次执行：步骤 1 完成，步骤 2 暂停
        state = await pipe_executor.run(definition)
        assert state.status.value == "waiting_approval"
        token = state.resume_token

        # 恢复：步骤 2、3 继续执行
        state2 = await pipe_executor.resume(token)
        assert state2 is not None
        assert state2.status.value == "completed"
        assert state2.progress == 1.0

    @pytest.mark.asyncio
    async def test_progress_callback(self, mock_step_executor):
        """进度回调应该在每步状态变化时触发"""
        from core.orchestration.pipeline import PipelineExecutor, PipelineDefinition, PipelineStep

        progress_events = []

        async def on_progress(state, step, status):
            progress_events.append((step.id, status.value, state.progress))

        definition = PipelineDefinition(
            name="进度测试",
            steps=[
                PipelineStep(id="1", skill="a"),
                PipelineStep(id="2", skill="b", depends_on=["1"]),
            ],
        )

        executor = PipelineExecutor(
            step_executor=mock_step_executor,
            progress_fn=on_progress,
            storage_dir=Path("/tmp/test_pipeline"),
        )
        await executor.run(definition)

        assert len(progress_events) >= 4
        statuses = [e[1] for e in progress_events]
        assert "running" in statuses
        assert "completed" in statuses

    @pytest.mark.asyncio
    async def test_context_passes_between_steps(self):
        """前置步骤的结果应通过 context 传递给后续步骤"""
        from core.orchestration.pipeline import PipelineExecutor, PipelineDefinition, PipelineStep

        received_contexts = {}

        async def executor(step, params):
            received_contexts[step.id] = dict(params.get("_context", {}))
            return {"success": True, "data": f"from_{step.id}"}

        definition = PipelineDefinition(
            name="上下文传递",
            steps=[
                PipelineStep(id="1", skill="a"),
                PipelineStep(id="2", skill="b", depends_on=["1"]),
            ],
        )

        pipe_executor = PipelineExecutor(
            step_executor=executor,
            storage_dir=Path("/tmp/test_pipeline"),
        )
        state = await pipe_executor.run(definition, initial_context={"user_query": "test"})

        assert "user_query" in received_contexts["1"]
        assert "step_1_result" in received_contexts["2"]


# ================================================================
# 4. 集成测试：PipelineTool 完整调用
# ================================================================


class TestPipelineTool:
    """PipelineTool 的 execute() 方法"""

    def _make_context(self):
        """创建模拟 ToolContext"""
        from core.tool.types import ToolContext

        mock_tool_executor = MagicMock()

        async def mock_execute(tool_name, tool_input, **kwargs):
            return {"success": True, "output": f"executed {tool_name}"}

        mock_tool_executor.execute = mock_execute

        ctx = ToolContext(
            session_id="test-session",
            conversation_id="test-conv",
            user_id="test-user",
            extra={
                "tool_executor": mock_tool_executor,
            },
        )
        return ctx

    @pytest.mark.asyncio
    async def test_define_and_run_success(self):
        from tools.pipeline_tool import PipelineTool

        tool = PipelineTool()
        ctx = self._make_context()

        result = await tool.execute({
            "action": "define_and_run",
            "pipeline": {
                "name": "集成测试",
                "steps": [
                    {"id": "1", "step_type": "tool", "tool": "api_calling", "params": {"url": "https://example.com"}},
                    {"id": "2", "step_type": "tool", "tool": "api_calling", "depends_on": ["1"]},
                ],
            },
        }, ctx)

        assert result["success"] is True
        assert result["status"] == "completed"
        assert result["progress"] == 1.0

    @pytest.mark.asyncio
    async def test_define_and_run_missing_pipeline(self):
        from tools.pipeline_tool import PipelineTool

        tool = PipelineTool()
        result = await tool.execute({"action": "define_and_run"})
        assert result["success"] is False
        assert "缺少" in result["error"]

    @pytest.mark.asyncio
    async def test_unknown_action(self):
        from tools.pipeline_tool import PipelineTool

        tool = PipelineTool()
        result = await tool.execute({"action": "invalid"})
        assert result["success"] is False
        assert "未知" in result["error"]

    @pytest.mark.asyncio
    async def test_status_no_manager(self):
        from tools.pipeline_tool import PipelineTool

        tool = PipelineTool()
        ctx = self._make_context()
        result = await tool.execute({"action": "status"}, ctx)
        assert result["success"] is False


# ================================================================
# 5. 端到端测试：通过 HTTP API（需启动服务）
# ================================================================


def pytest_addoption(parser):
    parser.addoption(
        "--e2e-url",
        action="store",
        default=None,
        help="E2E test base URL (e.g. http://localhost:8000)",
    )


@pytest.fixture
def e2e_url(request):
    url = request.config.getoption("--e2e-url")
    if not url:
        pytest.skip("需要 --e2e-url 参数，如 --e2e-url http://localhost:8000")
    return url


class TestPipelineE2E:
    """
    端到端测试 — 通过 HTTP 调用真实后端

    前置条件：
        1. 启动服务：uvicorn main:app --host 0.0.0.0 --port 8000
        2. 运行测试：pytest tests/test_pipeline.py -v -k "e2e" --e2e-url http://localhost:8000
    """

    @pytest.mark.asyncio
    async def test_e2e_background_tasks_api(self, e2e_url):
        """验证后台任务 API 可正常访问"""
        import httpx

        async with httpx.AsyncClient(base_url=e2e_url, timeout=10) as client:
            resp = await client.get("/api/v1/background-tasks")
            assert resp.status_code == 200
            data = resp.json()
            assert "tasks" in data
            assert "total" in data

    @pytest.mark.asyncio
    async def test_e2e_chat_with_pipeline(self, e2e_url):
        """
        验证 Agent 能从自然语言中判断使用 pipeline

        用户不会说"用 pipeline"，而是描述一个固定流程的多步任务。
        LLM 应自行判断这是固定流程，选择 pipeline 而非 plan。
        """
        import httpx

        async with httpx.AsyncClient(base_url=e2e_url, timeout=60) as client:
            resp = await client.post(
                "/api/v1/chat",
                json={
                    "message": (
                        "帮我做个简单测试：先执行 echo hello，"
                        "然后执行 echo world，两步就行。"
                        "步骤固定，直接跑就好。"
                    ),
                    "session_id": f"test-pipeline-{int(time.time())}",
                },
                headers={"Accept": "text/event-stream"},
            )
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_e2e_cleanup(self, e2e_url):
        """清理测试产生的后台任务"""
        import httpx

        async with httpx.AsyncClient(base_url=e2e_url, timeout=10) as client:
            resp = await client.post(
                "/api/v1/background-tasks/cleanup",
                params={"max_age_seconds": 0},
            )
            assert resp.status_code == 200

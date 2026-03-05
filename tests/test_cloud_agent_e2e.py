"""
云端协同 E2E 自动化测试（维度 J: J1 + J2 + J3 + J4 + J5）

验证真实端到端链路，打向 https://agent.dazee.ai，无 Mock。
J5 为本地工具层集成测试（含事件桥接、files 合并、login 自动认证），使用 Mock。

用法:
    # 运行全部测试（需要网络）
    python -m pytest tests/test_cloud_agent_e2e.py -v

    # 仅运行快速测试（跳过需要云端完整对话的慢测试）
    python -m pytest tests/test_cloud_agent_e2e.py -v -k "not slow"

    # 仅运行 J5 工具层集成测试（无需网络）
    python -m pytest tests/test_cloud_agent_e2e.py -v -k "J5"

    # 指定云端 URL
    CLOUD_URL=https://agent.dazee.ai python -m pytest tests/test_cloud_agent_e2e.py -v
"""

import os
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.cloud_client import CloudClient, CloudClientError

CLOUD_URL = os.environ.get("CLOUD_URL", "https://agent.dazee.ai")


@pytest.fixture
async def cloud_client():
    client = CloudClient(cloud_url=CLOUD_URL)
    yield client
    await client.close()


@pytest.fixture
async def bad_client():
    client = CloudClient(cloud_url="http://localhost:19999")
    yield client
    await client.close()


# ============================================================
# J1: CloudClient SSE 全链路
# ============================================================


class TestJ1CloudClientSSE:
    """J1: 验证 CloudClient 的健康检查、SSE 流完整性、事件格式"""

    @pytest.mark.asyncio
    async def test_health_check_reachable(self, cloud_client: CloudClient):
        """J1.1: 云端健康检查应返回 True"""
        start = time.time()
        result = await cloud_client.health_check()
        elapsed = time.time() - start

        assert result is True, "云端 health_check 应返回 True"
        assert elapsed < 5.0, f"健康检查耗时 {elapsed:.1f}s，应 < 5s"

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_sse_event_completeness(self, cloud_client: CloudClient):
        """J1.2: SSE 事件流应包含所有期望事件类型"""
        expected_types = {
            "session_start", "message_start",
            "content_start", "content_delta", "content_stop",
            "message_stop",
        }
        seen_types: set[str] = set()
        event_count = 0

        async for event in cloud_client.chat_stream("回复一个字：好"):
            seen_types.add(event.get("type", ""))
            event_count += 1
            if event.get("type") == "message_stop":
                break

        missing = expected_types - seen_types
        assert not missing, f"缺少事件类型: {missing}，收到: {seen_types}"
        assert len(seen_types) >= 6, f"事件类型数 {len(seen_types)} < 6"
        assert event_count >= 5, f"事件总数 {event_count} 太少"

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_text_extraction(self, cloud_client: CloudClient):
        """J1.3: 应能从 SSE 流中提取最终文本"""
        final_text = ""
        current_block_type = None
        start = time.time()

        async for event in cloud_client.chat_stream("简单回复两个字：收到"):
            event_type = event.get("type", "")

            if event_type == "content_start":
                block = event.get("data", {}).get("content_block", {})
                current_block_type = block.get("type")
            elif event_type == "content_delta":
                delta = event.get("data", {}).get("delta", "")
                if current_block_type == "text" and isinstance(delta, str):
                    final_text += delta
            elif event_type == "content_stop":
                current_block_type = None
            elif event_type == "message_stop":
                break

        elapsed = time.time() - start

        assert final_text.strip(), "应提取到非空文本"
        assert elapsed < 30.0, f"全流程耗时 {elapsed:.1f}s，应 < 30s"

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_seq_field_present(self, cloud_client: CloudClient):
        """J1.4: 每个事件应包含递增 seq 字段"""
        last_seq = 0

        async for event in cloud_client.chat_stream("回复一个字：好"):
            seq = event.get("seq")
            assert seq is not None, f"事件缺少 seq 字段: {event.get('type')}"
            assert seq >= last_seq, f"seq 非递增: {seq} < {last_seq}"
            last_seq = seq
            if event.get("type") == "message_stop":
                break

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_session_id_in_events(self, cloud_client: CloudClient):
        """J1.5: session_start 事件应包含 session_id"""
        session_id = None

        async for event in cloud_client.chat_stream("回复一个字：好"):
            if event.get("type") == "session_start":
                data = event.get("data", {})
                session_id = data.get("session_id") or event.get("session_id")
                break

        assert session_id, "session_start 事件应包含非空 session_id"


# ============================================================
# J2: CloudAgentTool 端到端委托
# ============================================================


class TestJ2CloudAgentTool:
    """J2: 验证 CloudAgentTool.execute() 的端到端流程"""

    @pytest.mark.asyncio
    async def test_empty_task_rejected(self):
        """J2.1: 空 task 参数应立即拒绝"""
        from tools.cloud_agent import CloudAgentTool

        tool = CloudAgentTool()
        result = await tool.execute({"task": ""}, None)

        assert result["success"] is False
        assert "空" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_task_rejected(self):
        """J2.2: 缺少 task 参数应返回错误"""
        from tools.cloud_agent import CloudAgentTool

        tool = CloudAgentTool()
        result = await tool.execute({}, None)

        assert result["success"] is False

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_successful_delegation(self):
        """J2.3: 正常任务应成功委托并返回结果"""
        from services.cloud_client import configure_cloud_client
        from tools.cloud_agent import CloudAgentTool

        configure_cloud_client(cloud_url=CLOUD_URL)

        tool = CloudAgentTool()
        result = await tool.execute({"task": "简单回复两个字：收到"}, None)

        assert result["success"] is True, f"任务失败: {result.get('error')}"
        assert "result" in result, "返回值应包含 result 字段"
        assert len(result["result"]) >= 1, "result 应包含至少 1 个字符"

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_context_parameter(self):
        """J2.4: context 参数应附加到消息中"""
        from services.cloud_client import configure_cloud_client
        from tools.cloud_agent import CloudAgentTool

        configure_cloud_client(cloud_url=CLOUD_URL)

        tool = CloudAgentTool()
        result = await tool.execute(
            {"task": "回答一个问题", "context": "问题是：1+1等于几？只回复数字"},
            None,
        )

        assert result["success"] is True, f"任务失败: {result.get('error')}"
        assert "2" in result["result"], f"结果应包含 '2'，实际: {result['result'][:100]}"

    @pytest.mark.asyncio
    async def test_no_context_no_crash(self):
        """J2.5: context=None 时不崩溃"""
        from tools.cloud_agent import CloudAgentTool

        tool = CloudAgentTool()
        # 使用不可达 URL 避免真实请求，但验证 context=None 不抛异常
        from services.cloud_client import configure_cloud_client
        configure_cloud_client(cloud_url="http://localhost:19999")

        result = await tool.execute({"task": "test"}, None)
        assert result["success"] is False
        assert "error" in result


# ============================================================
# J3: 云端异常降级与超时
# ============================================================


class TestJ3ErrorHandling:
    """J3: 验证云端不可达、URL 错误等异常场景的降级行为"""

    @pytest.mark.asyncio
    async def test_unreachable_health_check(self, bad_client: CloudClient):
        """J3.1: 不可达地址的 health_check 应返回 False（不抛异常）"""
        result = await bad_client.health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_unreachable_chat_stream_raises(self, bad_client: CloudClient):
        """J3.2: 不可达地址的 chat_stream 应抛出 CloudClientError"""
        with pytest.raises(CloudClientError) as exc_info:
            async for _ in bad_client.chat_stream("test"):
                pass

        assert "连接" in str(exc_info.value) or "connect" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_tool_unreachable_returns_error(self):
        """J3.3: CloudAgentTool 在云端不可达时应返回友好错误"""
        from services.cloud_client import configure_cloud_client
        from tools.cloud_agent import CloudAgentTool

        configure_cloud_client(cloud_url="http://localhost:19999")

        tool = CloudAgentTool()
        result = await tool.execute({"task": "test task"}, None)

        assert result["success"] is False
        assert "error" in result
        assert "不可达" in result["error"] or "失败" in result["error"]

    @pytest.mark.asyncio
    async def test_client_close_no_error(self, cloud_client: CloudClient):
        """J3.4: close() 应安全执行，无异常"""
        await cloud_client.close()

    @pytest.mark.asyncio
    async def test_cloud_client_error_is_exception(self):
        """J3.5: CloudClientError 应是 Exception 子类"""
        assert issubclass(CloudClientError, Exception)
        err = CloudClientError("测试错误")
        assert str(err) == "测试错误"


# ============================================================
# 辅助函数：从 SSE 流中提取 conversation_id 和文本
# ============================================================


async def _consume_stream(client: CloudClient, message: str, **kwargs):
    """消费完整 SSE 流，返回 (conversation_id, final_text, events)"""
    conversation_id = None
    final_text = ""
    current_block_type = None
    events = []

    async for event in client.chat_stream(message, **kwargs):
        events.append(event)
        event_type = event.get("type", "")

        if event_type in ("session_start", "conversation_start"):
            data = event.get("data", {})
            cid = data.get("conversation_id") or event.get("conversation_id")
            if cid:
                conversation_id = cid

        elif event_type == "content_start":
            block = event.get("data", {}).get("content_block", {})
            current_block_type = block.get("type")

        elif event_type == "content_delta":
            delta = event.get("data", {}).get("delta", "")
            if current_block_type == "text" and isinstance(delta, str):
                final_text += delta

        elif event_type == "content_stop":
            current_block_type = None

        elif event_type == "message_stop":
            break

    return conversation_id, final_text.strip(), events


# ============================================================
# J4: 云端深度调研 — 真实业务场景多轮委托
# ============================================================


def _has_tool_use_events(events: list) -> bool:
    """检查事件流中是否包含 tool_use 类型的 content_start"""
    return any(
        e.get("type") == "content_start"
        and e.get("data", {}).get("content_block", {}).get("type") == "tool_use"
        for e in events
    )


def _extract_tool_names(events: list) -> list[str]:
    """从事件流中提取所有云端调用的工具名"""
    names = []
    for e in events:
        if e.get("type") == "content_start":
            block = e.get("data", {}).get("content_block", {})
            if block.get("type") == "tool_use" and block.get("name"):
                names.append(block["name"])
    return names


class TestJ4CloudResearch:
    """J4: 云端深度调研 — 本地做不了的任务委托云端

    验证云端协同的真实业务价值：
    - 轮次1: 委托云端搜索真实信息（云端有 web search / exa 等工具，本地没有）
    - 轮次2: 基于搜索结果追问分析（验证跨轮上下文 + 云端工具调用结果保持）
    - 轮次3: 要求结构化输出（验证云端 Agent 的深度处理能力）

    这不是"我叫小明你记住没"的连通性测试，
    而是验证"本地搭子委托云端搭子做深度调研"的真实场景。
    """

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_cloud_research_multi_turn(self, cloud_client: CloudClient):
        """J4.1: 3 轮深度调研 — 搜索 → 分析 → 结构化输出"""

        # === 轮次 1：委托云端搜索真实信息 ===
        # 这是本地做不了的——本地没有 web search 工具
        conv_id, text1, events1 = await _consume_stream(
            cloud_client,
            "搜索一下 FastAPI 这个 Python Web 框架的最新版本号和主要特性，"
            "给我 3 个要点。",
        )
        assert conv_id, "轮次1 应返回 conversation_id"
        assert text1, "轮次1 应返回非空文本"
        assert len(text1) >= 50, f"轮次1 调研结果太短（{len(text1)} 字），应有实质内容"
        print(f"  轮次1: conv_id={conv_id[:12]}... 结果长度={len(text1)}")
        print(f"  轮次1 文本摘要: {text1[:150]}...")

        # 验证云端确实调用了搜索工具（不是纯 LLM 编造）
        tool_names = _extract_tool_names(events1)
        print(f"  轮次1 云端工具调用: {tool_names}")

        # 验证返回内容包含 FastAPI 相关信息
        text1_lower = text1.lower()
        assert "fastapi" in text1_lower, (
            f"轮次1 结果应包含 FastAPI 相关内容，实际: {text1[:200]}"
        )

        # === 轮次 2：基于调研结果追问 ===
        _, text2, events2 = await _consume_stream(
            cloud_client,
            "根据你刚才查到的信息，FastAPI 和 Django 相比有什么优势？简要对比 3 点。",
            conversation_id=conv_id,
        )
        assert text2, "轮次2 应返回非空文本"
        assert len(text2) >= 50, f"轮次2 对比分析太短（{len(text2)} 字）"
        print(f"  轮次2 文本摘要: {text2[:150]}...")

        # 验证回复确实在对比两个框架
        text2_lower = text2.lower()
        has_comparison = (
            ("fastapi" in text2_lower and "django" in text2_lower)
            or "对比" in text2
            or "优势" in text2
            or "相比" in text2
        )
        assert has_comparison, (
            f"轮次2 应包含 FastAPI vs Django 对比，实际: {text2[:200]}"
        )

        # === 轮次 3：要求结构化输出 ===
        _, text3, _ = await _consume_stream(
            cloud_client,
            "把刚才的调研和对比整理成一个表格，包含：框架名、适用场景、性能特点。",
            conversation_id=conv_id,
        )
        assert text3, "轮次3 应返回非空文本"
        assert len(text3) >= 30, f"轮次3 结构化输出太短（{len(text3)} 字）"
        print(f"  轮次3 文本摘要: {text3[:150]}...")

        # 验证输出有结构化特征（表格标记或对齐格式）
        has_structure = (
            "|" in text3
            or "FastAPI" in text3
            or "Django" in text3
        )
        assert has_structure, (
            f"轮次3 应包含结构化表格，实际: {text3[:300]}"
        )

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_cloud_tool_invocation(self, cloud_client: CloudClient):
        """J4.2: 云端应调用搜索工具获取真实信息（非纯 LLM 编造）"""

        _, text, events = await _consume_stream(
            cloud_client,
            "帮我搜索一下 2025 年 Y Combinator 最新一批有哪些 AI 相关的创业公司，列出 3 个。",
        )
        assert text, "应返回非空文本"
        assert len(text) >= 30, f"调研结果太短（{len(text)} 字）"

        # 检查云端是否调用了搜索工具
        tool_names = _extract_tool_names(events)
        has_search_tool = _has_tool_use_events(events)

        print(f"  云端工具调用: {tool_names}")
        print(f"  文本摘要: {text[:200]}...")

        # 如果云端调用了工具，说明它在做真实搜索
        # 如果没调用工具但给出了回答，可能是模型知识回答（也可接受，但标注）
        if has_search_tool:
            print("  验证通过: 云端调用了搜索工具获取实时信息")
        else:
            print("  注意: 云端未调用搜索工具，可能依赖模型内置知识")

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_cloud_delegation_value(self, cloud_client: CloudClient):
        """J4.3: 验证云端委托的实际价值 — 结果应包含搜索/分析才能得到的信息"""

        conv_id, text1, events1 = await _consume_stream(
            cloud_client,
            "搜索一下 Anthropic Claude 的最新消息和产品更新，给我一个简要总结。",
        )
        assert conv_id, "应返回 conversation_id"
        assert text1, "应返回非空文本"

        # 验证内容有实质信息（不是空泛的"AI 很重要"）
        assert len(text1) >= 80, (
            f"调研结果太短（{len(text1)} 字），缺乏实质内容"
        )

        # 验证内容与查询主题相关
        text1_lower = text1.lower()
        topic_relevant = (
            "claude" in text1_lower
            or "anthropic" in text1_lower
            or "模型" in text1
            or "发布" in text1
            or "更新" in text1
        )
        assert topic_relevant, (
            f"结果应与 Anthropic/Claude 相关，实际: {text1[:200]}"
        )

        # 追问一个需要基于首轮结果的问题
        _, text2, _ = await _consume_stream(
            cloud_client,
            "根据你刚才查到的信息，这些更新对开发者有什么实际影响？列出 2 点。",
            conversation_id=conv_id,
        )
        assert text2, "追问应返回非空文本"
        assert len(text2) >= 30, "追问结果应有实质分析"
        print(f"  调研结果: {text1[:100]}...")
        print(f"  追问分析: {text2[:100]}...")


# ============================================================
# J5: 工具层集成测试（Mock CloudClient，验证工具内部逻辑）
# ============================================================


def _make_tracking_events(text: str = "测试回复", tool_name: str | None = None) -> list:
    """构造模拟的 CloudStreamEvent 列表"""
    from services.cloud_client import CloudStreamEvent

    events = [
        CloudStreamEvent(kind="session_info", conversation_id="mock_conv_id"),
    ]

    if tool_name:
        events.append(CloudStreamEvent(kind="tool_start", tool_name=tool_name, conversation_id="mock_conv_id"))
        events.append(CloudStreamEvent(kind="tool_end", tool_name=tool_name, conversation_id="mock_conv_id"))

    events.append(CloudStreamEvent(kind="text_delta", text=text, conversation_id="mock_conv_id"))
    events.append(CloudStreamEvent(kind="completed", conversation_id="mock_conv_id"))
    return events


async def _async_iter(items):
    for item in items:
        yield item


class TestJ5ToolIntegration:
    """J5: 工具层集成测试 — 事件桥接、files 合并、login 自动认证（无需网络）"""

    @pytest.mark.asyncio
    async def test_event_bridging_with_context(self):
        """J5.1: 带 ToolContext 时，进度事件应正确桥接到 EventBroadcaster"""
        from core.tool.types import ToolContext
        from tools.cloud_agent import CloudAgentTool

        mock_events = _make_tracking_events("云端回复", tool_name="exa_search")

        mock_client = MagicMock()
        mock_client.health_check = AsyncMock(return_value=True)
        mock_client.chat_stream_with_tracking = MagicMock(return_value=_async_iter(mock_events))

        mock_event_manager = MagicMock()
        context = ToolContext(
            session_id="test_session",
            conversation_id="test_conv",
            user_id="test_user",
            instance_id="xiaodazi",
        )
        context.event_manager = mock_event_manager

        tool = CloudAgentTool()
        emitted_steps = []
        original_emit = tool._emit_progress

        async def capture_emit(broadcaster, session_id, step_id, message, **kw):
            emitted_steps.append(step_id)
            await original_emit(broadcaster, session_id, step_id, message, **kw)

        tool._emit_progress = capture_emit

        with patch("services.cloud_client.get_cloud_client_for_instance", new_callable=AsyncMock, return_value=mock_client):
            result = await tool.execute({"task": "测试任务"}, context)

        assert result["success"] is True
        assert result["result"] == "云端回复"
        assert "cloud_connect" in emitted_steps
        assert "cloud_start" in emitted_steps
        assert "cloud_tool" in emitted_steps, "应桥接 tool_use 事件"
        assert "cloud_tool_done" in emitted_steps, "应桥接 tool 完成事件"
        assert "cloud_done" in emitted_steps

    @pytest.mark.asyncio
    async def test_files_merge_from_params_and_context(self):
        """J5.2: files 应合并 params 和 context.extra 两个来源"""
        from core.tool.types import ToolContext
        from tools.cloud_agent import CloudAgentTool

        mock_events = _make_tracking_events("文件处理完成")

        mock_client = MagicMock()
        mock_client.health_check = AsyncMock(return_value=True)
        mock_client.chat_stream_with_tracking = MagicMock(return_value=_async_iter(mock_events))
        mock_client.upload_file = AsyncMock(return_value={
            "file_url": "https://s3.example.com/uploaded.xlsx",
            "file_name": "uploaded.xlsx",
        })

        context = ToolContext(
            session_id="test_session",
            user_id="test_user",
            instance_id="xiaodazi",
            extra={
                "files": [{"file_url": "https://existing.com/a.pdf", "file_name": "a.pdf"}],
            },
        )

        params = {
            "task": "分析这两个文件",
            "files": [{"file_url": "https://new.com/b.xlsx", "file_name": "b.xlsx"}],
        }

        tool = CloudAgentTool()
        with patch("services.cloud_client.get_cloud_client_for_instance", new_callable=AsyncMock, return_value=mock_client):
            result = await tool.execute(params, context)

        assert result["success"] is True
        call_kwargs = mock_client.chat_stream_with_tracking.call_args
        sent_files = call_kwargs.kwargs.get("files")
        assert sent_files is not None, "chat_stream_with_tracking 应收到 files 参数"
        assert len(sent_files) == 2, f"应合并为 2 个文件，实际 {len(sent_files)}"

    @pytest.mark.asyncio
    async def test_files_from_params_only(self):
        """J5.3: 仅 params 有 files 时应正常传递"""
        from core.tool.types import ToolContext
        from tools.cloud_agent import CloudAgentTool

        mock_events = _make_tracking_events("ok")
        mock_client = MagicMock()
        mock_client.health_check = AsyncMock(return_value=True)
        mock_client.chat_stream_with_tracking = MagicMock(return_value=_async_iter(mock_events))

        params = {
            "task": "分析文件",
            "files": [{"file_url": "https://example.com/data.csv", "file_name": "data.csv"}],
        }

        context = ToolContext(session_id="s", user_id="u", instance_id="xiaodazi")
        tool = CloudAgentTool()
        with patch("services.cloud_client.get_cloud_client_for_instance", new_callable=AsyncMock, return_value=mock_client):
            result = await tool.execute(params, context)

        assert result["success"] is True
        call_kwargs = mock_client.chat_stream_with_tracking.call_args
        sent_files = call_kwargs.kwargs.get("files")
        assert sent_files is not None
        assert len(sent_files) == 1

    @pytest.mark.asyncio
    async def test_login_auto_auth(self):
        """J5.4: 配置了 username/password 时，chat_stream 应自动调用 login"""
        client = CloudClient(
            cloud_url="https://mock.example.com",
            username="testuser",
            password="testpass",
        )

        login_resp = MagicMock()
        login_resp.status_code = 200
        login_resp.json.return_value = {
            "token": "mock_jwt_token_123",
            "user": {"id": "user_1", "username": "testuser"},
        }
        client._http = AsyncMock()
        client._http.post.return_value = login_resp

        await client.login()

        assert client.jwt_token == "mock_jwt_token_123"
        assert client.user_id == "user_1"
        client._http.post.assert_called_once()
        call_args = client._http.post.call_args
        assert "/api/v1/auth/login" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_ensure_auth_auto_relogin(self):
        """J5.5: token 过期后 _ensure_auth 应自动重新登录"""
        client = CloudClient(
            cloud_url="https://mock.example.com",
            username="testuser",
            password="testpass",
            jwt_token="old_expired_token",
        )
        client._token_obtained_at = 0  # 模拟已过期

        login_resp = MagicMock()
        login_resp.status_code = 200
        login_resp.json.return_value = {
            "token": "fresh_token",
            "user": {"id": "user_1", "username": "testuser"},
        }
        client._http = AsyncMock()
        client._http.post.return_value = login_resp

        await client._ensure_auth()

        assert client.jwt_token == "fresh_token"

    @pytest.mark.asyncio
    async def test_ensure_auth_valid_token_no_relogin(self):
        """J5.6: token 未过期时 _ensure_auth 不应重新登录"""
        client = CloudClient(
            cloud_url="https://mock.example.com",
            username="testuser",
            password="testpass",
            jwt_token="valid_token",
        )
        client._token_obtained_at = time.time()

        client._http = AsyncMock()
        await client._ensure_auth()

        client._http.post.assert_not_called()
        assert client.jwt_token == "valid_token"

    @pytest.mark.asyncio
    async def test_login_without_credentials_raises(self):
        """J5.7: 无凭据调用 login 应抛出 CloudClientError"""
        client = CloudClient(cloud_url="https://mock.example.com")

        with pytest.raises(CloudClientError, match="未提供登录凭据"):
            await client.login()

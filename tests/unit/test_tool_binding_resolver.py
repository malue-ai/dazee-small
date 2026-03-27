"""Unit tests for model-bound tool binding resolver."""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List, Optional, Union

from core.llm.base import BaseLLMService, LLMProvider, LLMResponse, Message, ToolType
from core.llm.router import ModelRouter, RouteTarget
from core.llm.tool_binding_resolver import resolve_tools_for_target


class _DummyService(BaseLLMService):
    async def create_message_async(
        self,
        messages: List[Message],
        system: Optional[str] = None,
        tools: Optional[List[Union[ToolType, str, Dict[str, Any]]]] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        return LLMResponse(content="ok")

    async def create_message_stream(
        self,
        messages: List[Message],
        system: Optional[str] = None,
        tools: Optional[List[Union[ToolType, str, Dict[str, Any]]]] = None,
        **kwargs: Any,
    ) -> AsyncIterator[LLMResponse]:
        if False:
            yield LLMResponse(content="", is_stream=True)

    def count_tokens(self, text: str) -> int:
        return len(text)


def test_resolve_tools_maps_web_search_for_supported_claude_model() -> None:
    tools: List[Union[ToolType, str, Dict[str, Any]]] = [
        {
            "name": "web_search",
            "description": "search web",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "plan",
            "description": "plan task",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
    ]

    resolved = resolve_tools_for_target(
        tools=tools,
        provider=LLMProvider.CLAUDE,
        model="claude-sonnet-4-6",
    )

    assert resolved is not None
    assert isinstance(resolved[0], dict)
    assert resolved[0]["type"] == "web_search_20260209"
    assert resolved[0]["name"] == "web_search"
    assert resolved[1] == tools[1]


def test_resolve_tools_keeps_logical_tool_for_unsupported_claude_model() -> None:
    tools: List[Union[ToolType, str, Dict[str, Any]]] = [
        {
            "name": "web_search",
            "description": "search web",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        }
    ]

    resolved = resolve_tools_for_target(
        tools=tools,
        provider=LLMProvider.CLAUDE,
        model="claude-3-5-sonnet-20241022",
    )

    assert resolved is not None
    assert isinstance(resolved[0], dict)
    assert resolved[0]["name"] == "web_search"
    assert "type" not in resolved[0]


def test_resolve_tools_maps_with_model_prefix_for_newer_claude_patch() -> None:
    tools: List[Union[ToolType, str, Dict[str, Any]]] = [
        {
            "name": "web_search",
            "description": "search web",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        }
    ]

    resolved = resolve_tools_for_target(
        tools=tools,
        provider=LLMProvider.CLAUDE,
        model="claude-sonnet-4-7",
    )

    assert resolved is not None
    assert isinstance(resolved[0], dict)
    assert resolved[0]["type"] == "web_search_20260209"
    assert resolved[0]["name"] == "web_search"


def test_resolve_tools_drops_claude_server_tool_on_non_claude_provider() -> None:
    tools: List[Union[ToolType, str, Dict[str, Any]]] = [
        {"type": "web_search_20260209", "name": "web_search"},
        {
            "name": "plan",
            "description": "plan task",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        ToolType.BASH,
    ]

    resolved = resolve_tools_for_target(
        tools=tools,
        provider=LLMProvider.OPENAI,
        model="gpt-4.1",
    )

    assert resolved == [tools[1]]


def test_model_router_uses_binding_resolver_for_target_model() -> None:
    primary = RouteTarget(
        service=_DummyService(),
        provider=LLMProvider.CLAUDE,
        model="claude-opus-4-6",
        name="primary",
    )
    router = ModelRouter(primary=primary)

    tools: List[Union[ToolType, str, Dict[str, Any]]] = [
        {
            "name": "web_fetch",
            "description": "fetch web page",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        }
    ]

    filtered = router._filter_tools_for_provider(tools, primary)

    assert filtered is not None
    assert isinstance(filtered[0], dict)
    assert filtered[0]["type"] == "web_fetch_20260209"
    assert filtered[0]["name"] == "web_fetch"


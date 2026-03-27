"""
Model-bound tool binding resolver.

This module keeps logical tool names stable in upper layers while mapping
them to provider/model-specific native tool schemas when available.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

from logger import get_logger

from .base import LLMProvider, ToolType

logger = get_logger("llm.tool_binding_resolver")

# Default bindings are used as safe fallback when config file is unavailable.
_DEFAULT_NATIVE_TOOL_BINDINGS: Dict[str, Dict[str, Dict[str, Any]]] = {
    "claude": {
        "web_search": {
            "server_tool_type": "web_search_20260209",
            "server_tool_name": "web_search",
            "model_exact": ["claude-sonnet-4-6", "claude-opus-4-6"],
            # Future patch versions (e.g. claude-sonnet-4-7) match by prefix.
            "model_prefix": ["claude-sonnet-4-", "claude-opus-4-"],
        },
        "web_fetch": {
            "server_tool_type": "web_fetch_20260209",
            "server_tool_name": "web_fetch",
            "model_exact": ["claude-sonnet-4-6", "claude-opus-4-6"],
            "model_prefix": ["claude-sonnet-4-", "claude-opus-4-"],
        },
    }
}

# Config cache (hot reload by file mtime).
_CACHE_PATH: Optional[Path] = None
_CACHE_MTIME_NS: Optional[int] = None
_CACHE_BINDINGS: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None
_CACHE_SERVER_INDEX: Optional[Dict[str, Dict[str, Any]]] = None


def _normalize_provider(provider: str) -> str:
    return provider.strip().lower()


def _ensure_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return []


def _normalize_model(model: str) -> str:
    return model.strip().lower()


def _get_bindings_path() -> Optional[Path]:
    global _CACHE_PATH
    if _CACHE_PATH is not None:
        return _CACHE_PATH
    try:
        from utils.app_paths import get_config_dir

        _CACHE_PATH = get_config_dir() / "capabilities.yaml"
        return _CACHE_PATH
    except Exception as e:
        logger.warning(f"获取 capabilities.yaml 路径失败，使用默认绑定: {e}")
        return None


def _normalize_rule(logical_tool_name: str, rule: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    # New style (preferred): flat keys
    server_tool_type = rule.get("server_tool_type")
    server_tool_name = rule.get("server_tool_name") or logical_tool_name
    model_exact = _ensure_list(rule.get("model_exact"))
    model_prefix = _ensure_list(rule.get("model_prefix"))

    # Backward compatibility: nested schema + model_allowlist.
    if not server_tool_type:
        schema = rule.get("schema")
        if isinstance(schema, dict):
            server_tool_type = schema.get("type")
            server_tool_name = schema.get("name") or server_tool_name
        if not model_exact:
            model_exact = _ensure_list(rule.get("model_allowlist"))

    if not isinstance(server_tool_type, str) or not server_tool_type:
        return None

    return {
        "server_tool_type": server_tool_type,
        "server_tool_name": str(server_tool_name),
        "model_exact": model_exact,
        "model_prefix": model_prefix,
    }


def _normalize_bindings(
    raw_bindings: Dict[str, Any],
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    normalized: Dict[str, Dict[str, Dict[str, Any]]] = {}

    for provider, tools in raw_bindings.items():
        if not isinstance(tools, dict):
            continue
        provider_key = _normalize_provider(str(provider))
        provider_rules: Dict[str, Dict[str, Any]] = {}

        for logical_tool_name, rule in tools.items():
            if not isinstance(rule, dict):
                continue
            normalized_rule = _normalize_rule(str(logical_tool_name), rule)
            if normalized_rule is None:
                continue
            provider_rules[str(logical_tool_name)] = normalized_rule

        if provider_rules:
            normalized[provider_key] = provider_rules

    return normalized


def _build_server_tool_index(
    bindings: Dict[str, Dict[str, Dict[str, Any]]],
) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for provider, provider_rules in bindings.items():
        for logical_tool_name, rule in provider_rules.items():
            server_tool_type = rule["server_tool_type"]
            index[server_tool_type] = {
                "provider": provider,
                "logical_tool_name": logical_tool_name,
                "rule": rule,
            }
    return index


def _refresh_cache_if_needed() -> None:
    global _CACHE_MTIME_NS, _CACHE_BINDINGS, _CACHE_SERVER_INDEX

    path = _get_bindings_path()
    if path is None or not path.exists():
        if _CACHE_BINDINGS is None:
            defaults = _normalize_bindings(copy.deepcopy(_DEFAULT_NATIVE_TOOL_BINDINGS))
            _CACHE_BINDINGS = defaults
            _CACHE_SERVER_INDEX = _build_server_tool_index(defaults)
        return

    try:
        mtime_ns = path.stat().st_mtime_ns
    except Exception as e:
        logger.warning(f"读取 capabilities.yaml mtime 失败，使用缓存/默认配置: {e}")
        if _CACHE_BINDINGS is None:
            defaults = _normalize_bindings(copy.deepcopy(_DEFAULT_NATIVE_TOOL_BINDINGS))
            _CACHE_BINDINGS = defaults
            _CACHE_SERVER_INDEX = _build_server_tool_index(defaults)
        return

    if _CACHE_BINDINGS is not None and _CACHE_SERVER_INDEX is not None and _CACHE_MTIME_NS == mtime_ns:
        return

    merged = copy.deepcopy(_DEFAULT_NATIVE_TOOL_BINDINGS)
    try:
        with path.open("r", encoding="utf-8") as f:
            parsed = yaml.safe_load(f) or {}
        if not isinstance(parsed, dict):
            raise ValueError("capabilities.yaml root must be a mapping")
        config_bindings = parsed.get("native_tool_bindings", {})
        if isinstance(config_bindings, dict):
            for provider, tools in config_bindings.items():
                if not isinstance(tools, dict):
                    continue
                provider_key = _normalize_provider(str(provider))
                base_provider = merged.setdefault(provider_key, {})
                for logical_tool_name, rule in tools.items():
                    if isinstance(rule, dict):
                        base_provider[str(logical_tool_name)] = rule
    except Exception as e:
        logger.warning(f"加载 native_tool_bindings 失败，回退默认配置: {e}")

    normalized = _normalize_bindings(merged)
    _CACHE_BINDINGS = normalized
    _CACHE_SERVER_INDEX = _build_server_tool_index(normalized)
    _CACHE_MTIME_NS = mtime_ns


def _model_matches_rule(model: str, rule: Dict[str, Any]) -> bool:
    exact_list = [str(item) for item in _ensure_list(rule.get("model_exact"))]
    prefix_list = [str(item) for item in _ensure_list(rule.get("model_prefix"))]

    # Empty matcher means "always supported".
    if not exact_list and not prefix_list:
        return True

    normalized = _normalize_model(model)
    exact_norm = {_normalize_model(item) for item in exact_list}
    if normalized in exact_norm:
        return True

    for prefix in prefix_list:
        if normalized.startswith(_normalize_model(prefix)):
            return True

    return False


def _resolve_dict_tool(
    tool: Dict[str, Any],
    provider_key: str,
    model: str,
    provider_rules: Dict[str, Dict[str, Any]],
    server_index: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    tool_type = tool.get("type")
    if isinstance(tool_type, str) and tool_type:
        server_meta = server_index.get(tool_type)
        if server_meta is not None:
            owner_provider = server_meta["provider"]
            rule = server_meta["rule"]
            if owner_provider != provider_key:
                return None
            if not _model_matches_rule(model, rule):
                return None
            return {
                "type": rule["server_tool_type"],
                "name": rule["server_tool_name"],
            }

    # Logical tool name: map to native server tool when supported.
    tool_name = tool.get("name")
    if isinstance(tool_name, str):
        rule = provider_rules.get(tool_name)
        if rule and _model_matches_rule(model, rule):
            return {
                "type": rule["server_tool_type"],
                "name": rule["server_tool_name"],
            }
        if rule and not _model_matches_rule(model, rule):
            # Keep logical tool definition as fallback when native binding is not supported.
            return tool

    return tool


def resolve_tools_for_target(
    tools: Optional[List[Union[ToolType, str, Dict[str, Any]]]],
    provider: LLMProvider,
    model: str,
) -> Optional[List[Union[ToolType, str, Dict[str, Any]]]]:
    """
    Resolve tool definitions for a specific provider/model target.

    Rules:
    - Claude:
      - Keep ToolType/str untouched.
      - Map logical dict tools (e.g. web_search/web_fetch) to native schemas
        when target model supports them.
      - Drop unsupported provider-native server-tool schemas for incompatible models.
    - Non-Claude:
      - Keep dict tools only.
      - Drop server-tool schemas that belong to other providers.
    """
    if tools is None:
        return None

    _refresh_cache_if_needed()
    bindings = _CACHE_BINDINGS or _normalize_bindings(copy.deepcopy(_DEFAULT_NATIVE_TOOL_BINDINGS))
    server_index = _CACHE_SERVER_INDEX or _build_server_tool_index(bindings)
    provider_key = _normalize_provider(provider.value)
    provider_rules = bindings.get(provider_key, {})

    resolved: List[Union[ToolType, str, Dict[str, Any]]] = []

    if provider == LLMProvider.CLAUDE:
        for tool in tools:
            if isinstance(tool, dict):
                mapped = _resolve_dict_tool(
                    tool=tool,
                    provider_key=provider_key,
                    model=model,
                    provider_rules=provider_rules,
                    server_index=server_index,
                )
                if mapped is not None:
                    resolved.append(mapped)
                continue
            resolved.append(tool)
        return resolved

    # Existing compatibility behavior for non-Claude providers:
    # keep only dict tools, and strip server tools owned by other providers.
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        mapped = _resolve_dict_tool(
            tool=tool,
            provider_key=provider_key,
            model=model,
            provider_rules=provider_rules,
            server_index=server_index,
        )
        if mapped is not None:
            resolved.append(mapped)

    return resolved


"""
实例加载器 - Instance Loader

职责：
- 加载 instances/ 目录下的智能体实例配置
- 合并 prompt.md 和框架通用提示词
- 调用 AgentFactory 创建 Agent
- 自动注册 Claude Skills（启动时）

设计原则：
- Prompt-First：提示词是配置的核心
- 无代码化：运营只需编辑配置文件
- 利用现有 AgentFactory
- Skills 自动生命周期管理
"""

import asyncio
import os
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles

from utils.app_paths import get_bundle_dir, get_instances_dir as _get_instances_dir

# 添加项目根目录到路径（兼容开发模式）
PROJECT_ROOT = get_bundle_dir()
sys.path.insert(0, str(PROJECT_ROOT))

from logger import get_logger

logger = get_logger("instance_loader")


@dataclass
class SkillConfig:
    """Skill 配置数据类（本地 Skill 系统）"""

    name: str
    enabled: bool = True
    description: str = ""
    skill_path: Optional[Path] = None  # Skill 目录路径


@dataclass
class ApiConfig:
    """API 配置数据类（REST API 描述）"""

    name: str
    base_url: str
    auth_type: str = "none"  # none / bearer / api_key / basic
    auth_header: str = "Authorization"  # 认证头名称
    auth_env: Optional[str] = None  # 认证密钥的环境变量名
    doc: Optional[str] = None  # 指向 api_desc/{doc}.md
    description: str = ""
    # 运行时填充
    headers: Dict[str, str] = field(default_factory=dict)
    doc_content: str = ""
    # 请求体配置（用于 api_calling 工具自动合成请求）
    request_body: Optional[Dict[str, Any]] = None  # 请求体模板
    default_method: str = "POST"  # 默认 HTTP 方法
    default_mode: str = "sync"  # 默认模式：sync / stream / async_poll
    poll_config: Optional[Dict[str, Any]] = None  # 异步轮询配置


@dataclass
class LLMParams:
    """LLM 超参数配置"""

    temperature: Optional[float] = None  # 温度，影响输出随机性（0-1）
    max_tokens: Optional[int] = None  # 最大输出 token 数
    enable_thinking: Optional[bool] = None  # 启用 Extended Thinking
    thinking_budget: Optional[int] = None  # Thinking token 预算
    enable_caching: Optional[bool] = None  # 启用 Prompt Caching
    top_p: Optional[float] = None  # 核采样参数
    thinking_mode: Optional[str] = None  # 思考模式: native/simulated/none


@dataclass
class InstanceConfig:
    """
    实例配置数据类

    配置优先级（从高到低）：
    1. config.yaml 显式配置 - 运营人员的场景化定制
    2. LLM 推断的 Schema - 基于 prompt.md 的智能推断
    3. DEFAULT_AGENT_SCHEMA - 高质量的框架默认值（兜底）
    """

    name: str
    description: str = ""
    version: str = "1.0.0"

    # Agent 基础配置
    model: Optional[str] = None
    max_turns: Optional[int] = None
    plan_manager_enabled: Optional[bool] = None
    allow_parallel_tools: Optional[bool] = None

    # LLM 超参数
    llm_params: LLMParams = field(default_factory=LLMParams)

    # Skills 配置（Claude Skills 官方 API）
    skills: List[SkillConfig] = field(default_factory=list)

    # APIs 配置（REST API 描述）
    apis: List[ApiConfig] = field(default_factory=list)

    # 通用工具启用配置（从 capabilities.yaml 选择）
    enabled_capabilities: Dict[str, bool] = field(default_factory=dict)

    # ===== 高级配置（从 config.yaml 的 advanced 部分读取）=====
    # 这些配置可选，未配置时使用 DEFAULT_AGENT_SCHEMA 的高质量默认值

    # 意图分析器配置
    intent_analyzer_enabled: Optional[bool] = None
    intent_analyzer_use_llm: Optional[bool] = None
    intent_analyzer_fast_mode: Optional[bool] = None
    intent_analyzer_semantic_cache_threshold: Optional[float] = None
    intent_analyzer_simplified_output: Optional[bool] = None

    # 开场白配置（Preface）
    preface_enabled: Optional[bool] = None
    preface_max_tokens: Optional[int] = None

    # 计划管理器配置
    plan_manager_max_steps: Optional[int] = None
    plan_manager_granularity: Optional[str] = None

    # 输出格式配置（V6.3 使用 Pydantic）
    output_format: Optional[str] = None
    output_code_highlighting: Optional[bool] = None
    output_json_model_name: Optional[str] = None
    output_json_schema: Optional[Dict[str, Any]] = None
    output_strict_json_validation: Optional[bool] = None
    output_json_ensure_ascii: Optional[bool] = None
    output_json_indent: Optional[int] = None

    # 记忆配置
    mem0_enabled: bool = True
    smart_retrieval: bool = True
    retention_policy: str = "user"

    # ===== 小搭子扩展配置（V11）=====
    # 未配置时为 None，由对应模块使用默认值
    termination: Optional[Dict[str, Any]] = None  # 终止策略（adaptive 等）
    skills_first_config: Optional[Dict[str, Any]] = None  # Skills-First 统一配置
    state_consistency: Optional[Dict[str, Any]] = None  # 状态一致性（快照、回滚）

    # 原始配置
    raw_config: Dict[str, Any] = field(default_factory=dict)


def get_instances_dir() -> Path:
    """获取 instances 目录路径"""
    return _get_instances_dir()


def list_instances() -> List[str]:
    """
    列出所有可用的实例

    Returns:
        实例名称列表（排除 _template）
    """
    instances_dir = get_instances_dir()
    if not instances_dir.exists():
        return []

    instances = []
    for item in instances_dir.iterdir():
        if item.is_dir() and not item.name.startswith("_"):
            # 检查是否有 prompt.md
            if (item / "prompt.md").exists():
                instances.append(item.name)

    return sorted(instances)


async def load_skill_registry(instance_name: str) -> List[SkillConfig]:
    """
    加载实例的 Skills 注册表

    Args:
        instance_name: 实例名称

    Returns:
        SkillConfig 列表
    """
    import yaml

    skills_dir = get_instances_dir() / instance_name / "skills"
    registry_path = skills_dir / "skill_registry.yaml"

    if not registry_path.exists():
        return []

    async with aiofiles.open(registry_path, "r", encoding="utf-8") as f:
        content = await f.read()
        registry = yaml.safe_load(content) or {}

    skills_list = registry.get("skills", [])
    if not isinstance(skills_list, list):
        return []

    result = []
    for skill_data in skills_list:
        if not isinstance(skill_data, dict):
            continue

        name = skill_data.get("name")
        if not name:
            continue

        # 解析 Skill 目录：先实例目录，再全局 library（与 SkillsLoader 一致）
        skill_path = skills_dir / name
        if not skill_path.exists():
            library_dir = PROJECT_ROOT / "skills" / "library"
            fallback = library_dir / name
            if fallback.exists():
                skill_path = fallback
            else:
                logger.warning(f"⚠️ Skill 目录不存在: {skills_dir / name} 且 library 无: {fallback}")
                continue

        # 检查 SKILL.md 是否存在
        skill_md = skill_path / "SKILL.md"
        if not skill_md.exists():
            logger.warning(f"⚠️ Skill 入口文件不存在: {skill_md}")
            continue

        result.append(
            SkillConfig(
                name=name,
                enabled=skill_data.get("enabled", True),
                description=skill_data.get("description", ""),
                skill_path=skill_path,
            )
        )

    return result


async def _load_yaml(path: Path) -> dict:
    """Load a YAML file, return empty dict if not found."""
    if not path.exists():
        return {}
    async with aiofiles.open(path, "r", encoding="utf-8") as f:
        content = await f.read()
    return __import__("yaml").safe_load(content) or {}


def _resolve_llm_profiles(
    provider_name: str,
    provider_templates: Dict[str, Any],
    raw_profiles: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """
    Resolve tier-based LLM profiles into fully-qualified profiles.

    Each profile specifies a ``tier`` ("heavy" / "light") which is expanded
    using the matching provider template.  If a profile already has an
    explicit ``provider`` key, the tier template is skipped (manual
    override).

    Args:
        provider_name: Active provider key (e.g. "qwen", "claude").
        provider_templates: The ``provider_templates`` section from
            llm_profiles.yaml.
        raw_profiles: The ``llm_profiles`` section (profile_name -> params).

    Returns:
        Dict of fully-resolved profiles ready for ``set_instance_profiles``.
    """
    template = provider_templates.get(provider_name)
    if not template:
        available = ", ".join(provider_templates.keys()) if provider_templates else "(empty)"
        raise ValueError(
            f"Provider '{provider_name}' not found in provider_templates. "
            f"Available: {available}"
        )

    resolved: Dict[str, Dict[str, Any]] = {}
    for name, params in raw_profiles.items():
        params = dict(params)  # shallow copy
        tier = params.pop("tier", None)

        if "provider" not in params and tier:
            # Merge tier template (provider/model/api_key_env/region)
            tier_cfg = template.get(tier, {})
            merged = {**tier_cfg, **params}  # profile params override template
            resolved[name] = merged
        else:
            # Explicit provider or no tier -> use as-is
            resolved[name] = params

    return resolved


async def load_instance_config(instance_name: str) -> InstanceConfig:
    """
    Load instance configuration from up to 3 files:

    1. ``config.yaml``              - user config (required)
    2. ``config/skills.yaml``       - skills & skill_groups
    3. ``config/llm_profiles.yaml`` - provider templates & LLM profiles

    Each config key lives in exactly ONE file. The loader merges them into
    a single ``raw_config`` dict for downstream processing.

    Args:
        instance_name: Instance directory name.

    Returns:
        InstanceConfig dataclass.

    Raises:
        FileNotFoundError: Instance directory missing.
        ValueError: Invalid configuration.
    """
    import yaml

    instance_dir = get_instances_dir() / instance_name

    if not instance_dir.exists():
        raise FileNotFoundError(f"实例不存在: {instance_name}")

    # ── 1. Load & merge config files ──────────────────────────────
    raw_config = await _load_yaml(instance_dir / "config.yaml")

    # Skills config (skill_groups + skills)
    skills_file = await _load_yaml(instance_dir / "config" / "skills.yaml")
    if skills_file:
        if "skills" in skills_file:
            raw_config["skills"] = skills_file["skills"]
        if "skill_groups" in skills_file:
            raw_config["skill_groups"] = skills_file["skill_groups"]
        logger.info(f"   已合并 config/skills.yaml")

    # LLM profiles (provider templates + profiles with tier)
    llm_file = await _load_yaml(instance_dir / "config" / "llm_profiles.yaml")

    # ── 2. Resolve provider templates ─────────────────────────────
    agent_config = raw_config.get("agent", {})
    provider_name = agent_config.get("provider", "")

    # Allow env var override (for E2E model compatibility testing)
    import os
    env_provider = os.environ.get("AGENT_PROVIDER")
    if env_provider:
        provider_name = env_provider
        agent_config["provider"] = env_provider
        # Clear explicit model so provider template auto-sets it
        agent_config.pop("model", None)
        raw_config["agent"] = agent_config
        logger.info(f"   ⚡ provider 被环境变量覆盖: {env_provider}")

    if llm_file and provider_name:
        provider_templates = llm_file.get("provider_templates", {})
        raw_profiles = llm_file.get("llm_profiles", {})

        if provider_templates and raw_profiles:
            resolved_profiles = _resolve_llm_profiles(
                provider_name, provider_templates, raw_profiles
            )
            raw_config["llm_profiles"] = resolved_profiles
            logger.info(
                f"   已合并 config/llm_profiles.yaml "
                f"(provider={provider_name}, {len(resolved_profiles)} profiles)"
            )

            tmpl = provider_templates.get(provider_name, {})

            # Auto-set agent.model from provider template if not explicit
            if not agent_config.get("model"):
                default_model = tmpl.get("agent_model")
                if default_model:
                    agent_config["model"] = default_model
                    logger.info(f"   agent.model 自动设置: {default_model}")

            # Auto-set agent.llm from provider template (user overrides win)
            template_llm = tmpl.get("agent_llm", {})
            if template_llm:
                user_llm = agent_config.get("llm", {})
                # template defaults + user overrides
                merged_llm = {**template_llm, **{k: v for k, v in user_llm.items() if v is not None}}
                agent_config["llm"] = merged_llm
                if user_llm:
                    logger.info(f"   agent.llm: 模板默认 + 用户覆盖 {list(user_llm.keys())}")
                else:
                    logger.info(f"   agent.llm: 使用 {provider_name} 模板默认值")

            raw_config["agent"] = agent_config
    elif llm_file:
        # No provider set but file exists: load raw profiles, strip tier hints
        raw_profiles = llm_file.get("llm_profiles", {})
        if raw_profiles:
            stripped = {}
            for name, params in raw_profiles.items():
                params = dict(params)
                params.pop("tier", None)
                stripped[name] = params
            raw_config["llm_profiles"] = stripped

    # ── 2b. Fallback: 如果 provider/model 仍为空，从已激活模型获取 ──
    if not agent_config.get("provider") or not agent_config.get("model"):
        try:
            from core.llm.model_registry import ModelRegistry
            activated = ModelRegistry.list_activated()
            if activated:
                first = activated[0]
                if not agent_config.get("provider"):
                    agent_config["provider"] = first.provider
                    logger.info(f"   agent.provider 从已激活模型自动设置: {first.provider}")
                if not agent_config.get("model"):
                    agent_config["model"] = first.model_name
                    logger.info(f"   agent.model 从已激活模型自动设置: {first.model_name}")
                raw_config["agent"] = agent_config

                # 重新解析 provider templates（如果有 llm_file 且刚设置了 provider）
                if llm_file and agent_config.get("provider"):
                    _pname = agent_config["provider"]
                    _templates = (llm_file.get("provider_templates") or {})
                    _profiles = (llm_file.get("llm_profiles") or {})
                    if _templates and _profiles:
                        resolved = _resolve_llm_profiles(_pname, _templates, _profiles)
                        raw_config["llm_profiles"] = resolved
                        _tmpl = _templates.get(_pname, {})
                        _tmpl_llm = _tmpl.get("agent_llm", {})
                        if _tmpl_llm:
                            agent_config["llm"] = {**_tmpl_llm, **agent_config.get("llm", {})}
                            raw_config["agent"] = agent_config
            else:
                logger.warning("   ⚠️ 未配置 provider/model 且无已激活模型，Agent 可能无法启动")
        except Exception as e:
            logger.warning(f"   ⚠️ 从已激活模型获取默认值失败: {e}")

    # ── 3. Parse config ────────────────────
    instance_info = raw_config.get("instance", {})
    memory_config = raw_config.get("memory", {})

    # 解析 LLM 超参数
    llm_config = agent_config.get("llm", {})
    llm_params = LLMParams(
        temperature=llm_config.get("temperature"),
        max_tokens=llm_config.get("max_tokens"),
        enable_thinking=llm_config.get("enable_thinking"),
        thinking_budget=llm_config.get("thinking_budget"),
        enable_caching=llm_config.get("enable_caching"),
        top_p=llm_config.get("top_p"),
        thinking_mode=llm_config.get("thinking_mode"),  # 思考模式: native/simulated/none
    )

    # 解析通用工具启用配置
    # V11: 检测 Skills-First 新格式（skills 含 common/darwin 等 OS 键）
    skills_raw = raw_config.get("skills", {})
    skills_first_config = None
    is_skills_first = isinstance(skills_raw, dict) and any(
        k in skills_raw for k in ("common", "darwin", "win32", "linux")
    )

    # 仅非 Skills-First 时从 skill_registry.yaml 加载，避免对 plan-todo/hitl 等框架工具报「目录不存在」
    if is_skills_first:
        skills = []
    else:
        skills = await load_skill_registry(instance_name)

    # 加载 APIs 配置（REST API 描述）
    apis = await _load_apis_config(instance_name, raw_config.get("apis", []))

    if is_skills_first:
        # Skills-First 新格式：从 SkillsLoader 派生 enabled_capabilities
        skills_first_config = skills_raw
        logger.info("   检测到 Skills-First 配置格式，使用 SkillsLoader")

        from core.skill import create_skills_loader

        _loader = create_skills_loader(
            skills_config=skills_raw,
            instance_skills_dir=instance_dir / "skills",
            instance_name=instance_name,
        )
        # 异步加载（load_instance_config 本身是 async）
        _entries = await _loader.load()
        enabled_capabilities = _loader.get_enabled_capabilities()

        logger.info(
            f"   Skills-First: {len(_entries)} 个 Skills, "
            f"派生 {len(enabled_capabilities)} 个 enabled_capabilities"
        )
    else:
        # 旧格式：直接从 enabled_capabilities 字段读取
        enabled_capabilities_raw = raw_config.get("enabled_capabilities", {})
        enabled_capabilities = {}
        if isinstance(enabled_capabilities_raw, dict):
            for tool_name, enabled in enabled_capabilities_raw.items():
                if isinstance(enabled, bool):
                    enabled_capabilities[tool_name] = enabled
                elif isinstance(enabled, int):
                    enabled_capabilities[tool_name] = bool(enabled)
                else:
                    logger.warning(f"⚠️ 工具 {tool_name} 的启用配置值无效: {enabled}，将被忽略")

    # 解析 advanced 配置（高级配置，可选）
    # 未配置时使用 DEFAULT_AGENT_SCHEMA 的高质量默认值兜底
    advanced_config = raw_config.get("advanced", {})
    intent_config = advanced_config.get("intent_analyzer", {})
    preface_config = advanced_config.get("preface", {})
    plan_config = advanced_config.get("plan_manager", {})
    output_config = advanced_config.get("output_formatter", {})

    return InstanceConfig(
        name=instance_info.get("name", instance_name),
        description=instance_info.get("description", ""),
        version=instance_info.get("version", "1.0.0"),
        model=agent_config.get("model"),
        max_turns=agent_config.get("max_turns"),
        plan_manager_enabled=agent_config.get("plan_manager_enabled"),
        allow_parallel_tools=agent_config.get("allow_parallel_tools"),
        llm_params=llm_params,
        skills=skills,
        apis=apis,
        enabled_capabilities=enabled_capabilities,
        # 高级配置（从 advanced 部分读取）
        intent_analyzer_enabled=intent_config.get("enabled"),
        intent_analyzer_use_llm=intent_config.get("use_llm"),
        intent_analyzer_fast_mode=intent_config.get("fast_mode"),
        intent_analyzer_semantic_cache_threshold=intent_config.get("semantic_cache_threshold"),
        intent_analyzer_simplified_output=intent_config.get("simplified_output"),
        preface_enabled=preface_config.get("enabled"),
        preface_max_tokens=preface_config.get("max_tokens"),
        plan_manager_max_steps=plan_config.get("max_steps"),
        plan_manager_granularity=plan_config.get("granularity"),
        output_format=output_config.get("default_format"),
        output_code_highlighting=output_config.get("code_highlighting"),
        output_json_model_name=output_config.get("json_model_name"),
        output_json_schema=output_config.get("json_schema"),
        output_strict_json_validation=output_config.get("strict_json_validation"),
        output_json_ensure_ascii=output_config.get("json_ensure_ascii"),
        output_json_indent=output_config.get("json_indent"),
        # 记忆配置
        mem0_enabled=memory_config.get("mem0_enabled", True),
        smart_retrieval=memory_config.get("smart_retrieval", True),
        retention_policy=memory_config.get("retention_policy", "user"),
        # 小搭子扩展配置（V11）
        termination=raw_config.get("termination") if isinstance(raw_config.get("termination"), dict) else None,
        skills_first_config=skills_first_config,
        state_consistency=raw_config.get("state_consistency") if isinstance(raw_config.get("state_consistency"), dict) else None,
        raw_config=raw_config,
    )


async def _load_apis_config(instance_name: str, apis_raw: List[Dict]) -> List[ApiConfig]:
    """
    加载并解析 APIs 配置

    Args:
        instance_name: 实例名称
        apis_raw: config.yaml 中的 apis 配置列表

    Returns:
        ApiConfig 列表
    """
    if not isinstance(apis_raw, list):
        return []

    result = []
    api_desc_dir = get_instances_dir() / instance_name / "api_desc"

    for api_data in apis_raw:
        if not isinstance(api_data, dict):
            continue

        name = api_data.get("name")
        base_url = api_data.get("base_url")

        if not name or not base_url:
            logger.warning(f"⚠️ API 配置缺少 name 或 base_url，跳过")
            continue

        # 解析认证配置
        auth = api_data.get("auth", {})
        auth_type = auth.get("type", "none") if isinstance(auth, dict) else "none"
        auth_header = (
            auth.get("header", "Authorization") if isinstance(auth, dict) else "Authorization"
        )
        auth_env = auth.get("env") if isinstance(auth, dict) else None

        # 加载 API 描述文档
        doc_name = api_data.get("doc")
        doc_content = ""
        if doc_name:
            doc_path = api_desc_dir / f"{doc_name}.md"
            if doc_path.exists():
                async with aiofiles.open(doc_path, "r", encoding="utf-8") as f:
                    doc_content = await f.read()
                logger.info(f"   📄 已加载 API 文档: {doc_path.name}")
            else:
                logger.warning(f"⚠️ API 文档不存在: {doc_path}")

        result.append(
            ApiConfig(
                name=name,
                base_url=base_url,
                auth_type=auth_type,
                auth_header=auth_header,
                auth_env=auth_env,
                doc=doc_name,
                description=api_data.get("description", ""),
                doc_content=doc_content,
                # 请求体配置（用于 api_calling 工具自动合成请求）
                request_body=api_data.get("request_body"),
                default_method=api_data.get("default_method", "POST"),
                default_mode=api_data.get("default_mode", "sync"),
                poll_config=api_data.get("poll_config"),
            )
        )

    return result


def _prepare_apis(apis: List[ApiConfig]) -> List[ApiConfig]:
    """
    准备 APIs 运行时参数（构建 headers）

    Args:
        apis: ApiConfig 列表

    Returns:
        填充了 headers 的 ApiConfig 列表
    """
    for api in apis:
        headers = {}

        # 构建认证头
        if api.auth_type in ("bearer", "api_key", "token") and api.auth_env:
            auth_value = os.getenv(api.auth_env)
            if auth_value:
                if api.auth_type == "bearer":
                    headers[api.auth_header] = f"Bearer {auth_value}"
                else:  # api_key 或 token：直接使用值
                    headers[api.auth_header] = auth_value
                # 🔍 调试：显示 token 的前 10 位和后 4 位
                masked_value = (
                    f"{auth_value[:10]}...{auth_value[-4:]}" if len(auth_value) > 14 else "***"
                )
                logger.info(f"   🔑 API {api.name}: 已配置认证 (token: {masked_value})")
            else:
                logger.warning(
                    f"⚠️ API {api.name}: 环境变量 {api.auth_env} 未设置（当前环境变量列表中无此项）"
                )

        api.headers = headers

    return apis


def _build_apis_prompt_section(apis: List[ApiConfig]) -> str:
    """
    构建 APIs 提示词片段（注入到 System Prompt）

    Args:
        apis: ApiConfig 列表

    Returns:
        APIs 描述的 Markdown 文本
    """
    if not apis:
        return ""

    sections = ["# 可用的 REST APIs\n"]

    for api in apis:
        sections.append(f"## {api.name}")
        sections.append(f"- Base URL: `{api.base_url}`")
        if api.description:
            sections.append(f"- 描述: {api.description}")

        # 添加文档内容
        if api.doc_content:
            sections.append(f"\n{api.doc_content}")

        sections.append("")  # 空行分隔

    sections.append(
        """
> 💡 调用 API 时，使用 `api_calling` 工具：
> - `url`: 完整 URL（base_url + 路径）
> - `method`: HTTP 方法
> - `body`: 请求体（JSON）
> - 认证头已自动配置
"""
    )

    return "\n".join(sections)


def _build_persona_prompt(persona: dict) -> str:
    """
    将用户个性化配置（persona）转换为提示词片段

    所有字段可选，空值跳过。只构建用户实际填写的部分。
    注入到 runtime_context["persona_prompt"]，在 system prompt 动态层使用。

    Args:
        persona: config.yaml 中的 persona 字段

    Returns:
        个性化提示词片段，空配置返回空字符串
    """
    if not persona or not isinstance(persona, dict):
        return ""

    parts = []

    nickname = (persona.get("nickname") or "").strip()
    if nickname:
        parts.append(f"- 称呼用户为「{nickname}」")

    tone = (persona.get("tone") or "").strip()
    if tone:
        parts.append(f"- 说话风格：{tone}")

    language = (persona.get("language") or "").strip()
    if language and language != "中文":
        parts.append(f"- 回复语言：{language}")

    detail_level = (persona.get("detail_level") or "").strip()
    if detail_level and detail_level != "适中":
        detail_map = {"简洁": "尽量简短，要点即可", "详细": "给出详细解释和步骤"}
        if detail_level in detail_map:
            parts.append(f"- 回答详细度：{detail_map[detail_level]}")

    work_dirs = persona.get("work_dirs") or []
    if work_dirs and isinstance(work_dirs, list):
        dirs_str = "、".join(str(d) for d in work_dirs[:5])
        parts.append(f"- 用户常用工作目录：{dirs_str}（优先在这些目录查找文件）")

    custom_rules = persona.get("custom_rules") or []
    if custom_rules and isinstance(custom_rules, list):
        for rule in custom_rules[:10]:
            rule_str = str(rule).strip()
            if rule_str:
                parts.append(f"- {rule_str}")

    if not parts:
        return ""

    return "<user_preferences>\n" + "\n".join(parts) + "\n</user_preferences>"


async def load_instance_prompt(instance_name: str) -> str:
    """
    加载实例提示词

    Args:
        instance_name: 实例名称

    Returns:
        实例提示词内容

    Raises:
        FileNotFoundError: prompt.md 不存在
    """
    prompt_path = get_instances_dir() / instance_name / "prompt.md"

    if not prompt_path.exists():
        raise FileNotFoundError(f"实例提示词不存在: {prompt_path}")

    async with aiofiles.open(prompt_path, "r", encoding="utf-8") as f:
        return await f.read()


def load_instance_env_from_config(instance_name: str) -> None:
    """
    从实例目录加载环境变量到 os.environ

    加载顺序（后加载的覆盖先加载的）：
    1. 实例目录下的 .env 文件（通过 python-dotenv）
    2. 实例 config.yaml 的 env_vars 段（优先级更高）

    Args:
        instance_name: 实例名称
    """
    import os

    import yaml

    instance_dir = get_instances_dir() / instance_name

    # Step 1: 加载实例目录下的 .env 文件
    env_file = instance_dir / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(dotenv_path=env_file, override=False)
            logger.info(f"从实例 {instance_name}/.env 加载环境变量")
        except ImportError:
            logger.warning("python-dotenv 未安装，跳过 .env 加载。安装: pip install python-dotenv")

    # Step 2: 加载 config.yaml 的 env_vars 段（优先级更高，会覆盖 .env）
    config_path = instance_dir / "config.yaml"
    if not config_path.exists():
        if not env_file.exists():
            logger.warning(f"实例配置文件不存在: {config_path}")
        return

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw_config = yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"加载实例配置失败: {e}", exc_info=True)
        return

    env_vars = raw_config.get("env_vars", {})
    if not isinstance(env_vars, dict) or not env_vars:
        return

    injected_count = 0
    for key, value in env_vars.items():
        if value is not None and str(value).strip():
            os.environ[key] = str(value).strip()
            injected_count += 1

    if injected_count > 0:
        logger.info(f"从实例 {instance_name}/config.yaml 注入 {injected_count} 个环境变量")


def _merge_config_to_schema(base_schema, config: InstanceConfig):
    """
    将 config.yaml 配置合并到 AgentSchema

    合并策略：
    - config.yaml 有显式配置 → 覆盖 Schema 默认值
    - config.yaml 未配置（None）→ 保留 Schema 的高质量默认值

    这样即使运营配置不全或配置错误，也能依赖 DEFAULT_AGENT_SCHEMA 兜底。

    Args:
        base_schema: 基础 Schema（来自 LLM 推断或 DEFAULT_AGENT_SCHEMA）
        config: InstanceConfig（从 config.yaml 读取）

    Returns:
        合并后的 AgentSchema
    """
    # 深拷贝 Schema，避免修改原始默认值
    merged = base_schema.copy(deep=True)

    # === 基础配置覆盖 ===
    if config.model:
        merged.model = config.model
    if config.max_turns:
        merged.max_turns = config.max_turns
    if config.allow_parallel_tools is not None:
        merged.allow_parallel_tools = config.allow_parallel_tools

    # === 计划管理器配置覆盖 ===
    if config.plan_manager_enabled is not None:
        merged.plan_manager.enabled = config.plan_manager_enabled
    if config.plan_manager_max_steps is not None:
        merged.plan_manager.max_steps = config.plan_manager_max_steps
    if config.plan_manager_granularity is not None:
        merged.plan_manager.granularity = config.plan_manager_granularity

    # === 意图分析器配置覆盖 ===
    if config.intent_analyzer_enabled is not None:
        merged.intent_analyzer.enabled = config.intent_analyzer_enabled
    if config.intent_analyzer_use_llm is not None:
        merged.intent_analyzer.use_llm = config.intent_analyzer_use_llm
    if config.intent_analyzer_fast_mode is not None:
        merged.intent_analyzer.fast_mode = config.intent_analyzer_fast_mode
    if config.intent_analyzer_semantic_cache_threshold is not None:
        merged.intent_analyzer.semantic_cache_threshold = config.intent_analyzer_semantic_cache_threshold
    if config.intent_analyzer_simplified_output is not None:
        merged.intent_analyzer.simplified_output = config.intent_analyzer_simplified_output

    # === 开场白配置覆盖（Preface）===
    if config.preface_enabled is not None:
        if merged.prompts and merged.prompts.preface:
            merged.prompts.preface.enabled = config.preface_enabled
        elif config.preface_enabled:
            # 如果启用但没有默认模板，记录警告
            logger.warning("⚠️ preface.enabled=true 但没有配置 preface 模板，将被忽略")
    if config.preface_max_tokens is not None:
        if merged.prompts and merged.prompts.preface:
            merged.prompts.preface.max_tokens = config.preface_max_tokens

    # === LLM 参数配置覆盖 ===
    # 注意：这些参数只影响通过 instance_config.llm_params 创建的 LLM service
    # 不会影响已通过 provider 模板解析的 LLM profiles
    # 此处用于记录配置意图，实际 LLM service 创建时会优先使用 profile
    llm_override_count = 0
    if config.llm_params.temperature is not None:
        llm_override_count += 1
    if config.llm_params.max_tokens is not None:
        llm_override_count += 1
    if config.llm_params.enable_thinking is not None:
        llm_override_count += 1
    if config.llm_params.thinking_budget is not None:
        llm_override_count += 1
    if config.llm_params.enable_caching is not None:
        llm_override_count += 1
    if config.llm_params.top_p is not None:
        llm_override_count += 1
    if config.llm_params.thinking_mode is not None:
        llm_override_count += 1
        # 🆕 V7.10: 将 thinking_mode 应用到 AgentSchema
        merged.thinking_mode = config.llm_params.thinking_mode
        logger.info(f"🧠 thinking_mode 配置: {config.llm_params.thinking_mode}")

    if llm_override_count > 0:
        logger.debug(
            f"📝 config.yaml 覆盖了 {llm_override_count} 项 LLM 参数 (注意：需要检查是否被 profile 覆盖)"
        )

    # === 输出格式配置覆盖（V6.3 Pydantic 支持）===
    if config.output_format:
        merged.output_formatter.default_format = config.output_format
    if config.output_code_highlighting is not None:
        merged.output_formatter.code_highlighting = config.output_code_highlighting
    if config.output_json_model_name:
        merged.output_formatter.json_model_name = config.output_json_model_name
    if config.output_json_schema:
        merged.output_formatter.json_schema = config.output_json_schema
    if config.output_strict_json_validation is not None:
        merged.output_formatter.strict_json_validation = config.output_strict_json_validation
    if config.output_json_ensure_ascii is not None:
        merged.output_formatter.json_ensure_ascii = config.output_json_ensure_ascii
    if config.output_json_indent is not None:
        merged.output_formatter.json_indent = config.output_json_indent

    # === 工具列表覆盖（从 enabled_capabilities 生成）===
    # 🆕 V10.1: 将 enabled_capabilities 设置到 Schema.tools
    # 确保实例配置的工具全量注入到 LLM 调用，而不是根据 intent 动态过滤
    if config.enabled_capabilities:
        enabled_tools = [
            tool_name for tool_name, enabled in config.enabled_capabilities.items() if enabled
        ]
        if enabled_tools:
            merged.tools = enabled_tools
            logger.info(
                f"🔧 从 enabled_capabilities 设置 {len(enabled_tools)} 个工具到 Schema.tools"
            )

    # === 记录合并结果 ===
    override_count = sum(
        [
            config.model is not None,
            config.max_turns is not None,
            config.allow_parallel_tools is not None,
            config.plan_manager_enabled is not None,
            config.plan_manager_max_steps is not None,
            config.plan_manager_granularity is not None,
            config.intent_analyzer_enabled is not None,
            config.intent_analyzer_use_llm is not None,
            config.preface_enabled is not None,
            config.preface_max_tokens is not None,
            config.output_format is not None,
            config.output_code_highlighting is not None,
            config.output_json_model_name is not None,
            config.output_json_schema is not None,
            config.output_strict_json_validation is not None,
            config.output_json_ensure_ascii is not None,
            config.output_json_indent is not None,
            bool(config.enabled_capabilities),  # 🆕 V10.1: 工具列表覆盖
        ]
    )

    if override_count > 0:
        logger.info(f"✅ config.yaml 覆盖了 {override_count} 项 Schema 配置")
    else:
        logger.info("✅ config.yaml 无显式配置，使用 Schema 默认值")

    return merged


async def create_agent_from_instance(
    instance_name: str,
    event_manager=None,
    conversation_service=None,
    skip_skills_registration: bool = False,
    force_refresh: bool = False,
):
    """
    从实例配置创建 Agent（核心方法）

    配置优先级（从高到低）：
    ┌────────────────────────────────────────────────────────────┐
    │ 1. config.yaml 显式配置  - 运营人员的场景化定制            │
    │ 2. LLM 推断的 Schema     - 基于 prompt.md 的智能推断       │
    │ 3. DEFAULT_AGENT_SCHEMA  - 高质量的框架默认值（兜底）      │
    └────────────────────────────────────────────────────────────┘

    设计理念：
    - config.yaml 有配置 → 使用 config.yaml 的值
    - config.yaml 未配置 → 使用 LLM 推断或框架默认值兜底
    - 即使运营配置不全/错误，Agent 也能以高质量默认行为运行

    流程：
    1. 加载环境变量
    2. 加载实例配置（config.yaml）
    3. 加载实例提示词（prompt.md）
    4. 加载 InstancePromptCache（包含 LLM 推断的 Schema 和提示词版本）
    5. 合并配置：config.yaml 覆盖 Schema 默认值
    6. 调用 AgentFactory.from_schema() 创建 Agent
    7. 注册 Claude Skills
    8. 保存工具推断缓存

    Args:
        instance_name: 实例名称
        event_manager: 事件管理器
        conversation_service: 会话服务
        skip_skills_registration: 是否跳过 Skills 注册
        force_refresh: 强制刷新缓存，重新生成 Schema 和推断工具

    Returns:
        配置好的 Agent 实例
    """
    from pathlib import Path

    from core.agent import AgentFactory
    from prompts.universal_agent_prompt import get_universal_agent_prompt

    logger.info(f"🚀 开始加载实例: {instance_name}")

    # 0. 确保 AGENT_INSTANCE 环境变量与当前实例一致
    # 这是所有存储组件（DB/Memory/Mem0/Playbook/Snapshot）
    # 实例隔离的基础 — 各组件通过此变量自动派生隔离路径
    os.environ["AGENT_INSTANCE"] = instance_name

    # 准备缓存目录
    instance_path = get_instances_dir() / instance_name
    cache_dir = instance_path / ".cache"

    if force_refresh:
        logger.info("🔄 强制刷新缓存模式")

    # 1. 加载实例环境变量（从 config.yaml 的 env_vars 段）
    load_instance_env_from_config(instance_name)

    # 2. 加载实例配置
    config = await load_instance_config(instance_name)
    logger.info(f"   配置: {config.name} v{config.version}")
    logger.info(f"   描述: {config.description}")

    # 2.0.1 注册自定义数据目录（若 config.yaml 配置了 storage.data_dir）
    storage_cfg = (config.raw_config or {}).get("storage", {})
    custom_data_dir = storage_cfg.get("data_dir") if isinstance(storage_cfg, dict) else None
    if custom_data_dir:
        from utils.app_paths import register_instance_data_dir
        register_instance_data_dir(instance_name, custom_data_dir)
        logger.info(f"   自定义存储路径: {custom_data_dir}")

    # 2.1 注入实例 LLM Profiles（必须在 InstancePromptCache 加载之前）
    from config.llm_config.loader import set_instance_profiles

    llm_profiles = (config.raw_config or {}).get("llm_profiles", {})
    if llm_profiles:
        set_instance_profiles(llm_profiles)
    else:
        logger.warning("⚠️ 实例未配置 llm_profiles，框架内部 LLM 调用将不可用")

    # V11: Skills-First 加载器（统一处理 Skills 二维分类）
    skills_loader = None
    if config.skills_first_config:
        from core.skill import create_skills_loader

        skills_loader = create_skills_loader(
            skills_config=config.skills_first_config,
            instance_skills_dir=instance_path / "skills",
            instance_name=instance_name,
        )
        skill_entries = await skills_loader.load()
        available_count = len(skills_loader.get_available_skills())
        logger.info(
            f"   Skills-First: {len(skill_entries)} 个 Skills, "
            f"{available_count} 个可用"
        )
    logger.info(f"   Skills: {len(config.skills)} 个")
    logger.info(f"   APIs: {len(config.apis)} 个")

    # 3. 加载实例提示词
    instance_prompt = await load_instance_prompt(instance_name)

    # 合并用户个性化配置（persona + user_prompt）到实例提示词
    # 启动时一次性合并，走 Prompt Caching STABLE 层（Layer 2）
    persona_prompt = _build_persona_prompt(config.raw_config.get("persona", {}))
    user_prompt = (config.raw_config.get("user_prompt") or "").strip()

    user_config_parts = []
    if persona_prompt:
        user_config_parts.append(persona_prompt)
    if user_prompt:
        user_config_parts.append(f"<user_instructions>\n{user_prompt}\n</user_instructions>")

    if user_config_parts:
        instance_prompt = instance_prompt + "\n\n" + "\n\n".join(user_config_parts)
        logger.info(f"   用户配置已合并: persona={bool(persona_prompt)}, user_prompt={bool(user_prompt)}")

    logger.info(f"   提示词长度: {len(instance_prompt)} 字符")

    # 🆕 V5.0: 一次性加载 InstancePromptCache（核心改动）
    # 这会在启动时：
    # 1. 🆕 优先从磁盘缓存加载（< 100ms）
    # 2. 缓存无效时执行 LLM 分析（2-3秒）
    # 生成内容：
    # - PromptSchema（提示词结构）
    # - AgentSchema（Agent 配置）
    # - 三个版本的系统提示词（Simple/Medium/Complex）
    # - 意图识别提示词
    from core.prompt import InstancePromptCache, load_instance_cache

    prompt_cache = await load_instance_cache(
        instance_name=instance_name,
        raw_prompt=instance_prompt,
        config=config.raw_config,
        cache_dir=str(cache_dir),  # 🆕 V5.0: 启用磁盘持久化
        force_refresh=force_refresh,
    )

    # 打印缓存状态
    cache_status = prompt_cache.get_status()
    persistence_info = cache_status.get("persistence", {})
    metrics = cache_status.get("metrics", {})

    logger.info(f"✅ InstancePromptCache 加载完成")
    logger.info(
        f"   Agent: {prompt_cache.agent_schema.name if prompt_cache.agent_schema else 'Default'}"
    )
    logger.info(
        f"   提示词版本: Simple={len(prompt_cache.system_prompt_simple or '')}字符, "
        f"Medium={len(prompt_cache.system_prompt_medium or '')}字符, "
        f"Complex={len(prompt_cache.system_prompt_complex or '')}字符"
    )

    # 🆕 V5.0: 显示持久化状态
    if persistence_info.get("enabled"):
        if metrics.get("disk_hits", 0) > 0:
            logger.info(f"   💾 从磁盘缓存加载（{metrics.get('disk_load_time_ms', 0):.0f}ms）")
        else:
            logger.info(f"   🔄 LLM 分析生成（{metrics.get('llm_analysis_time_ms', 0):.0f}ms）")
            logger.info(f"   💾 已保存到磁盘缓存: {cache_dir}")

    # 4. 准备 APIs 运行时参数
    if config.apis:
        config.apis = _prepare_apis(config.apis)

    # 🆕 V5.1: 准备运行时上下文（APIs + 框架协议）
    # 不再将完整 prompt.md 与框架提示词合并
    # 而是让 Agent 运行时根据任务复杂度动态获取缓存版本
    apis_prompt = _build_apis_prompt_section(config.apis)
    framework_prompt = await get_universal_agent_prompt()

    # 存储运行时上下文到 prompt_cache（供 Agent 动态追加）
    prompt_cache.runtime_context = {
        "apis_prompt": apis_prompt,
        "framework_prompt": framework_prompt,
    }

    # 🆕 V5.1: 仅在 fallback 时使用完整拼接版本
    # 正常流程使用缓存的精简版本 + 运行时追加
    fallback_prompt = f"""# 实例配置

{instance_prompt}

---

{apis_prompt}

---

# 框架能力协议

{framework_prompt}
"""

    logger.info(
        f"   运行时上下文: APIs={len(apis_prompt)} 字符, Framework={len(framework_prompt)} 字符"
    )
    logger.info(
        f"   缓存版本: Simple={len(prompt_cache.system_prompt_simple or '')} 字符, "
        f"Medium={len(prompt_cache.system_prompt_medium or '')} 字符, "
        f"Complex={len(prompt_cache.system_prompt_complex or '')} 字符"
    )

    # 6. 创建事件管理器（如果未提供）
    if event_manager is None:
        from core.events import create_event_manager, get_memory_storage

        # 使用内存存储（适合单机测试）
        storage = get_memory_storage()
        event_manager = create_event_manager(storage)

    # 使用缓存的 AgentSchema 创建 Agent
    # 系统提示词运行时根据任务复杂度动态获取
    if prompt_cache.is_loaded and prompt_cache.agent_schema:
        # 获取基础 Schema（来自 LLM 推断）
        base_schema = prompt_cache.agent_schema

        # 合并 config.yaml 配置到 Schema
        # 策略：config.yaml 显式配置覆盖 Schema，未配置则使用 Schema 默认值
        merged_schema = _merge_config_to_schema(base_schema, config)

        # 更新 prompt_cache 中的 agent_schema（供后续使用）
        prompt_cache.agent_schema = merged_schema

        # V11: 终止策略（始终启用 adaptive，使用框架默认值，无需配置）
        terminator = None
        try:
            from core.termination import AdaptiveTerminator, AdaptiveTerminatorConfig, HITLConfig

            # 从 config 读取覆盖值，未配置则使用默认值
            t = config.termination or {}
            hitl_raw = t.get("hitl", {}) if isinstance(t, dict) else {}

            terminator = AdaptiveTerminator(
                AdaptiveTerminatorConfig(
                    max_turns=t.get("max_turns", 100) if isinstance(t, dict) else 100,
                    max_duration_seconds=t.get("max_duration_seconds", 1800) if isinstance(t, dict) else 1800,
                    idle_timeout_seconds=t.get("idle_timeout_seconds", 120) if isinstance(t, dict) else 120,
                    consecutive_failure_limit=t.get("consecutive_failure_limit", 5) if isinstance(t, dict) else 5,
                    long_running_confirm_after_turns=t.get("long_running_confirm_after_turns", 20) if isinstance(t, dict) else 20,
                    hitl=HITLConfig(
                        enabled=hitl_raw.get("enabled", True),
                        require_confirmation=hitl_raw.get("require_confirmation", [
                            "delete", "overwrite", "send_email", "publish", "payment",
                        ]),
                        on_rejection=hitl_raw.get("on_rejection", "ask_rollback"),
                        show_rollback_on_error=hitl_raw.get("show_rollback_on_error", True),
                    ),
                )
            )
            logger.info("   终止策略: adaptive（框架内置，始终启用）")
        except ImportError:
            logger.warning("   终止策略: 未安装 core.termination，使用框架默认")
            terminator = None

        # 创建 Agent，使用合并后的 Schema
        # prompt_cache 包含：
        # - system_prompt_simple/medium/complex（缓存版本）
        # - runtime_context（APIs + framework 运行时追加）
        agent = await AgentFactory.from_schema(
            schema=merged_schema,
            system_prompt=None,  # 运行时从 prompt_cache 动态获取
            event_manager=event_manager,
            conversation_service=conversation_service,
            prompt_cache=prompt_cache,
            terminator=terminator,
        )

        # V11: 状态一致性（仅当实例配置了 state_consistency 且 enabled 为 true 时启用）
        try:
            from core.state import (
                ConsistencyCheckConfig,
                RollbackConfig,
                SnapshotConfig,
                StateConsistencyConfig,
                StateConsistencyManager,
            )

            sc_raw = config.state_consistency if isinstance(config.state_consistency, dict) else {}
            enabled = bool(sc_raw and sc_raw.get("enabled", True))
            snap_raw = sc_raw.get("snapshot") if isinstance(sc_raw.get("snapshot"), dict) else {}
            rb_raw = sc_raw.get("rollback") if isinstance(sc_raw.get("rollback"), dict) else {}
            cc_raw = sc_raw.get("consistency_check") if isinstance(sc_raw.get("consistency_check"), dict) else {}

            sc_config = StateConsistencyConfig(
                enabled=bool(enabled),
                snapshot=SnapshotConfig(
                    storage_path=snap_raw.get("storage_path", ""),  # Empty = auto from AGENT_INSTANCE
                    retention_hours=int(snap_raw.get("retention_hours", 24)),
                    max_size_mb=int(snap_raw.get("max_size_mb", 500)),
                    capture_cwd=bool(snap_raw.get("capture_cwd", True)),
                    capture_files=bool(snap_raw.get("capture_files", True)),
                    capture_clipboard=bool(snap_raw.get("capture_clipboard", True)),
                ),
                rollback=RollbackConfig(
                    auto_rollback_on_consecutive_failures=int(
                        rb_raw.get("auto_rollback_on_consecutive_failures", 3)
                    ),
                    auto_rollback_on_critical_error=bool(
                        rb_raw.get("auto_rollback_on_critical_error", True)
                    ),
                    rollback_timeout_seconds=int(rb_raw.get("rollback_timeout_seconds", 60)),
                ),
                consistency_check=ConsistencyCheckConfig(
                    pre_task_disk_space_mb=int(cc_raw.get("pre_task_disk_space_mb", 100)),
                    pre_task_check_permissions=bool(cc_raw.get("pre_task_check_permissions", True)),
                    post_task_check_integrity=bool(cc_raw.get("post_task_check_integrity", True)),
                ),
            )
            agent._state_consistency_manager = StateConsistencyManager(config=sc_config)
            agent._state_consistency_enabled = sc_config.enabled
            if sc_config.enabled:
                logger.info(
                    f"   状态一致性: 已启用（快照={sc_config.snapshot.storage_path}, "
                    f"自动回滚={sc_config.rollback.auto_rollback_on_critical_error}）"
                )
            else:
                logger.info("   状态一致性: 未启用")
        except Exception as e:
            logger.warning(f"状态一致性初始化失败（不阻断启动）: {e}", exc_info=True)

        logger.info("✅ Agent 创建成功（使用动态提示词路由）")
    else:
        # Fallback: 如果缓存加载失败，使用完整拼接版本
        # 此时使用 DEFAULT_AGENT_SCHEMA 作为兜底
        logger.warning("⚠️ InstancePromptCache 加载失败，使用 fallback 完整提示词")

        from core.schemas import DEFAULT_AGENT_SCHEMA

        fallback_schema = _merge_config_to_schema(DEFAULT_AGENT_SCHEMA, config)

        agent = await AgentFactory.from_prompt(
            system_prompt=fallback_prompt,
            event_manager=event_manager,
            conversation_service=conversation_service,
            use_default_if_failed=True,
            cache_dir=str(cache_dir),
            instance_path=str(instance_path),
            force_refresh=force_refresh,
            prompt_schema=prompt_cache.prompt_schema,
        )

    logger.info(f"✅ Agent 创建成功")

    # V12: 注入 SkillsLoader + SkillGroupRegistry（供 tool_provider 动态生成 skills_prompt）
    if skills_loader:
        agent._skills_loader = skills_loader
        agent._instance_skills = []  # 新格式由 skills_loader 管理

        # 构建 SkillGroupRegistry（单一数据源）
        from core.skill.group_registry import SkillGroupRegistry

        skill_groups_cfg = (config.raw_config or {}).get("skill_groups", {})
        group_registry = SkillGroupRegistry(skill_groups_cfg)

        # 启动时校验：检测未归入任何分组的 skill
        all_non_system = {
            e.name for e in skills_loader.get_enabled_skills()
            if e.backend_type.value != "tool"
            and not (e.raw_config or {}).get("system", False)
        }
        group_registry.validate_and_warn(all_non_system)

        # 构建 Skills 提示词并注入到运行时上下文
        skills_prompt = await skills_loader.build_skills_prompt()
        if skills_prompt and hasattr(prompt_cache, "runtime_context") and prompt_cache.runtime_context:
            prompt_cache.runtime_context["skills_prompt"] = skills_prompt
            logger.info(f"   Skills 提示词: {len(skills_prompt)} 字符已注入（Fallback 用）")

            # V12: 注入 loader 引用和 group_registry
            prompt_cache.runtime_context["_skills_loader"] = skills_loader
            prompt_cache.runtime_context["_skill_group_registry"] = group_registry
            logger.info(
                f"   SkillGroupRegistry 已注入: {group_registry}"
            )
    elif config.skills:
        # 旧格式兼容
        agent._skills_loader = None
        agent._instance_skills = config.skills
        enabled_instance_skills = [s for s in config.skills if s.enabled]
        if enabled_instance_skills:
            logger.info(f"   注入实例级 Skills: {len(enabled_instance_skills)} 个已启用")
            for skill in enabled_instance_skills:
                logger.debug(f"      • {skill.name}")
    else:
        agent._skills_loader = None
        agent._instance_skills = []

    # 9. 🆕 创建实例级工具注册表
    from core.tool import InstanceRegistry, create_tool_loader, get_capability_registry

    global_registry = get_capability_registry()

    # 🆕 V5.1: 使用 ToolLoader 统一加载工具
    tool_loader = create_tool_loader(global_registry)

    # 加载所有工具（通用工具、Claude Skills）（异步）
    load_result = await tool_loader.load_tools(
        enabled_capabilities=config.enabled_capabilities,
        skills=config.skills,
    )

    # 创建过滤后的注册表
    filtered_registry = tool_loader.create_filtered_registry(config.enabled_capabilities)

    # 使用过滤后的 registry 创建实例级注册表
    instance_registry = InstanceRegistry(global_registry=filtered_registry)
    agent._instance_registry = instance_registry  # 注入到 Agent

    # 🔧 FIX: 更新 capability_registry、tool_executor、tool_selector 使用 filtered_registry
    # 原问题：tool_executor 使用全局 Registry，导致被过滤掉的工具（如 hitl）找不到
    # 修复：重新创建 tool_executor 和 tool_selector，使用 filtered_registry
    from core.tool import create_tool_executor, create_tool_selector
    from core.tool.types import create_tool_context

    agent.capability_registry = filtered_registry

    # 重新创建 tool_executor
    agent._tool_executor = create_tool_executor(
        registry=filtered_registry,
        tool_context=create_tool_context(
            event_manager=agent.event_manager, apis_config=getattr(agent, "apis_config", None)
        ),
        enable_compaction=(
            getattr(agent._tool_executor, "enable_compaction", True)
            if agent._tool_executor
            else True
        ),
    )

    # 重新创建 tool_selector（如果存在）
    if hasattr(agent, "tool_selector") and agent.tool_selector is not None:
        agent.tool_selector = create_tool_selector(registry=filtered_registry)

    logger.info(
        f"   ✅ ToolExecutor/ToolSelector 已更新，使用过滤后的 Registry ({len(filtered_registry.capabilities)} 个工具)"
    )

    # 🆕 V4.6: 加载工具推断缓存（用于增量推断）
    tools_cache_file = cache_dir / "tools_inference.json"
    if tools_cache_file.exists() and not force_refresh:
        await instance_registry.load_inference_cache(tools_cache_file)
        logger.info("✅ 已加载工具推断缓存")

    # 10. 注册 Claude Skills（如果配置了）
    if not skip_skills_registration and config.skills:
        enabled_skills = [s for s in config.skills if s.enabled]
        if enabled_skills:
            # TODO: _register_skills 函数未实现，需要补充
            logger.warning(
                f"⚠️ Claude Skills 注册功能未实现: {[s.skill_name for s in enabled_skills]}"
            )

    # 🆕 V4.6: 保存工具推断缓存（包含新推断的工具）
    cache_dir.mkdir(parents=True, exist_ok=True)
    await instance_registry.save_inference_cache(tools_cache_file)
    logger.info("✅ 已保存工具推断缓存")

    # 11. 统一工具统计（仅用于调试日志）
    # 注意：Plan 阶段只使用 capability_categories，不使用具体工具列表
    all_tools = instance_registry.get_all_tools_unified()
    logger.info(f"📋 工具统计: {len(all_tools)} 个（全局+实例），仅供调试")
    logger.debug(f"   工具列表: {[t['name'] for t in all_tools]}")

    logger.info(f"🎉 实例 {instance_name} 加载完成")

    return agent


async def validate_skill_directory(skill_path: Path) -> Dict[str, Any]:
    """
    验证 Skill 目录结构

    参考官方文档：https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices

    检查项：
    - SKILL.md 存在
    - YAML frontmatter 格式正确
    - name 字段：最大 64 字符，只能包含小写字母、数字和连字符，不能包含保留词
    - description 字段：必须非空，最大 1024 字符，不能包含 XML 标签
    - 总大小不超过 8MB
    - SKILL.md 正文推荐不超过 500 行

    Args:
        skill_path: Skill 目录路径

    Returns:
        验证结果字典：
        {
            "valid": bool,
            "errors": List[str],
            "warnings": List[str],
            "info": Dict[str, Any]
        }
    """
    import re

    import yaml

    result = {"valid": True, "errors": [], "warnings": [], "info": {}}

    # 保留词（不能用于 name）
    RESERVED_WORDS = ["anthropic", "claude"]

    # 检查目录存在
    if not skill_path.exists():
        result["valid"] = False
        result["errors"].append(f"目录不存在: {skill_path}")
        return result

    # 检查 SKILL.md 存在
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        result["valid"] = False
        result["errors"].append("SKILL.md 文件不存在")
        return result

    # 读取并验证 SKILL.md
    async with aiofiles.open(skill_md, "r", encoding="utf-8") as f:
        content = await f.read()

    # 检查 YAML frontmatter 格式
    if not content.startswith("---"):
        result["valid"] = False
        result["errors"].append("SKILL.md 必须以 YAML frontmatter (---) 开头")
    else:
        try:
            # 提取 frontmatter
            end_idx = content.index("---", 3)
            frontmatter_str = content[3:end_idx].strip()
            body_content = content[end_idx + 3 :].strip()

            # 解析 YAML
            try:
                frontmatter = yaml.safe_load(frontmatter_str) or {}
            except yaml.YAMLError as e:
                result["valid"] = False
                result["errors"].append(f"YAML 解析错误: {str(e)}")
                frontmatter = {}

            # ===== name 字段验证（官方文档要求）=====
            name = frontmatter.get("name", "")

            if not name:
                result["valid"] = False
                result["errors"].append("YAML frontmatter 缺少 'name' 字段")
            else:
                # 最大 64 字符
                if len(name) > 64:
                    result["valid"] = False
                    result["errors"].append(f"name 超过 64 字符 (当前: {len(name)})")

                # 只能包含小写字母、数字和连字符
                if not re.match(r"^[a-z0-9-]+$", name):
                    result["valid"] = False
                    result["errors"].append(f"name 只能包含小写字母、数字和连字符: '{name}'")

                # 不能包含 XML 标签
                if re.search(r"<[^>]+>", name):
                    result["valid"] = False
                    result["errors"].append("name 不能包含 XML 标签")

                # 不能包含保留词
                for reserved in RESERVED_WORDS:
                    if reserved in name.lower():
                        result["valid"] = False
                        result["errors"].append(f"name 不能包含保留词 '{reserved}'")

            result["info"]["name"] = name

            # ===== description 字段验证（官方文档要求）=====
            description = frontmatter.get("description") or ""

            # 确保是字符串类型
            if not isinstance(description, str):
                description = str(description) if description else ""

            if not description.strip():
                result["valid"] = False
                result["errors"].append("YAML frontmatter 缺少 'description' 字段或为空")
            else:
                # 最大 1024 字符
                if len(description) > 1024:
                    result["valid"] = False
                    result["errors"].append(
                        f"description 超过 1024 字符 (当前: {len(description)})"
                    )

                # 不能包含 XML 标签
                if re.search(r"<[^>]+>", description):
                    result["valid"] = False
                    result["errors"].append("description 不能包含 XML 标签")

            result["info"]["description"] = (
                (description[:100] + "...")
                if description and len(description) > 100
                else description
            )
            result["info"]["frontmatter_size"] = len(frontmatter_str)

            # ===== SKILL.md 正文行数检查（官方推荐）=====
            body_lines = len(body_content.split("\n"))
            result["info"]["body_lines"] = body_lines

            if body_lines > 500:
                result["warnings"].append(
                    f"SKILL.md 正文超过 500 行 (当前: {body_lines})，建议拆分到单独文件"
                )

        except ValueError:
            result["valid"] = False
            result["errors"].append("YAML frontmatter 格式无效（缺少结束 ---）")

    # 检查总大小（8MB 限制）
    total_size = sum(f.stat().st_size for f in skill_path.rglob("*") if f.is_file())
    result["info"]["total_size_mb"] = total_size / (1024 * 1024)

    if total_size > 8 * 1024 * 1024:
        result["valid"] = False
        result["errors"].append(f"总大小超过 8MB (当前: {total_size / (1024 * 1024):.2f} MB)")

    # 统计文件信息
    files = list(skill_path.rglob("*"))
    result["info"]["file_count"] = len([f for f in files if f.is_file()])
    result["info"]["has_scripts"] = (skill_path / "scripts").exists()
    result["info"]["has_reference"] = (skill_path / "REFERENCE.md").exists()

    return result


async def _update_skill_registry(instance_name: str, skills: List[SkillConfig]) -> None:
    """
    更新 skill_registry.yaml

    Args:
        instance_name: 实例名称
        skills: 更新后的 Skill 配置列表
    """
    import yaml

    registry_path = get_instances_dir() / instance_name / "skills" / "skill_registry.yaml"

    if not registry_path.exists():
        return

    async with aiofiles.open(registry_path, "r", encoding="utf-8") as f:
        content = await f.read()
        registry = yaml.safe_load(content) or {}

    # 更新 skills 列表
    skills_data = []
    for skill in skills:
        skill_dict = {
            "name": skill.name,
            "enabled": skill.enabled,
            "description": skill.description,
        }
        skills_data.append(skill_dict)

    registry["skills"] = skills_data

    # 异步写回文件
    output = yaml.dump(registry, default_flow_style=False, allow_unicode=True, sort_keys=False)
    async with aiofiles.open(registry_path, "w", encoding="utf-8") as f:
        await f.write(output)


# ============================================================
# Skills 管理功能
# ============================================================


async def scan_skills_directory(instance_name: str) -> List[SkillConfig]:
    """
    扫描实例目录中的所有 Skills

    Args:
        instance_name: 实例名称

    Returns:
        SkillConfig 列表
    """
    import yaml

    skills_dir = get_instances_dir() / instance_name / "skills"

    if not skills_dir.exists():
        return []

    # 加载现有注册表
    registry_path = skills_dir / "skill_registry.yaml"
    registered_skills = {}
    if registry_path.exists():
        async with aiofiles.open(registry_path, "r", encoding="utf-8") as f:
            content = await f.read()
            registry = yaml.safe_load(content) or {}
        for s in registry.get("skills", []):
            if isinstance(s, dict):
                registered_skills[s.get("name")] = s

    skills = []

    # 扫描 skills 目录
    for skill_dir in skills_dir.iterdir():
        if not skill_dir.is_dir():
            continue

        # 跳过特殊目录
        if skill_dir.name.startswith("_") or skill_dir.name == "__pycache__":
            continue

        # 检查 SKILL.md 是否存在
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue

        # 获取已注册信息
        registered_info = registered_skills.get(skill_dir.name, {})

        # 从 SKILL.md 提取描述
        description = registered_info.get("description", "")
        if not description:
            try:
                async with aiofiles.open(skill_md, "r", encoding="utf-8") as f:
                    content = await f.read()
                if content.startswith("---"):
                    end_idx = content.index("---", 3)
                    frontmatter = content[3:end_idx].strip()
                    metadata = yaml.safe_load(frontmatter)
                    description = metadata.get("description", skill_dir.name)
            except (FileNotFoundError, ValueError, yaml.YAMLError) as e:
                logger.debug(f"无法读取 skill 元数据: {e}")
                description = skill_dir.name

        skills.append(
            SkillConfig(
                name=skill_dir.name,
                enabled=registered_info.get("enabled", True),
                description=description,
                skill_path=skill_dir,
            )
        )

    return skills


async def get_skills_status(instance_name: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """
    获取 Skills 状态

    Args:
        instance_name: 实例名称（None 则获取所有实例）

    Returns:
        {instance_name: [{"name": ..., "enabled": ..., "status": ...}, ...]}
    """
    status = {}

    instances = [instance_name] if instance_name else list_instances()

    for inst in instances:
        skills = await scan_skills_directory(inst)
        inst_status = []

        for skill in skills:
            skill_status = "enabled" if skill.enabled else "disabled"

            inst_status.append(
                {
                    "name": skill.name,
                    "enabled": skill.enabled,
                    "description": skill.description,
                    "status": skill_status,
                }
            )

        status[inst] = inst_status

    return status


async def print_skills_status(instance_name: Optional[str] = None):
    """打印 Skills 状态"""
    print("\n📋 Skills 状态总览")
    print("=" * 70)

    status = await get_skills_status(instance_name)

    if not status:
        print("  没有找到任何实例")
        return

    total_skills = 0

    for inst_name, skills in status.items():
        print(f"\n📦 实例: {inst_name}")
        print("-" * 50)

        if not skills:
            print("  (无 Skills)")
            continue

        for skill in skills:
            total_skills += 1

            if skill["status"] == "enabled":
                icon = "✅"
                text = "已启用"
            else:
                icon = "⏸️"
                text = "已禁用"

            desc = (
                skill["description"][:40] + "..."
                if len(skill["description"]) > 40
                else skill["description"]
            )
            print(f"  {icon} {skill['name']}")
            print(f"     描述: {desc}")
            print(f"     状态: {text}")

    print("\n" + "=" * 70)
    print(f"📊 总计: {total_skills} 个 Skills")


# ============================================================
# 便捷函数
# ============================================================


async def quick_load(instance_name: str):
    """
    快速加载实例（便捷函数）

    Args:
        instance_name: 实例名称

    Returns:
        Agent 实例
    """
    return await create_agent_from_instance(instance_name)


def print_available_instances():
    """打印所有可用实例"""
    instances = list_instances()

    if not instances:
        print("📭 没有可用的实例")
        print(f"   请在 {get_instances_dir()} 目录下创建实例")
        return

    print(f"📦 可用实例 ({len(instances)} 个):")
    for name in instances:
        try:
            config = asyncio.run(load_instance_config(name))
            print(f"   • {name}: {config.description or '(无描述)'}")
        except Exception as e:
            print(f"   • {name}: ⚠️ 配置加载失败 ({str(e)})")


# ============================================================
# CLI 入口
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="智能体实例加载器 & Skills 管理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 实例管理
  python utils/instance_loader.py --list                     # 列出所有实例
  python utils/instance_loader.py -i dazee_agent --info      # 显示实例详情
  
  # Skills 管理
  python utils/instance_loader.py --skills-status            # 查看所有实例的 Skills 状态
  python utils/instance_loader.py -i dazee_agent --skills-status  # 查看指定实例
        """,
    )

    # 实例相关参数
    parser.add_argument("--list", "-l", action="store_true", help="列出所有可用实例")
    parser.add_argument("--instance", "-i", type=str, help="指定实例名称")
    parser.add_argument("--info", action="store_true", help="显示实例详细信息")

    # Skills 管理参数
    parser.add_argument("--skills-status", action="store_true", help="显示 Skills 状态")

    args = parser.parse_args()

    try:
        # ==================== 实例管理 ====================
        if args.list:
            print_available_instances()

        # ==================== Skills 状态 ====================
        elif args.skills_status:
            print_skills_status(args.instance)

        # ==================== 显示实例信息 ====================
        elif args.instance and args.info:
            config = asyncio.run(load_instance_config(args.instance))
            print(f"📋 实例信息: {args.instance}")
            print(f"   名称: {config.name}")
            print(f"   描述: {config.description}")
            print(f"   版本: {config.version}")
            print(f"   模型: {config.model or '默认'}")
            print(f"   Mem0: {'启用' if config.mem0_enabled else '禁用'}")

            # LLM 超参数
            llm = config.llm_params
            llm_info = []
            if llm.temperature is not None:
                llm_info.append(f"temperature={llm.temperature}")
            if llm.max_tokens is not None:
                llm_info.append(f"max_tokens={llm.max_tokens}")
            if llm.enable_thinking is not None:
                llm_info.append(f"thinking={'开' if llm.enable_thinking else '关'}")
            if llm.thinking_mode is not None:
                llm_info.append(f"thinking_mode={llm.thinking_mode}")
            if llm.enable_caching is not None:
                llm_info.append(f"caching={'开' if llm.enable_caching else '关'}")

            if llm_info:
                print(f"   LLM 参数: {', '.join(llm_info)}")

            # Skills 信息（本地 Skill 系统）
            enabled_skills = [s for s in config.skills if s.enabled]
            print(f"   Skills: {len(config.skills)} 个 ({len(enabled_skills)} 启用)")
            for skill in config.skills:
                status = "✅" if skill.enabled else "⬜"
                print(f"      {status} {skill.name}")

            # APIs 信息（REST API 描述）
            print(f"   APIs: {len(config.apis)} 个")
            for api in config.apis:
                doc_status = f"文档: {api.doc}" if api.doc else "无文档"
                print(f"      • {api.name}: {api.base_url} ({doc_status})")

        else:
            parser.print_help()

    except Exception as e:
        print(f"❌ 错误: {str(e)}")
        import traceback

        traceback.print_exc()
        exit(1)

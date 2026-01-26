"""
实例加载器 - Instance Loader

职责：
- 加载 instances/ 目录下的智能体实例配置
- 合并 prompt.md 和框架通用提示词
- 调用 AgentFactory 创建 Agent
- 注册 MCP 工具
- 自动注册 Claude Skills（启动时）

设计原则：
- Prompt-First：提示词是配置的核心
- 无代码化：运营只需编辑配置文件
- 利用现有 AgentFactory
- Skills 自动生命周期管理
"""

import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from logger import get_logger

logger = get_logger("instance_loader")


@dataclass
class SkillConfig:
    """Skill 配置数据类（Claude Skills 官方 API）"""
    name: str
    enabled: bool = True
    description: str = ""
    skill_id: Optional[str] = None  # 注册后回写
    registered_at: Optional[str] = None  # 注册时间
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
    
    # MCP 工具配置
    mcp_tools: List[Dict[str, Any]] = field(default_factory=list)
    
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
    
    # Multi-Agent 配置（暂时禁用，作为待扩展功能）
    multi_agent_enabled: bool = False
    max_concurrent_workers: int = 5
    workers: List[Any] = field(default_factory=list)
    
    # 原始配置
    raw_config: Dict[str, Any] = field(default_factory=dict)


def get_instances_dir() -> Path:
    """获取 instances 目录路径"""
    return PROJECT_ROOT / "instances"


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


def load_skill_registry(instance_name: str) -> List[SkillConfig]:
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
    
    with open(registry_path, "r", encoding="utf-8") as f:
        registry = yaml.safe_load(f) or {}
    
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
        
        # 检查 Skill 目录是否存在
        skill_path = skills_dir / name
        if not skill_path.exists():
            logger.warning(f"⚠️ Skill 目录不存在: {skill_path}")
            continue
        
        # 检查 SKILL.md 是否存在
        skill_md = skill_path / "SKILL.md"
        if not skill_md.exists():
            logger.warning(f"⚠️ Skill 入口文件不存在: {skill_md}")
            continue
        
        result.append(SkillConfig(
            name=name,
            enabled=skill_data.get("enabled", True),
            description=skill_data.get("description", ""),
            skill_id=skill_data.get("skill_id"),
            registered_at=skill_data.get("registered_at"),
            skill_path=skill_path
        ))
    
    return result


def load_instance_config(instance_name: str) -> InstanceConfig:
    """
    加载实例配置
    
    Args:
        instance_name: 实例名称（目录名）
        
    Returns:
        InstanceConfig 实例配置
        
    Raises:
        FileNotFoundError: 实例不存在
        ValueError: 配置格式错误
    """
    import yaml
    
    instance_dir = get_instances_dir() / instance_name
    
    if not instance_dir.exists():
        raise FileNotFoundError(f"实例不存在: {instance_name}")
    
    # 加载 config.yaml（可选）
    config_path = instance_dir / "config.yaml"
    raw_config = {}
    
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            raw_config = yaml.safe_load(f) or {}
    
    # 解析配置
    instance_info = raw_config.get("instance", {})
    agent_config = raw_config.get("agent", {})
    memory_config = raw_config.get("memory", {})
    mcp_tools = raw_config.get("mcp_tools", [])
    
    # 解析 LLM 超参数
    llm_config = agent_config.get("llm", {})
    llm_params = LLMParams(
        temperature=llm_config.get("temperature"),
        max_tokens=llm_config.get("max_tokens"),
        enable_thinking=llm_config.get("enable_thinking"),
        thinking_budget=llm_config.get("thinking_budget"),
        enable_caching=llm_config.get("enable_caching"),
        top_p=llm_config.get("top_p"),
        thinking_mode=llm_config.get("thinking_mode")  # 思考模式: native/simulated/none
    )
    
    # 加载 Skills 配置（Claude Skills 官方 API）
    skills = load_skill_registry(instance_name)
    
    # 加载 APIs 配置（REST API 描述）
    apis = _load_apis_config(instance_name, raw_config.get("apis", []))
    
    # 解析通用工具启用配置
    enabled_capabilities_raw = raw_config.get("enabled_capabilities", {})
    enabled_capabilities = {}
    if isinstance(enabled_capabilities_raw, dict):
        # 将配置值转换为布尔值（1/True -> True, 0/False -> False）
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
        mcp_tools=mcp_tools if isinstance(mcp_tools, list) else [],
        skills=skills,
        apis=apis,
        enabled_capabilities=enabled_capabilities,
        # 高级配置（从 advanced 部分读取）
        intent_analyzer_enabled=intent_config.get("enabled"),
        intent_analyzer_use_llm=intent_config.get("use_llm"),
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
        # Multi-Agent 配置（暂时禁用）
        multi_agent_enabled=raw_config.get("multi_agent", {}).get("mode", "disabled") != "disabled",
        max_concurrent_workers=raw_config.get("multi_agent", {}).get("max_parallel_workers", 5),
        workers=[],  # Workers 暂不解析，待扩展
        raw_config=raw_config
    )


def _load_apis_config(instance_name: str, apis_raw: List[Dict]) -> List[ApiConfig]:
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
        auth_header = auth.get("header", "Authorization") if isinstance(auth, dict) else "Authorization"
        auth_env = auth.get("env") if isinstance(auth, dict) else None
        
        # 加载 API 描述文档
        doc_name = api_data.get("doc")
        doc_content = ""
        if doc_name:
            doc_path = api_desc_dir / f"{doc_name}.md"
            if doc_path.exists():
                doc_content = doc_path.read_text(encoding="utf-8")
                logger.info(f"   📄 已加载 API 文档: {doc_path.name}")
            else:
                logger.warning(f"⚠️ API 文档不存在: {doc_path}")
        
        result.append(ApiConfig(
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
        ))
    
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
                masked_value = f"{auth_value[:10]}...{auth_value[-4:]}" if len(auth_value) > 14 else "***"
                logger.info(f"   🔑 API {api.name}: 已配置认证 (token: {masked_value})")
            else:
                logger.warning(f"⚠️ API {api.name}: 环境变量 {api.auth_env} 未设置（当前环境变量列表中无此项）")
        
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
    
    sections.append("""
> 💡 调用 API 时，使用 `api_calling` 工具：
> - `url`: 完整 URL（base_url + 路径）
> - `method`: HTTP 方法
> - `body`: 请求体（JSON）
> - 认证头已自动配置
""")
    
    return "\n".join(sections)


def load_instance_prompt(instance_name: str) -> str:
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
    
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def load_instance_env(instance_name: str) -> None:
    """
    加载实例环境变量
    
    Args:
        instance_name: 实例名称
    """
    import os
    
    try:
        from dotenv import load_dotenv
    except ImportError:
        logger.warning("❌ python-dotenv 未安装，跳过 .env 加载")
        return
    
    env_path = get_instances_dir() / instance_name / ".env"
    logger.info(f"🔍 检查实例 .env 文件: {env_path}")
    
    if env_path.exists():
        # 加载前检查关键环境变量
        coze_before = os.getenv("COZE_API_KEY", "")
        
        result = load_dotenv(env_path, override=True)
        
        # 加载后检查
        coze_after = os.getenv("COZE_API_KEY", "")
        
        if coze_after and coze_after != coze_before:
            masked = f"{coze_after[:10]}...{coze_after[-4:]}" if len(coze_after) > 14 else "***"
            logger.info(f"✅ 已加载环境变量: {env_path} (COZE_API_KEY: {masked})")
        elif coze_after:
            logger.info(f"✅ 已加载环境变量: {env_path} (COZE_API_KEY 未变化)")
        else:
            logger.warning(f"⚠️ 已加载 .env 但 COZE_API_KEY 仍为空: {env_path}")
    else:
        logger.warning(f"⚠️ .env 文件不存在: {env_path}")


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
    
    # === LLM 参数配置覆盖（V6.3 支持 Prompt Caching）===
    # 注意：这些参数只影响通过 instance_config.llm_params 创建的 LLM service
    # 不会影响已经从 profiles.yaml 加载的 LLM profile
    # 此处用于记录配置意图，实际 LLM service 创建时会优先使用 profile
    # （但保留此逻辑，供未来扩展使用）
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
        logger.debug(f"📝 config.yaml 覆盖了 {llm_override_count} 项 LLM 参数 (注意：需要检查是否被 profile 覆盖)")
    
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
    
    # === 记录合并结果 ===
    override_count = sum([
        config.model is not None,
        config.max_turns is not None,
        config.allow_parallel_tools is not None,
        config.plan_manager_enabled is not None,
        config.plan_manager_max_steps is not None,
        config.plan_manager_granularity is not None,
        config.intent_analyzer_enabled is not None,
        config.intent_analyzer_use_llm is not None,
        config.output_format is not None,
        config.output_code_highlighting is not None,
        config.output_json_model_name is not None,
        config.output_json_schema is not None,
        config.output_strict_json_validation is not None,
        config.output_json_ensure_ascii is not None,
        config.output_json_indent is not None,
    ])
    
    if override_count > 0:
        logger.info(f"✅ config.yaml 覆盖了 {override_count} 项 Schema 配置")
    else:
        logger.info("✅ config.yaml 无显式配置，使用 Schema 默认值")
    
    return merged


async def create_agent_from_instance(
    instance_name: str,
    event_manager = None,
    conversation_service = None,
    skip_mcp_registration: bool = False,
    skip_skills_registration: bool = False,
    force_refresh: bool = False
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
    7. 注册 MCP 工具
    8. 注册 Claude Skills
    9. 保存工具推断缓存
    
    Args:
        instance_name: 实例名称
        event_manager: 事件管理器
        conversation_service: 会话服务
        skip_mcp_registration: 是否跳过 MCP 工具注册
        skip_skills_registration: 是否跳过 Skills 注册
        force_refresh: 强制刷新缓存，重新生成 Schema 和推断工具
        
    Returns:
        配置好的 Agent 实例
    """
    from core.agent import AgentFactory
    from prompts.universal_agent_prompt import get_universal_agent_prompt
    from pathlib import Path
    
    logger.info(f"🚀 开始加载实例: {instance_name}")
    
    # 准备缓存目录
    instance_path = get_instances_dir() / instance_name
    cache_dir = instance_path / ".cache"
    
    if force_refresh:
        logger.info("🔄 强制刷新缓存模式")
    
    # 1. 加载环境变量
    load_instance_env(instance_name)
    
    # 2. 加载实例配置
    config = load_instance_config(instance_name)
    logger.info(f"   配置: {config.name} v{config.version}")
    logger.info(f"   描述: {config.description}")
    logger.info(f"   Skills: {len(config.skills)} 个")
    logger.info(f"   APIs: {len(config.apis)} 个")
    
    # 🆕 V6.0 显示 Multi-Agent 配置
    # 注意：只有当 multi_agent_enabled=True 时才显示 Workers 信息
    if config.multi_agent_enabled:
        enabled_workers = [w for w in config.workers if w.enabled]
        logger.info(f"   Multi-Agent: 已启用 (最大并发: {config.max_concurrent_workers})")
        if config.workers:
            logger.info(f"   Workers: {len(config.workers)} 个 ({len(enabled_workers)} 启用)")
            for worker in enabled_workers:
                logger.info(f"      • {worker.name} ({worker.specialization})")
    else:
        logger.info(f"   Multi-Agent: 已禁用（使用 SimpleAgent）")
    
    # 3. 加载实例提示词
    instance_prompt = load_instance_prompt(instance_name)
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
        force_refresh=force_refresh
    )
    
    # 打印缓存状态
    cache_status = prompt_cache.get_status()
    persistence_info = cache_status.get("persistence", {})
    metrics = cache_status.get("metrics", {})
    
    logger.info(f"✅ InstancePromptCache 加载完成")
    logger.info(f"   Agent: {prompt_cache.agent_schema.name if prompt_cache.agent_schema else 'Default'}")
    logger.info(f"   提示词版本: Simple={len(prompt_cache.system_prompt_simple or '')}字符, "
                f"Medium={len(prompt_cache.system_prompt_medium or '')}字符, "
                f"Complex={len(prompt_cache.system_prompt_complex or '')}字符")
    
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
    # 而是让 SimpleAgent 运行时根据任务复杂度动态获取缓存版本
    apis_prompt = _build_apis_prompt_section(config.apis)
    framework_prompt = get_universal_agent_prompt()
    
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
    
    logger.info(f"   运行时上下文: APIs={len(apis_prompt)} 字符, Framework={len(framework_prompt)} 字符")
    logger.info(f"   缓存版本: Simple={len(prompt_cache.system_prompt_simple or '')} 字符, "
                f"Medium={len(prompt_cache.system_prompt_medium or '')} 字符, "
                f"Complex={len(prompt_cache.system_prompt_complex or '')} 字符")
    
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
        
        # 注入 multi_agent 配置到合并后的 Schema
        if config.multi_agent_enabled:
            from core.multi_agent.config import MultiAgentConfig
            
            multi_agent_config = MultiAgentConfig.from_dict(config.raw_config.get("multi_agent", {}))
            merged_schema.multi_agent = multi_agent_config
            
            logger.info(f"✅ 注入 multi_agent 配置到 AgentSchema: mode={multi_agent_config.mode.value}")
        
        # 更新 prompt_cache 中的 agent_schema（供后续使用）
        prompt_cache.agent_schema = merged_schema
        
        # 创建 Agent，使用合并后的 Schema
        # prompt_cache 包含：
        # - system_prompt_simple/medium/complex（缓存版本）
        # - runtime_context（APIs + framework 运行时追加）
        agent = AgentFactory.from_schema(
            schema=merged_schema,
            system_prompt=None,  # 运行时从 prompt_cache 动态获取
            event_manager=event_manager,
            conversation_service=conversation_service,
            prompt_cache=prompt_cache,
        )
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
    
    # 🆕 V6.0: 注入 Workers 配置（仅当 Multi-Agent 启用时）
    if config.multi_agent_enabled:
        agent.workers_config = config.workers
        if config.workers:
            enabled_workers = [w for w in config.workers if w.enabled]
            logger.info(f"   注入 Workers 配置: {len(enabled_workers)} 个启用")
    else:
        agent.workers_config = []  # 禁用时清空 Workers 配置
    
    # 9. 🆕 创建实例级工具注册表
    from core.tool import InstanceToolRegistry, get_capability_registry, create_tool_loader
    
    global_registry = get_capability_registry()
    
    # 🆕 V5.1: 使用 ToolLoader 统一加载工具
    tool_loader = create_tool_loader(global_registry)
    
    # 加载所有工具（通用工具、MCP 工具、Claude Skills）
    load_result = tool_loader.load_tools(
        enabled_capabilities=config.enabled_capabilities,
        mcp_tools=config.mcp_tools,
        skills=config.skills,
    )
    
    # 创建过滤后的注册表
    filtered_registry = tool_loader.create_filtered_registry(config.enabled_capabilities)
    
    # 使用过滤后的 registry 创建实例级注册表
    instance_registry = InstanceToolRegistry(global_registry=filtered_registry)
    agent._instance_registry = instance_registry  # 注入到 Agent
    
    # 🆕 V4.6: 加载工具推断缓存（用于增量推断）
    tools_cache_file = cache_dir / "tools_inference.json"
    if tools_cache_file.exists() and not force_refresh:
        await instance_registry.load_inference_cache(tools_cache_file)
        logger.info("✅ 已加载工具推断缓存")
    
    # 10. 注册 MCP 工具（使用 InstanceToolRegistry，利用缓存）
    if not skip_mcp_registration and config.mcp_tools:
        await _register_mcp_tools(agent, config.mcp_tools, instance_registry)
    
    # 11. 注册 Claude Skills（如果配置了）
    if not skip_skills_registration and config.skills:
        enabled_skills = [s for s in config.skills if s.enabled]
        if enabled_skills:
            await _register_skills(instance_name, enabled_skills)
    
    # 🆕 V4.6: 保存工具推断缓存（包含新推断的工具）
    cache_dir.mkdir(parents=True, exist_ok=True)
    await instance_registry.save_inference_cache(tools_cache_file)
    logger.info("✅ 已保存工具推断缓存")
    
    # 12. 🆕 V4.6 统一工具统计（仅用于调试日志）
    # 注意：Plan 阶段只使用 capability_categories，不使用具体工具列表
    # MCP 工具通过 InstanceToolRegistry.get_tools_for_claude() 合并到 tools_for_llm
    all_tools = instance_registry.get_all_tools_unified()
    logger.info(f"📋 工具统计: {len(all_tools)} 个（全局+实例），仅供调试")
    logger.debug(f"   工具列表: {[t['name'] for t in all_tools]}")
    
    logger.info(f"🎉 实例 {instance_name} 加载完成")
    
    return agent


async def _register_mcp_tools(
    agent, 
    mcp_tools: List[Dict[str, Any]], 
    instance_registry=None
) -> List:
    """
    注册 MCP 工具（使用缓存，避免重复连接）
    
    🆕 V4.4 优化：
    - 同一个 MCP 服务器只连接一次，后续复用缓存的客户端
    - 统一注册到 InstanceToolRegistry，用于 Plan 阶段工具发现
    
    Args:
        agent: Agent 实例
        mcp_tools: MCP 工具配置列表
        instance_registry: 实例级工具注册表（可选）
        
    Returns:
        已连接的 MCP 客户端列表
    """
    from services.mcp_client import create_mcp_tool_definition
    from infra.pools import get_mcp_pool
    
    connected_clients = []
    mcp_tool_definitions = []  # Claude API 格式的工具定义
    mcp_pool = get_mcp_pool()  # 使用统一的 MCPPool 管理连接
    
    for tool_config in mcp_tools:
        name = tool_config.get("name", "unknown")
        try:
            # 🆕 支持禁用 MCP 工具（在 config.yaml 中设置 enabled: false）
            if not tool_config.get("enabled", True):
                logger.info(f"⏭️ MCP 工具 {name} 已被禁用，跳过")
                continue
            
            server_url = tool_config.get("server_url")
            server_name = tool_config.get("server_name", name)
            auth_type = tool_config.get("auth_type", "none")
            auth_env = tool_config.get("auth_env")
            
            if not server_url:
                logger.warning(f"⚠️ MCP 工具 {name} 缺少 server_url，跳过")
                continue
            
            # 获取认证令牌
            auth_token = None
            if auth_type in ("bearer", "api_key") and auth_env:
                auth_token = os.getenv(auth_env)
                if not auth_token:
                    logger.warning(f"⚠️ MCP 工具 {name} 的密钥环境变量 {auth_env} 未设置")
                    continue
            
            logger.info(f"🔧 注册 MCP 工具: {name} ({server_url})")
            
            # 🆕 统一使用 MCPPool 获取 MCP 客户端（避免重复连接）
            try:
                client = await mcp_pool.get_client(
                    server_url=server_url,
                    server_name=server_name,
                    auth_token=auth_token
                )
            except Exception as conn_error:
                logger.error(f"❌ MCP 客户端连接异常，跳过工具 {name}: {type(conn_error).__name__}: {str(conn_error)}")
                continue
            
            # 🆕 处理连接失败的情况
            if client is None:
                logger.warning(f"⚠️ MCP 客户端连接失败，跳过工具 {name}")
                continue
            
            if client._connected:
                tools = client._tools
                if not tools:
                    # 如果工具列表为空，可能需要重新发现
                    tools_list = await client.discover_tools()
                    tools = {t['name']: t for t in tools_list}
                
                logger.info(f"   ✅ 注册成功: 发现 {len(tools)} 个工具")
                
                for tool_name, tool_info in tools.items():
                    # 🔍 显示工具的 input_schema 参数，便于调试
                    schema = tool_info.get("input_schema", {})
                    props = schema.get("properties", {}) if isinstance(schema, dict) else {}
                    param_info = f"参数: {list(props.keys())}" if props else "无参数定义"
                    logger.info(f"      • {tool_name} ({param_info})")
                    
                    # 创建 Claude API 格式的工具定义
                    tool_def = create_mcp_tool_definition(tool_info, client)
                    mcp_tool_definitions.append(tool_def)
                    
                    # 🆕 注册到 InstanceToolRegistry（用于 Plan 阶段工具发现）
                    # 注意：tool_name 已经带有 server_name_ 前缀（来自 mcp_client.discover_tools）
                    # 不要再重复加前缀！
                    if instance_registry:
                        # 获取原始工具名（不带前缀）
                        original_name = tool_info.get("original_name", tool_name)
                        
                        # 🆕 V4.6: 获取 capability（用户意图类别）
                        capability = tool_config.get("capability")  # 从 config.yaml 读取
                        
                        # 创建处理器闭包（动态获取客户端，支持断线重连）
                        async def make_handler(_server_url, _server_name, _auth_token, _orig_name):
                            async def handler(tool_input: Dict[str, Any]):
                                # 每次调用时动态获取客户端（断开时会创建新连接）
                                from infra.pools import get_mcp_pool
                                pool = get_mcp_pool()
                                current_client = await pool.get_client(
                                    server_url=_server_url,
                                    server_name=_server_name,
                                    auth_token=_auth_token
                                )
                                if not current_client:
                                    return {"success": False, "error": "MCP 服务器连接失败"}
                                
                                # 调用工具
                                result = await current_client.call_tool(_orig_name, tool_input)
                                
                                # 如果需要重连，自动重试一次
                                if result.get("_need_reconnect"):
                                    # 强制重连
                                    current_client = await pool.get_client(
                                        server_url=_server_url,
                                        server_name=_server_name,
                                        auth_token=_auth_token,
                                        force_reconnect=True
                                    )
                                    if not current_client:
                                        return {"success": False, "error": "MCP 服务器重连失败"}
                                    result = await current_client.call_tool(_orig_name, tool_input)
                                
                                return result
                            return handler
                        
                        handler = await make_handler(server_url, server_name, auth_token, original_name)
                        
                        # 使用已带前缀的 tool_name，不要再加前缀
                        await instance_registry.register_mcp_tool(
                            name=tool_name,  # 🆕 直接使用 tool_name，不再加前缀
                            server_url=server_url,
                            server_name=server_name,
                            tool_info=tool_info,
                            mcp_client=client,
                            handler=handler,
                            capability=capability  # 🆕 传递 capability
                        )
                
                # 保存客户端引用
                connected_clients.append(client)
                
                # 将 MCP 客户端添加到 Agent
                if hasattr(agent, '_mcp_clients'):
                    if client not in agent._mcp_clients:
                        agent._mcp_clients.append(client)
                else:
                    agent._mcp_clients = [client]
            else:
                logger.warning(f"   ⚠️ 连接失败")
                
        except Exception as e:
            logger.error(f"❌ 注册 MCP 工具 {name} 失败: {type(e).__name__}: {str(e)}", exc_info=True)
            # 确保即使发生异常也继续处理下一个工具
            continue
    
    # 将 MCP 工具定义注入到 Agent（兼容旧逻辑）
    if mcp_tool_definitions and hasattr(agent, '_mcp_tools'):
        agent._mcp_tools.extend(mcp_tool_definitions)
    elif mcp_tool_definitions:
        agent._mcp_tools = mcp_tool_definitions
        
    # 注册 MCP 工具到 tool_executor 的处理器（动态获取客户端，支持断线重连）
    if mcp_tool_definitions and hasattr(agent, 'tool_executor'):
        for tool_def in mcp_tool_definitions:
            tool_name = tool_def['name']
            original_name = tool_def['_original_name']
            # 从 tool_def 获取连接信息（用于重连）
            server_url = tool_def.get('_server_url')
            server_name_for_handler = tool_def.get('_server_name')
            auth_token_for_handler = tool_def.get('_auth_token')
            
            # 创建工具处理器（动态获取客户端，支持自动重连）
            async def mcp_handler(
                tool_input: Dict[str, Any], 
                _url=server_url, 
                _name=server_name_for_handler, 
                _token=auth_token_for_handler,
                _orig_name=original_name
            ):
                from infra.pools import get_mcp_pool
                pool = get_mcp_pool()
                current_client = await pool.get_client(
                    server_url=_url,
                    server_name=_name,
                    auth_token=_token
                )
                if not current_client:
                    return {"success": False, "error": "MCP 服务器连接失败"}
                
                result = await current_client.call_tool(_orig_name, tool_input)
                
                # 如果需要重连，自动重试
                if result.get("_need_reconnect"):
                    current_client = await pool.get_client(
                        server_url=_url,
                        server_name=_name,
                        auth_token=_token,
                        force_reconnect=True
                    )
                    if not current_client:
                        return {"success": False, "error": "MCP 服务器重连失败"}
                    result = await current_client.call_tool(_orig_name, tool_input)
                
                return result
            
            # 注册处理器
            agent.tool_executor.register_handler(tool_name, mcp_handler)
            logger.info(f"   📌 已注册 MCP 工具处理器: {tool_name}")
    
    return connected_clients


def validate_skill_directory(skill_path: Path) -> Dict[str, Any]:
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
    content = skill_md.read_text(encoding="utf-8")
    
    # 检查 YAML frontmatter 格式
    if not content.startswith("---"):
        result["valid"] = False
        result["errors"].append("SKILL.md 必须以 YAML frontmatter (---) 开头")
    else:
        try:
            # 提取 frontmatter
            end_idx = content.index("---", 3)
            frontmatter_str = content[3:end_idx].strip()
            body_content = content[end_idx + 3:].strip()
            
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
                if not re.match(r'^[a-z0-9-]+$', name):
                    result["valid"] = False
                    result["errors"].append(
                        f"name 只能包含小写字母、数字和连字符: '{name}'"
                    )
                
                # 不能包含 XML 标签
                if re.search(r'<[^>]+>', name):
                    result["valid"] = False
                    result["errors"].append("name 不能包含 XML 标签")
                
                # 不能包含保留词
                for reserved in RESERVED_WORDS:
                    if reserved in name.lower():
                        result["valid"] = False
                        result["errors"].append(
                            f"name 不能包含保留词 '{reserved}'"
                        )
            
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
                if re.search(r'<[^>]+>', description):
                    result["valid"] = False
                    result["errors"].append("description 不能包含 XML 标签")
            
            result["info"]["description"] = (description[:100] + "...") if description and len(description) > 100 else description
            result["info"]["frontmatter_size"] = len(frontmatter_str)
            
            # ===== SKILL.md 正文行数检查（官方推荐）=====
            body_lines = len(body_content.split('\n'))
            result["info"]["body_lines"] = body_lines
            
            if body_lines > 500:
                result["warnings"].append(
                    f"SKILL.md 正文超过 500 行 (当前: {body_lines})，建议拆分到单独文件"
                )
            
        except ValueError:
            result["valid"] = False
            result["errors"].append("YAML frontmatter 格式无效（缺少结束 ---）")
    
    # 检查总大小（8MB 限制）
    total_size = sum(
        f.stat().st_size for f in skill_path.rglob("*") if f.is_file()
    )
    result["info"]["total_size_mb"] = total_size / (1024 * 1024)
    
    if total_size > 8 * 1024 * 1024:
        result["valid"] = False
        result["errors"].append(
            f"总大小超过 8MB (当前: {total_size / (1024 * 1024):.2f} MB)"
        )
    
    # 统计文件信息
    files = list(skill_path.rglob("*"))
    result["info"]["file_count"] = len([f for f in files if f.is_file()])
    result["info"]["has_scripts"] = (skill_path / "scripts").exists()
    result["info"]["has_reference"] = (skill_path / "REFERENCE.md").exists()
    
    return result


async def _register_skills(
    instance_name: str,
    skills: List[SkillConfig]
) -> None:
    """
    自动注册 Claude Skills
    
    流程：
    1. 验证 Skill 目录结构
    2. 检查每个 Skill 是否已注册（有 skill_id）
    3. 未注册的调用 Anthropic API 注册
    4. 注册成功后回写 skill_id 到 skill_registry.yaml
    
    Args:
        instance_name: 实例名称
        skills: 启用的 Skill 配置列表
    """
    import yaml
    from datetime import datetime
    
    try:
        from anthropic import Anthropic
        from anthropic.lib import files_from_dir
    except ImportError:
        logger.warning("⚠️ anthropic 库未安装，跳过 Skills 注册")
        return
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("⚠️ ANTHROPIC_API_KEY 未设置，跳过 Skills 注册")
        return
    
    # 创建带 Skills beta 的客户端
    client = Anthropic(
        api_key=api_key,
        default_headers={"anthropic-beta": "skills-2025-10-02"}
    )
    
    logger.info(f"🎯 开始注册 Skills ({len(skills)} 个)")
    
    updated_skills = []
    has_updates = False
    
    for skill in skills:
        try:
            # 检查是否已注册
            if skill.skill_id:
                logger.info(f"   ⏭️ {skill.name}: 已注册 (skill_id={skill.skill_id})")
                updated_skills.append(skill)
                continue
            
            # 检查 Skill 路径
            if not skill.skill_path or not skill.skill_path.exists():
                logger.warning(f"   ⚠️ {skill.name}: Skill 目录不存在")
                updated_skills.append(skill)
                continue
            
            # 验证 Skill 目录结构（参考标准 validate_skill_directory）
            validation = validate_skill_directory(skill.skill_path)
            if not validation["valid"]:
                for error in validation["errors"]:
                    logger.warning(f"   ⚠️ {skill.name}: {error}")
                updated_skills.append(skill)
                continue
            
            logger.info(f"   🔧 注册 Skill: {skill.name}")
            logger.info(f"      目录验证通过 (大小: {validation['info']['total_size_mb']:.2f} MB)")
            
            # 调用 Anthropic API 注册（参考官方文档格式）
            # 参数: display_title（显示名称）, files（目录内容）, betas（API 版本）
            display_title = skill.description or skill.name
            skill_create = client.beta.skills.create(
                display_title=display_title,
                files=files_from_dir(str(skill.skill_path)),
                betas=["skills-2025-10-02"]
            )
            
            # 更新 skill_id（标准返回字段）
            skill.skill_id = skill_create.id
            skill.registered_at = datetime.now().isoformat()
            has_updates = True
            
            logger.info(f"      ✅ 注册成功: skill_id={skill.skill_id}")
            logger.info(f"         display_title={skill_create.display_title}")
            logger.info(f"         version={skill_create.latest_version}")
            updated_skills.append(skill)
            
        except Exception as e:
            logger.error(f"   ❌ {skill.name}: 注册失败 - {str(e)}")
            updated_skills.append(skill)
    
    # 回写 skill_registry.yaml
    if has_updates:
        _update_skill_registry(instance_name, updated_skills)
        logger.info(f"   💾 已更新 skill_registry.yaml")


def _update_skill_registry(instance_name: str, skills: List[SkillConfig]) -> None:
    """
    更新 skill_registry.yaml（回写 skill_id）
    
    Args:
        instance_name: 实例名称
        skills: 更新后的 Skill 配置列表
    """
    import yaml
    
    registry_path = get_instances_dir() / instance_name / "skills" / "skill_registry.yaml"
    
    if not registry_path.exists():
        return
    
    # 读取现有内容
    with open(registry_path, "r", encoding="utf-8") as f:
        content = f.read()
        registry = yaml.safe_load(content) or {}
    
    # 更新 skills 列表
    skills_data = []
    for skill in skills:
        skill_dict = {
            "name": skill.name,
            "enabled": skill.enabled,
            "description": skill.description,
        }
        if skill.skill_id:
            skill_dict["skill_id"] = skill.skill_id
        if skill.registered_at:
            skill_dict["registered_at"] = skill.registered_at
        skills_data.append(skill_dict)
    
    registry["skills"] = skills_data
    
    # 写回文件
    with open(registry_path, "w", encoding="utf-8") as f:
        yaml.dump(
            registry,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False
        )


# ============================================================
# Skills 管理功能（注册/注销/更新/状态）
# ============================================================

def get_anthropic_client():
    """
    获取带 Skills beta 的 Anthropic 客户端
    
    Returns:
        Anthropic 客户端实例
        
    Raises:
        ImportError: anthropic 库未安装
        ValueError: API Key 未配置
    """
    try:
        from anthropic import Anthropic
    except ImportError:
        raise ImportError("❌ anthropic 库未安装，请运行: pip install anthropic")
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("❌ ANTHROPIC_API_KEY 未配置，请在 .env 文件中设置")
    
    return Anthropic(
        api_key=api_key,
        default_headers={"anthropic-beta": "skills-2025-10-02"}
    )


def scan_skills_directory(instance_name: str) -> List[SkillConfig]:
    """
    扫描实例目录中的所有 Skills（包括未在 registry 中的）
    
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
        with open(registry_path, "r", encoding="utf-8") as f:
            registry = yaml.safe_load(f) or {}
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
                content = skill_md.read_text(encoding="utf-8")
                if content.startswith("---"):
                    end_idx = content.index("---", 3)
                    frontmatter = content[3:end_idx].strip()
                    metadata = yaml.safe_load(frontmatter)
                    description = metadata.get("description", skill_dir.name)
            except:
                description = skill_dir.name
        
        skills.append(SkillConfig(
            name=skill_dir.name,
            enabled=registered_info.get("enabled", True),
            description=description,
            skill_id=registered_info.get("skill_id"),
            registered_at=registered_info.get("registered_at"),
            skill_path=skill_dir
        ))
    
    return skills


def register_skill_to_claude(
    instance_name: str,
    skill_name: str,
    force: bool = False
) -> Dict[str, Any]:
    """
    注册单个 Skill 到 Claude
    
    Args:
        instance_name: 实例名称
        skill_name: Skill 名称
        force: 是否强制重新注册
        
    Returns:
        注册结果 {"success": bool, "message": str, "skill_id": str|None}
    """
    from datetime import datetime
    from anthropic.lib import files_from_dir
    
    # 扫描获取 skill 信息
    skills = scan_skills_directory(instance_name)
    skill = next((s for s in skills if s.name == skill_name), None)
    
    if not skill:
        return {"success": False, "message": f"Skill '{skill_name}' 不存在", "skill_id": None}
    
    # 检查是否已注册
    if skill.skill_id and not force:
        return {"success": True, "message": f"已注册 (skill_id: {skill.skill_id})", "skill_id": skill.skill_id}
    
    # 验证目录结构
    validation = validate_skill_directory(skill.skill_path)
    if not validation["valid"]:
        return {"success": False, "message": f"验证失败: {'; '.join(validation['errors'])}", "skill_id": None}
    
    try:
        client = get_anthropic_client()
        
        # 调用 API 创建 Skill（参考官方文档格式）
        display_title = skill.description or skill.name
        skill_create = client.beta.skills.create(
            display_title=display_title,
            files=files_from_dir(str(skill.skill_path)),
            betas=["skills-2025-10-02"]
        )
        
        # 更新并保存
        skill.skill_id = skill_create.id
        skill.registered_at = datetime.now().isoformat()
        
        # 更新所有 skills 的注册表
        _update_skill_registry(instance_name, skills)
        
        return {"success": True, "message": f"注册成功", "skill_id": skill.skill_id}
        
    except Exception as e:
        return {"success": False, "message": f"API 错误: {str(e)}", "skill_id": None}


def unregister_skill_from_claude(
    instance_name: str,
    skill_name: str
) -> Dict[str, Any]:
    """
    从 Claude 注销 Skill
    
    Args:
        instance_name: 实例名称
        skill_name: Skill 名称
        
    Returns:
        注销结果 {"success": bool, "message": str}
    """
    # 扫描获取 skill 信息
    skills = scan_skills_directory(instance_name)
    skill = next((s for s in skills if s.name == skill_name), None)
    
    if not skill:
        return {"success": False, "message": f"Skill '{skill_name}' 不存在"}
    
    if not skill.skill_id:
        return {"success": False, "message": f"Skill '{skill_name}' 未注册"}
    
    try:
        client = get_anthropic_client()
        
        # 先删除所有版本（参考官方文档：删除 Skill 前必须删除所有版本）
        try:
            versions = client.beta.skills.versions.list(
                skill_id=skill.skill_id,
                betas=["skills-2025-10-02"]
            )
            for version in versions.data:
                client.beta.skills.versions.delete(
                    skill_id=skill.skill_id,
                    version=version.version,
                    betas=["skills-2025-10-02"]
                )
        except:
            pass  # 版本不存在时忽略
        
        # 删除 Skill（使用关键字参数，符合官方文档格式）
        client.beta.skills.delete(
            skill_id=skill.skill_id,
            betas=["skills-2025-10-02"]
        )
        
        # 清除本地 skill_id
        skill.skill_id = None
        skill.registered_at = None
        
        # 更新注册表
        _update_skill_registry(instance_name, skills)
        
        return {"success": True, "message": "注销成功"}
        
    except Exception as e:
        # 即使 API 失败，也清除本地记录（可能服务器上已不存在）
        skill.skill_id = None
        skill.registered_at = None
        _update_skill_registry(instance_name, skills)
        
        return {"success": True, "message": f"本地已清除 (服务器可能已不存在: {str(e)})"}


def update_skill_version(
    instance_name: str,
    skill_name: str
) -> Dict[str, Any]:
    """
    更新 Skill 版本（上传新版本到已注册的 Skill）
    
    Args:
        instance_name: 实例名称
        skill_name: Skill 名称
        
    Returns:
        更新结果 {"success": bool, "message": str, "version": str|None}
    """
    from anthropic.lib import files_from_dir
    
    # 扫描获取 skill 信息
    skills = scan_skills_directory(instance_name)
    skill = next((s for s in skills if s.name == skill_name), None)
    
    if not skill:
        return {"success": False, "message": f"Skill '{skill_name}' 不存在", "version": None}
    
    if not skill.skill_id:
        return {"success": False, "message": f"Skill '{skill_name}' 未注册，请先注册", "version": None}
    
    # 验证目录结构
    validation = validate_skill_directory(skill.skill_path)
    if not validation["valid"]:
        return {"success": False, "message": f"验证失败: {'; '.join(validation['errors'])}", "version": None}
    
    try:
        client = get_anthropic_client()
        
        # 创建新版本（参考官方文档格式）
        version = client.beta.skills.versions.create(
            skill_id=skill.skill_id,
            files=files_from_dir(str(skill.skill_path)),
            betas=["skills-2025-10-02"]
        )
        
        return {"success": True, "message": "更新成功", "version": version.version}
        
    except Exception as e:
        return {"success": False, "message": f"API 错误: {str(e)}", "version": None}


def register_all_instance_skills(
    instance_name: str,
    force: bool = False
) -> Dict[str, Any]:
    """
    注册实例的所有未注册 Skills
    
    Args:
        instance_name: 实例名称
        force: 是否强制重新注册已有的
        
    Returns:
        注册统计 {"total": int, "registered": int, "skipped": int, "failed": int, "details": [...]}
    """
    results = {
        "instance": instance_name,
        "total": 0,
        "registered": 0,
        "skipped": 0,
        "failed": 0,
        "details": []
    }
    
    skills = scan_skills_directory(instance_name)
    
    if not skills:
        return results
    
    results["total"] = len(skills)
    
    for skill in skills:
        if not skill.enabled:
            results["skipped"] += 1
            results["details"].append({"name": skill.name, "status": "disabled", "message": "已禁用"})
            continue
        
        if skill.skill_id and not force:
            results["skipped"] += 1
            results["details"].append({"name": skill.name, "status": "exists", "message": f"已注册 ({skill.skill_id})"})
            continue
        
        result = register_skill_to_claude(instance_name, skill.name, force=force)
        
        if result["success"] and result.get("skill_id"):
            results["registered"] += 1
            results["details"].append({"name": skill.name, "status": "success", "message": f"skill_id: {result['skill_id']}"})
        elif result["success"]:
            results["skipped"] += 1
            results["details"].append({"name": skill.name, "status": "exists", "message": result["message"]})
        else:
            results["failed"] += 1
            results["details"].append({"name": skill.name, "status": "failed", "message": result["message"]})
    
    return results


def get_skills_status(instance_name: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """
    获取 Skills 状态
    
    Args:
        instance_name: 实例名称（None 则获取所有实例）
        
    Returns:
        {instance_name: [{"name": ..., "enabled": ..., "skill_id": ..., "status": ...}, ...]}
    """
    status = {}
    
    instances = [instance_name] if instance_name else list_instances()
    
    for inst in instances:
        skills = scan_skills_directory(inst)
        inst_status = []
        
        for skill in skills:
            if skill.skill_id:
                skill_status = "registered"
            elif not skill.enabled:
                skill_status = "disabled"
            else:
                skill_status = "pending"
            
            inst_status.append({
                "name": skill.name,
                "enabled": skill.enabled,
                "skill_id": skill.skill_id,
                "description": skill.description,
                "status": skill_status,
                "registered_at": skill.registered_at
            })
        
        status[inst] = inst_status
    
    return status


def print_skills_status(instance_name: Optional[str] = None):
    """打印 Skills 状态"""
    print("\n📋 Skills 状态总览")
    print("=" * 70)
    
    status = get_skills_status(instance_name)
    
    if not status:
        print("  没有找到任何实例")
        return
    
    total_skills = 0
    total_registered = 0
    
    for inst_name, skills in status.items():
        print(f"\n📦 实例: {inst_name}")
        print("-" * 50)
        
        if not skills:
            print("  (无 Skills)")
            continue
        
        for skill in skills:
            total_skills += 1
            
            if skill["status"] == "registered":
                total_registered += 1
                icon = "✅"
                text = f"已注册 ({skill['skill_id'][:20]}...)" if skill['skill_id'] and len(skill['skill_id']) > 20 else f"已注册 ({skill['skill_id']})"
            elif skill["status"] == "disabled":
                icon = "⏸️"
                text = "已禁用"
            else:
                icon = "❌"
                text = "待注册"
            
            desc = skill['description'][:40] + "..." if len(skill['description']) > 40 else skill['description']
            print(f"  {icon} {skill['name']}")
            print(f"     描述: {desc}")
            print(f"     状态: {text}")
    
    print("\n" + "=" * 70)
    print(f"📊 总计: {total_skills} 个 Skills, {total_registered} 个已注册, {total_skills - total_registered} 个待处理")


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
            config = load_instance_config(name)
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
  python scripts/instance_loader.py --list                     # 列出所有实例
  python scripts/instance_loader.py -i dazee_agent --info      # 显示实例详情
  
  # Skills 管理
  python scripts/instance_loader.py --skills-status            # 查看所有实例的 Skills 状态
  python scripts/instance_loader.py -i dazee_agent --skills-status  # 查看指定实例
  python scripts/instance_loader.py -i dazee_agent --register-skills  # 注册所有未注册 Skills
  python scripts/instance_loader.py -i dazee_agent --register remotion  # 注册指定 Skill
  python scripts/instance_loader.py -i dazee_agent --unregister remotion  # 注销指定 Skill
  python scripts/instance_loader.py -i dazee_agent --update remotion  # 更新 Skill 版本
  python scripts/instance_loader.py -i dazee_agent --register remotion --force  # 强制重新注册
        """
    )
    
    # 实例相关参数
    parser.add_argument("--list", "-l", action="store_true", help="列出所有可用实例")
    parser.add_argument("--instance", "-i", type=str, help="指定实例名称")
    parser.add_argument("--info", action="store_true", help="显示实例详细信息")
    
    # Skills 管理参数
    parser.add_argument("--skills-status", action="store_true", help="显示 Skills 状态")
    parser.add_argument("--register-skills", action="store_true", help="注册实例的所有未注册 Skills")
    parser.add_argument("--register", type=str, metavar="SKILL", help="注册指定 Skill")
    parser.add_argument("--unregister", type=str, metavar="SKILL", help="注销指定 Skill")
    parser.add_argument("--update", type=str, metavar="SKILL", help="更新指定 Skill 版本")
    parser.add_argument("--force", "-f", action="store_true", help="强制重新注册（配合 --register 使用）")
    
    args = parser.parse_args()
    
    try:
        # ==================== 实例管理 ====================
        if args.list:
            print_available_instances()
        
        # ==================== Skills 状态 ====================
        elif args.skills_status:
            print_skills_status(args.instance)
        
        # ==================== 注册所有 Skills ====================
        elif args.register_skills:
            if not args.instance:
                print("❌ 请使用 --instance 指定实例名称")
                exit(1)
            
            print(f"\n🚀 注册实例 [{args.instance}] 的所有 Skills...")
            if args.force:
                print("   模式: 强制重新注册")
            
            results = register_all_instance_skills(args.instance, force=args.force)
            
            print(f"\n📊 结果: 总计 {results['total']} | 注册 {results['registered']} | 跳过 {results['skipped']} | 失败 {results['failed']}")
            
            for detail in results["details"]:
                if detail["status"] == "success":
                    icon = "✅"
                elif detail["status"] in ("exists", "disabled"):
                    icon = "⏭️"
                else:
                    icon = "❌"
                print(f"   {icon} {detail['name']}: {detail['message']}")
            
            if results["registered"] > 0:
                print(f"\n✨ 已更新 skill_registry.yaml")
        
        # ==================== 注册单个 Skill ====================
        elif args.register:
            if not args.instance:
                print("❌ 请使用 --instance 指定实例名称")
                exit(1)
            
            print(f"\n🔧 注册 Skill: {args.register}")
            if args.force:
                print("   模式: 强制重新注册")
            
            result = register_skill_to_claude(args.instance, args.register, force=args.force)
            
            if result["success"]:
                print(f"✅ {result['message']}")
                if result.get("skill_id"):
                    print(f"   skill_id: {result['skill_id']}")
            else:
                print(f"❌ {result['message']}")
        
        # ==================== 注销 Skill ====================
        elif args.unregister:
            if not args.instance:
                print("❌ 请使用 --instance 指定实例名称")
                exit(1)
            
            print(f"\n🗑️ 注销 Skill: {args.unregister}")
            
            result = unregister_skill_from_claude(args.instance, args.unregister)
            
            if result["success"]:
                print(f"✅ {result['message']}")
            else:
                print(f"❌ {result['message']}")
        
        # ==================== 更新 Skill 版本 ====================
        elif args.update:
            if not args.instance:
                print("❌ 请使用 --instance 指定实例名称")
                exit(1)
            
            print(f"\n🔄 更新 Skill 版本: {args.update}")
            
            result = update_skill_version(args.instance, args.update)
            
            if result["success"]:
                print(f"✅ {result['message']}")
                if result.get("version"):
                    print(f"   新版本: {result['version']}")
            else:
                print(f"❌ {result['message']}")
        
        # ==================== 显示实例信息 ====================
        elif args.instance and args.info:
            config = load_instance_config(args.instance)
            print(f"📋 实例信息: {args.instance}")
            print(f"   名称: {config.name}")
            print(f"   描述: {config.description}")
            print(f"   版本: {config.version}")
            print(f"   模型: {config.model or '默认'}")
            print(f"   MCP 工具: {len(config.mcp_tools)} 个")
            for mcp in config.mcp_tools:
                print(f"      • {mcp.get('name', 'unknown')}: {mcp.get('server_url', '-')}")
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
            
            # Skills 信息（Claude Skills 官方 API）
            enabled_skills = [s for s in config.skills if s.enabled]
            print(f"   Skills: {len(config.skills)} 个 ({len(enabled_skills)} 启用)")
            for skill in config.skills:
                status = "✅" if skill.enabled else "⬜"
                registered = f"已注册: {skill.skill_id}" if skill.skill_id else "未注册"
                print(f"      {status} {skill.name}: {registered}")
            
            # APIs 信息（REST API 描述）
            print(f"   APIs: {len(config.apis)} 个")
            for api in config.apis:
                doc_status = f"文档: {api.doc}" if api.doc else "无文档"
                print(f"      • {api.name}: {api.base_url} ({doc_status})")
            
            # 🆕 V6.0 Multi-Agent 配置
            ma_status = "启用" if config.multi_agent_enabled else "禁用"
            print(f"   Multi-Agent: {ma_status}")
            
            # 只有当 Multi-Agent 启用时才显示 Workers 信息
            if config.multi_agent_enabled:
                print(f"      最大并发 Workers: {config.max_concurrent_workers}")
                enabled_workers = [w for w in config.workers if w.enabled]
                print(f"      Workers: {len(config.workers)} 个 ({len(enabled_workers)} 启用)")
                for worker in config.workers:
                    status = "✅" if worker.enabled else "⬜"
                    # 根据类型显示不同信息
                    if worker.worker_type == "agent":
                        prompt_len = len(worker.system_prompt) if worker.system_prompt else 0
                        info = f"{prompt_len} 字符"
                    elif worker.worker_type == "mcp":
                        info = f"MCP → {worker.server_url or '未配置'}"
                    elif worker.worker_type == "workflow":
                        info = f"{worker.platform or 'custom'} → {worker.workflow_id or worker.workflow_url or '未配置'}"
                    else:
                        info = worker.worker_type
                    print(f"         {status} {worker.name} [{worker.worker_type}] ({worker.specialization}): {info}")
        
        else:
            parser.print_help()
            
    except Exception as e:
        print(f"❌ 错误: {str(e)}")
        import traceback
        traceback.print_exc()
        exit(1)

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


@dataclass
class LLMParams:
    """LLM 超参数配置"""
    temperature: Optional[float] = None  # 温度，影响输出随机性（0-1）
    max_tokens: Optional[int] = None  # 最大输出 token 数
    enable_thinking: Optional[bool] = None  # 启用 Extended Thinking
    thinking_budget: Optional[int] = None  # Thinking token 预算
    enable_caching: Optional[bool] = None  # 启用 Prompt Caching
    top_p: Optional[float] = None  # 核采样参数


@dataclass
class InstanceConfig:
    """实例配置数据类"""
    name: str
    description: str = ""
    version: str = "1.0.0"
    
    # Agent 配置
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
    
    # 记忆配置
    mem0_enabled: bool = True
    smart_retrieval: bool = True
    retention_policy: str = "user"
    
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
        top_p=llm_config.get("top_p")
    )
    
    # 加载 Skills 配置（Claude Skills 官方 API）
    skills = load_skill_registry(instance_name)
    
    # 加载 APIs 配置（REST API 描述）
    apis = _load_apis_config(instance_name, raw_config.get("apis", []))
    
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
        mem0_enabled=memory_config.get("mem0_enabled", True),
        smart_retrieval=memory_config.get("smart_retrieval", True),
        retention_policy=memory_config.get("retention_policy", "user"),
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
            doc_content=doc_content
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
        if api.auth_type in ("bearer", "api_key") and api.auth_env:
            auth_value = os.getenv(api.auth_env)
            if auth_value:
                if api.auth_type == "bearer":
                    headers[api.auth_header] = f"Bearer {auth_value}"
                else:  # api_key
                    headers[api.auth_header] = auth_value
                logger.info(f"   🔑 API {api.name}: 已配置认证")
            else:
                logger.warning(f"⚠️ API {api.name}: 环境变量 {api.auth_env} 未设置")
        
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
    try:
        from dotenv import load_dotenv
    except ImportError:
        logger.warning("python-dotenv 未安装，跳过 .env 加载")
        return
    
    env_path = get_instances_dir() / instance_name / ".env"
    
    if env_path.exists():
        load_dotenv(env_path, override=True)
        logger.info(f"✅ 已加载环境变量: {env_path}")
    else:
        logger.warning(f"⚠️ .env 文件不存在: {env_path}")


async def create_agent_from_instance(
    instance_name: str,
    event_manager = None,
    workspace_dir: str = None,
    conversation_service = None,
    skip_mcp_registration: bool = False,
    skip_skills_registration: bool = False
):
    """
    从实例配置创建 Agent（核心方法）
    
    流程：
    1. 加载环境变量
    2. 加载实例配置
    3. 加载实例提示词
    4. 合并框架通用提示词
    5. 调用 AgentFactory.from_prompt() 创建 Agent
    6. 注册 MCP 工具（如果配置了）
    7. 注册 Claude Skills（如果配置了）
    
    Args:
        instance_name: 实例名称
        event_manager: 事件管理器
        workspace_dir: 工作目录
        conversation_service: 会话服务
        skip_mcp_registration: 是否跳过 MCP 工具注册
        skip_skills_registration: 是否跳过 Skills 注册
        
    Returns:
        配置好的 Agent 实例
    """
    from core.agent import AgentFactory
    from prompts.universal_agent_prompt import get_universal_agent_prompt
    
    logger.info(f"🚀 开始加载实例: {instance_name}")
    
    # 1. 加载环境变量
    load_instance_env(instance_name)
    
    # 2. 加载实例配置
    config = load_instance_config(instance_name)
    logger.info(f"   配置: {config.name} v{config.version}")
    logger.info(f"   描述: {config.description}")
    logger.info(f"   Skills: {len(config.skills)} 个")
    logger.info(f"   APIs: {len(config.apis)} 个")
    
    # 3. 加载实例提示词
    instance_prompt = load_instance_prompt(instance_name)
    logger.info(f"   提示词长度: {len(instance_prompt)} 字符")
    
    # 4. 准备 APIs 运行时参数
    if config.apis:
        config.apis = _prepare_apis(config.apis)
    
    # 5. 合并框架通用提示词
    # 实例提示词在前，APIs 描述，框架提示词在后
    framework_prompt = get_universal_agent_prompt()
    apis_prompt = _build_apis_prompt_section(config.apis)
    
    full_prompt = f"""# 实例配置

{instance_prompt}

---

{apis_prompt}

---

# 框架能力协议

{framework_prompt}
"""
    
    logger.info(f"   合并后提示词长度: {len(full_prompt)} 字符")
    
    # 6. 创建事件管理器（如果未提供）
    if event_manager is None:
        from core.events import create_event_manager, get_memory_storage
        # 使用内存存储（适合单机测试）
        storage = get_memory_storage()
        event_manager = create_event_manager(storage)
    
    # 7. 调用 AgentFactory 创建 Agent
    agent = await AgentFactory.from_prompt(
        system_prompt=full_prompt,
        event_manager=event_manager,
        workspace_dir=workspace_dir,
        conversation_service=conversation_service,
        use_default_if_failed=True
    )
    
    logger.info(f"✅ Agent 创建成功")
    
    # 8. 应用配置覆盖
    if config.model:
        agent.model = config.model
        logger.info(f"   覆盖 model: {config.model}")
    
    if config.max_turns:
        agent.max_turns = config.max_turns
        logger.info(f"   覆盖 max_turns: {config.max_turns}")
    
    # 9. 🆕 创建实例级工具注册表
    from core.tool import InstanceToolRegistry, get_capability_registry
    
    global_registry = get_capability_registry()
    instance_registry = InstanceToolRegistry(global_registry=global_registry)
    agent._instance_registry = instance_registry  # 注入到 Agent
    
    # 10. 注册 MCP 工具（使用 InstanceToolRegistry）
    if not skip_mcp_registration and config.mcp_tools:
        await _register_mcp_tools(agent, config.mcp_tools, instance_registry)
    
    # 11. 注册 Claude Skills（如果配置了）
    if not skip_skills_registration and config.skills:
        enabled_skills = [s for s in config.skills if s.enabled]
        if enabled_skills:
            await _register_skills(instance_name, enabled_skills)
    
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
    from services.mcp_client import get_mcp_client, create_mcp_tool_definition
    
    connected_clients = []
    mcp_tool_definitions = []  # Claude API 格式的工具定义
    
    for tool_config in mcp_tools:
        name = tool_config.get("name", "unknown")
        try:
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
            
            # 🆕 使用缓存获取 MCP 客户端（避免重复连接）
            client = await get_mcp_client(
                server_url=server_url,
                server_name=server_name,
                auth_token=auth_token
            )
            
            if client._connected:
                tools = client._tools
                if not tools:
                    # 如果工具列表为空，可能需要重新发现
                    tools_list = await client.discover_tools()
                    tools = {t['name']: t for t in tools_list}
                
                logger.info(f"   ✅ 注册成功: 发现 {len(tools)} 个工具")
                
                for tool_name, tool_info in tools.items():
                    logger.info(f"      • {tool_name}")
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
                        
                        # 创建处理器闭包
                        async def make_handler(_client, _orig_name):
                            async def handler(tool_input: Dict[str, Any]):
                                return await _client.call_tool(_orig_name, tool_input)
                            return handler
                        
                        handler = await make_handler(client, original_name)
                        
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
            logger.warning(f"⚠️ 注册 MCP 工具 {name} 失败: {str(e)}")
    
    # 将 MCP 工具定义注入到 Agent（兼容旧逻辑）
    if mcp_tool_definitions and hasattr(agent, '_mcp_tools'):
        agent._mcp_tools.extend(mcp_tool_definitions)
    elif mcp_tool_definitions:
        agent._mcp_tools = mcp_tool_definitions
        
    # 注册 MCP 工具到 tool_executor 的处理器
    if mcp_tool_definitions and hasattr(agent, 'tool_executor'):
        for tool_def in mcp_tool_definitions:
            tool_name = tool_def['name']
            client = tool_def['_mcp_client']
            original_name = tool_def['_original_name']
            
            # 创建工具处理器
            async def mcp_handler(tool_input: Dict[str, Any], _client=client, _orig_name=original_name):
                return await _client.call_tool(_orig_name, tool_input)
            
            # 注册处理器
            agent.tool_executor.register_handler(tool_name, mcp_handler)
            logger.info(f"   📌 已注册 MCP 工具处理器: {tool_name}")
    
    return connected_clients


def validate_skill_directory(skill_path: Path) -> Dict[str, Any]:
    """
    验证 Skill 目录结构（参考标准 skill_utils.validate_skill_directory）
    
    检查项：
    - SKILL.md 存在
    - YAML frontmatter 格式正确
    - 包含 name 和 description 字段
    - frontmatter 不超过 1024 字符
    - 总大小不超过 8MB
    
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
    result = {"valid": True, "errors": [], "warnings": [], "info": {}}
    
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
            frontmatter = content[3:end_idx].strip()
            
            # 检查必需字段
            if "name:" not in frontmatter:
                result["valid"] = False
                result["errors"].append("YAML frontmatter 缺少 'name' 字段")
            
            if "description:" not in frontmatter:
                result["valid"] = False
                result["errors"].append("YAML frontmatter 缺少 'description' 字段")
            
            # 检查 frontmatter 大小
            if len(frontmatter) > 1024:
                result["valid"] = False
                result["errors"].append(
                    f"YAML frontmatter 超过 1024 字符 (当前: {len(frontmatter)})"
                )
            
            result["info"]["frontmatter_size"] = len(frontmatter)
            
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
            
            # 调用 Anthropic API 注册（遵循标准 skill_utils.py 实现）
            # 参数: display_title（显示名称）, files（目录内容）
            display_title = skill.description or skill.name
            skill_create = client.beta.skills.create(
                display_title=display_title,
                files=files_from_dir(str(skill.skill_path))
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
    
    parser = argparse.ArgumentParser(description="智能体实例加载器")
    parser.add_argument("--list", "-l", action="store_true", help="列出所有可用实例")
    parser.add_argument("--instance", "-i", type=str, help="要加载的实例名称")
    parser.add_argument("--info", action="store_true", help="显示实例详细信息")
    
    args = parser.parse_args()
    
    if args.list:
        print_available_instances()
    elif args.instance and args.info:
        try:
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
        except Exception as e:
            print(f"❌ 加载失败: {str(e)}")
    else:
        parser.print_help()

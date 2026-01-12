"""
Worker 工厂 - 根据配置创建不同类型的 Worker

统一的 Worker 创建入口，支持 7 种 Worker 类型：
1. agent: 内置 SimpleAgent
2. skill: Claude Skills
3. mcp: MCP Server
4. workflow: Coze/Dify Workflow
5. sandbox: E2B/代码执行沙箱
6. subagent: Claude 原生子智能体
7. human: Human-In-The-Loop
"""

import logging
from typing import Any, Dict, List, Optional
from pathlib import Path

from .base import BaseWorker, WorkerType
from .agent_worker import AgentWorker
from .skill_worker import SkillWorker
from .mcp_worker import MCPWorker
from .workflow_worker import WorkflowWorker, WorkflowPlatform
from .sandbox_worker import SandboxWorker
from .subagent_worker import SubagentWorker
from .human_worker import HumanWorker, HumanTaskType

logger = logging.getLogger(__name__)


class WorkerFactory:
    """
    Worker 工厂
    
    支持从配置创建 7 种类型的 Worker
    
    Example:
        factory = WorkerFactory()
        
        # Agent Worker
        worker = factory.create_from_config({
            "name": "refactor-worker",
            "type": "agent",
            "specialization": "refactor",
            "system_prompt": "你是重构专家..."
        })
        
        # Skill Worker
        worker = factory.create_from_config({
            "name": "pptx-worker",
            "type": "skill",
            "skill_id": "pptx-generator"
        })
        
        # Workflow Worker (Coze)
        worker = factory.create_from_config({
            "name": "coze-research",
            "type": "workflow",
            "platform": "coze",
            "workflow_id": "7xxx"
        })
    """
    
    # 支持的 Worker 类型
    SUPPORTED_TYPES = ["agent", "skill", "mcp", "workflow", "sandbox", "subagent", "human"]
    
    @staticmethod
    def create_from_config(config: Dict[str, Any]) -> BaseWorker:
        """
        从配置字典创建 Worker
        
        Args:
            config: Worker 配置
                - name: Worker 名称（必需）
                - type: Worker 类型（默认 agent）
                - specialization: 专业领域
                - ... 其他类型特定配置
        
        Returns:
            BaseWorker 实例
        """
        name = config.get("name")
        if not name:
            raise ValueError("Worker 配置缺少 'name' 字段")
        
        worker_type = config.get("type", "agent").lower()
        specialization = config.get("specialization", "general")
        
        if worker_type not in WorkerFactory.SUPPORTED_TYPES:
            raise ValueError(f"不支持的 Worker 类型: {worker_type}，支持: {WorkerFactory.SUPPORTED_TYPES}")
        
        logger.info(f"创建 Worker: {name} (类型: {worker_type})")
        
        # 根据类型创建对应的 Worker
        creators = {
            "agent": WorkerFactory._create_agent_worker,
            "skill": WorkerFactory._create_skill_worker,
            "mcp": WorkerFactory._create_mcp_worker,
            "workflow": WorkerFactory._create_workflow_worker,
            "sandbox": WorkerFactory._create_sandbox_worker,
            "subagent": WorkerFactory._create_subagent_worker,
            "human": WorkerFactory._create_human_worker,
        }
        
        creator = creators.get(worker_type)
        return creator(name, specialization, config)
    
    @staticmethod
    def _create_agent_worker(name: str, specialization: str, config: Dict) -> AgentWorker:
        """创建 Agent Worker"""
        return AgentWorker(
            name=name,
            specialization=specialization,
            system_prompt=config.get("system_prompt", ""),
            model=config.get("model", "claude-sonnet-4-5-20250929"),
            max_turns=config.get("max_turns", 10),
            config=config
        )
    
    @staticmethod
    def _create_skill_worker(name: str, specialization: str, config: Dict) -> SkillWorker:
        """创建 Skill Worker"""
        skill_path = config.get("skill_path")
        if skill_path:
            skill_path = Path(skill_path)
        
        return SkillWorker(
            name=name,
            skill_id=config.get("skill_id"),
            skill_path=skill_path,
            skills_base_dir=config.get("skills_base_dir"),
            specialization=specialization,
            model=config.get("model", "claude-sonnet-4-5-20250929"),
            max_turns=config.get("max_turns", 10),
            config=config
        )
    
    @staticmethod
    def _create_mcp_worker(name: str, specialization: str, config: Dict) -> MCPWorker:
        """创建 MCP Worker"""
        server_url = config.get("server_url")
        if not server_url:
            raise ValueError(f"MCP Worker '{name}' 缺少 'server_url' 配置")
        
        return MCPWorker(
            name=name,
            server_url=server_url,
            specialization=specialization,
            server_name=config.get("server_name"),
            auth_type=config.get("auth_type", "bearer"),
            auth_token=config.get("auth_token"),
            auth_env=config.get("auth_env"),
            timeout=config.get("timeout", 60),
            config=config
        )
    
    @staticmethod
    def _create_workflow_worker(name: str, specialization: str, config: Dict) -> WorkflowWorker:
        """创建 Workflow Worker"""
        platform_str = config.get("platform", "custom").lower()
        
        platform_map = {
            "coze": WorkflowPlatform.COZE,
            "dify": WorkflowPlatform.DIFY,
            "langflow": WorkflowPlatform.LANGFLOW,
            "custom": WorkflowPlatform.CUSTOM
        }
        platform = platform_map.get(platform_str, WorkflowPlatform.CUSTOM)
        
        return WorkflowWorker(
            name=name,
            platform=platform,
            workflow_id=config.get("workflow_id"),
            workflow_url=config.get("workflow_url"),
            base_url=config.get("base_url"),
            api_key=config.get("api_key"),
            api_key_env=config.get("auth_env") or config.get("api_key_env"),
            specialization=specialization,
            timeout=config.get("timeout", 120),
            config=config
        )
    
    @staticmethod
    def _create_sandbox_worker(name: str, specialization: str, config: Dict) -> SandboxWorker:
        """创建 Sandbox Worker"""
        return SandboxWorker(
            name=name,
            backend=config.get("backend", "e2b"),
            template=config.get("template"),
            specialization=specialization,
            timeout=config.get("timeout", 300),
            model=config.get("model", "claude-sonnet-4-5-20250929"),
            config=config
        )
    
    @staticmethod
    def _create_subagent_worker(name: str, specialization: str, config: Dict) -> SubagentWorker:
        """创建 Subagent Worker"""
        return SubagentWorker(
            name=name,
            specialization=specialization,
            subagent_prompt=config.get("subagent_prompt"),
            delegated_tools=config.get("delegated_tools", []),
            max_iterations=config.get("max_iterations", 5),
            model=config.get("model", "claude-sonnet-4-5-20250929"),
            config=config
        )
    
    @staticmethod
    def _create_human_worker(name: str, specialization: str, config: Dict) -> HumanWorker:
        """创建 Human Worker"""
        task_type_str = config.get("task_type", "review").lower()
        
        task_type_map = {
            "review": HumanTaskType.REVIEW,
            "decision": HumanTaskType.DECISION,
            "annotation": HumanTaskType.ANNOTATION,
            "correction": HumanTaskType.CORRECTION,
            "creative": HumanTaskType.CREATIVE,
        }
        task_type = task_type_map.get(task_type_str, HumanTaskType.REVIEW)
        
        return HumanWorker(
            name=name,
            specialization=specialization,
            task_type=task_type,
            notification_webhook=config.get("notification_webhook"),
            notification_email=config.get("notification_email"),
            timeout=config.get("timeout", 3600),
            fallback_action=config.get("fallback_action", "pending"),
            poll_interval=config.get("poll_interval", 10),
            config=config
        )
    
    @staticmethod
    def create_from_registry(
        registry_path: Path,
        workers_dir: Path = None
    ) -> List[BaseWorker]:
        """
        从 worker_registry.yaml 批量创建 Workers
        
        Args:
            registry_path: worker_registry.yaml 路径
            workers_dir: Workers 目录（用于加载 prompt.md）
        
        Returns:
            Worker 列表
        """
        import yaml
        
        if not registry_path.exists():
            logger.warning(f"Worker 注册表不存在: {registry_path}")
            return []
        
        with open(registry_path, "r", encoding="utf-8") as f:
            registry = yaml.safe_load(f) or {}
        
        workers_list = registry.get("workers", [])
        if not isinstance(workers_list, list):
            return []
        
        workers_dir = workers_dir or registry_path.parent
        workers = []
        
        for worker_config in workers_list:
            if not isinstance(worker_config, dict):
                continue
            
            name = worker_config.get("name")
            if not name:
                continue
            
            # 检查是否启用
            if not worker_config.get("enabled", True):
                logger.info(f"Worker '{name}' 已禁用，跳过")
                continue
            
            worker_type = worker_config.get("type", "agent").lower()
            
            # 对于 Agent 类型，尝试加载 prompt.md
            if worker_type == "agent" and not worker_config.get("system_prompt"):
                prompt_path = workers_dir / name / "prompt.md"
                if prompt_path.exists():
                    worker_config["system_prompt"] = prompt_path.read_text(encoding="utf-8")
                else:
                    logger.warning(f"Agent Worker '{name}' 缺少 prompt.md")
            
            # 对于 Skill 类型，设置搜索路径
            if worker_type == "skill":
                worker_config.setdefault("skills_base_dir", workers_dir)
            
            try:
                worker = WorkerFactory.create_from_config(worker_config)
                workers.append(worker)
                logger.info(f"   ✅ 创建 Worker: {name} ({worker_type})")
            except Exception as e:
                logger.error(f"   ❌ 创建 Worker '{name}' 失败: {e}")
        
        return workers
    
    @staticmethod
    def get_supported_types() -> List[str]:
        """获取支持的 Worker 类型列表"""
        return WorkerFactory.SUPPORTED_TYPES.copy()

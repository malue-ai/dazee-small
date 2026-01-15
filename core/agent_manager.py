"""
AgentManager - Multi-Agent 中央调度器 (V4.0)

职责:
- Agent 生命周期管理 (创建/启动/停止/销毁)
- 任务编排与调度
- 冲突检测与解决
- 状态监控与告警

Date: 2025-12-26
"""

import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

# 导入现有组件
from .agent import SimpleAgent
from .tool.capability import CapabilityRegistry, CapabilityRouter
from .memory import MemoryManager


class AgentStatus(Enum):
    """Agent 状态"""
    IDLE = "idle"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass
class AgentInstance:
    """Agent 实例"""
    id: str
    agent: SimpleAgent
    specialization: str  # "css" | "test" | "refactor" | "general"
    status: AgentStatus = AgentStatus.IDLE
    current_task: Optional[str] = None
    progress: float = 0.0
    artifacts: List[Dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def update_status(self, status: AgentStatus, task: str = None, progress: float = None):
        """更新状态"""
        self.status = status
        if task is not None:
            self.current_task = task
        if progress is not None:
            self.progress = progress
        self.updated_at = datetime.now()


@dataclass
class Task:
    """任务定义"""
    id: str
    action: str
    specialization: str
    dependencies: List[str] = field(default_factory=list)
    estimated_time: int = 0  # 秒
    can_parallel: bool = True
    target_files: List[str] = field(default_factory=list)
    status: str = "pending"
    result: Optional[Dict] = None


@dataclass
class TaskPlan:
    """任务计划"""
    goal: str
    tasks: List[Task]
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'TaskPlan':
        """从字典创建"""
        tasks = [Task(**t) for t in data.get('tasks', [])]
        return cls(goal=data.get('goal', ''), tasks=tasks)


@dataclass
class ExecutionResult:
    """执行结果"""
    status: str  # "success" | "partial" | "failed"
    results: Dict[str, Any]  # {task_id: result}
    total_time: float
    errors: List[Dict] = field(default_factory=list)
    
    def get_summary(self) -> str:
        """生成摘要"""
        completed = sum(1 for r in self.results.values() if r.get('status') == 'success')
        total = len(self.results)
        return f"完成 {completed}/{total} 任务，总耗时 {self.total_time:.1f}秒"


class AgentManager:
    """
    Multi-Agent 中央调度器
    
    Example:
        manager = AgentManager()
        
        # 创建专业 Agent
        css_agent = await manager.create_agent("agent-1", "css")
        test_agent = await manager.create_agent("agent-2", "test")
        
        # 执行复杂任务 (自动拆解与调度)
        result = await manager.execute_task(
            "重构用户认证模块，同时优化CSS并补充测试",
            strategy="parallel"
        )
    """
    
    def __init__(
        self,
        capability_registry: Optional[CapabilityRegistry] = None,
        capability_router: Optional[CapabilityRouter] = None,
        config: Optional[Dict] = None
    ):
        """
        初始化
        
        Args:
            capability_registry: 能力注册表 (可选，自动创建)
            capability_router: 能力路由器 (可选，自动创建)
            config: 配置 (可选)
        """
        # Agent 池
        self.agent_pool: Dict[str, AgentInstance] = {}
        
        # 共享资源
        self.capability_registry = capability_registry
        self.capability_router = capability_router
        
        # 配置
        self.config = config or {}
        self.max_agents = self.config.get('max_agents', 10)
        self.max_retries = self.config.get('max_retries', 3)
        
        # 事件回调 (简化版)
        self._event_callbacks: Dict[str, List] = {}
        
        # 统计信息
        self.stats = {
            'total_tasks': 0,
            'completed_tasks': 0,
            'failed_tasks': 0,
            'total_time': 0.0
        }
        
        print(f"✅ AgentManager 初始化完成 (最大 Agent 数: {self.max_agents})")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Agent 生命周期管理
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    async def create_agent(
        self,
        agent_id: str,
        specialization: str = "general",
        config: Optional[Dict] = None
    ) -> AgentInstance:
        """
        创建专业 Agent
        
        Args:
            agent_id: Agent 唯一标识
            specialization: 专业领域
                - "css": CSS 样式专家
                - "test": 单元测试专家
                - "refactor": 重构专家
                - "general": 通用 Agent
            config: 自定义配置 (可选)
        
        Returns:
            AgentInstance
        
        Raises:
            ValueError: Agent ID 已存在或超过最大数量
        """
        # 验证
        if agent_id in self.agent_pool:
            raise ValueError(f"Agent {agent_id} 已存在")
        
        if len(self.agent_pool) >= self.max_agents:
            raise ValueError(f"已达到最大 Agent 数量 ({self.max_agents})")
        
        # 加载专业配置
        agent_config = self._load_specialization_config(specialization)
        
        # 合并自定义配置
        if config:
            agent_config.update(config)
        
        # 创建 SimpleAgent 实例
        agent = SimpleAgent(
            agent_id=agent_id,
            system_prompt=agent_config.get('system_prompt'),
            capabilities=agent_config.get('capabilities', []),
            config=agent_config
        )
        
        # 包装为 AgentInstance
        instance = AgentInstance(
            id=agent_id,
            agent=agent,
            specialization=specialization,
            status=AgentStatus.IDLE
        )
        
        # 注册到 Agent 池
        self.agent_pool[agent_id] = instance
        
        # 发布事件
        await self._publish_event("agent.created", {
            "agent_id": agent_id,
            "specialization": specialization
        })
        
        print(f"✅ 创建 Agent: {agent_id} ({specialization})")
        
        return instance
    
    async def start_agent(self, agent_id: str, task: str) -> Dict:
        """
        启动 Agent 执行任务
        
        Args:
            agent_id: Agent ID
            task: 任务描述
        
        Returns:
            执行结果
        """
        instance = self.agent_pool.get(agent_id)
        if not instance:
            raise ValueError(f"Agent {agent_id} 不存在")
        
        # 更新状态
        instance.update_status(AgentStatus.RUNNING, task=task, progress=0.0)
        
        await self._publish_event("agent.started", {
            "agent_id": agent_id,
            "task": task
        })
        
        try:
            # 执行任务
            result = await instance.agent.run(task)
            
            # 更新状态
            instance.update_status(AgentStatus.COMPLETED, progress=1.0)
            instance.artifacts.append({
                'task': task,
                'result': result,
                'timestamp': datetime.now().isoformat()
            })
            
            await self._publish_event("agent.completed", {
                "agent_id": agent_id,
                "task": task,
                "result": result
            })
            
            return result
            
        except Exception as e:
            # 错误处理
            instance.update_status(AgentStatus.FAILED)
            
            await self._publish_event("agent.failed", {
                "agent_id": agent_id,
                "task": task,
                "error": str(e)
            })
            
            raise
    
    async def stop_agent(self, agent_id: str):
        """停止 Agent"""
        instance = self.agent_pool.get(agent_id)
        if instance:
            instance.update_status(AgentStatus.STOPPED)
            
            await self._publish_event("agent.stopped", {
                "agent_id": agent_id
            })
    
    def get_agent(self, agent_id: str) -> Optional[AgentInstance]:
        """获取 Agent 实例"""
        return self.agent_pool.get(agent_id)
    
    def list_agents(self) -> List[AgentInstance]:
        """列出所有 Agent"""
        return list(self.agent_pool.values())
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 任务编排与调度 (核心功能)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    async def execute_task(
        self,
        user_query: str,
        strategy: str = "auto"  # auto | sequential | parallel
    ) -> ExecutionResult:
        """
        执行复杂任务 (自动拆解为多 Agent 协作)
        
        流程:
        1. 任务分析与拆解 (使用 LLM)
        2. 构建执行计划
        3. 创建专业 Agent
        4. 并行/串行调度执行
        5. 结果聚合
        
        Args:
            user_query: 用户查询
            strategy: 执行策略
                - auto: 自动选择 (根据任务依赖关系)
                - sequential: 串行执行
                - parallel: 并行执行 (无依赖任务)
        
        Returns:
            ExecutionResult
        
        Example:
            result = await manager.execute_task(
                "重构用户认证模块，同时优化CSS并补充测试",
                strategy="parallel"
            )
        """
        start_time = datetime.now()
        
        print(f"\n{'='*60}")
        print(f"📋 任务: {user_query}")
        print(f"{'='*60}\n")
        
        # 1. 任务拆解 (使用 LLM)
        print("1️⃣ 任务分析与拆解...")
        task_plan = await self._decompose_task(user_query)
        
        print(f"   拆解为 {len(task_plan.tasks)} 个子任务:")
        for task in task_plan.tasks:
            deps = f" (依赖: {', '.join(task.dependencies)})" if task.dependencies else ""
            print(f"   - {task.id}: {task.action} [{task.specialization}]{deps}")
        
        # 2. 创建 Agent
        print("\n2️⃣ 创建专业 Agent...")
        agents = await self._create_agents_for_tasks(task_plan)
        
        # 3. 执行调度
        if strategy == "auto":
            # 自动检测是否可并行
            has_dependencies = any(task.dependencies for task in task_plan.tasks)
            strategy = "sequential" if has_dependencies else "parallel"
        
        print(f"\n3️⃣ 开始执行 (策略: {strategy})...\n")
        
        if strategy == "parallel":
            results = await self._execute_parallel(task_plan, agents)
        else:
            results = await self._execute_sequential(task_plan, agents)
        
        # 4. 聚合结果
        end_time = datetime.now()
        total_time = (end_time - start_time).total_seconds()
        
        execution_result = ExecutionResult(
            status="success" if all(r.get('status') == 'success' for r in results.values()) else "partial",
            results=results,
            total_time=total_time
        )
        
        # 5. 更新统计
        self.stats['total_tasks'] += len(task_plan.tasks)
        self.stats['completed_tasks'] += sum(1 for r in results.values() if r.get('status') == 'success')
        self.stats['total_time'] += total_time
        
        print(f"\n{'='*60}")
        print(f"✅ {execution_result.get_summary()}")
        print(f"{'='*60}\n")
        
        return execution_result
    
    async def _decompose_task(self, user_query: str) -> TaskPlan:
        """
        使用 LLM 进行任务分解（语义理解）
        
        🔑 原则：通过 LLM 理解任务语义，而不是关键词匹配
        """
        logger.info(f"开始任务分解: {user_query}")
        
        # 使用 LLM 进行任务分解
        decompose_prompt = f"""请分析以下用户请求，将其分解为具体的子任务：

用户请求：{user_query}

分析要求：
1. 识别任务类型（如重构、测试、样式优化、功能开发等）
2. 确定任务之间的依赖关系
3. 估算每个任务的大致耗时（秒）

请以 JSON 格式返回：
{{
  "tasks": [
    {{
      "action": "具体任务描述",
      "specialization": "任务类型（refactor/test/css/general等）",
      "dependencies": ["依赖的任务ID"],
      "estimated_time": 300
    }}
  ]
}}

如果是简单任务，返回单个任务即可。"""

        try:
            response = await self.llm.generate(decompose_prompt, temperature=0.3)
            import json
            from utils.json_utils import extract_json
            
            # 解析 LLM 返回的任务分解
            task_data = extract_json(response)
            tasks = []
            
            for idx, task_info in enumerate(task_data.get("tasks", []), start=1):
                tasks.append(Task(
                    id=f"task-{idx}",
                    action=task_info.get("action", user_query),
                    specialization=task_info.get("specialization", "general"),
                    dependencies=task_info.get("dependencies", []),
                    estimated_time=task_info.get("estimated_time", 300)
                ))
            
            # 如果 LLM 未返回任务，创建默认任务
            if not tasks:
                tasks.append(Task(
                    id="task-1",
                    action=user_query,
                    specialization="general",
                    dependencies=[],
                    estimated_time=300
                ))
                
            logger.info(f"任务分解完成，共 {len(tasks)} 个子任务")
            
        except Exception as e:
            logger.warning(f"LLM 任务分解失败，使用默认任务: {e}")
            # 降级：创建单个通用任务
            tasks = [Task(
                id="task-1",
                action=user_query,
                specialization="general",
                dependencies=[],
                estimated_time=300
            )]
        
        return TaskPlan(goal=user_query, tasks=tasks)
    
    async def _create_agents_for_tasks(self, task_plan: TaskPlan) -> Dict[str, AgentInstance]:
        """为任务创建 Agent"""
        agents = {}
        
        # 按专业类型分组
        specializations = set(task.specialization for task in task_plan.tasks)
        
        for spec in specializations:
            agent_id = f"agent-{spec}-{len(self.agent_pool) + 1}"
            
            try:
                agent = await self.create_agent(agent_id, spec)
                agents[spec] = agent
                print(f"   ✅ 创建 {agent_id} ({spec})")
            except Exception as e:
                print(f"   ❌ 创建 {agent_id} 失败: {e}")
        
        return agents
    
    async def _execute_parallel(
        self,
        task_plan: TaskPlan,
        agents: Dict[str, AgentInstance]
    ) -> Dict[str, Dict]:
        """并行执行任务"""
        # 并行执行所有无依赖任务
        tasks_to_run = []
        
        for task in task_plan.tasks:
            if not task.dependencies:
                agent = agents.get(task.specialization)
                if agent:
                    tasks_to_run.append(self._execute_single_task(task, agent))
        
        # 等待所有任务完成
        results = await asyncio.gather(*tasks_to_run, return_exceptions=True)
        
        # 整理结果
        result_dict = {}
        for i, task in enumerate([t for t in task_plan.tasks if not t.dependencies]):
            result_dict[task.id] = results[i] if not isinstance(results[i], Exception) else {
                'status': 'failed',
                'error': str(results[i])
            }
        
        return result_dict
    
    async def _execute_sequential(
        self,
        task_plan: TaskPlan,
        agents: Dict[str, AgentInstance]
    ) -> Dict[str, Dict]:
        """串行执行任务 (支持依赖关系)"""
        results = {}
        
        # 拓扑排序 (简化版: 按依赖关系排序)
        sorted_tasks = self._topological_sort(task_plan.tasks)
        
        for task in sorted_tasks:
            agent = agents.get(task.specialization)
            
            if not agent:
                print(f"   ⚠️  跳过 {task.id}: 无可用 Agent")
                results[task.id] = {'status': 'skipped', 'reason': 'no_agent'}
                continue
            
            # 检查依赖是否完成
            dependencies_met = all(
                results.get(dep_id, {}).get('status') == 'success'
                for dep_id in task.dependencies
            )
            
            if not dependencies_met:
                print(f"   ⚠️  跳过 {task.id}: 依赖未满足")
                results[task.id] = {'status': 'skipped', 'reason': 'dependencies_not_met'}
                continue
            
            # 执行任务
            result = await self._execute_single_task(task, agent)
            results[task.id] = result
        
        return results
    
    async def _execute_single_task(
        self,
        task: Task,
        agent_instance: AgentInstance
    ) -> Dict:
        """执行单个任务"""
        start_time = datetime.now()
        
        print(f"   🔧 [{agent_instance.id}] 执行: {task.action}")
        
        try:
            # 模拟执行 (实际应调用 agent.run)
            # result = await agent_instance.agent.run(task.action)
            
            # 简化版: 模拟延迟
            await asyncio.sleep(1)  # 模拟执行时间
            
            result = {
                'status': 'success',
                'task_id': task.id,
                'agent_id': agent_instance.id,
                'result': f"{task.action} 完成",
                'time': (datetime.now() - start_time).total_seconds()
            }
            
            print(f"   ✅ [{agent_instance.id}] 完成: {task.action} ({result['time']:.1f}s)")
            
            return result
            
        except Exception as e:
            print(f"   ❌ [{agent_instance.id}] 失败: {task.action} - {e}")
            
            return {
                'status': 'failed',
                'task_id': task.id,
                'agent_id': agent_instance.id,
                'error': str(e),
                'time': (datetime.now() - start_time).total_seconds()
            }
    
    def _topological_sort(self, tasks: List[Task]) -> List[Task]:
        """拓扑排序 (简化版)"""
        # TODO: 实现完整的拓扑排序算法
        # 当前简化版: 先执行无依赖任务，再执行有依赖任务
        
        no_deps = [t for t in tasks if not t.dependencies]
        has_deps = [t for t in tasks if t.dependencies]
        
        return no_deps + has_deps
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 监控与状态
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def get_status(self) -> Dict:
        """
        获取整体状态
        
        Returns:
            {
                "agents": [...],
                "stats": {...},
                "health": "healthy"
            }
        """
        agents_status = [
            {
                "id": instance.id,
                "status": instance.status.value,
                "specialization": instance.specialization,
                "current_task": instance.current_task,
                "progress": instance.progress,
                "artifacts_count": len(instance.artifacts),
                "uptime": (datetime.now() - instance.created_at).total_seconds()
            }
            for instance in self.agent_pool.values()
        ]
        
        return {
            "agents": agents_status,
            "stats": self.stats,
            "health": self._calculate_health()
        }
    
    def _calculate_health(self) -> str:
        """计算系统健康状态"""
        if not self.agent_pool:
            return "idle"
        
        statuses = [a.status for a in self.agent_pool.values()]
        
        if all(s == AgentStatus.FAILED for s in statuses):
            return "critical"
        elif any(s == AgentStatus.FAILED for s in statuses):
            return "degraded"
        elif any(s == AgentStatus.RUNNING for s in statuses):
            return "active"
        else:
            return "healthy"
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 辅助方法
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    def _load_specialization_config(self, specialization: str) -> Dict:
        """
        加载专业配置
        
        TODO: 从 config/agents/{specialization}_agent.yaml 加载
        """
        # 简化版: 硬编码配置
        configs = {
            "css": {
                "system_prompt": "你是一个 CSS 样式专家，专注于优化网页样式和布局。",
                "capabilities": ["file_operations", "code_execution"]
            },
            "test": {
                "system_prompt": "你是一个单元测试专家，专注于编写高质量的测试用例。",
                "capabilities": ["file_operations", "code_execution"]
            },
            "refactor": {
                "system_prompt": "你是一个代码重构专家，专注于改善代码结构和质量。",
                "capabilities": ["file_operations", "code_execution"]
            },
            "general": {
                "system_prompt": "你是一个通用 AI 助手。",
                "capabilities": []
            }
        }
        
        return configs.get(specialization, configs["general"])
    
    async def _publish_event(self, event_type: str, data: Dict):
        """发布事件 (简化版)"""
        if event_type in self._event_callbacks:
            for callback in self._event_callbacks[event_type]:
                try:
                    await callback(data)
                except Exception as e:
                    print(f"⚠️  事件回调失败: {event_type} - {e}")
    
    def on(self, event_type: str, callback):
        """注册事件监听器"""
        if event_type not in self._event_callbacks:
            self._event_callbacks[event_type] = []
        self._event_callbacks[event_type].append(callback)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 工厂函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def create_agent_manager(
    capability_registry: Optional[CapabilityRegistry] = None,
    capability_router: Optional[CapabilityRouter] = None,
    config: Optional[Dict] = None
) -> AgentManager:
    """
    创建 AgentManager 实例
    
    Example:
        manager = create_agent_manager()
    """
    return AgentManager(
        capability_registry=capability_registry,
        capability_router=capability_router,
        config=config
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 示例用法
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    async def main():
        # 创建 AgentManager
        manager = create_agent_manager()
        
        # 示例 1: 并行执行独立任务
        print("\n" + "="*60)
        print("示例 1: 并行执行独立任务")
        print("="*60)
        
        result = await manager.execute_task(
            "优化CSS样式，同时补充单元测试",
            strategy="parallel"
        )
        
        # 示例 2: 串行执行有依赖任务
        print("\n" + "="*60)
        print("示例 2: 串行执行有依赖任务")
        print("="*60)
        
        result = await manager.execute_task(
            "重构用户认证模块，然后补充单元测试",
            strategy="sequential"
        )
        
        # 查看状态
        print("\n" + "="*60)
        print("系统状态")
        print("="*60)
        status = manager.get_status()
        print(f"总任务数: {status['stats']['total_tasks']}")
        print(f"完成任务: {status['stats']['completed_tasks']}")
        print(f"健康状态: {status['health']}")
    
    asyncio.run(main())












# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置

将 ZenFlux Agent FastAPI 后端打包为单文件可执行程序。
执行: pyinstaller zenflux-backend.spec --noconfirm
"""

import sys
from pathlib import Path

block_cipher = None
project_root = Path(SPECPATH)

# ==================== 数据文件（只读资源）====================
# 这些文件会被打包到临时目录，运行时通过 sys._MEIPASS 访问

datas = [
    # 配置文件
    (str(project_root / 'config'), 'config'),
    # 提示词
    (str(project_root / 'prompts'), 'prompts'),
    # 智能体实例配置
    (str(project_root / 'instances'), 'instances'),
    # Skill 库
    (str(project_root / 'skills' / 'library'), 'skills/library'),
]

# ==================== 隐式导入 ====================
# PyInstaller 无法自动发现的动态导入

hiddenimports = [
    # FastAPI / Web 框架
    'uvicorn',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'fastapi',
    'starlette',
    'pydantic',
    'pydantic_core',

    # LLM 客户端
    'anthropic',
    'openai',

    # 数据库
    'aiosqlite',
    'sqlalchemy',
    'sqlalchemy.ext.asyncio',

    # 异步 I/O
    'aiofiles',
    'httpx',
    'anyio',
    'anyio._backends',
    'anyio._backends._asyncio',

    # 配置
    'yaml',
    'dotenv',

    # ==================== 项目模块 ====================

    # routers（全量）
    'routers',
    'routers.agents',
    'routers.chat',
    'routers.conversation',
    'routers.docs',
    'routers.files',
    'routers.health',
    'routers.human_confirmation',
    'routers.knowledge',
    'routers.mem0_router',
    'routers.models',
    'routers.realtime',
    'routers.settings',
    'routers.skills',
    'routers.tasks',
    'routers.tools',
    'routers.websocket',

    # services（全量）
    'services',
    'services.agent_registry',
    'services.chat_service',
    'services.confirmation_service',
    'services.conversation_service',
    'services.docs_service',
    'services.file_service',
    'services.health_probe_service',
    'services.knowledge_service',
    'services.mcp_client',
    'services.mcp_service',
    'services.mem0_service',
    'services.realtime_service',
    'services.session_service',
    'services.settings_service',
    'services.task_service',
    'services.tool_service',
    'services.user_task_scheduler',

    # core.agent
    'core',
    'core.agent',
    'core.agent.base',
    'core.agent.factory',
    'core.agent.components.critic',
    'core.agent.components.lead_agent',
    'core.agent.context.prompt_builder',
    'core.agent.execution.multi',
    'core.agent.execution.protocol',
    'core.agent.execution.rvr',
    'core.agent.execution.rvrb',
    'core.agent.execution._multi.critic_evaluator',
    'core.agent.execution._multi.events',
    'core.agent.execution._multi.orchestrator',
    'core.agent.execution._multi.result_aggregator',
    'core.agent.execution._multi.task_decomposer',
    'core.agent.execution._multi.worker_runner',
    'core.agent.tools.flow',

    # core.context
    'core.context.context_engineering',
    'core.context.injectors.phase1.tool_provider',
    'core.context.injectors.phase2.user_memory',
    'core.context.runtime',

    # core.events
    'core.events',
    'core.events.adapters.base',
    'core.events.base',
    'core.events.broadcaster',
    'core.events.content_events',
    'core.events.conversation_events',
    'core.events.dispatcher',
    'core.events.manager',
    'core.events.message_events',
    'core.events.session_events',
    'core.events.storage',
    'core.events.system_events',
    'core.events.user_events',

    # core.evaluation / core.inference
    'core.evaluation.reward_attribution',
    'core.inference.semantic_inference',

    # core.llm
    'core.llm',
    'core.llm.adaptor',
    'core.llm.base',
    'core.llm.claude',
    'core.llm.model_registry',
    'core.llm.openai',
    'core.llm.qwen',
    'core.llm.registry',
    'core.llm.router',

    # core.memory
    'core.memory',
    'core.memory.base',
    'core.memory.manager',
    'core.memory.working',
    'core.memory.mem0.config',
    'core.memory.mem0.extraction.extractor',
    'core.memory.mem0.pool',
    'core.memory.mem0.retrieval.formatter',
    'core.memory.mem0.retrieval.reranker',
    'core.memory.mem0.schemas.behavior',
    'core.memory.mem0.schemas.emotion',
    'core.memory.mem0.schemas.explicit_memory',
    'core.memory.mem0.schemas.fragment',
    'core.memory.mem0.schemas.persona',
    'core.memory.mem0.schemas.plan',
    'core.memory.mem0.sqlite_vec_store',
    'core.memory.mem0.update.aggregator',
    'core.memory.mem0.update.analyzer',
    'core.memory.mem0.update.persona_builder',
    'core.memory.mem0.update.planner',
    'core.memory.mem0.update.prompts',
    'core.memory.mem0.update.quality_control',
    'core.memory.mem0.update.reminder',
    'core.memory.mem0.update.reporter',
    'core.memory.system.cache',
    'core.memory.system.skill',
    'core.memory.user.episodic',
    'core.memory.user.plan',
    'core.memory.user.preference',

    # core.monitoring
    'core.monitoring',
    'core.monitoring.case_converter',
    'core.monitoring.failure_case_db',
    'core.monitoring.failure_detector',
    'core.monitoring.production_monitor',
    'core.monitoring.quality_scanner',
    'core.monitoring.token_audit',
    'core.monitoring.token_budget',

    # core.multi_agent
    'core.multi_agent',
    'core.multi_agent.checkpoint',
    'core.multi_agent.orchestrator',
    'core.multi_agent.scheduling.result_aggregator',

    # core.nodes
    'core.nodes',
    'core.nodes.executors.base',
    'core.nodes.executors.shell',
    'core.nodes.local.base',
    'core.nodes.local.macos',
    'core.nodes.manager',
    'core.nodes.protocol',

    # core.orchestration
    'core.orchestration',
    'core.orchestration.code_orchestrator',
    'core.orchestration.code_validator',
    'core.orchestration.pipeline_tracer',

    # core.output
    'core.output',
    'core.output.formatter',

    # core.planning
    'core.planning',
    'core.planning.dag_scheduler',
    'core.planning.protocol',
    'core.planning.storage',
    'core.planning.validators',

    # core.playbook
    'core.playbook',
    'core.playbook.manager',
    'core.playbook.storage',

    # core.prompt
    'core.prompt',
    'core.prompt.complexity_detector',
    'core.prompt.framework_rules',
    'core.prompt.instance_cache',
    'core.prompt.intent_prompt_generator',
    'core.prompt.llm_analyzer',
    'core.prompt.prompt_layer',
    'core.prompt.prompt_results_writer',
    'core.prompt.runtime_context_builder',
    'core.prompt.skill_prompt_builder',

    # core.routing
    'core.routing',
    'core.routing.intent_analyzer',
    'core.routing.intent_cache',
    'core.routing.router',
    'core.routing.types',

    # core.schemas
    'core.schemas',
    'core.schemas.validator',

    # core.skill
    'core.skill',
    'core.skill.dynamic_loader',

    # core.tool
    'core.tool',
    'core.tool.capability.skill_loader',
    'core.tool.executor',
    'core.tool.llm_description',
    'core.tool.loader',
    'core.tool.registry',
    'core.tool.registry_config',
    'core.tool.selector',
    'core.tool.types',
    'core.tool.validator',

    # infra（全量）
    'infra',
    'infra.local_store',
    'infra.local_store.crud.conversation',
    'infra.local_store.crud.message',
    'infra.local_store.crud.scheduled_task',
    'infra.local_store.engine',
    'infra.local_store.fts',
    'infra.local_store.models',
    'infra.local_store.pools',
    'infra.local_store.session_store',
    'infra.local_store.skills_cache',
    'infra.local_store.vector',
    'infra.local_store.workspace',
    'infra.resilience',
    'infra.resilience.circuit_breaker',
    'infra.resilience.config',
    'infra.resilience.fallback',
    'infra.resilience.retry',
    'infra.resilience.timeout',
    'infra.storage',
    'infra.storage.async_writer',
    'infra.storage.base',
    'infra.storage.batch_writer',
    'infra.storage.local',
    'infra.storage.storage_manager',

    # utils（全量）
    'utils',
    'utils.app_paths',
    'utils.background_tasks',
    'utils.background_tasks.context',
    'utils.background_tasks.registry',
    'utils.background_tasks.scheduler',
    'utils.background_tasks.service',
    'utils.background_tasks.tasks',
    'utils.background_tasks.tasks.clue_generation',
    'utils.background_tasks.tasks.mem0_update',
    'utils.background_tasks.tasks.recommended_questions',
    'utils.background_tasks.tasks.title_generation',
    'utils.cache_utils',
    'utils.file_handler',
    'utils.file_processor',
    'utils.instance_loader',
    'utils.json_file_store',
    'utils.json_utils',
    'utils.knowledge_store',
    'utils.message_utils',
    'utils.query_utils',

    # models（全量）
    'models',
    'models.agent',
    'models.api',
    'models.chat',
    'models.chat_request',
    'models.database',
    'models.docs',
    'models.file',
    'models.hitl',
    'models.knowledge',
    'models.llm',
    'models.mcp',
    'models.mem0',
    'models.realtime',
    'models.scheduled_task',
    'models.skill',
    'models.tool',
    'models.usage',

    # 日志
    'logger',

    # MCP
    'mcp',
]

# ==================== 排除包（减小体积）====================

excludes = [
    'matplotlib',
    'pandas',
    'scipy',
    'PIL',
    'cv2',
    'torch',
    'tensorflow',
    'jupyter',
    'notebook',
    'IPython',
    'pytest',
    'test',
    'tests',
    'unittest',
]

# ==================== 分析 ====================

a = Analysis(
    [str(project_root / 'main.py')],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ==================== 打包 ====================

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='zenflux-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # 保留控制台输出，便于调试
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

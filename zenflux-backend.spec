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

    # 项目模块（动态导入）
    'routers',
    'routers.chat',
    'routers.health',
    'routers.conversation',
    'routers.files',
    'routers.tools',
    'routers.settings',
    'routers.agents',
    'routers.skills',
    'routers.docs',
    'routers.models',
    'routers.mem0_router',
    'routers.tasks',
    'routers.realtime',
    'routers.human_confirmation',
    'services',
    'services.chat_service',
    'services.settings_service',
    'services.agent_registry',
    'services.session_service',
    'services.conversation_service',
    'services.file_service',
    'services.mcp_service',
    'services.mcp_client',
    'services.tool_service',
    'core',
    'core.agent',
    'core.agent.base',
    'core.agent.factory',
    'core.llm',
    'core.llm.claude',
    'core.llm.openai',
    'core.llm.qwen',
    'core.tool',
    'core.tool.registry',
    'core.tool.executor',
    'core.tool.selector',
    'core.routing',
    'core.routing.router',
    'core.routing.intent_analyzer',
    'infra',
    'infra.local_store',
    'infra.local_store.engine',
    'infra.local_store.models',
    'infra.storage',
    'infra.storage.local',
    'utils',
    'utils.app_paths',
    'utils.instance_loader',
    'models',
    'logger',

    # MCP
    'mcp',
]

# ==================== 排除包（减小体积）====================

excludes = [
    'tkinter',
    'matplotlib',
    'numpy',
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

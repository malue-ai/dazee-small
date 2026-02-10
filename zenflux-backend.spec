# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置（onedir 模式）

将 ZenFlux Agent FastAPI 后端打包为目录结构：
  dist/zenflux-backend/
    zenflux-backend        # 主可执行文件
    _internal/             # 所有依赖（.so/.dylib/数据文件）

使用 onedir 而非 onefile 的原因：
  macOS AMFI（代码签名验证）会阻止 onefile 模式在运行时
  解压到 /tmp 的动态库。onedir 模式允许在构建阶段对所有
  文件进行代码签名，从而通过 Spotlight/Finder 启动时的安全检查。

执行: pyinstaller zenflux-backend.spec --noconfirm
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None
project_root = Path(SPECPATH)

# ==================== 原生扩展（binaries）====================
# 包含 C 扩展 .so/.dylib 文件，PyInstaller 无法通过 import 链发现

binaries = []

# sqlite-vec: SQLite 向量搜索扩展（包含原生 .so/.dylib）
try:
    _sv_datas, _sv_binaries, _sv_hiddenimports = collect_all('sqlite_vec')
    binaries += _sv_binaries
except Exception:
    pass  # sqlite-vec 未安装时跳过

# ==================== 数据文件（只读资源）====================
# 这些文件会被打包到临时目录，运行时通过 sys._MEIPASS 访问

datas = [
    # 版本号（单一来源）
    (str(project_root / 'VERSION'), '.'),
    # 配置文件
    (str(project_root / 'config'), 'config'),
    # 提示词
    (str(project_root / 'prompts'), 'prompts'),
    # 智能体实例配置
    (str(project_root / 'instances'), 'instances'),
    # Skill 库
    (str(project_root / 'skills' / 'library'), 'skills/library'),
]

# sqlite-vec 数据文件（与上方 binaries 配合，确保 loadable_path() 能找到扩展）
try:
    datas += _sv_datas
except NameError:
    pass

# ==================== C 扩展包完整收集 ====================
# 问题：含 C 扩展（.so）的包，PyInstaller 将 .so 解压到目录但纯 Python 文件
# 放入 PYZ 归档。运行时 Python 找到目录后不再查 PYZ，导致 ModuleNotFoundError。
# 解决：对这些包使用 collect_all() 将 .py 文件也复制到输出目录。
hiddenimports = []
_native_packages = [
    # Rust / C 扩展类
    'pydantic_core',   # Rust 扩展 + core_schema.py
    'yaml',            # _yaml.so + error.py 等
    'aiohttp',         # _http_parser.so 等
    'asyncpg',         # PostgreSQL C 扩展
    'charset_normalizer',
    'cryptography',    # Rust 扩展
    'frozenlist',
    'greenlet',
    'httptools',
    'jiter',
    'lxml',
    'multidict',
    'numpy',
    'propcache',
    'psutil',
    'regex',
    'rpds',
    'tiktoken',
    'uvloop',
    'watchfiles',
    'websockets',
    'yarl',
    'PIL',             # Pillow
    # 数据文件类（有 .py 时区数据 / JSON schema / 模板文件导致建目录）
    'pytz',
    'jsonschema',
    'jsonschema_specifications',
    'Crypto',          # pycryptodome
    'boto3',
    'botocore',
    'docx',            # python-docx
    'google',          # google-* 命名空间
    'grpc',
    'grpc_tools',
]

for _pkg in _native_packages:
    try:
        _d, _b, _h = collect_all(_pkg)
        datas += _d
        binaries += _b
        hiddenimports += _h
    except Exception:
        pass  # 未安装的包跳过

# ==================== 隐式导入 ====================
# 使用 collect_submodules() 自动递归收集，不再手动维护模块列表。
# 新增项目模块时无需修改此文件，PyInstaller 会自动发现。

hiddenimports = list(set(hiddenimports))  # 去重 collect_all 结果

# --- 项目模块：自动递归收集所有子模块 ---
_project_packages = [
    'routers', 'services', 'core', 'infra', 'utils', 'models', 'tools',
]
for _pkg in _project_packages:
    hiddenimports += collect_submodules(_pkg)

# 单文件模块（不属于任何包）
hiddenimports += ['logger', 'main']

# --- 第三方库：仅声明 PyInstaller 无法通过 import 链自动发现的 ---
# uvicorn/anyio 使用动态导入选择后端，需要显式收集
hiddenimports += collect_submodules('uvicorn')
hiddenimports += collect_submodules('anyio')

hiddenimports += collect_submodules('pydantic')

hiddenimports += [
    # Web 框架
    'fastapi', 'starlette',
    # LLM 客户端
    'anthropic', 'openai',
    # 数据库
    'aiosqlite', 'sqlalchemy', 'sqlalchemy.ext.asyncio',
    # 异步 I/O
    'aiofiles', 'httpx',
    # 配置
    'yaml',
    # tiktoken（编码数据通过 entry_points 插件发现，PyInstaller 需要显式声明）
    'tiktoken', 'tiktoken_ext', 'tiktoken_ext.openai_public',
]

# --- 延迟导入 / 条件导入的第三方库 ---
# 这些库在代码中通过函数内 import 或 try/except 导入，
# PyInstaller 静态分析无法通过 import 链自动发现。


# 记忆系统 mem0（core/memory/mem0/pool.py 全部 lazy import）
hiddenimports += collect_submodules('mem0')

# sqlite-vec Python 模块（配合上方 binaries/datas 一起打包）
try:
    hiddenimports += _sv_hiddenimports
except NameError:
    hiddenimports += ['sqlite_vec']

# 定时任务 APScheduler（services/user_task_scheduler.py 等 lazy import）
hiddenimports += collect_submodules('apscheduler')

# 文件处理（utils/file_handler.py try/except, core/knowledge/file_indexer.py lazy import）
hiddenimports += ['PyPDF2', 'docx']


# macOS 原生 OCR（tools/observe_screen.py 函数内 lazy import）
if sys.platform == 'darwin':
    hiddenimports += [
        'objc', 'Vision', 'Quartz', 'Foundation',
    ]

# 去重
hiddenimports = list(set(hiddenimports))

# ==================== 排除包（减小体积）====================

excludes = [
    # 科学计算 / 机器学习（服务端不需要）
    # 注意：不排除 numpy（intent_cache 需要）和 PIL（file_handler 需要图片压缩）
    'matplotlib', 'pandas', 'scipy',
    'cv2',
    'torch', 'tensorflow',
    # 开发/测试工具
    'jupyter', 'notebook', 'IPython',
    'pytest', 'test', 'tests', 'unittest',
    # 构建/包管理工具（运行时不需要）
    # pkg_resources 依赖 jaraco.text（setuptools 80.x），项目代码不使用，直接排除
    # 注意：保留 setuptools（Python 3.12 的 distutils 来自 setuptools）
    'pkg_resources', 'jaraco',
    'pip', '_distutils_hack',
    'ensurepip', 'venv',
    # GUI 工具包（服务端不需要）
    'tkinter', '_tkinter', 'tcl', 'tk',
    # 其他不需要的标准库模块
    'xmlrpc', 'pydoc', 'doctest', 'lib2to3',
]

# ==================== 分析 ====================

a = Analysis(
    [str(project_root / 'main.py')],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=True,  # 关键：不用 PYZ 归档，所有 .pyc 直接提取到文件系统
                      # 避免 C 扩展包目录存在但纯 Python 文件在 PYZ 中导致 ModuleNotFoundError
)

# ==================== 打包（onedir 模式）====================
# 使用 onedir 模式：所有 .so/.dylib 在构建时就存在于磁盘上，
# 可以在打包阶段统一签名，避免 macOS AMFI 代码签名验证失败。
# （onefile 模式会在运行时解压到 /tmp，无法预先签名）

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# onedir 模式下 EXE 只包含引导脚本，不包含 binaries/zipfiles/datas
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='zenflux-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# COLLECT 将所有依赖文件收集到 dist/zenflux-backend/ 目录
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='zenflux-backend',
)

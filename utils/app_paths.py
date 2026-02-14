"""
应用路径管理器

统一管理开发模式和 PyInstaller 打包模式下的路径解析。

两类路径：
- bundle_dir: 只读资源（config/、prompts/、instances/、skills/library/）
  - 开发时 = 项目根目录
  - 打包后 = sys._MEIPASS（PyInstaller 解压临时目录）

- user_data_dir: 可写数据（数据库、日志、用户配置）
  - 开发时 = 项目根目录
  - 打包后 = 平台标准用户数据目录
    - macOS: ~/Library/Application Support/com.xiaodazi.app/
    - Windows: %APPDATA%/xiaodazi/
    - Linux: ~/.local/share/xiaodazi/
"""

import os
import sys
from pathlib import Path
from typing import Optional

# 应用标识
APP_ID = "com.xiaodazi.app"
APP_NAME = "xiaodazi"

# 命令行参数键（Tauri sidecar 传入）
_CLI_DATA_DIR_KEY = "--data-dir"
_CLI_PORT_KEY = "--port"

# 缓存（避免重复计算）
_user_data_dir: Optional[Path] = None
_bundle_dir: Optional[Path] = None


def is_frozen() -> bool:
    """是否在 PyInstaller 打包环境中运行"""
    return getattr(sys, "frozen", False)


def get_bundle_dir() -> Path:
    """
    获取打包资源目录（只读资源）

    包含: config/、prompts/、instances/、skills/library/ 等

    Returns:
        开发时 = 项目根目录
        打包后 = PyInstaller 解压临时目录
    """
    global _bundle_dir
    if _bundle_dir is not None:
        return _bundle_dir

    if is_frozen():
        # PyInstaller 打包模式：资源解压到临时目录
        _bundle_dir = Path(sys._MEIPASS)
    else:
        # 开发模式：项目根目录（utils/app_paths.py -> 上两级）
        _bundle_dir = Path(__file__).parent.parent

    return _bundle_dir


def get_user_data_dir() -> Path:
    """
    获取用户数据目录（可写数据）

    存储: 数据库、日志、用户配置 (config.yaml)

    优先级：
    1. 命令行参数 --data-dir（Tauri sidecar 传入）
    2. 环境变量 ZENFLUX_DATA_DIR
    3. 平台标准用户数据目录

    Returns:
        可写的用户数据目录路径
    """
    global _user_data_dir
    if _user_data_dir is not None:
        return _user_data_dir

    # 1. 命令行参数优先
    data_dir = _get_cli_arg(_CLI_DATA_DIR_KEY)
    if data_dir:
        _user_data_dir = Path(data_dir)
        _user_data_dir.mkdir(parents=True, exist_ok=True)
        return _user_data_dir

    # 2. 环境变量
    env_dir = os.getenv("XIAODAZI_DATA_DIR") or os.getenv("ZENFLUX_DATA_DIR")
    if env_dir:
        _user_data_dir = Path(env_dir)
        _user_data_dir.mkdir(parents=True, exist_ok=True)
        return _user_data_dir

    # 3. 开发模式：使用项目根目录
    if not is_frozen():
        _user_data_dir = Path(__file__).parent.parent
        return _user_data_dir

    # 4. 打包模式：平台标准用户数据目录
    _user_data_dir = _get_platform_data_dir()
    _user_data_dir.mkdir(parents=True, exist_ok=True)
    return _user_data_dir


def get_cli_port() -> int:
    """
    获取命令行指定的端口号

    Returns:
        端口号，默认 18900
    """
    port_str = _get_cli_arg(_CLI_PORT_KEY)
    if port_str:
        try:
            return int(port_str)
        except ValueError:
            pass
    return int(os.getenv("XIAODAZI_PORT") or os.getenv("ZENFLUX_PORT", "18900"))


# ==================== 全局共享路径 ====================


def get_shared_models_dir() -> Path:
    """获取共享模型目录（embedding 模型等，多实例复用）"""
    d = get_user_data_dir() / "data" / "shared" / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_storage_dir() -> Path:
    """
    Convenience wrapper: get instance-scoped storage dir from AGENT_INSTANCE env var.

    Used by file upload/serve routes and FileProcessor to resolve local file paths.
    Delegates to get_instance_storage_dir() for actual instance isolation.
    """
    instance_name = os.getenv("AGENT_INSTANCE", "default")
    return get_instance_storage_dir(instance_name)




# ==================== 自定义实例数据路径注册表 ====================

# instance_name -> custom absolute data_dir path
_custom_data_dirs: dict[str, Path] = {}


def register_instance_data_dir(instance_name: str, data_dir: str) -> None:
    """
    Register a custom data directory for a specific instance.

    Called during instance loading when config.yaml contains
    ``storage.data_dir``. All downstream path helpers
    (get_instance_db_dir, get_instance_storage_dir, etc.) will
    automatically use this custom root instead of the default.

    Args:
        instance_name: Instance name (e.g. "my-agent")
        data_dir: Absolute path string to the custom data directory
    """
    resolved = Path(data_dir).expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    _custom_data_dirs[instance_name] = resolved


def get_instance_custom_data_dir(instance_name: str) -> Optional[str]:
    """
    Return the registered custom data_dir for an instance, or None.

    Used by API responses to expose the current storage path to the frontend.
    """
    p = _custom_data_dirs.get(instance_name)
    return str(p) if p else None


# ==================== 实例隔离路径 ====================


def get_instance_data_dir(instance_name: str) -> Path:
    """
    Get instance-scoped data directory.

    If a custom data_dir was registered via ``register_instance_data_dir``,
    that path is used. Otherwise falls back to the default:
    ``{user_data_dir}/data/instances/{instance_name}/``

    Args:
        instance_name: Instance name (e.g. "xiaodazi")

    Returns:
        Custom data_dir or default path.
    """
    if not instance_name:
        instance_name = os.getenv("AGENT_INSTANCE", "default")

    # Check custom registry first
    custom = _custom_data_dirs.get(instance_name)
    if custom:
        custom.mkdir(parents=True, exist_ok=True)
        return custom

    d = get_user_data_dir() / "data" / "instances" / instance_name
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_instance_db_dir(instance_name: str) -> Path:
    """Instance-scoped database directory (instance.db, knowledge FTS5)."""
    d = get_instance_data_dir(instance_name) / "db"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_instance_memory_dir(instance_name: str) -> Path:
    """Instance-scoped memory directory (MEMORY.md, daily logs, projects)."""
    d = get_instance_data_dir(instance_name) / "memory"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_instance_store_dir(instance_name: str) -> Path:
    """Instance-scoped store directory (memory_fts.db, mem0 vectors)."""
    d = get_instance_data_dir(instance_name) / "store"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_instance_storage_dir(instance_name: str) -> Path:
    """Instance-scoped file storage directory (uploaded files)."""
    d = get_instance_data_dir(instance_name) / "storage"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_instance_playbooks_dir(instance_name: str) -> Path:
    """Instance-scoped playbooks directory."""
    d = get_instance_data_dir(instance_name) / "playbooks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_instance_playbook_vectors_path(instance_name: str) -> Path:
    """Instance-scoped playbook vector DB path (independent from user memory vectors)."""
    return get_instance_store_dir(instance_name) / "playbook_vectors.db"


def get_instance_snapshots_dir(instance_name: str) -> Path:
    """Instance-scoped state snapshots directory."""
    d = get_instance_data_dir(instance_name) / "snapshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_config_dir() -> Path:
    """获取只读配置目录（capabilities.yaml 等）"""
    return get_bundle_dir() / "config"


def get_prompts_dir() -> Path:
    """获取只读提示词目录"""
    return get_bundle_dir() / "prompts"


def get_instances_dir() -> Path:
    """
    获取 instances 目录路径（运行时读写）

    开发模式：项目根目录/instances/（直接读写）
    打包模式：用户数据目录/instances/（可写副本）

    打包后首次启动时，需调用 ensure_instances_initialized()
    将 bundle 内的种子实例复制到用户数据目录。
    """
    if is_frozen():
        d = get_user_data_dir() / "instances"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return get_bundle_dir() / "instances"


def get_bundle_instances_dir() -> Path:
    """
    获取 bundle 内的 instances 目录（只读种子数据）

    仅在打包模式下有意义，用于首次启动时复制到用户数据目录。
    开发模式下与 get_instances_dir() 返回相同路径。
    """
    return get_bundle_dir() / "instances"


def ensure_instances_initialized() -> bool:
    """
    确保用户 instances 目录已初始化（仅打包模式需要）

    首次启动时，将 bundle 内的种子实例（_template、xiaodazi 等）
    复制到用户数据目录。后续启动跳过已存在的实例。

    Returns:
        True if any instances were copied, False if already initialized
    """
    if not is_frozen():
        return False

    import shutil

    bundle_instances = get_bundle_instances_dir()
    user_instances = get_instances_dir()

    if not bundle_instances.exists():
        return False

    copied = False
    for item in bundle_instances.iterdir():
        if not item.is_dir():
            continue
        target = user_instances / item.name
        if not target.exists():
            shutil.copytree(item, target)
            copied = True

    return copied


def get_logs_dir() -> Path:
    """获取日志目录"""
    d = get_user_data_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_user_config_path() -> Path:
    """获取用户配置文件路径（config.yaml）"""
    return get_user_data_dir() / "config.yaml"


# ==================== 内部辅助函数 ====================


def _get_cli_arg(key: str) -> Optional[str]:
    """
    从命令行参数提取值

    支持两种格式：
    - --key value
    - --key=value
    """
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == key and i + 1 < len(args):
            return args[i + 1]
        if arg.startswith(f"{key}="):
            return arg.split("=", 1)[1]
    return None


def _get_platform_data_dir() -> Path:
    """获取平台标准用户数据目录"""
    if sys.platform == "darwin":
        # macOS: ~/Library/Application Support/com.xiaodazi.app/
        return Path.home() / "Library" / "Application Support" / APP_ID
    elif sys.platform == "win32":
        # Windows: %APPDATA%/xiaodazi/
        appdata = os.getenv("APPDATA")
        if appdata:
            return Path(appdata) / APP_NAME
        return Path.home() / "AppData" / "Roaming" / APP_NAME
    else:
        # Linux/其他: ~/.local/share/xiaodazi/
        xdg_data = os.getenv("XDG_DATA_HOME")
        if xdg_data:
            return Path(xdg_data) / APP_NAME
        return Path.home() / ".local" / "share" / APP_NAME


def reset_cache() -> None:
    """重置路径缓存（仅用于测试）"""
    global _user_data_dir, _bundle_dir
    _user_data_dir = None
    _bundle_dir = None

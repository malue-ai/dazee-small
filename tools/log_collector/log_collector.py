#!/usr/bin/env python3
"""
小搭子日志收集器

从小搭子桌面应用的日志文件中提取指定日期的内容，上传到腾讯云 COS。
独立运行，通过系统计划任务每天定时触发。

配置文件位置（按平台）:
    Windows: %APPDATA%\\com.zenflux.agent\\config\\cos_config.yaml
    macOS:   ~/Library/Application Support/com.zenflux.agent/config/cos_config.yaml
    Linux:   ~/.local/share/com.zenflux.agent/config/cos_config.yaml

用法:
    python log_collector.py                          # 上传今天的日志
    python log_collector.py --date 2026-03-08        # 补传指定日期
    python log_collector.py --dry-run                # 仅提取，不上传
    python log_collector.py --install                # 注册系统计划任务
    python log_collector.py --uninstall              # 注销系统计划任务
"""

import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ============================================================
# 常量
# ============================================================

APP_ID = "com.zenflux.agent"
SLICE_THRESHOLD = 2 * 1024 * 1024  # 2MB
SCRIPT_DIR = Path(__file__).parent.resolve()
TASK_NAME_WIN = "XiaodaziLogCollector"
LAUNCHAGENT_LABEL = "com.zenflux.log-collector"

# ============================================================
# 环境依赖检查
# ============================================================

REQUIRED_PACKAGES: List[Tuple[str, str]] = [
    ("yaml", "python -m pip install pyyaml"),
    ("qcloud_cos", "python -m pip install cos-python-sdk-v5"),
]


def check_dependencies() -> bool:
    """逐个检查外部依赖，缺失时打印安装命令。返回 True 表示全部就绪。"""
    import importlib

    missing = []
    for module_name, install_cmd in REQUIRED_PACKAGES:
        try:
            importlib.import_module(module_name)
        except ImportError:
            missing.append((module_name, install_cmd))

    if not missing:
        return True

    print("[ERROR] 缺少以下依赖，请先安装：\n")
    for module_name, install_cmd in missing:
        print(f"  - {module_name:20s} →  {install_cmd}")
    print()
    return False


# ============================================================
# OS 探测与路径
# ============================================================


def get_os_info() -> Dict[str, str]:
    return {
        "platform": sys.platform,
        "os_version": platform.version(),
        "arch": platform.machine(),
    }


def find_user_data_dir() -> Path:
    """获取小搭子用户数据目录（与 app_paths.py 逻辑一致）。"""
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            return Path(appdata) / APP_ID
        return Path.home() / "AppData" / "Roaming" / APP_ID
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_ID
    else:
        xdg = os.environ.get("XDG_DATA_HOME", "")
        if xdg:
            return Path(xdg) / APP_ID
        return Path.home() / ".local" / "share" / APP_ID


def find_log_dir(override: Optional[str] = None) -> Path:
    """定位日志目录。"""
    if override:
        p = Path(override)
        if p.is_dir():
            return p
        raise FileNotFoundError(f"指定的日志目录不存在: {override}")
    d = find_user_data_dir() / "logs"
    if not d.is_dir():
        raise FileNotFoundError(
            f"日志目录不存在: {d}\n"
            f"请确认小搭子已在本机运行过，或使用 --log-dir 手动指定。"
        )
    return d


# ============================================================
# 配置文件管理
# ============================================================


def get_default_config_path() -> Path:
    """获取默认配置文件路径（用户数据目录/config/cos_config.yaml）。"""
    return find_user_data_dir() / "config" / "cos_config.yaml"


def init_config(config_path: Path) -> bool:
    """
    初始化配置文件。

    查找顺序：
    1. 目标路径已存在 → 直接可用
    2. 脚本同级目录存在 cos_config.yaml（旧版位置）→ 迁移到新位置
    3. 脚本同级目录存在 cos_config.yaml.example → 从模板创建

    返回 True 表示配置文件可用，False 表示无法找到可用模板。
    """
    if config_path.exists():
        return True

    config_path.parent.mkdir(parents=True, exist_ok=True)

    legacy_path = SCRIPT_DIR / "cos_config.yaml"
    if legacy_path.exists():
        shutil.copy2(legacy_path, config_path)
        print(f"[INFO] 已将配置文件从旧位置迁移到: {config_path}")
        return True

    example_path = SCRIPT_DIR / "cos_config.yaml.example"
    if example_path.exists():
        shutil.copy2(example_path, config_path)
        print(f"[INFO] 已从模板创建配置文件: {config_path}")
        print(f"       请编辑填写 COS 凭证后重新运行。")
        return True

    return False


def validate_config_credentials(config_path: Path) -> bool:
    """检查配置文件中的 COS 凭证是否已填写（非空）。"""
    try:
        import yaml
    except ImportError:
        return False
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except (OSError, Exception):
        return False
    cos = config.get("cos", {})
    return all(cos.get(k) for k in ("secret_id", "secret_key", "bucket", "region"))


def _read_input(prompt: str, default: str = "", required: bool = True) -> str:
    """读取用户输入，支持默认值和必填校验。"""
    suffix = f" [{default}]" if default else ""
    while True:
        try:
            value = input(f"  {prompt}{suffix}: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n[INFO] 已取消。")
            sys.exit(0)
        result = value or default
        if result or not required:
            return result
        print(f"    此项不能为空，请重新输入。")


def _save_cos_config(config_path: Path, cos: Dict[str, str], user: str) -> None:
    """将 COS 配置写入 YAML 文件（保留注释格式）。"""
    lines = [
        "# 小搭子日志收集器配置",
        "",
        "# 腾讯云 COS 配置",
        "cos:",
        f'  secret_id: "{cos["secret_id"]}"',
        f'  secret_key: "{cos["secret_key"]}"',
        f'  bucket: "{cos["bucket"]}"',
        f'  region: "{cos["region"]}"',
        f'  key_prefix: "{cos.get("key_prefix", "logs")}"',
        "",
        "# 当前机器使用者",
        f'user: "{user}"',
        "",
    ]
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("\n".join(lines), encoding="utf-8")


def prompt_cos_credentials(config_path: Path) -> Dict[str, Any]:
    """
    交互式引导用户输入 COS 凭证，保存到配置文件。

    如果配置文件已存在且有部分值，显示为默认值供用户确认。
    """
    existing: Dict[str, Any] = {}
    if config_path.exists():
        try:
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                existing = yaml.safe_load(f) or {}
        except Exception:
            pass

    old_cos = existing.get("cos", {})

    print("\n[INFO] COS 凭证配置")
    print("=" * 40)
    print("  请输入腾讯云 COS 凭证（按 Enter 保留已有值）:\n")

    cos = {
        "secret_id": _read_input("Secret ID", old_cos.get("secret_id", "")),
        "secret_key": _read_input("Secret Key", old_cos.get("secret_key", "")),
        "bucket": _read_input(
            "Bucket (格式: name-appid)", old_cos.get("bucket", "")
        ),
        "region": _read_input(
            "Region (如 ap-shanghai)", old_cos.get("region", "")
        ),
        "key_prefix": _read_input(
            "COS 路径前缀", old_cos.get("key_prefix", "logs"), required=False
        ) or "logs",
    }

    default_user = existing.get("user", "")
    try:
        fallback_user = os.getlogin()
    except OSError:
        fallback_user = os.environ.get("USERNAME", os.environ.get("USER", ""))
    user = _read_input(
        "用户标识", default_user or fallback_user, required=False
    )

    _save_cos_config(config_path, cos, user)
    print(f"\n[OK] 配置已保存到: {config_path}")

    return {"cos": cos, "user": user}


# ============================================================
# 设备标识
# ============================================================


def get_or_create_device_id(data_dir: Path) -> str:
    """获取或生成设备唯一标识。"""
    id_file = data_dir / "device_id"
    if id_file.exists():
        stored = id_file.read_text(encoding="utf-8").strip()
        if stored:
            return stored
    device_id = str(uuid.uuid4())
    data_dir.mkdir(parents=True, exist_ok=True)
    id_file.write_text(device_id, encoding="utf-8")
    return device_id


# ============================================================
# 用户标识
# ============================================================


def resolve_user(cli_user: Optional[str], config: Dict[str, Any]) -> str:
    """确定用户标识：CLI 参数 > 配置文件 > 系统用户名。"""
    if cli_user:
        return cli_user
    if config.get("user"):
        return config["user"]
    try:
        return os.getlogin()
    except OSError:
        return os.environ.get("USERNAME", os.environ.get("USER", "unknown"))


# ============================================================
# 版本信息
# ============================================================


def read_build_info(data_dir: Path) -> Dict[str, str]:
    """
    读取构建信息。

    查找顺序：
    1. 用户数据目录下的 BUILD_INFO（打包模式下 sidecar 旁边）
    2. 用户数据目录下的 VERSION
    3. 返回 unknown
    """
    # 在打包模式下，BUILD_INFO 被 PyInstaller 打入 bundle，
    # 但脚本独立运行时无法直接访问 bundle。
    # 尝试常见位置：用户数据目录的父级、sidecar 可执行文件旁等。
    search_paths = [
        data_dir,
        data_dir.parent,
    ]

    # 在 Windows 上也检查 Program Files 中可能的安装位置
    if sys.platform == "win32":
        local_app = os.environ.get("LOCALAPPDATA", "")
        if local_app:
            search_paths.append(Path(local_app) / APP_ID)

    for base in search_paths:
        build_info_path = base / "BUILD_INFO"
        if build_info_path.exists():
            try:
                info = json.loads(build_info_path.read_text(encoding="utf-8"))
                return {
                    "app_version": info.get("version", "unknown"),
                    "git_commit": info.get("git_commit", "unknown"),
                    "git_branch": info.get("git_branch", "unknown"),
                }
            except (json.JSONDecodeError, OSError):
                pass

        version_path = base / "VERSION"
        if version_path.exists():
            try:
                ver = version_path.read_text(encoding="utf-8").strip()
                return {"app_version": ver, "git_commit": "unknown", "git_branch": "unknown"}
            except OSError:
                pass

    return {"app_version": "unknown", "git_commit": "unknown", "git_branch": "unknown"}


# ============================================================
# 日志提取
# ============================================================


def _parse_log_date(line: str) -> Optional[datetime]:
    """从 JSON 日志行中解析 ts 字段为本地 datetime。"""
    try:
        obj = json.loads(line)
        ts_str = obj.get("ts", "")
        if not ts_str:
            return None
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.astimezone()  # 转为本地时区
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


def extract_lines_for_date(log_path: Path, target_date: datetime) -> List[str]:
    """
    从单个日志文件中提取指定日期的所有行。

    参数:
        log_path: 日志文件路径
        target_date: 目标日期（本地时区的 date 对象用于比较）
    """
    if not log_path.exists():
        return []

    target = target_date.date()
    matched = []

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.rstrip("\n\r")
                if not line:
                    continue
                dt = _parse_log_date(line)
                if dt is None:
                    continue
                if dt.date() == target:
                    matched.append(line)
    except OSError as e:
        print(f"  [WARN] 读取文件失败 {log_path}: {e}")

    return matched


def extract_daily_logs(log_dir: Path, target_date: datetime) -> Dict[str, List[str]]:
    """
    提取指定日期的 app 和 error 日志。

    同时扫描主文件和 .1 备份（应对日志轮转）。
    """
    result = {}

    for log_name in ("app", "error"):
        main_file = log_dir / f"{log_name}.log"
        backup_file = log_dir / f"{log_name}.log.1"

        lines = []
        # 先扫描备份文件（时间更早），再扫描主文件
        if backup_file.exists():
            lines.extend(extract_lines_for_date(backup_file, target_date))
        lines.extend(extract_lines_for_date(main_file, target_date))

        if lines:
            result[log_name] = lines

    return result


# ============================================================
# 切片
# ============================================================


def slice_lines(lines: List[str], max_bytes: int = SLICE_THRESHOLD) -> List[List[str]]:
    """将行列表切分为多个分片，每片不超过 max_bytes。"""
    if not lines:
        return []

    total_size = sum(len(l.encode("utf-8")) + 1 for l in lines)  # +1 for newline
    if total_size <= max_bytes:
        return [lines]

    slices: List[List[str]] = []
    current: List[str] = []
    current_size = 0

    for line in lines:
        line_size = len(line.encode("utf-8")) + 1
        if current and current_size + line_size > max_bytes:
            slices.append(current)
            current = []
            current_size = 0
        current.append(line)
        current_size += line_size

    if current:
        slices.append(current)

    return slices


# ============================================================
# COS 上传
# ============================================================


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """加载配置文件。"""
    if config_path is None:
        default_path = get_default_config_path()
        init_config(default_path)
        config_path = str(default_path)

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(
            f"配置文件不存在: {path}\n"
            f"请编辑 {get_default_config_path()} 并填写 COS 凭证。"
        )

    try:
        import yaml
    except ImportError:
        raise ImportError("需要 pyyaml: pip install pyyaml")

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def create_cos_client(config: Dict[str, Any]):
    """创建腾讯云 COS 客户端。"""
    try:
        from qcloud_cos import CosConfig, CosS3Client
    except ImportError:
        raise ImportError("需要腾讯云 COS SDK: pip install cos-python-sdk-v5")

    cos_cfg = config.get("cos", {})
    secret_id = cos_cfg.get("secret_id", "")
    secret_key = cos_cfg.get("secret_key", "")
    region = cos_cfg.get("region", "")
    bucket = cos_cfg.get("bucket", "")

    if not all([secret_id, secret_key, region, bucket]):
        raise ValueError(
            "COS 配置不完整，请检查 cos_config.yaml 中的 secret_id, secret_key, region, bucket"
        )

    cos_config = CosConfig(
        Region=region,
        SecretId=secret_id,
        SecretKey=secret_key,
    )
    return CosS3Client(cos_config), bucket


def test_cos_connection(config: Dict[str, Any]) -> bool:
    """测试 COS 连接是否正常（检查 Bucket 可达性）。"""
    print("\n[INFO] 正在测试 COS 连接...")
    try:
        client, bucket = create_cos_client(config)
    except ImportError as e:
        print(f"[ERROR] {e}")
        return False
    except ValueError as e:
        print(f"[ERROR] {e}")
        return False

    try:
        client.head_bucket(Bucket=bucket)
        print("[OK] COS 连接测试成功！Bucket 可访问。")
        return True
    except Exception as e:
        msg = str(e)
        if "NoSuchBucket" in msg:
            print(f"[ERROR] Bucket 不存在: {bucket}")
        elif "AccessDenied" in msg or "403" in msg:
            print(f"[ERROR] 访问被拒绝，请检查 Secret ID / Secret Key 是否正确")
        elif "could not be resolved" in msg or "getaddrinfo" in msg:
            print(f"[ERROR] 无法解析 COS 域名，请检查 Region 是否正确")
        else:
            print(f"[ERROR] COS 连接失败: {e}")
        return False


def upload_to_cos(
    client,
    bucket: str,
    key: str,
    body: str,
    verbose: bool = False,
) -> bool:
    """上传字符串内容到 COS。"""
    try:
        client.put_object(
            Bucket=bucket,
            Body=body.encode("utf-8"),
            Key=key,
            ContentType="application/x-ndjson",
        )
        if verbose:
            print(f"  [OK] 上传: {key} ({len(body)} bytes)")
        return True
    except Exception as e:
        print(f"  [ERROR] 上传失败 {key}: {e}")
        return False


def upload_meta(
    client,
    bucket: str,
    key_prefix: str,
    user: str,
    device_id: str,
    build_info: Dict[str, str],
    verbose: bool = False,
) -> None:
    """上传/更新设备元信息。"""
    meta = {
        "user": user,
        "device_id": device_id,
        "hostname": socket.gethostname(),
        "os": get_os_info(),
        **build_info,
        "last_upload": datetime.now().isoformat(timespec="seconds"),
    }
    meta_key = f"{key_prefix}/meta.json"
    body = json.dumps(meta, indent=2, ensure_ascii=False)
    try:
        client.put_object(
            Bucket=bucket,
            Body=body.encode("utf-8"),
            Key=meta_key,
            ContentType="application/json",
        )
        if verbose:
            print(f"  [OK] 上传: {meta_key}")
    except Exception as e:
        print(f"  [WARN] meta.json 上传失败: {e}")


# ============================================================
# 计划任务检测与自愈
# ============================================================


def _get_plist_path() -> Path:
    """获取 macOS LaunchAgent plist 文件路径。"""
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHAGENT_LABEL}.plist"


def check_task_exists() -> bool:
    """检查日志收集定时任务是否已注册。"""
    if sys.platform == "win32":
        result = subprocess.run(
            ["schtasks", "/Query", "/TN", TASK_NAME_WIN],
            capture_output=True, text=True,
        )
        return result.returncode == 0
    elif sys.platform == "darwin":
        return _get_plist_path().exists()
    return False


def get_task_registered_command() -> Optional[str]:
    """
    获取定时任务中注册的命令内容（XML / plist 原文），用于路径比对。

    Windows 使用 /XML 输出避免中英文 locale 差异。
    """
    if sys.platform == "win32":
        result = subprocess.run(
            ["schtasks", "/Query", "/TN", TASK_NAME_WIN, "/XML"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            return None
        return result.stdout
    elif sys.platform == "darwin":
        plist = _get_plist_path()
        if not plist.exists():
            return None
        try:
            return plist.read_text(encoding="utf-8")
        except OSError:
            return None
    return None


def verify_scheduled_task(
    config_path: str, user: Optional[str], verbose: bool = False
) -> None:
    """
    启动时校验定时任务中的脚本路径和 Python 解释器路径是否与当前一致。

    如果检测到已注册的定时任务指向其他路径（用户重装/移动了脚本/重建了 venv），
    则自动删除旧任务并以当前路径重新注册。
    """
    if not check_task_exists():
        if verbose:
            print("[INFO] 未检测到已注册的定时任务")
        return

    current_script = str(Path(__file__).resolve())
    current_python = str(Path(sys.executable).resolve())
    registered = get_task_registered_command()

    if registered is None:
        return

    script_ok = current_script in registered
    python_ok = current_python in registered

    if script_ok and python_ok:
        if verbose:
            print("[OK] 定时任务路径验证通过")
        return

    reasons = []
    if not script_ok:
        reasons.append(f"  脚本路径不一致 (当前: {current_script})")
    if not python_ok:
        reasons.append(f"  Python 解释器不一致 (当前: {current_python})")

    print("[WARN] 定时任务路径校验失败，正在自动修复...")
    for r in reasons:
        print(r)
    install_scheduled_task(config_path, user)
    print("[OK] 定时任务已修复为当前路径")


# ============================================================
# 计划任务安装/卸载
# ============================================================


def get_scheduled_command(config_path: str, user: Optional[str]) -> str:
    """生成计划任务要执行的命令。"""
    script_path = Path(__file__).resolve()
    parts = [sys.executable, str(script_path), "--config", config_path]
    if user:
        parts.extend(["--user", user])
    if sys.platform == "win32":
        parts.append("--log-output")
    return " ".join(f'"{p}"' if " " in p else p for p in parts)


def install_scheduled_task(config_path: str, user: Optional[str]) -> None:
    """注册系统计划任务（幂等：已有任务会先删除再重建）。"""
    cmd = get_scheduled_command(config_path, user)

    if sys.platform == "win32":
        if check_task_exists():
            print(f"  [INFO] 检测到已有定时任务 {TASK_NAME_WIN}，正在删除后重建...")
            subprocess.run(
                ["schtasks", "/Delete", "/TN", TASK_NAME_WIN, "/F"],
                capture_output=True, text=True,
            )

        schtasks_cmd = [
            "schtasks", "/Create",
            "/TN", TASK_NAME_WIN,
            "/TR", cmd,
            "/SC", "DAILY",
            "/ST", "23:30",
            "/F",
        ]
        result = subprocess.run(schtasks_cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"[OK] Windows 计划任务已创建: {TASK_NAME_WIN}")
            print(f"     每天 23:30 执行: {cmd}")
        else:
            print(f"[ERROR] 创建计划任务失败: {result.stderr}")
            sys.exit(1)

    elif sys.platform == "darwin":
        plist_path = _get_plist_path()
        script_path_str = str(Path(__file__).resolve())

        if plist_path.exists():
            print(f"  [INFO] 检测到已有 LaunchAgent，正在清理后重建...")
            subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)

        program_args = [sys.executable, script_path_str, "--config", config_path]
        if user:
            program_args.extend(["--user", user])

        args_xml = "\n".join(f"        <string>{a}</string>" for a in program_args)
        plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LAUNCHAGENT_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
{args_xml}
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>23</integer>
        <key>Minute</key>
        <integer>30</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/tmp/{LAUNCHAGENT_LABEL}.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/{LAUNCHAGENT_LABEL}.err</string>
</dict>
</plist>"""
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        plist_path.write_text(plist_content, encoding="utf-8")

        result = subprocess.run(
            ["launchctl", "load", str(plist_path)], capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f"[OK] macOS LaunchAgent 已注册: {LAUNCHAGENT_LABEL}")
            print(f"     每天 23:30 执行")
            print(f"     Plist: {plist_path}")
        else:
            print(f"[ERROR] LaunchAgent 注册失败: {result.stderr}")
            sys.exit(1)
    else:
        print("[ERROR] 当前系统不支持自动注册计划任务，请手动配置 cron。")
        print(f"        建议 crontab 条目: 30 23 * * * {cmd}")
        sys.exit(1)


def uninstall_scheduled_task() -> None:
    """注销系统计划任务。"""
    if sys.platform == "win32":
        result = subprocess.run(
            ["schtasks", "/Delete", "/TN", TASK_NAME_WIN, "/F"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            print(f"[OK] Windows 计划任务已删除: {TASK_NAME_WIN}")
        else:
            print(f"[WARN] 删除计划任务失败（可能不存在）: {result.stderr}")

    elif sys.platform == "darwin":
        plist_path = _get_plist_path()
        subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
        if plist_path.exists():
            plist_path.unlink()
        print(f"[OK] macOS LaunchAgent 已注销: {LAUNCHAGENT_LABEL}")
    else:
        print("[INFO] 请手动从 crontab 中移除 XiaodaziLogCollector 条目。")


# ============================================================
# 主流程
# ============================================================


def _setup_log_output() -> None:
    """将 stdout/stderr 重定向到日志文件（Windows 定时任务模式）。"""
    log_file = find_user_data_dir() / "logs" / "log_collector_task.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    fh = open(log_file, "a", encoding="utf-8")
    sys.stdout = fh
    sys.stderr = fh


def run(args: argparse.Namespace) -> None:
    """主执行逻辑。"""

    # --- 输出日志重定向（Windows 定时任务） ---
    if getattr(args, "log_output", False):
        _setup_log_output()
        print(f"\n{'=' * 60}")
        print(f"[{datetime.now().isoformat(timespec='seconds')}] 定时任务执行开始")

    # --- 环境依赖检查 ---
    if not check_dependencies():
        sys.exit(1)

    # --- 处理 install/uninstall ---
    if args.install:
        config_path = args.config or str(get_default_config_path())
        init_config(Path(config_path))

        if validate_config_credentials(Path(config_path)):
            # 凭证已填写 → 加载配置并测试连接
            config = load_config(config_path)
            if not test_cos_connection(config):
                try:
                    retry = input("\nCOS 连接测试失败，是否仍要创建定时任务？(y/N): ").strip().lower()
                except (KeyboardInterrupt, EOFError):
                    print("\n[INFO] 已取消。")
                    sys.exit(0)
                if retry != "y":
                    print("[INFO] 已取消安装。请检查 COS 凭证后重试。")
                    sys.exit(1)
        else:
            # 凭证未填写 → 交互式引导输入
            config = prompt_cos_credentials(Path(config_path))
            if not test_cos_connection(config):
                try:
                    retry = input("\nCOS 连接测试失败，是否仍要创建定时任务？(y/N): ").strip().lower()
                except (KeyboardInterrupt, EOFError):
                    print("\n[INFO] 已取消。")
                    sys.exit(0)
                if retry != "y":
                    print("[INFO] 已取消安装。请修正凭证后重新运行 --install。")
                    sys.exit(1)

        install_scheduled_task(config_path, args.user)
        return

    if args.uninstall:
        uninstall_scheduled_task()
        return

    # --- 加载配置 ---
    config = load_config(args.config)
    cos_cfg = config.get("cos", {})
    key_prefix_base = cos_cfg.get("key_prefix", "logs")

    # --- 校验定时任务路径（自愈机制） ---
    effective_config_path = args.config or str(get_default_config_path())
    verify_scheduled_task(effective_config_path, args.user, verbose=args.verbose)

    # --- 确定目标日期 ---
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            print(f"[ERROR] 日期格式错误: {args.date}（应为 YYYY-MM-DD）")
            sys.exit(1)
    else:
        target_date = datetime.now()

    date_str = target_date.strftime("%Y-%m-%d")

    # --- 定位日志目录 ---
    try:
        log_dir = find_log_dir(args.log_dir)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    # --- 用户 & 设备 ---
    data_dir = find_user_data_dir()
    user = resolve_user(args.user, config)
    device_id = get_or_create_device_id(data_dir)

    # --- 版本信息 ---
    build_info = read_build_info(data_dir)

    print(f"[INFO] 日志收集器启动")
    print(f"  用户:     {user}")
    print(f"  设备ID:   {device_id[:8]}...")
    print(f"  主机名:   {socket.gethostname()}")
    print(f"  系统:     {sys.platform} / {platform.machine()}")
    print(f"  版本:     {build_info.get('app_version', 'unknown')}")
    print(f"  提交:     {build_info.get('git_commit', 'unknown')}")
    print(f"  日志目录: {log_dir}")
    print(f"  目标日期: {date_str}")

    # --- 提取日志 ---
    print(f"\n[INFO] 提取 {date_str} 的日志...")
    daily_logs = extract_daily_logs(log_dir, target_date)

    if not daily_logs:
        print(f"[INFO] {date_str} 没有日志数据，跳过。")
        return

    total_lines = sum(len(v) for v in daily_logs.values())
    total_bytes = sum(
        sum(len(l.encode("utf-8")) + 1 for l in lines)
        for lines in daily_logs.values()
    )
    print(f"  提取到 {total_lines} 行日志 ({total_bytes / 1024:.1f} KB)")

    # --- dry-run 模式 ---
    if args.dry_run:
        print(f"\n[DRY-RUN] 以下为将要上传的内容预览:")
        for log_name, lines in daily_logs.items():
            slices = slice_lines(lines)
            if len(slices) == 1:
                print(f"  {log_name}.log: {len(lines)} 行")
            else:
                for i, s in enumerate(slices, 1):
                    size = sum(len(l.encode("utf-8")) + 1 for l in s)
                    print(f"  {log_name}_part{i:03d}.log: {len(s)} 行 ({size / 1024:.1f} KB)")
        print(f"\n[DRY-RUN] 上传路径: {key_prefix_base}/{user}/{device_id}/{date_str}/")
        return

    # --- 上传到 COS ---
    print(f"\n[INFO] 上传到腾讯云 COS...")
    try:
        client, bucket = create_cos_client(config)
    except (ImportError, ValueError) as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    device_prefix = f"{key_prefix_base}/{user}/{device_id}"
    date_prefix = f"{device_prefix}/{date_str}"
    uploaded = 0
    failed = 0

    for log_name, lines in daily_logs.items():
        slices = slice_lines(lines)

        if len(slices) == 1:
            key = f"{date_prefix}/{log_name}.log"
            body = "\n".join(slices[0]) + "\n"
            if upload_to_cos(client, bucket, key, body, verbose=args.verbose):
                uploaded += 1
            else:
                failed += 1
        else:
            for i, slice_lines_chunk in enumerate(slices, 1):
                key = f"{date_prefix}/{log_name}_part{i:03d}.log"
                body = "\n".join(slice_lines_chunk) + "\n"
                if upload_to_cos(client, bucket, key, body, verbose=args.verbose):
                    uploaded += 1
                else:
                    failed += 1

    # --- 上传 meta.json ---
    upload_meta(client, bucket, device_prefix, user, device_id, build_info, args.verbose)

    # --- 结果汇总 ---
    print(f"\n[INFO] 上传完成: {uploaded} 个文件成功", end="")
    if failed:
        print(f", {failed} 个失败")
    else:
        print()
    print(f"  COS 路径: {date_prefix}/")


# ============================================================
# CLI
# ============================================================


def main():
    parser = argparse.ArgumentParser(
        description="小搭子日志收集器 — 提取每日日志并上传到腾讯云 COS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config", type=str, default=None,
        help="COS 配置文件路径（默认：用户数据目录/config/cos_config.yaml）",
    )
    parser.add_argument(
        "--user", type=str, default=None,
        help="用户标识，如 zhangsan（默认：配置文件中的 user 或系统用户名）",
    )
    parser.add_argument(
        "--log-dir", type=str, default=None,
        help="日志目录路径（默认：自动探测小搭子日志目录）",
    )
    parser.add_argument(
        "--date", type=str, default=None,
        help="目标日期 YYYY-MM-DD（默认：今天）",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="仅提取日志到本地，不上传",
    )
    parser.add_argument(
        "--install", action="store_true",
        help="注册系统计划任务（每天 23:30 执行）",
    )
    parser.add_argument(
        "--uninstall", action="store_true",
        help="注销系统计划任务（应用卸载时自动调用以清理残留任务）",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="输出详细信息",
    )
    parser.add_argument(
        "--log-output", action="store_true",
        help=argparse.SUPPRESS,
    )

    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()

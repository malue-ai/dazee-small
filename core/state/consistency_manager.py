"""
状态一致性管理器 - StateConsistencyManager

提供类数据库事务语义的桌面端状态安全保障：
- Snapshot: 任务前快照（文件内容 + 环境状态）
- OperationLog: 操作日志（可逆操作序列）
- Commit: 任务成功后清理快照
- Rollback: 异常时逆序回滚 + 恢复快照

安全增强：
- 磁盘持久化快照（防止进程崩溃丢失）
- 前置一致性检查（磁盘空间、文件权限）
- 后置一致性检查（文件完整性）
- 自动回滚触发（连续失败 / 严重错误）
- 快照保留策略（自动清理过期快照）
"""

import json
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from logger import get_logger

from core.state.operation_log import OperationLog, OperationRecord

logger = get_logger(__name__)


def _capture_clipboard() -> str:
    """
    捕获当前剪贴板内容（仅文本）。
    macOS 使用 pbpaste，其他平台暂返回空字符串。
    失败或超时返回空字符串。
    """
    try:
        if sys.platform == "darwin":
            result = subprocess.run(
                ["pbpaste"],
                capture_output=True,
                text=True,
                timeout=2,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode == 0 and result.stdout is not None:
                return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.debug(f"剪贴板捕获跳过: {e}")
    return ""


# ==================== 配置 ====================


@dataclass
class SnapshotConfig:
    """快照配置"""

    storage_path: str = ""  # Empty = auto-resolve from AGENT_INSTANCE
    retention_hours: int = 24
    max_size_mb: int = 500
    capture_cwd: bool = True
    capture_files: bool = True
    capture_clipboard: bool = True


@dataclass
class RollbackConfig:
    """回滚配置"""

    auto_rollback_on_consecutive_failures: int = 3
    auto_rollback_on_critical_error: bool = True
    rollback_timeout_seconds: int = 60


@dataclass
class ConsistencyCheckConfig:
    """一致性检查配置"""

    pre_task_disk_space_mb: int = 100
    pre_task_check_permissions: bool = True
    post_task_check_integrity: bool = True


@dataclass
class StateConsistencyConfig:
    """状态一致性管理器总配置"""

    enabled: bool = False
    snapshot: SnapshotConfig = field(default_factory=SnapshotConfig)
    rollback: RollbackConfig = field(default_factory=RollbackConfig)
    consistency_check: ConsistencyCheckConfig = field(
        default_factory=ConsistencyCheckConfig
    )


# ==================== 数据模型 ====================


@dataclass
class EnvironmentState:
    """环境状态快照（CWD + 剪贴板）"""

    cwd: str = ""
    clipboard_content: str = ""
    timestamp: str = ""


@dataclass
class Snapshot:
    """任务前快照"""

    snapshot_id: str
    task_id: str
    affected_files: List[str] = field(default_factory=list)
    file_contents: Dict[str, str] = field(default_factory=dict)
    environment: Optional[EnvironmentState] = None
    created_at: Optional[str] = None


@dataclass
class PreCheckResult:
    """前置一致性检查结果"""

    passed: bool
    issues: List[str] = field(default_factory=list)


@dataclass
class PostCheckResult:
    """后置一致性检查结果"""

    passed: bool
    missing_files: List[str] = field(default_factory=list)
    integrity_errors: List[str] = field(default_factory=list)


# ==================== 核心实现 ====================


class StateConsistencyManager:
    """
    状态一致性管理器

    职责：
    1. 任务开始前创建快照（文件内容 + 环境状态）
    2. 记录每个操作的日志和逆操作
    3. 前置/后置一致性检查
    4. 异常时提供回滚能力（支持自动触发）
    5. 任务完成后清理快照
    6. 快照磁盘持久化（防止进程崩溃）
    """

    def __init__(self, config: Optional[StateConsistencyConfig] = None) -> None:
        self._config = config or StateConsistencyConfig()
        self._snapshots: Dict[str, Snapshot] = {}
        self._task_logs: Dict[str, OperationLog] = {}
        self._listeners: List[Callable[..., None]] = []

        raw_path = self._config.snapshot.storage_path
        if raw_path:
            self._storage_path = Path(raw_path).expanduser()
        else:
            import os
            from utils.app_paths import get_instance_snapshots_dir
            _inst = os.getenv("AGENT_INSTANCE", "default")
            self._storage_path = get_instance_snapshots_dir(_inst)
        if self._config.enabled:
            self._storage_path.mkdir(parents=True, exist_ok=True)
            # 启动时清理过期快照
            self._cleanup_expired_snapshots()

    # ==================== 前置一致性检查 ====================

    def pre_task_check(
        self, affected_files: List[str]
    ) -> PreCheckResult:
        """
        任务执行前的一致性检查

        Args:
            affected_files: 将要修改的文件路径列表

        Returns:
            PreCheckResult: 检查结果
        """
        issues: List[str] = []
        cfg = self._config.consistency_check

        # 1. 磁盘空间检查
        if cfg.pre_task_disk_space_mb > 0:
            try:
                usage = shutil.disk_usage(self._storage_path)
                free_mb = usage.free / (1024 * 1024)
                if free_mb < cfg.pre_task_disk_space_mb:
                    issues.append(
                        f"磁盘空间不足: 剩余 {free_mb:.0f}MB < 要求 {cfg.pre_task_disk_space_mb}MB"
                    )
            except OSError as e:
                issues.append(f"磁盘空间检查失败: {e}")

        # 2. 文件权限检查
        if cfg.pre_task_check_permissions and affected_files:
            for file_path in affected_files:
                p = Path(file_path)
                if p.exists():
                    # 检查文件是否可写
                    import os

                    if not os.access(str(p), os.W_OK):
                        issues.append(f"文件无写入权限: {file_path}")
                else:
                    # 检查父目录是否可写（用于创建新文件）
                    parent = p.parent
                    if parent.exists() and not os.access(str(parent), os.W_OK):
                        issues.append(f"目录无写入权限: {parent}")

        passed = len(issues) == 0
        if not passed:
            logger.warning(f"前置一致性检查未通过: {issues}")
        else:
            logger.debug("前置一致性检查通过")

        return PreCheckResult(passed=passed, issues=issues)

    # ==================== 快照管理 ====================

    def create_snapshot(
        self, task_id: str, affected_files: List[str]
    ) -> str:
        """
        为任务创建快照（文件内容 + 环境状态）

        Args:
            task_id: 任务 ID
            affected_files: 可能被修改的文件路径列表

        Returns:
            snapshot_id
        """
        snapshot_id = f"snap_{uuid.uuid4().hex[:12]}"

        # 1. 备份文件内容
        file_contents: Dict[str, str] = {}
        if self._config.snapshot.capture_files:
            for path in affected_files:
                p = Path(path)
                if p.exists() and p.is_file():
                    try:
                        file_contents[path] = p.read_text(
                            encoding="utf-8", errors="replace"
                        )
                    except Exception as e:
                        logger.warning(f"快照读取失败 {path}: {e}")

        # 2. 捕获环境状态（CWD + 剪贴板）
        environment = None
        if self._config.snapshot.capture_cwd or self._config.snapshot.capture_clipboard:
            try:
                cwd = str(Path.cwd()) if self._config.snapshot.capture_cwd else ""
                clipboard = ""
                if self._config.snapshot.capture_clipboard:
                    clipboard = _capture_clipboard()
                environment = EnvironmentState(
                    cwd=cwd,
                    clipboard_content=clipboard,
                    timestamp=datetime.now().isoformat(),
                )
            except Exception as e:
                logger.warning(f"环境状态捕获失败: {e}")

        # 3. 构建快照
        now = datetime.now().isoformat()
        snapshot = Snapshot(
            snapshot_id=snapshot_id,
            task_id=task_id,
            affected_files=affected_files,
            file_contents=file_contents,
            environment=environment,
            created_at=now,
        )

        # 4. 内存存储
        self._snapshots[snapshot_id] = snapshot
        self._task_logs[task_id] = OperationLog()

        # 5. 磁盘持久化
        self._persist_snapshot(snapshot)

        logger.info(
            f"快照已创建: {snapshot_id}, 文件数={len(file_contents)}, "
            f"环境={'已捕获' if environment else '未捕获'}"
        )
        return snapshot_id

    # ==================== 动态文件捕获 ====================

    def ensure_file_captured(self, task_id: str, file_path: str) -> bool:
        """
        确保文件已被捕获到该任务的快照中（懒加载）。

        如果文件尚未在快照的 file_contents 中，读取当前内容并追加。
        用于工具执行前动态捕获即将被修改的文件。

        Args:
            task_id: 任务 ID
            file_path: 文件路径

        Returns:
            是否成功捕获（文件不存在或已捕获时返回 False）
        """
        snapshot_id = self._find_snapshot_for_task(task_id)
        if not snapshot_id:
            return False

        snap = self._snapshots.get(snapshot_id)
        if not snap:
            return False

        # 已捕获过则跳过
        if file_path in snap.file_contents:
            return False

        # 读取并追加到快照
        try:
            target = Path(file_path)
            if target.is_file():
                content = target.read_text(encoding="utf-8")
                snap.file_contents[file_path] = content
                if file_path not in snap.affected_files:
                    snap.affected_files.append(file_path)
                logger.debug(f"动态捕获文件到快照: {file_path}, task={task_id}")
                return True
        except Exception as e:
            logger.warning(f"动态捕获文件失败 {file_path}: {e}")

        return False

    # ==================== 操作记录 ====================

    def subscribe(self, callback: Callable[..., None]) -> None:
        """
        订阅状态变更（供前端进度或 devtools 调试）

        Args:
            callback: 接收 (event_type, task_id, *args)
                      event_type 为 "record" | "rollback"
        """
        if callback not in self._listeners:
            self._listeners.append(callback)

    def record_operation(
        self, task_id: str, record: OperationRecord
    ) -> None:
        """记录一条操作（用于回滚）"""
        if task_id not in self._task_logs:
            self._task_logs[task_id] = OperationLog()
        self._task_logs[task_id].append(record)
        logger.debug(f"操作已记录: task={task_id}, action={record.action} -> {record.target}")
        for cb in self._listeners:
            try:
                cb("record", task_id, record.to_dict())
            except Exception as e:
                logger.debug(f"StateConsistencyManager 监听器异常: {e}")

    # ==================== 回滚 ====================

    def rollback(self, snapshot_id: str) -> List[str]:
        """
        按快照回滚：先执行操作日志逆序回滚，再恢复快照文件内容

        Args:
            snapshot_id: 快照 ID

        Returns:
            回滚结果消息列表
        """
        # 优先从内存获取，其次从磁盘恢复
        snap = self._snapshots.get(snapshot_id)
        if not snap:
            snap = self._load_snapshot_from_disk(snapshot_id)
        if not snap:
            return [f"快照不存在: {snapshot_id}"]

        task_id = snap.task_id
        messages: List[str] = []
        start_time = time.monotonic()
        timeout = self._config.rollback.rollback_timeout_seconds

        logger.info(f"开始回滚: {snapshot_id}, task={task_id}")

        # 1. 操作日志逆序回滚
        if task_id in self._task_logs:
            elapsed = time.monotonic() - start_time
            if elapsed < timeout:
                messages.extend(self._task_logs[task_id].rollback_all())
            else:
                messages.append("回滚超时: 操作日志回滚被跳过")
                logger.warning("回滚超时，跳过操作日志回滚")
            del self._task_logs[task_id]

        # 2. 恢复快照文件内容
        for path, content in snap.file_contents.items():
            elapsed = time.monotonic() - start_time
            if elapsed >= timeout:
                messages.append(f"回滚超时: 文件 {path} 恢复被跳过")
                logger.warning(f"回滚超时，跳过文件恢复: {path}")
                continue

            try:
                target = Path(path)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                messages.append(f"已恢复: {path}")
            except Exception as e:
                logger.error(f"恢复文件失败 {path}: {e}", exc_info=True)
                messages.append(f"恢复失败: {path} - {e}")

        # 3. 恢复环境状态（CWD + 剪贴板）
        if snap.environment:
            if snap.environment.cwd:
                try:
                    import os

                    os.chdir(snap.environment.cwd)
                    messages.append(f"工作目录已恢复: {snap.environment.cwd}")
                except Exception as e:
                    logger.warning(f"工作目录恢复失败: {e}")
                    messages.append(f"工作目录恢复失败: {e}")
            clipboard = getattr(snap.environment, "clipboard_content", None)
            if clipboard is not None and clipboard and sys.platform == "darwin":
                try:
                    subprocess.run(
                        ["pbcopy"],
                        input=clipboard,
                        capture_output=True,
                        text=True,
                        timeout=2,
                        encoding="utf-8",
                    )
                    messages.append("剪贴板已恢复")
                except Exception as e:
                    logger.debug(f"剪贴板恢复跳过: {e}")

        # 4. 清理
        if snapshot_id in self._snapshots:
            del self._snapshots[snapshot_id]
        self._remove_snapshot_from_disk(snapshot_id)

        total_elapsed = time.monotonic() - start_time
        logger.info(f"回滚完成: {snapshot_id}, 耗时 {total_elapsed:.2f}s, 结果数={len(messages)}")
        for cb in self._listeners:
            try:
                cb("rollback", task_id, snapshot_id, messages)
            except Exception as e:
                logger.debug(f"StateConsistencyManager 监听器异常: {e}")
        return messages

    def should_auto_rollback(
        self, task_id: str, consecutive_failures: int = 0, is_critical: bool = False
    ) -> bool:
        """
        判断是否应自动触发回滚

        Args:
            task_id: 任务 ID
            consecutive_failures: 连续失败次数
            is_critical: 是否为严重错误

        Returns:
            是否应自动回滚
        """
        cfg = self._config.rollback

        # 严重错误自动回滚
        if is_critical and cfg.auto_rollback_on_critical_error:
            logger.warning(f"严重错误触发自动回滚: task={task_id}")
            return True

        # 连续失败达到阈值自动回滚
        if consecutive_failures >= cfg.auto_rollback_on_consecutive_failures:
            logger.warning(
                f"连续失败触发自动回滚: task={task_id}, "
                f"failures={consecutive_failures} >= {cfg.auto_rollback_on_consecutive_failures}"
            )
            return True

        return False

    def auto_rollback_if_needed(
        self,
        task_id: str,
        consecutive_failures: int = 0,
        is_critical: bool = False,
    ) -> Optional[List[str]]:
        """
        如需要则自动执行回滚

        Args:
            task_id: 任务 ID
            consecutive_failures: 连续失败次数
            is_critical: 是否为严重错误

        Returns:
            回滚消息列表（如果执行了回滚），None 表示未触发
        """
        if not self.should_auto_rollback(task_id, consecutive_failures, is_critical):
            return None

        # 查找该任务对应的快照
        snapshot_id = self._find_snapshot_for_task(task_id)
        if not snapshot_id:
            logger.warning(f"自动回滚失败: 未找到 task={task_id} 的快照")
            return None

        return self.rollback(snapshot_id)

    # ==================== 提交 ====================

    def commit(self, task_id: str) -> None:
        """任务成功后清理该任务的快照与日志"""
        to_remove = [
            sid for sid, s in self._snapshots.items() if s.task_id == task_id
        ]
        for sid in to_remove:
            del self._snapshots[sid]
            self._remove_snapshot_from_disk(sid)
        if task_id in self._task_logs:
            del self._task_logs[task_id]
        logger.debug(f"已提交任务: {task_id}")

    # ==================== 后置一致性检查 ====================

    def post_task_check(
        self, task_id: str, expected_outputs: Optional[List[str]] = None
    ) -> PostCheckResult:
        """
        任务完成后的一致性检查

        Args:
            task_id: 任务 ID
            expected_outputs: 预期输出文件列表

        Returns:
            PostCheckResult
        """
        missing_files: List[str] = []
        integrity_errors: List[str] = []
        cfg = self._config.consistency_check

        # 1. 预期输出文件存在性检查
        if expected_outputs:
            for path in expected_outputs:
                if not Path(path).exists():
                    missing_files.append(path)

        # 2. 文件完整性检查（操作日志中记录的输出文件）
        if cfg.post_task_check_integrity and task_id in self._task_logs:
            log = self._task_logs[task_id]
            for option in log.get_rollback_options():
                target = option.get("target", "")
                action = option.get("action", "")
                # 对于写入操作，检查文件是否存在且非空
                if action in ("file_write", "file_create") and target:
                    p = Path(target)
                    if not p.exists():
                        integrity_errors.append(f"写入后文件不存在: {target}")
                    elif p.stat().st_size == 0:
                        integrity_errors.append(f"写入后文件为空: {target}")

        passed = len(missing_files) == 0 and len(integrity_errors) == 0
        if not passed:
            logger.warning(
                f"后置一致性检查未通过: missing={missing_files}, errors={integrity_errors}"
            )
        else:
            logger.debug(f"后置一致性检查通过: task={task_id}")

        return PostCheckResult(
            passed=passed,
            missing_files=missing_files,
            integrity_errors=integrity_errors,
        )

    # ==================== 查询方法 ====================

    def get_rollback_options(self, task_id: str) -> List[Dict[str, Any]]:
        """
        获取该任务的回滚选项（供 HITL 展示）

        Returns:
            [{"id": "...", "action": "...", "target": "..."}, ...]
        """
        if task_id not in self._task_logs:
            return []
        return self._task_logs[task_id].get_rollback_options()

    def get_snapshot_for_task(self, task_id: str) -> Optional[str]:
        """获取任务对应的快照 ID"""
        return self._find_snapshot_for_task(task_id)

    def has_active_snapshot(self, task_id: str) -> bool:
        """检查任务是否有活跃的快照"""
        return self._find_snapshot_for_task(task_id) is not None

    # ==================== 磁盘持久化（私有方法）====================

    def _persist_snapshot(self, snapshot: Snapshot) -> None:
        """将快照持久化到磁盘"""
        if not self._config.enabled:
            return

        try:
            snap_dir = self._storage_path / snapshot.snapshot_id
            snap_dir.mkdir(parents=True, exist_ok=True)

            # 保存元数据
            metadata = {
                "snapshot_id": snapshot.snapshot_id,
                "task_id": snapshot.task_id,
                "affected_files": snapshot.affected_files,
                "created_at": snapshot.created_at,
                "environment": {
                    "cwd": snapshot.environment.cwd,
                    "clipboard_content": getattr(
                        snapshot.environment, "clipboard_content", ""
                    ),
                    "timestamp": snapshot.environment.timestamp,
                }
                if snapshot.environment
                else None,
            }
            meta_file = snap_dir / "metadata.json"
            meta_file.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            # 保存文件内容（每个文件单独存储，避免巨型 JSON）
            files_dir = snap_dir / "files"
            files_dir.mkdir(exist_ok=True)
            file_manifest: Dict[str, str] = {}

            for original_path, content in snapshot.file_contents.items():
                # 使用哈希作为文件名避免路径冲突
                import hashlib

                name_hash = hashlib.md5(
                    original_path.encode()
                ).hexdigest()[:16]
                backup_name = f"{name_hash}.bak"
                (files_dir / backup_name).write_text(
                    content, encoding="utf-8"
                )
                file_manifest[original_path] = backup_name

            # 保存文件清单
            manifest_file = snap_dir / "file_manifest.json"
            manifest_file.write_text(
                json.dumps(file_manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            logger.debug(f"快照已持久化: {snapshot.snapshot_id}")
        except Exception as e:
            logger.error(f"快照持久化失败: {e}", exc_info=True)

    def _load_snapshot_from_disk(
        self, snapshot_id: str
    ) -> Optional[Snapshot]:
        """从磁盘加载快照"""
        snap_dir = self._storage_path / snapshot_id
        meta_file = snap_dir / "metadata.json"

        if not meta_file.exists():
            return None

        try:
            metadata = json.loads(meta_file.read_text(encoding="utf-8"))

            # 加载文件内容
            file_contents: Dict[str, str] = {}
            manifest_file = snap_dir / "file_manifest.json"
            if manifest_file.exists():
                manifest = json.loads(
                    manifest_file.read_text(encoding="utf-8")
                )
                files_dir = snap_dir / "files"
                for original_path, backup_name in manifest.items():
                    backup_file = files_dir / backup_name
                    if backup_file.exists():
                        file_contents[original_path] = backup_file.read_text(
                            encoding="utf-8"
                        )

            # 重建环境状态
            env_data = metadata.get("environment")
            environment = None
            if env_data:
                environment = EnvironmentState(
                    cwd=env_data.get("cwd", ""),
                    clipboard_content=env_data.get("clipboard_content", ""),
                    timestamp=env_data.get("timestamp", ""),
                )

            return Snapshot(
                snapshot_id=metadata["snapshot_id"],
                task_id=metadata["task_id"],
                affected_files=metadata.get("affected_files", []),
                file_contents=file_contents,
                environment=environment,
                created_at=metadata.get("created_at"),
            )
        except Exception as e:
            logger.error(f"快照加载失败 {snapshot_id}: {e}", exc_info=True)
            return None

    def _remove_snapshot_from_disk(self, snapshot_id: str) -> None:
        """删除磁盘上的快照"""
        snap_dir = self._storage_path / snapshot_id
        if snap_dir.exists():
            try:
                shutil.rmtree(snap_dir)
                logger.debug(f"磁盘快照已删除: {snapshot_id}")
            except Exception as e:
                logger.warning(f"磁盘快照删除失败 {snapshot_id}: {e}")

    def _cleanup_expired_snapshots(self) -> None:
        """清理过期快照（根据保留策略）"""
        if not self._storage_path.exists():
            return

        retention = timedelta(hours=self._config.snapshot.retention_hours)
        now = datetime.now()
        cleaned = 0

        try:
            for snap_dir in self._storage_path.iterdir():
                if not snap_dir.is_dir():
                    continue

                meta_file = snap_dir / "metadata.json"
                if not meta_file.exists():
                    # 无元数据的孤立目录，直接清理
                    shutil.rmtree(snap_dir, ignore_errors=True)
                    cleaned += 1
                    continue

                try:
                    metadata = json.loads(
                        meta_file.read_text(encoding="utf-8")
                    )
                    created_at = metadata.get("created_at", "")
                    if created_at:
                        created_time = datetime.fromisoformat(created_at)
                        if now - created_time > retention:
                            shutil.rmtree(snap_dir, ignore_errors=True)
                            cleaned += 1
                except (json.JSONDecodeError, ValueError):
                    # 损坏的元数据，清理
                    shutil.rmtree(snap_dir, ignore_errors=True)
                    cleaned += 1

            if cleaned > 0:
                logger.info(f"已清理 {cleaned} 个过期快照")
        except Exception as e:
            logger.warning(f"过期快照清理失败: {e}")

    # ==================== 辅助方法 ====================

    def _find_snapshot_for_task(self, task_id: str) -> Optional[str]:
        """查找任务对应的快照 ID"""
        # 优先从内存查找
        for sid, snap in self._snapshots.items():
            if snap.task_id == task_id:
                return sid

        # 从磁盘查找
        if self._storage_path.exists():
            for snap_dir in self._storage_path.iterdir():
                meta_file = snap_dir / "metadata.json"
                if meta_file.exists():
                    try:
                        metadata = json.loads(
                            meta_file.read_text(encoding="utf-8")
                        )
                        if metadata.get("task_id") == task_id:
                            return metadata.get("snapshot_id")
                    except (json.JSONDecodeError, ValueError):
                        continue

        return None

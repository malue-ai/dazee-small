# -*- coding: utf-8 -*-
"""
Windows 执行审批策略引擎

管理 system.run 命令的执行权限，支持：
- glob 模式规则（* 匹配任意字符，? 匹配单字符）
- 按 shell 类型过滤（powershell/cmd 等）
- allow / deny 两种动作
- 持久化存储（JSON 文件）
- 远程管理（通过 system.execApprovals.get/set 命令）

规则评估顺序：从上到下，第一个匹配规则生效；无匹配则使用 defaultAction（默认 deny）。
"""

import fnmatch
import json
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ExecAction(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass
class ExecRule:
    """单条执行规则"""

    pattern: str = "*"
    action: ExecAction = ExecAction.DENY
    shells: Optional[List[str]] = None  # None 表示所有 shell 都适用
    description: Optional[str] = None
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "pattern": self.pattern,
            "action": self.action.value,
            "enabled": self.enabled,
        }
        if self.shells:
            d["shells"] = self.shells
        if self.description:
            d["description"] = self.description
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecRule":
        return cls(
            pattern=data.get("pattern", "*"),
            action=ExecAction(data.get("action", "deny")),
            shells=data.get("shells"),
            description=data.get("description"),
            enabled=data.get("enabled", True),
        )


@dataclass
class ExecEvalResult:
    """规则评估结果"""

    allowed: bool
    action: ExecAction
    matched_pattern: Optional[str] = None
    reason: Optional[str] = None


def _default_rules() -> List[ExecRule]:
    """内置默认规则：开放常用只读命令，封锁危险命令"""
    return [
        # ── 允许：常用只读 / 诊断命令 ──
        ExecRule("echo *", ExecAction.ALLOW, description="echo 命令"),
        ExecRule("Get-*", ExecAction.ALLOW, shells=["powershell", "pwsh"], description="PowerShell Get- cmdlet（只读）"),
        ExecRule("dir *", ExecAction.ALLOW, description="目录列表"),
        ExecRule("dir", ExecAction.ALLOW, description="目录列表"),
        ExecRule("hostname", ExecAction.ALLOW, description="主机名查询"),
        ExecRule("whoami", ExecAction.ALLOW, description="当前用户"),
        ExecRule("systeminfo", ExecAction.ALLOW, description="系统信息"),
        ExecRule("ipconfig *", ExecAction.ALLOW, description="网络配置"),
        ExecRule("ipconfig", ExecAction.ALLOW, description="网络配置"),
        ExecRule("ping *", ExecAction.ALLOW, description="Ping"),
        ExecRule("type *", ExecAction.ALLOW, shells=["cmd"], description="读取文件（cmd）"),
        ExecRule("cat *", ExecAction.ALLOW, description="读取文件"),
        ExecRule("tasklist*", ExecAction.ALLOW, description="进程列表"),
        ExecRule("netstat*", ExecAction.ALLOW, description="网络状态"),
        ExecRule("python *", ExecAction.ALLOW, description="Python 脚本"),
        ExecRule("python3 *", ExecAction.ALLOW, description="Python 脚本"),
        ExecRule("pip *", ExecAction.ALLOW, description="pip 包管理"),
        ExecRule("pip3 *", ExecAction.ALLOW, description="pip 包管理"),
        ExecRule("git *", ExecAction.ALLOW, description="Git 操作"),
        ExecRule("node *", ExecAction.ALLOW, description="Node.js"),
        ExecRule("npm *", ExecAction.ALLOW, description="npm 包管理"),
        # ── 拒绝：危险命令明确封锁 ──
        ExecRule("Remove-Item *", ExecAction.DENY, description="封锁文件删除"),
        ExecRule("rm *", ExecAction.DENY, description="封锁 rm"),
        ExecRule("del *", ExecAction.DENY, description="封锁 del"),
        ExecRule("Format-*", ExecAction.DENY, description="封锁磁盘格式化"),
        ExecRule("Stop-Computer*", ExecAction.DENY, description="封锁关机"),
        ExecRule("Restart-Computer*", ExecAction.DENY, description="封锁重启"),
        ExecRule("*Invoke-WebRequest*", ExecAction.DENY, description="封锁 web 下载执行"),
        ExecRule("*Start-Process*", ExecAction.DENY, description="封锁进程启动绕过"),
        ExecRule("*reg *", ExecAction.DENY, description="封锁注册表编辑"),
        ExecRule("shutdown*", ExecAction.DENY, description="封锁关机"),
        ExecRule("net user*", ExecAction.DENY, description="封锁账号操作"),
        ExecRule("net localgroup*", ExecAction.DENY, description="封锁组管理"),
        ExecRule("schtasks *", ExecAction.DENY, description="封锁计划任务"),
    ]


class ExecApprovalPolicy:
    """
    执行审批策略引擎

    策略规则从文件加载，支持运行时热更新。
    评估逻辑：规则从上到下匹配，第一个命中规则生效；无匹配时使用 defaultAction。
    """

    def __init__(self, data_dir: str) -> None:
        self._policy_path = os.path.join(data_dir, "exec-policy.json")
        self._rules: List[ExecRule] = []
        self._default_action: ExecAction = ExecAction.DENY
        self._load()

    @property
    def rules(self) -> List[ExecRule]:
        return list(self._rules)

    @property
    def default_action(self) -> ExecAction:
        return self._default_action

    def evaluate(self, command: str, shell: Optional[str] = None) -> ExecEvalResult:
        """评估命令是否允许执行"""
        if not command or not command.strip():
            return ExecEvalResult(
                allowed=False,
                action=ExecAction.DENY,
                reason="空命令",
            )

        normalized_shell = (shell or "powershell").lower()

        for rule in self._rules:
            if not rule.enabled:
                continue

            # shell 过滤
            if rule.shells:
                if not any(s.lower() == normalized_shell for s in rule.shells):
                    continue

            # 模式匹配（fnmatch，大小写不敏感）
            if fnmatch.fnmatch(command.lower(), rule.pattern.lower()):
                allowed = rule.action == ExecAction.ALLOW
                logger.debug(
                    f"[EXEC-POLICY] {'ALLOW' if allowed else 'DENY'}: "
                    f"'{command}' 匹配规则 '{rule.pattern}'"
                )
                return ExecEvalResult(
                    allowed=allowed,
                    action=rule.action,
                    matched_pattern=rule.pattern,
                    reason=rule.description or f"匹配规则: {rule.pattern}",
                )

        # 无规则匹配 → 使用默认动作
        default_allowed = self._default_action == ExecAction.ALLOW
        logger.debug(
            f"[EXEC-POLICY] DEFAULT {self._default_action.value.upper()}: "
            f"'{command}'（无匹配规则）"
        )
        return ExecEvalResult(
            allowed=default_allowed,
            action=self._default_action,
            reason="无匹配规则，使用默认策略",
        )

    def set_policy(
        self,
        rules: List[Dict[str, Any]],
        default_action: Optional[str] = None,
    ) -> None:
        """更新策略规则（远程管理入口）"""
        self._rules = [ExecRule.from_dict(r) for r in rules]
        if default_action:
            self._default_action = ExecAction(default_action)
        self._save()
        logger.info(f"[EXEC-POLICY] 策略已更新：{len(self._rules)} 条规则，默认={self._default_action.value}")

    def get_policy_dict(self) -> Dict[str, Any]:
        """获取策略的可序列化字典（用于 system.execApprovals.get 响应）"""
        return {
            "defaultAction": self._default_action.value,
            "rules": [r.to_dict() for r in self._rules],
            "policyPath": self._policy_path,
        }

    def _load(self) -> None:
        if os.path.isfile(self._policy_path):
            try:
                with open(self._policy_path, encoding="utf-8") as f:
                    data = json.load(f)
                self._rules = [ExecRule.from_dict(r) for r in data.get("rules", [])]
                self._default_action = ExecAction(data.get("defaultAction", "deny"))
                logger.info(
                    f"[EXEC-POLICY] 加载 {len(self._rules)} 条规则 from {self._policy_path}"
                )
                return
            except Exception as e:
                logger.warning(f"[EXEC-POLICY] 加载策略文件失败，使用默认策略: {e}")

        # 首次运行：写入默认策略
        self._rules = _default_rules()
        self._default_action = ExecAction.DENY
        logger.info("[EXEC-POLICY] 使用内置默认策略")
        self._save()

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._policy_path), exist_ok=True)
            data = {
                "defaultAction": self._default_action.value,
                "rules": [r.to_dict() for r in self._rules],
            }
            with open(self._policy_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[EXEC-POLICY] 保存策略失败: {e}")

"""
CodeOrchestrator - 代码生成、验证、执行编排器

职责：
- 统一管理代码生成 → 验证 → 执行 → 结果验证的完整流程
- 自动错误恢复：执行失败时自动分析错误并重试
- 状态追踪：记录每次执行的详细信息

设计原则：
- Code-First: 将代码生成和执行作为核心能力
- 验证闭环: 执行前验证 + 执行后验证
- 自动恢复: 错误自动分析和重试

使用方式：
    orchestrator = create_code_orchestrator(
        validator=validator,
        tracer=tracer
    )

    result = await orchestrator.execute_code(
        code=code,
        conversation_id=conversation_id,
        session_id=session_id,
        max_retries=3
    )
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from logger import get_logger

from .code_validator import CodeValidator, ValidationResult, create_code_validator
from .pipeline_tracer import E2EPipelineTracer, PipelineStage

logger = get_logger("code_orchestrator")


class ExecutionStatus(Enum):
    """执行状态"""

    PENDING = "pending"
    VALIDATING = "validating"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class ExecutionRecord:
    """执行记录"""

    attempt: int
    code: str
    status: ExecutionStatus

    # 验证结果
    validation_result: Optional[ValidationResult] = None

    # 执行结果
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    execution_time_ms: float = 0

    # 产物
    output_files: List[str] = field(default_factory=list)

    # 错误恢复
    error_analysis: Optional[Dict[str, Any]] = None
    fix_suggestion: Optional[str] = None

    # 时间戳
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attempt": self.attempt,
            "status": self.status.value,
            "validation": self.validation_result.to_dict() if self.validation_result else None,
            "stdout": self.stdout[:500] if self.stdout else "",
            "stderr": self.stderr[:500] if self.stderr else "",
            "exit_code": self.exit_code,
            "execution_time_ms": self.execution_time_ms,
            "output_files": self.output_files,
            "error_analysis": self.error_analysis,
            "fix_suggestion": self.fix_suggestion,
        }


@dataclass
class OrchestratorResult:
    """编排器执行结果"""

    success: bool
    final_code: str

    # 执行结果
    stdout: str = ""
    stderr: str = ""
    output_files: List[str] = field(default_factory=list)

    # 执行记录
    execution_records: List[ExecutionRecord] = field(default_factory=list)

    # 统计
    total_attempts: int = 0
    total_execution_time_ms: float = 0

    # 错误信息
    error: Optional[str] = None
    error_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "final_code": self.final_code[:1000] if self.final_code else "",
            "stdout": self.stdout[:500] if self.stdout else "",
            "stderr": self.stderr[:500] if self.stderr else "",
            "output_files": self.output_files,
            "total_attempts": self.total_attempts,
            "total_execution_time_ms": self.total_execution_time_ms,
            "error": self.error,
            "error_type": self.error_type,
            "execution_records": [r.to_dict() for r in self.execution_records],
        }


class CodeOrchestrator:
    """
    代码编排器

    管理代码执行的完整生命周期：
    1. 代码验证（语法 + 依赖 + 安全）
    2. 代码执行
    3. 结果验证
    4. 错误恢复（自动重试）
    """

    def __init__(
        self,
        validator: CodeValidator = None,
        tracer: E2EPipelineTracer = None,
        max_retries: int = 3,
        auto_fix_enabled: bool = True,
    ):
        """
        初始化编排器

        Args:
            validator: 代码验证器
            tracer: 管道追踪器
            max_retries: 最大重试次数
            auto_fix_enabled: 是否启用自动修复
        """
        self.validator = validator or create_code_validator()
        self.tracer = tracer
        self.max_retries = max_retries
        self.auto_fix_enabled = auto_fix_enabled

        # 已安装的包缓存（按 conversation_id）
        self._installed_packages: Dict[str, set] = {}

        # LLM 服务（用于代码修复，延迟初始化）
        self._fix_llm = None

        logger.info(f"✅ CodeOrchestrator 初始化完成 (max_retries={max_retries})")

    async def execute_code(
        self,
        code: str,
        conversation_id: str,
        session_id: str = None,
        return_files: List[str] = None,
        save_to: str = "",
        timeout: int = 300,
        max_retries: int = None,
        skip_validation: bool = False,
        on_retry: Callable[[int, str, str], Optional[str]] = None,
    ) -> OrchestratorResult:
        """
        执行代码（带完整验证和错误恢复）

        Args:
            code: Python 代码
            conversation_id: 对话ID（必须）
            session_id: 会话ID
            return_files: 要返回的文件列表
            save_to: 产物保存路径
            timeout: 超时时间（秒）
            max_retries: 最大重试次数（覆盖默认值）
            skip_validation: 跳过验证
            on_retry: 重试回调函数，参数为 (attempt, code, error)，返回修复后的代码

        Returns:
            OrchestratorResult
        """
        max_attempts = (max_retries or self.max_retries) + 1
        records: List[ExecutionRecord] = []
        current_code = code

        logger.info(f"\n{'='*60}")
        logger.info(f"🚀 CodeOrchestrator 开始执行")
        logger.info(f"   Conversation: {conversation_id}")
        logger.info(f"   代码长度: {len(code)} 字符")
        logger.info(f"   最大尝试: {max_attempts}")
        logger.info(f"{'='*60}")

        # 开始追踪（如果有 tracer）
        if self.tracer:
            self.tracer.log_code_execution()

        for attempt in range(1, max_attempts + 1):
            logger.info(f"\n📍 尝试 #{attempt}/{max_attempts}")

            record = ExecutionRecord(
                attempt=attempt,
                code=current_code,
                status=ExecutionStatus.PENDING,
                started_at=datetime.now(),
            )

            try:
                # ===== 阶段 1: 代码验证 =====
                if not skip_validation:
                    record.status = ExecutionStatus.VALIDATING

                    if self.tracer:
                        with self.tracer.stage("code_validation", "执行前代码验证") as stage:
                            stage.set_input({"code_length": len(current_code)})
                            validation_result = self._validate_code(current_code, conversation_id)
                            stage.set_output({"is_valid": validation_result.is_valid})
                    else:
                        validation_result = self._validate_code(current_code, conversation_id)

                    record.validation_result = validation_result

                    # 如果有致命错误，尝试修复
                    if not validation_result.is_valid:
                        logger.warning(f"❌ 验证失败: {validation_result.get_error_summary()}")

                        if self.auto_fix_enabled and attempt < max_attempts:
                            # 尝试自动修复
                            fixed_code = await self._try_fix_code(
                                current_code, validation_result, on_retry
                            )

                            if fixed_code and fixed_code != current_code:
                                logger.info("🔧 已生成修复代码，准备重试")
                                current_code = fixed_code
                                record.status = ExecutionStatus.RETRYING
                                record.fix_suggestion = "自动修复语法错误"
                                records.append(record)
                                continue

                        # 无法修复，记录失败
                        record.status = ExecutionStatus.FAILED
                        record.error_analysis = {"type": "validation_error"}
                        records.append(record)

                        return OrchestratorResult(
                            success=False,
                            final_code=current_code,
                            error=validation_result.get_error_summary(),
                            error_type="VALIDATION_ERROR",
                            execution_records=records,
                            total_attempts=attempt,
                        )

                # ===== 阶段 2: 代码执行 =====
                record.status = ExecutionStatus.EXECUTING

                if self.tracer:
                    with self.tracer.stage("code_execution", "代码执行") as stage:
                        stage.set_input(
                            {"conversation_id": conversation_id, "return_files": return_files}
                        )

                        exec_result = await self._execute_code(
                            code=current_code,
                            conversation_id=conversation_id,
                            session_id=session_id,
                            return_files=return_files or [],
                            save_to=save_to,
                            timeout=timeout,
                        )

                        stage.set_output(
                            {
                                "success": exec_result.get("success"),
                                "has_error": bool(exec_result.get("error")),
                            }
                        )
                else:
                    exec_result = await self._execute_code(
                        code=current_code,
                        conversation_id=conversation_id,
                        session_id=session_id,
                        return_files=return_files or [],
                        save_to=save_to,
                        timeout=timeout,
                    )

                # 更新记录
                record.stdout = exec_result.get("stdout", "")
                record.stderr = exec_result.get("stderr", "")
                record.execution_time_ms = exec_result.get("execution_time", 0) * 1000
                record.output_files = list(exec_result.get("files", {}).keys())

                # ===== 阶段 3: 结果验证 =====
                if exec_result.get("success"):
                    # 验证执行结果
                    result_validation = self.validator.validate_execution_result(
                        code=current_code, stdout=record.stdout, stderr=record.stderr, exit_code=0
                    )

                    if result_validation.is_valid:
                        # 执行成功！
                        record.status = ExecutionStatus.COMPLETED
                        record.completed_at = datetime.now()
                        records.append(record)

                        logger.info(f"✅ 执行成功 (耗时: {record.execution_time_ms:.1f}ms)")

                        return OrchestratorResult(
                            success=True,
                            final_code=current_code,
                            stdout=record.stdout,
                            stderr=record.stderr,
                            output_files=record.output_files,
                            execution_records=records,
                            total_attempts=attempt,
                            total_execution_time_ms=sum(r.execution_time_ms for r in records),
                        )
                    else:
                        # 结果验证失败，但不一定是致命错误
                        logger.warning(f"⚠️ 结果验证警告: {result_validation.issues}")

                        # 如果只有警告，仍然返回成功
                        if not result_validation.has_errors:
                            record.status = ExecutionStatus.COMPLETED
                            record.completed_at = datetime.now()
                            records.append(record)

                            return OrchestratorResult(
                                success=True,
                                final_code=current_code,
                                stdout=record.stdout,
                                stderr=record.stderr,
                                output_files=record.output_files,
                                execution_records=records,
                                total_attempts=attempt,
                                total_execution_time_ms=sum(r.execution_time_ms for r in records),
                            )

                # 执行失败，分析错误
                error_msg = exec_result.get("error") or record.stderr
                record.error_analysis = self._analyze_execution_error(error_msg)

                logger.warning(f"❌ 执行失败: {error_msg[:200]}")

                # 尝试修复并重试
                if self.auto_fix_enabled and attempt < max_attempts:
                    fixed_code = await self._try_fix_execution_error(
                        current_code, error_msg, record.error_analysis, on_retry
                    )

                    if fixed_code and fixed_code != current_code:
                        logger.info("🔧 已生成修复代码，准备重试")
                        current_code = fixed_code
                        record.status = ExecutionStatus.RETRYING
                        record.fix_suggestion = record.error_analysis.get("suggestion")
                        records.append(record)
                        continue

                # 无法修复
                record.status = ExecutionStatus.FAILED
                records.append(record)

            except Exception as e:
                logger.error(f"❌ 编排器异常: {e}", exc_info=True)
                record.status = ExecutionStatus.FAILED
                record.error_analysis = {"type": "orchestrator_error", "message": str(e)}
                records.append(record)

                if attempt >= max_attempts:
                    return OrchestratorResult(
                        success=False,
                        final_code=current_code,
                        error=str(e),
                        error_type="ORCHESTRATOR_ERROR",
                        execution_records=records,
                        total_attempts=attempt,
                    )

        # 所有尝试都失败
        return OrchestratorResult(
            success=False,
            final_code=current_code,
            error="达到最大重试次数",
            error_type="MAX_RETRIES_EXCEEDED",
            stdout=records[-1].stdout if records else "",
            stderr=records[-1].stderr if records else "",
            execution_records=records,
            total_attempts=len(records),
        )

    def _validate_code(self, code: str, conversation_id: str) -> ValidationResult:
        """验证代码"""
        installed = self._installed_packages.get(conversation_id, set())
        return self.validator.validate_all(code, installed)

    async def _execute_code(
        self,
        code: str,
        conversation_id: str,
        session_id: str = None,
        return_files: List[str] = None,
        save_to: str = "",
        timeout: int = 300,
    ) -> Dict[str, Any]:
        """执行代码（需要子类实现具体执行逻辑）"""
        raise NotImplementedError("代码执行后端未配置")

    def _analyze_execution_error(self, error: str) -> Dict[str, Any]:
        """分析执行错误"""
        error_lower = error.lower()

        if "modulenotfounderror" in error_lower or "no module named" in error_lower:
            import re

            match = re.search(r"no module named ['\"]?(\w+)['\"]?", error_lower)
            module = match.group(1) if match else "unknown"
            return {
                "type": "missing_module",
                "module": module,
                "suggestion": f"添加 'import {module}' 或安装包",
                "auto_fixable": True,
            }

        elif "filenotfounderror" in error_lower:
            return {
                "type": "file_not_found",
                "suggestion": "检查文件路径是否正确",
                "auto_fixable": False,
            }

        elif "syntaxerror" in error_lower:
            return {"type": "syntax_error", "suggestion": "检查代码语法", "auto_fixable": True}

        elif "indentationerror" in error_lower:
            return {"type": "indentation_error", "suggestion": "检查代码缩进", "auto_fixable": True}

        elif "typeerror" in error_lower:
            return {"type": "type_error", "suggestion": "检查参数类型", "auto_fixable": False}

        elif "nameerror" in error_lower:
            return {"type": "name_error", "suggestion": "检查变量是否定义", "auto_fixable": True}

        elif "keyerror" in error_lower:
            return {"type": "key_error", "suggestion": "检查字典键是否存在", "auto_fixable": False}

        elif "timeout" in error_lower:
            return {
                "type": "timeout",
                "suggestion": "代码执行超时，考虑优化或增加超时时间",
                "auto_fixable": False,
            }

        else:
            return {
                "type": "unknown_error",
                "suggestion": "检查完整错误信息",
                "auto_fixable": False,
            }

    async def _try_fix_code(
        self, code: str, validation_result: ValidationResult, on_retry: Callable = None
    ) -> Optional[str]:
        """尝试修复代码（验证错误）"""
        # 如果提供了自定义修复函数，优先使用
        if on_retry:
            error_summary = validation_result.get_error_summary()
            try:
                fixed = on_retry(0, code, error_summary)
                if fixed:
                    return fixed
            except Exception as e:
                logger.warning(f"自定义修复函数失败: {e}")

        # 简单的自动修复逻辑
        errors = validation_result.errors
        if not errors:
            return None

        # 目前只支持简单的修复
        # TODO: 集成 LLM 进行智能修复
        return None

    async def _try_fix_execution_error(
        self, code: str, error: str, error_analysis: Dict[str, Any], on_retry: Callable = None
    ) -> Optional[str]:
        """尝试修复代码（执行错误）"""
        # 如果提供了自定义修复函数
        if on_retry:
            try:
                fixed = on_retry(0, code, error)
                if fixed:
                    return fixed
            except Exception as e:
                logger.warning(f"自定义修复函数失败: {e}")

        # 简单的自动修复
        error_type = error_analysis.get("type")

        if error_type == "missing_module":
            # 对于缺失模块，可能需要安装依赖
            return code

        # TODO: 更多自动修复逻辑
        return None

    def update_installed_packages(self, conversation_id: str, packages: List[str]):
        """更新已安装的包列表"""
        if conversation_id not in self._installed_packages:
            self._installed_packages[conversation_id] = set()
        self._installed_packages[conversation_id].update(packages)


def create_code_orchestrator(
    validator: CodeValidator = None,
    tracer: E2EPipelineTracer = None,
    max_retries: int = 3,
    auto_fix_enabled: bool = True,
) -> CodeOrchestrator:
    """
    创建代码编排器

    Args:
        validator: 代码验证器
        tracer: 管道追踪器
        max_retries: 最大重试次数
        auto_fix_enabled: 是否启用自动修复

    Returns:
        CodeOrchestrator 实例
    """
    return CodeOrchestrator(
        validator=validator,
        tracer=tracer,
        max_retries=max_retries,
        auto_fix_enabled=auto_fix_enabled,
    )

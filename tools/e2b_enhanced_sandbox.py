"""
E2B Enhanced Sandbox - 增强版 E2B 沙箱

基于原有 E2BPythonSandbox，集成 CodeOrchestrator 提供：
- 执行前代码验证
- 自动错误恢复和重试
- 端到端管道追踪
- 更丰富的执行反馈

设计原则（Code-First + VM Scaffolding）：
- 代码优先：将代码生成和执行作为核心能力
- 虚拟机脚手架：E2B 沙箱作为安全的执行环境
- 验证闭环：执行前验证 + 执行后验证
- 可观测性：完整的执行链路追踪

使用方式：
    sandbox = create_enhanced_sandbox(
        event_manager=event_manager,
        workspace_base_dir="./workspace"
    )
    
    result = await sandbox.execute_with_orchestration(
        code=code,
        conversation_id=conversation_id,
        session_id=session_id,
        max_retries=3
    )
"""

import os
import json
import time
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path

from logger import get_logger
from tools.e2b_sandbox import E2BPythonSandbox, E2B_AVAILABLE

# 延迟导入编排模块
try:
    from core.orchestration import (
        CodeOrchestrator,
        CodeValidator,
        E2EPipelineTracer,
        create_code_orchestrator,
        create_code_validator,
        create_pipeline_tracer
    )
    ORCHESTRATION_AVAILABLE = True
except ImportError:
    ORCHESTRATION_AVAILABLE = False

logger = get_logger("e2b_enhanced_sandbox")


class E2BEnhancedSandbox(E2BPythonSandbox):
    """
    增强版 E2B 沙箱
    
    在原有功能基础上增加：
    - CodeOrchestrator 集成：代码验证 + 自动重试
    - E2EPipelineTracer 集成：完整执行链路追踪
    - 更丰富的执行反馈
    
    API 保持向后兼容：
    - execute(): 原有 API，直接执行
    - execute_with_orchestration(): 新 API，带编排和验证
    """
    
    def __init__(
        self,
        api_key: str = None,
        event_manager=None,
        workspace_base_dir: str = "./workspace",
        enable_orchestration: bool = True,
        max_retries: int = 3
    ):
        """
        初始化增强版沙箱
        
        Args:
            api_key: E2B API密钥
            event_manager: EventManager实例
            workspace_base_dir: workspace 根目录
            enable_orchestration: 是否启用编排功能
            max_retries: 默认最大重试次数
        """
        # 调用父类初始化
        super().__init__(
            api_key=api_key,
            event_manager=event_manager,
            workspace_base_dir=workspace_base_dir
        )
        
        self.enable_orchestration = enable_orchestration and ORCHESTRATION_AVAILABLE
        self.default_max_retries = max_retries
        
        # 初始化验证器
        if self.enable_orchestration:
            self.validator = create_code_validator()
            logger.info("✅ E2BEnhancedSandbox 已启用编排功能")
        else:
            self.validator = None
            if enable_orchestration and not ORCHESTRATION_AVAILABLE:
                logger.warning("⚠️ 编排模块未找到，使用基础模式")
        
        # 追踪器缓存（按 session_id）
        self._tracers: Dict[str, E2EPipelineTracer] = {}
        
        logger.info("✅ E2BEnhancedSandbox 初始化完成 (V2.1)")
    
    def get_or_create_tracer(
        self,
        session_id: str,
        conversation_id: str = None
    ) -> Optional[E2EPipelineTracer]:
        """
        获取或创建追踪器
        
        Args:
            session_id: 会话ID
            conversation_id: 对话ID
            
        Returns:
            E2EPipelineTracer 实例或 None
        """
        if not self.enable_orchestration:
            return None
        
        if session_id not in self._tracers:
            self._tracers[session_id] = create_pipeline_tracer(
                session_id=session_id,
                conversation_id=conversation_id
            )
        
        return self._tracers[session_id]
    
    async def execute_with_orchestration(
        self,
        code: str,
        conversation_id: str,
        session_id: str = None,
        user_id: str = None,
        template: str = "base",
        return_files: List[str] = None,
        save_to: str = "",
        timeout: int = 300,
        max_retries: int = None,
        skip_validation: bool = False,
        enable_tracing: bool = True
    ) -> Dict[str, Any]:
        """
        带编排的代码执行
        
        执行流程：
        1. 创建/获取追踪器
        2. 代码语法验证
        3. 依赖检查（自动安装）
        4. 安全检查（警告）
        5. E2B 沙箱执行
        6. 结果验证
        7. 如果失败，分析错误并重试
        
        Args:
            code: Python 代码
            conversation_id: 对话ID（必须）
            session_id: 会话ID
            user_id: 用户ID
            template: 沙箱模板
            return_files: 要返回的文件列表
            save_to: 产物保存路径
            timeout: 超时时间
            max_retries: 最大重试次数
            skip_validation: 跳过验证
            enable_tracing: 是否启用追踪
            
        Returns:
            执行结果字典，包含：
            - success: 是否成功
            - stdout: 标准输出
            - stderr: 标准错误
            - files: 输出文件
            - execution_time: 执行时间
            - attempts: 尝试次数
            - validation: 验证结果
            - trace: 追踪信息（如果启用）
        """
        start_time = time.time()
        max_attempts = (max_retries or self.default_max_retries) + 1
        
        # 创建追踪器
        tracer = None
        if enable_tracing and self.enable_orchestration:
            tracer = self.get_or_create_tracer(session_id, conversation_id)
            tracer.set_user_query(f"[代码执行] {len(code)} 字符")
        
        logger.info(f"\n{'='*60}")
        logger.info(f"🚀 E2B Enhanced Sandbox 开始执行")
        logger.info(f"   Conversation: {conversation_id}")
        logger.info(f"   代码长度: {len(code)} 字符")
        logger.info(f"   最大尝试: {max_attempts}")
        logger.info(f"   追踪: {'启用' if tracer else '禁用'}")
        logger.info(f"{'='*60}")
        
        current_code = code
        attempts = []
        
        for attempt in range(1, max_attempts + 1):
            attempt_start = time.time()
            attempt_result = {
                "attempt": attempt,
                "code": current_code[:500] + "..." if len(current_code) > 500 else current_code,
                "validation": None,
                "execution": None,
                "error_analysis": None
            }
            
            logger.info(f"\n📍 尝试 #{attempt}/{max_attempts}")
            
            try:
                # ===== 阶段 1: 代码验证 =====
                if not skip_validation and self.validator:
                    if tracer:
                        stage = tracer.create_stage("code_validation")
                        stage.start()
                        stage.set_input({"code_length": len(current_code)})
                    
                    validation_result = self.validator.validate_all(
                        current_code,
                        self._get_installed_packages(conversation_id)
                    )
                    
                    attempt_result["validation"] = validation_result.to_dict()
                    
                    if tracer:
                        stage.set_output({
                            "is_valid": validation_result.is_valid,
                            "error_count": len(validation_result.errors),
                            "warning_count": len(validation_result.warnings)
                        })
                        if validation_result.is_valid:
                            stage.complete()
                        else:
                            stage.fail(Exception(validation_result.get_error_summary()))
                    
                    # 检查验证结果
                    if not validation_result.is_valid:
                        logger.warning(f"❌ 代码验证失败: {validation_result.get_error_summary()}")
                        
                        # 如果还有重试机会，尝试修复
                        if attempt < max_attempts:
                            fixed_code = self._try_simple_fix(
                                current_code,
                                validation_result
                            )
                            if fixed_code and fixed_code != current_code:
                                logger.info("🔧 应用简单修复，准备重试")
                                current_code = fixed_code
                                attempts.append(attempt_result)
                                continue
                        
                        # 无法修复，返回失败
                        attempts.append(attempt_result)
                        return {
                            "success": False,
                            "error": validation_result.get_error_summary(),
                            "error_type": "VALIDATION_ERROR",
                            "stdout": "",
                            "stderr": "",
                            "files": {},
                            "execution_time": time.time() - start_time,
                            "attempts": attempts,
                            "validation": validation_result.to_dict()
                        }
                    
                    # 显示警告（但不阻止执行）
                    if validation_result.warnings:
                        logger.warning(f"⚠️ 代码验证警告: {len(validation_result.warnings)} 个")
                        for w in validation_result.warnings[:3]:
                            logger.warning(f"   - {w.message}")
                
                # ===== 阶段 2: E2B 执行 =====
                if tracer:
                    stage = tracer.create_stage("code_execution")
                    stage.start()
                    stage.set_input({
                        "conversation_id": conversation_id,
                        "return_files": return_files
                    })
                
                # 调用父类的 execute 方法
                exec_result = await super().execute(
                    session_id=session_id,
                    code=current_code,
                    conversation_id=conversation_id,
                    user_id=user_id,
                    template=template,
                    return_files=return_files or [],
                    save_to=save_to,
                    timeout=timeout,
                    auto_install=True,
                    enable_stream=bool(self.event_manager and session_id)
                )
                
                attempt_result["execution"] = {
                    "success": exec_result.get("success"),
                    "stdout_length": len(exec_result.get("stdout", "")),
                    "stderr_length": len(exec_result.get("stderr", "")),
                    "files_count": len(exec_result.get("files", {}))
                }
                
                if tracer:
                    stage.set_output(attempt_result["execution"])
                    if exec_result.get("success"):
                        stage.complete()
                    else:
                        stage.fail(Exception(exec_result.get("error", "执行失败")))
                
                # ===== 阶段 3: 结果验证 =====
                if exec_result.get("success"):
                    # 验证执行结果
                    if self.validator:
                        result_validation = self.validator.validate_execution_result(
                            code=current_code,
                            stdout=exec_result.get("stdout", ""),
                            stderr=exec_result.get("stderr", ""),
                            exit_code=0
                        )
                        
                        if not result_validation.is_valid:
                            logger.warning(f"⚠️ 结果验证失败: {result_validation.issues}")
                            # 结果验证失败通常不需要重试，只记录警告
                    
                    # 执行成功！
                    attempts.append(attempt_result)
                    
                    if tracer:
                        tracer.finish()
                    
                    return {
                        "success": True,
                        "stdout": exec_result.get("stdout", ""),
                        "stderr": exec_result.get("stderr", ""),
                        "files": exec_result.get("files", {}),
                        "execution_time": time.time() - start_time,
                        "attempts": attempts,
                        "total_attempts": attempt
                    }
                
                # 执行失败，分析错误
                error_msg = exec_result.get("error") or exec_result.get("stderr", "")
                error_analysis = self._analyze_error(error_msg)
                attempt_result["error_analysis"] = error_analysis
                
                logger.warning(f"❌ 执行失败: {error_msg[:200]}")
                logger.debug(f"   错误分析: {error_analysis}")
                
                # 尝试修复并重试
                if attempt < max_attempts:
                    fixed_code = self._try_fix_for_error(
                        current_code,
                        error_msg,
                        error_analysis
                    )
                    
                    if fixed_code and fixed_code != current_code:
                        logger.info(f"🔧 应用修复建议: {error_analysis.get('suggestion', 'N/A')}")
                        current_code = fixed_code
                        attempts.append(attempt_result)
                        continue
                
                # 无法修复
                attempts.append(attempt_result)
                
            except Exception as e:
                logger.error(f"❌ 执行异常: {e}", exc_info=True)
                attempt_result["error_analysis"] = {
                    "type": "exception",
                    "message": str(e)
                }
                attempts.append(attempt_result)
                
                if attempt >= max_attempts:
                    break
        
        # 所有尝试都失败
        if tracer:
            tracer.finish()
        
        return {
            "success": False,
            "error": "达到最大重试次数",
            "error_type": "MAX_RETRIES_EXCEEDED",
            "stdout": attempts[-1].get("execution", {}).get("stdout", "") if attempts else "",
            "stderr": attempts[-1].get("execution", {}).get("stderr", "") if attempts else "",
            "files": {},
            "execution_time": time.time() - start_time,
            "attempts": attempts,
            "total_attempts": len(attempts)
        }
    
    def _get_installed_packages(self, conversation_id: str) -> set:
        """获取已安装的包列表"""
        session_data = self._get_session_data(conversation_id)
        return set(session_data.get("installed_packages", []))
    
    def _analyze_error(self, error: str) -> Dict[str, Any]:
        """分析错误信息"""
        error_lower = error.lower()
        
        if "modulenotfounderror" in error_lower or "no module named" in error_lower:
            import re
            match = re.search(r"no module named ['\"]?(\w+)['\"]?", error_lower)
            module = match.group(1) if match else "unknown"
            return {
                "type": "missing_module",
                "module": module,
                "suggestion": f"安装包: pip install {module}",
                "auto_fixable": True
            }
        
        elif "filenotfounderror" in error_lower:
            return {
                "type": "file_not_found",
                "suggestion": "检查文件路径",
                "auto_fixable": False
            }
        
        elif "syntaxerror" in error_lower:
            return {
                "type": "syntax_error",
                "suggestion": "修复语法错误",
                "auto_fixable": True
            }
        
        elif "indentationerror" in error_lower:
            return {
                "type": "indentation_error",
                "suggestion": "修复缩进",
                "auto_fixable": True
            }
        
        elif "nameerror" in error_lower:
            return {
                "type": "name_error",
                "suggestion": "检查变量定义",
                "auto_fixable": False
            }
        
        elif "timeout" in error_lower:
            return {
                "type": "timeout",
                "suggestion": "优化代码或增加超时时间",
                "auto_fixable": False
            }
        
        else:
            return {
                "type": "unknown",
                "suggestion": "检查错误详情",
                "auto_fixable": False
            }
    
    def _try_simple_fix(self, code: str, validation_result) -> Optional[str]:
        """尝试简单修复（验证错误）"""
        # 目前只支持简单的自动修复
        # TODO: 集成 LLM 进行智能修复
        return None
    
    def _try_fix_for_error(
        self,
        code: str,
        error: str,
        error_analysis: Dict[str, Any]
    ) -> Optional[str]:
        """尝试修复执行错误"""
        error_type = error_analysis.get("type")
        
        # 对于缺失模块，E2B 会自动安装，不需要修改代码
        if error_type == "missing_module":
            return code
        
        # TODO: 更多自动修复逻辑
        return None
    
    def clear_tracer(self, session_id: str):
        """清除追踪器"""
        if session_id in self._tracers:
            del self._tracers[session_id]
    
    def get_tracer_report(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取追踪报告"""
        tracer = self._tracers.get(session_id)
        if tracer:
            return tracer.to_dict()
        return None


def create_enhanced_sandbox(
    api_key: str = None,
    event_manager=None,
    workspace_base_dir: str = "./workspace",
    enable_orchestration: bool = True,
    max_retries: int = 3
) -> E2BEnhancedSandbox:
    """
    创建增强版 E2B 沙箱
    
    Args:
        api_key: E2B API密钥
        event_manager: EventManager实例
        workspace_base_dir: workspace 根目录
        enable_orchestration: 是否启用编排功能
        max_retries: 默认最大重试次数
        
    Returns:
        E2BEnhancedSandbox 实例
    """
    return E2BEnhancedSandbox(
        api_key=api_key,
        event_manager=event_manager,
        workspace_base_dir=workspace_base_dir,
        enable_orchestration=enable_orchestration,
        max_retries=max_retries
    )


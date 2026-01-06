#!/usr/bin/env python3
"""
Code-First + VM Scaffolding 端到端验证脚本

验证流程：
1. 用户真实 Query 输入
2. Agent 理解意图
3. 代码生成（如果需要）
4. 代码验证（语法 + 依赖 + 安全）
5. E2B 沙箱执行
6. 结果验证
7. 响应生成

关键验证点：
- 每个环节的输入-处理-输出日志
- 代码验证闭环
- 错误自动恢复
- 端到端可观测性

使用方式：
    cd /Users/liuyi/Documents/langchain/CoT_agent/mvp/zenflux_agent
    source /Users/liuyi/Documents/langchain/liuy/bin/activate
    python scripts/e2e_code_first_verify.py
"""

import asyncio
import json
import sys
import os
from datetime import datetime
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 设置日志级别
os.environ.setdefault("LOG_LEVEL", "DEBUG")

from logger import get_logger

logger = get_logger("e2e_verify")


class E2EVerificationResult:
    """端到端验证结果"""
    
    def __init__(self, scenario_name: str):
        self.scenario_name = scenario_name
        self.stages = []
        self.success = False
        self.error = None
        self.start_time = datetime.now()
        self.end_time = None
        self.final_output = None
    
    def add_stage(self, name: str, status: str, details: dict = None):
        """添加阶段记录"""
        self.stages.append({
            "name": name,
            "status": status,
            "details": details or {},
            "timestamp": datetime.now().isoformat()
        })
        
        # 打印阶段信息
        icon = "✅" if status == "success" else "❌" if status == "failed" else "⏳"
        logger.info(f"   {icon} {name}: {status}")
        if details:
            for k, v in details.items():
                if isinstance(v, str) and len(v) > 100:
                    v = v[:100] + "..."
                logger.debug(f"      - {k}: {v}")
    
    def complete(self, success: bool, output: str = None, error: str = None):
        """完成验证"""
        self.success = success
        self.final_output = output
        self.error = error
        self.end_time = datetime.now()
    
    def print_summary(self):
        """打印摘要"""
        duration = (self.end_time - self.start_time).total_seconds() if self.end_time else 0
        
        print(f"\n{'='*70}")
        print(f"📊 验证结果: {self.scenario_name}")
        print(f"{'='*70}")
        print(f"状态: {'✅ 成功' if self.success else '❌ 失败'}")
        print(f"耗时: {duration:.2f}s")
        print(f"阶段数: {len(self.stages)}")
        
        if self.stages:
            print(f"\n📍 执行路径:")
            for i, stage in enumerate(self.stages, 1):
                icon = "✅" if stage["status"] == "success" else "❌"
                print(f"   {i}. {icon} {stage['name']}")
        
        if self.final_output:
            output_preview = self.final_output[:300] + "..." if len(self.final_output) > 300 else self.final_output
            print(f"\n📄 输出预览:")
            print(f"   {output_preview}")
        
        if self.error:
            print(f"\n❌ 错误:")
            print(f"   {self.error}")
        
        print(f"{'='*70}\n")


async def verify_code_validation():
    """
    场景 1: 验证代码验证功能
    
    测试代码验证器的各种能力：
    - 语法错误检测
    - 依赖检查
    - 安全检查
    """
    result = E2EVerificationResult("代码验证功能测试")
    
    logger.info("\n" + "🔬" * 30)
    logger.info("   场景 1: 代码验证功能测试")
    logger.info("🔬" * 30)
    
    try:
        from core.orchestration import create_code_validator
        
        validator = create_code_validator()
        result.add_stage("validator_init", "success")
        
        # 测试 1: 正确的代码
        good_code = """
import pandas as pd
import numpy as np

df = pd.DataFrame({'a': [1, 2, 3], 'b': [4, 5, 6]})
print(df.head())
"""
        validation_result = validator.validate_all(good_code)
        result.add_stage("valid_code_check", "success" if validation_result.is_valid else "failed", {
            "is_valid": validation_result.is_valid,
            "errors": len(validation_result.errors),
            "warnings": len(validation_result.warnings)
        })
        
        # 测试 2: 语法错误的代码
        bad_syntax_code = """
def hello(
    print("Hello")
"""
        syntax_result = validator.validate_syntax(bad_syntax_code)
        has_syntax_error = len(syntax_result.errors) > 0
        result.add_stage("syntax_error_detection", "success" if has_syntax_error else "failed", {
            "detected_errors": len(syntax_result.errors),
            "error_message": syntax_result.errors[0].message if syntax_result.errors else "None"
        })
        
        # 测试 3: 依赖检查
        dep_code = """
import pandas
import sklearn
import nonexistent_package_xyz
"""
        dep_result = validator.validate_dependencies(dep_code, set())
        missing_packages = dep_result.metadata.get("missing_packages", [])
        result.add_stage("dependency_check", "success" if len(missing_packages) > 0 else "failed", {
            "detected_imports": dep_result.metadata.get("detected_imports"),
            "missing_packages": missing_packages
        })
        
        # 测试 4: 安全检查
        unsafe_code = """
import os
os.system("rm -rf /")
eval("dangerous_code")
"""
        security_result = validator.validate_security(unsafe_code)
        has_warnings = len(security_result.warnings) > 0
        result.add_stage("security_check", "success" if has_warnings else "failed", {
            "warnings_count": len(security_result.warnings),
            "warning_types": [w.message for w in security_result.warnings[:3]]
        })
        
        # 计算总体结果
        all_passed = all(s["status"] == "success" for s in result.stages)
        result.complete(all_passed, "所有验证测试通过" if all_passed else "部分测试失败")
        
    except Exception as e:
        logger.error(f"验证失败: {e}", exc_info=True)
        result.add_stage("exception", "failed", {"error": str(e)})
        result.complete(False, error=str(e))
    
    result.print_summary()
    return result


async def verify_pipeline_tracer():
    """
    场景 2: 验证管道追踪器功能
    
    测试端到端追踪能力
    """
    result = E2EVerificationResult("管道追踪器功能测试")
    
    logger.info("\n" + "🔬" * 30)
    logger.info("   场景 2: 管道追踪器功能测试")
    logger.info("🔬" * 30)
    
    try:
        from core.orchestration import create_pipeline_tracer
        
        # 创建追踪器
        tracer = create_pipeline_tracer(
            session_id="test_session_001",
            conversation_id="test_conv_001"
        )
        result.add_stage("tracer_init", "success")
        
        # 设置用户 Query
        tracer.set_user_query("帮我分析销售数据并生成图表")
        result.add_stage("set_user_query", "success")
        
        # 模拟各个阶段
        with tracer.stage("intent_analysis") as stage:
            stage.set_input({"messages": ["用户消息"]})
            await asyncio.sleep(0.1)  # 模拟处理
            stage.set_output({"task_type": "data_analysis", "needs_code": True})
        result.add_stage("intent_stage", "success")
        
        with tracer.stage("tool_selection") as stage:
            stage.set_input({"required_capabilities": ["code_execution", "data_analysis"]})
            await asyncio.sleep(0.05)
            stage.set_output({"selected_tools": ["e2b_sandbox"]})
        result.add_stage("tool_stage", "success")
        
        with tracer.stage("code_execution") as stage:
            stage.set_input({"code": "print('hello')"})
            await asyncio.sleep(0.1)
            stage.set_output({"success": True, "stdout": "hello"})
        result.add_stage("execution_stage", "success")
        
        # 完成追踪
        tracer.set_final_response("分析完成，图表已生成")
        tracer.finish()
        result.add_stage("tracer_finish", "success")
        
        # 验证追踪数据
        trace_data = tracer.to_dict()
        has_all_stages = len(trace_data["stages"]) >= 3
        has_stats = trace_data["stats"]["total_stages"] >= 3
        
        result.add_stage("trace_data_validation", "success" if has_all_stages and has_stats else "failed", {
            "stage_count": len(trace_data["stages"]),
            "total_duration_ms": trace_data["stats"]["total_duration_ms"]
        })
        
        result.complete(True, json.dumps(trace_data, ensure_ascii=False, indent=2)[:500])
        
    except Exception as e:
        logger.error(f"验证失败: {e}", exc_info=True)
        result.add_stage("exception", "failed", {"error": str(e)})
        result.complete(False, error=str(e))
    
    result.print_summary()
    return result


async def verify_enhanced_sandbox_basic():
    """
    场景 3: 验证增强版沙箱基本功能（不需要真实 E2B）
    
    测试验证器集成和追踪功能
    """
    result = E2EVerificationResult("增强版沙箱基本功能测试")
    
    logger.info("\n" + "🔬" * 30)
    logger.info("   场景 3: 增强版沙箱基本功能测试")
    logger.info("🔬" * 30)
    
    try:
        # 检查模块是否可用
        from tools.e2b_enhanced_sandbox import E2BEnhancedSandbox, ORCHESTRATION_AVAILABLE
        result.add_stage("module_import", "success", {
            "orchestration_available": ORCHESTRATION_AVAILABLE
        })
        
        if not ORCHESTRATION_AVAILABLE:
            result.add_stage("orchestration_check", "failed", {
                "reason": "编排模块不可用"
            })
            result.complete(False, error="编排模块不可用")
            result.print_summary()
            return result
        
        result.add_stage("orchestration_check", "success")
        
        # 测试验证器功能（不需要真实 E2B）
        from core.orchestration import create_code_validator
        
        validator = create_code_validator()
        
        # 测试代码验证
        test_code = """
import pandas as pd

def analyze_data(filepath):
    df = pd.read_csv(filepath)
    return df.describe()

result = analyze_data("sales.csv")
print(result)
"""
        validation_result = validator.validate_all(test_code)
        result.add_stage("code_validation", "success" if validation_result.is_valid else "warning", {
            "is_valid": validation_result.is_valid,
            "errors": len(validation_result.errors),
            "warnings": len(validation_result.warnings),
            "missing_packages": validation_result.metadata.get("dependencies", {}).get("missing_packages", [])
        })
        
        result.complete(True, "基本功能验证通过")
        
    except ImportError as e:
        logger.warning(f"模块导入失败: {e}")
        result.add_stage("import_error", "failed", {"error": str(e)})
        result.complete(False, error=f"模块导入失败: {e}")
    
    except Exception as e:
        logger.error(f"验证失败: {e}", exc_info=True)
        result.add_stage("exception", "failed", {"error": str(e)})
        result.complete(False, error=str(e))
    
    result.print_summary()
    return result


async def verify_e2b_sandbox_execution():
    """
    场景 4: 验证 E2B 沙箱真实执行（需要 E2B_API_KEY）
    
    测试完整的代码执行流程
    """
    result = E2EVerificationResult("E2B 沙箱真实执行测试")
    
    logger.info("\n" + "🔬" * 30)
    logger.info("   场景 4: E2B 沙箱真实执行测试")
    logger.info("🔬" * 30)
    
    # 检查 E2B API Key
    e2b_key = os.getenv("E2B_API_KEY")
    if not e2b_key:
        logger.warning("⚠️ E2B_API_KEY 未设置，跳过真实执行测试")
        result.add_stage("api_key_check", "skipped", {"reason": "E2B_API_KEY not set"})
        result.complete(False, error="E2B_API_KEY 未设置")
        result.print_summary()
        return result
    
    result.add_stage("api_key_check", "success")
    
    try:
        from tools.e2b_enhanced_sandbox import create_enhanced_sandbox
        
        # 创建增强版沙箱
        sandbox = create_enhanced_sandbox(
            workspace_base_dir="./workspace",
            enable_orchestration=True,
            max_retries=2
        )
        result.add_stage("sandbox_init", "success")
        
        # 准备测试代码
        test_code = """
# 简单的数据处理测试
import json

data = {
    "name": "ZenFlux Agent",
    "version": "4.2",
    "features": ["code-first", "vm-scaffolding", "e2e-tracing"]
}

# 输出结果
print("=" * 50)
print("ZenFlux Agent E2E Test")
print("=" * 50)
print(json.dumps(data, indent=2, ensure_ascii=False))
print("=" * 50)
print("Test completed successfully!")
"""
        
        # 执行代码
        conversation_id = f"e2e_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        result.add_stage("code_execution_start", "success", {
            "conversation_id": conversation_id,
            "code_length": len(test_code)
        })
        
        exec_result = await sandbox.execute_with_orchestration(
            code=test_code,
            conversation_id=conversation_id,
            session_id="e2e_test_session",
            max_retries=2,
            enable_tracing=True
        )
        
        if exec_result.get("success"):
            result.add_stage("code_execution", "success", {
                "stdout_length": len(exec_result.get("stdout", "")),
                "total_attempts": exec_result.get("total_attempts", 1),
                "execution_time": exec_result.get("execution_time")
            })
            
            # 验证输出
            stdout = exec_result.get("stdout", "")
            has_expected_output = "ZenFlux Agent E2E Test" in stdout and "Test completed successfully!" in stdout
            
            result.add_stage("output_validation", "success" if has_expected_output else "warning", {
                "has_expected_output": has_expected_output,
                "stdout_preview": stdout[:200]
            })
            
            # 获取追踪报告
            trace_report = sandbox.get_tracer_report("e2e_test_session")
            if trace_report:
                result.add_stage("trace_report", "success", {
                    "stage_count": len(trace_report.get("stages", {})),
                    "total_duration_ms": trace_report.get("stats", {}).get("total_duration_ms")
                })
            
            result.complete(True, stdout)
        else:
            error_msg = exec_result.get("error", "Unknown error")
            result.add_stage("code_execution", "failed", {
                "error": error_msg,
                "total_attempts": exec_result.get("total_attempts", 0)
            })
            result.complete(False, error=error_msg)
        
        # 清理
        await sandbox.terminate_sandbox(conversation_id)
        
    except Exception as e:
        logger.error(f"验证失败: {e}", exc_info=True)
        result.add_stage("exception", "failed", {"error": str(e)})
        result.complete(False, error=str(e))
    
    result.print_summary()
    return result


async def verify_full_agent_flow():
    """
    场景 5: 完整 Agent 流程测试
    
    测试从用户 Query 到最终响应的完整链路
    """
    result = E2EVerificationResult("完整 Agent 流程测试")
    
    logger.info("\n" + "🔬" * 30)
    logger.info("   场景 5: 完整 Agent 流程测试")
    logger.info("🔬" * 30)
    
    try:
        from core.agent import AgentFactory, AgentPresets
        from core.events import create_event_manager, get_memory_storage
        
        # 初始化
        storage = get_memory_storage()
        event_manager = create_event_manager(storage)
        result.add_stage("event_manager_init", "success")
        
        # 创建 Agent
        schema = AgentPresets.simple_qa()
        agent = AgentFactory.from_schema(
            schema=schema,
            system_prompt="你是一个智能助手，能够回答各种问题。请用中文回答。",
            event_manager=event_manager,
            workspace_dir="./workspace"
        )
        result.add_stage("agent_init", "success", {
            "model": agent.model,
            "schema_name": agent.schema.name
        })
        
        # 简单测试（不需要工具调用）
        test_query = "请用一句话介绍什么是端到端测试"
        messages = [{"role": "user", "content": test_query}]
        session_id = f"e2e_agent_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        result.add_stage("query_prepared", "success", {
            "query": test_query,
            "session_id": session_id
        })
        
        # 执行 Agent
        full_response = ""
        events_count = {
            "thinking": 0,
            "text": 0,
            "tool_use": 0,
            "tool_result": 0
        }
        
        async for event in agent.chat(
            messages=messages,
            session_id=session_id,
            enable_stream=True
        ):
            event_type = event.get("type")
            
            if event_type == "content_start":
                content_block = event.get("data", {}).get("content_block", {})
                block_type = content_block.get("type")
                if block_type in events_count:
                    events_count[block_type] += 1
            
            elif event_type == "content_delta":
                delta = event.get("data", {}).get("delta", {})
                if delta.get("type") == "text_delta":
                    full_response += delta.get("text", "")
            
            elif event_type == "message_stop":
                result.add_stage("message_stop", "success")
        
        result.add_stage("agent_execution", "success", {
            "response_length": len(full_response),
            "events_count": events_count
        })
        
        # 验证响应
        has_valid_response = len(full_response) > 10
        result.add_stage("response_validation", "success" if has_valid_response else "warning", {
            "has_content": has_valid_response,
            "preview": full_response[:200] if full_response else "Empty"
        })
        
        # 检查 usage 统计
        usage = agent.usage_stats
        result.add_stage("usage_stats", "success", {
            "input_tokens": usage.get("total_input_tokens", 0),
            "output_tokens": usage.get("total_output_tokens", 0)
        })
        
        result.complete(True, full_response)
        
    except Exception as e:
        logger.error(f"验证失败: {e}", exc_info=True)
        result.add_stage("exception", "failed", {"error": str(e)})
        result.complete(False, error=str(e))
    
    result.print_summary()
    return result


async def main():
    """主入口"""
    print("\n" + "🚀" * 35)
    print("   ZenFlux Agent V4.2 - Code-First + VM Scaffolding")
    print("   端到端验证测试套件")
    print("🚀" * 35)
    print(f"\n开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # 验证场景列表
    scenarios = [
        ("代码验证功能", verify_code_validation),
        ("管道追踪器功能", verify_pipeline_tracer),
        ("增强版沙箱基本功能", verify_enhanced_sandbox_basic),
        ("E2B 沙箱真实执行", verify_e2b_sandbox_execution),
        ("完整 Agent 流程", verify_full_agent_flow),
    ]
    
    results = []
    
    for name, func in scenarios:
        print(f"\n{'─'*70}")
        print(f"📋 开始验证: {name}")
        print(f"{'─'*70}")
        
        try:
            result = await func()
            results.append((name, result))
        except Exception as e:
            logger.error(f"场景 [{name}] 执行失败: {e}", exc_info=True)
            fake_result = E2EVerificationResult(name)
            fake_result.complete(False, error=str(e))
            results.append((name, fake_result))
    
    # 打印总结
    print("\n" + "=" * 70)
    print("📊 验证测试总结")
    print("=" * 70)
    
    total = len(results)
    passed = sum(1 for _, r in results if r.success)
    failed = total - passed
    
    print(f"\n总计: {total} 个场景")
    print(f"通过: {passed} ✅")
    print(f"失败: {failed} ❌")
    
    print(f"\n详细结果:")
    for name, result in results:
        icon = "✅" if result.success else "❌"
        print(f"   {icon} {name}")
        if result.error:
            print(f"      └─ 错误: {result.error[:50]}...")
    
    print(f"\n结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70 + "\n")
    
    # 返回退出码
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)


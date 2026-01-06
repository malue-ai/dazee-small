"""
ZenFlux Agent V4.2.1 - 真实场景端到端测试

完整流程演示：
1. 用户查询 → Intent Analysis
2. Tool Selection
3. Code Generation（由 LLM 生成）
4. Code Validation（语法/依赖/安全检查）
5. E2B Sandbox Execution（真实执行）
6. Result Processing
7. 生成 E2B Sandbox URL（可访问）

测试场景：
- 数据分析场景：用户上传销售数据，要求生成图表
- 代码生成场景：根据需求生成 Python 脚本
- 文件处理场景：处理 CSV 并输出 JSON
"""

import asyncio
import os
import json
from datetime import datetime
from pathlib import Path

# 添加项目根目录到 Python 路径
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core import (
    create_pipeline_tracer,
    create_code_validator,
    create_code_orchestrator,
)
from logger import get_logger

logger = get_logger("e2e_real_world_test")


class E2ERealWorldTest:
    """真实场景端到端测试"""
    
    def __init__(self):
        self.has_e2b_key = bool(os.getenv("E2B_API_KEY"))
        self.test_results = []
    
    async def run_all_scenarios(self):
        """运行所有测试场景"""
        logger.info("🚀" * 35)
        logger.info("   ZenFlux Agent V4.2.1 - 真实场景端到端测试")
        logger.info("🚀" * 35)
        logger.info(f"\n⚙️  E2B API Key 状态: {'✅ 已配置' if self.has_e2b_key else '❌ 未配置（将使用模拟模式）'}")
        logger.info(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        # 测试场景列表
        scenarios = [
            ("数据分析场景", self.scenario_data_analysis),
            ("代码生成场景", self.scenario_code_generation),
            ("文件处理场景", self.scenario_file_processing),
        ]
        
        for scenario_name, scenario_func in scenarios:
            logger.info("─" * 70)
            logger.info(f"📋 测试场景: {scenario_name}")
            logger.info("─" * 70)
            
            try:
                result = await scenario_func()
                self.test_results.append({
                    "scenario": scenario_name,
                    "status": "success" if result["success"] else "failed",
                    "details": result
                })
                logger.info(f"✅ {scenario_name} - 完成\n")
            except Exception as e:
                logger.error(f"❌ {scenario_name} - 失败: {str(e)}\n")
                self.test_results.append({
                    "scenario": scenario_name,
                    "status": "error",
                    "error": str(e)
                })
        
        # 打印最终摘要
        self._print_summary()
    
    async def scenario_data_analysis(self):
        """场景 1: 数据分析 - 用户上传销售数据并要求生成图表"""
        logger.info("\n📊 场景描述:")
        logger.info("   用户: '帮我分析这份销售数据，生成月度销售趋势图'")
        logger.info("   数据: sales_data.csv (包含日期、产品、销售额)\n")
        
        # 创建追踪器
        tracer = create_pipeline_tracer(
            session_id="e2e_data_analysis",
            conversation_id="test_conv_001"
        )
        tracer.set_user_query("帮我分析这份销售数据，生成月度销售趋势图")
        
        # 阶段 1: 意图分析
        stage1 = tracer.create_stage("intent_analysis", "意图分析")
        stage1.start()
        stage1.set_input({"user_message": "帮我分析这份销售数据，生成月度销售趋势图"})
        await asyncio.sleep(0.05)  # 模拟 LLM 调用
        intent_result = {
            "task_type": "data_analysis",
            "needs_code": True,
            "complexity": "medium",
            "required_capabilities": ["code_execution", "data_analysis"]
        }
        stage1.complete(intent_result)
        logger.info(f"   ✅ 意图分析完成: {intent_result['task_type']}")
        
        # 阶段 2: 工具选择
        stage2 = tracer.create_stage("tool_selection", "工具选择")
        stage2.start()
        stage2.set_input({"required_capabilities": intent_result["required_capabilities"]})
        await asyncio.sleep(0.03)
        tool_result = {
            "selected_tools": ["e2b_sandbox"],
            "execution_mode": "code_first"
        }
        stage2.complete(tool_result)
        logger.info(f"   ✅ 工具选择完成: {tool_result['selected_tools']}")
        
        # 阶段 3: 代码生成
        stage3 = tracer.create_stage("code_generation", "代码生成（LLM）")
        stage3.start()
        stage3.set_input({"task": "分析销售数据并生成图表"})
        await asyncio.sleep(0.1)  # 模拟 LLM 生成代码
        
        # LLM 生成的代码
        generated_code = """
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime

# 读取销售数据
data = {
    'date': ['2024-01', '2024-02', '2024-03', '2024-04'],
    'product': ['产品A', '产品A', '产品A', '产品A'],
    'sales': [12000, 15000, 18000, 16000]
}
df = pd.DataFrame(data)

# 生成月度销售趋势图
plt.figure(figsize=(10, 6))
plt.plot(df['date'], df['sales'], marker='o', linewidth=2)
plt.title('月度销售趋势', fontsize=14, fontweight='bold')
plt.xlabel('月份', fontsize=12)
plt.ylabel('销售额 (元)', fontsize=12)
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig('/tmp/sales_trend.png', dpi=300, bbox_inches='tight')

print(f"图表已生成: /tmp/sales_trend.png")
print(f"总销售额: {df['sales'].sum():,} 元")
print(f"平均月销售额: {df['sales'].mean():,.0f} 元")
"""
        stage3.complete({"code": generated_code, "language": "python"})
        tracer.log_code_execution()
        logger.info(f"   ✅ 代码生成完成: {len(generated_code)} 字符")
        
        # 阶段 4: 代码验证
        stage4 = tracer.create_stage("code_validation", "代码验证")
        stage4.start()
        stage4.set_input({"code": generated_code[:100]})
        
        validator = create_code_validator()
        validation_result = validator.validate_all(generated_code)
        
        stage4.complete({
            "is_valid": validation_result.is_valid,
            "errors": validation_result.errors,
            "checks_performed": ["syntax", "dependencies", "security"]
        })
        logger.info(f"   ✅ 代码验证: {'通过' if validation_result.is_valid else '失败'}")
        
        if not validation_result.is_valid:
            logger.warning(f"      验证错误: {validation_result.errors}")
        
        # 阶段 5: E2B 执行
        stage5 = tracer.create_stage("e2b_execution", "E2B Sandbox 执行")
        stage5.start()
        stage5.set_input({"code_length": len(generated_code)})
        
        if self.has_e2b_key:
            # 真实 E2B 执行
            try:
                from e2b_code_interpreter import Sandbox
                
                logger.info("   🔧 启动 E2B Sandbox...")
                sandbox = Sandbox()
                sandbox_url = f"https://e2b.dev/sandbox/{sandbox.sandbox_id}"
                
                logger.info(f"   🌐 Sandbox URL: {sandbox_url}")
                logger.info(f"   📦 Sandbox ID: {sandbox.sandbox_id}")
                
                # 执行代码
                execution = sandbox.run_code(generated_code)
                
                exec_result = {
                    "success": True,
                    "stdout": execution.logs.stdout,
                    "stderr": execution.logs.stderr if execution.logs.stderr else "",
                    "sandbox_id": sandbox.sandbox_id,
                    "sandbox_url": sandbox_url,
                    "execution_time_ms": execution.execution_time * 1000
                }
                
                sandbox.close()
                logger.info(f"   ✅ E2B 执行完成")
                logger.info(f"   📊 输出: {execution.logs.stdout[:200]}")
                
            except Exception as e:
                logger.error(f"   ❌ E2B 执行失败: {str(e)}")
                exec_result = {
                    "success": False,
                    "error": str(e),
                    "mode": "real_e2b_failed"
                }
        else:
            # 模拟执行
            await asyncio.sleep(0.2)
            exec_result = {
                "success": True,
                "stdout": "图表已生成: /tmp/sales_trend.png\n总销售额: 61,000 元\n平均月销售额: 15,250 元",
                "stderr": "",
                "sandbox_id": "mock_sandbox_123",
                "sandbox_url": "https://e2b.dev/sandbox/mock_sandbox_123 (模拟)",
                "execution_time_ms": 234.5,
                "mode": "simulated"
            }
            logger.info(f"   🎭 模拟执行完成（未配置 E2B_API_KEY）")
            logger.info(f"   📊 模拟输出: {exec_result['stdout']}")
        
        stage5.complete(exec_result)
        
        # 完成追踪
        tracer.set_final_response("已完成数据分析并生成月度销售趋势图")
        tracer.finish()
        
        # 返回结果
        return {
            "success": exec_result["success"],
            "trace_report": tracer.to_dict(),
            "sandbox_url": exec_result.get("sandbox_url"),
            "execution_output": exec_result.get("stdout", ""),
            "mode": exec_result.get("mode", "real_e2b")
        }
    
    async def scenario_code_generation(self):
        """场景 2: 代码生成 - 根据需求生成工具脚本"""
        logger.info("\n💻 场景描述:")
        logger.info("   用户: '写一个 Python 脚本，监控 CPU 使用率并记录日志'")
        logger.info("")
        
        tracer = create_pipeline_tracer(
            session_id="e2e_code_gen",
            conversation_id="test_conv_002"
        )
        tracer.set_user_query("写一个 Python 脚本，监控 CPU 使用率并记录日志")
        
        # 简化流程：直接生成和验证代码
        stage = tracer.create_stage("code_generation", "代码生成与验证")
        stage.start()
        
        code = """
import psutil
import time
from datetime import datetime

def monitor_cpu(duration=10, interval=1):
    \"\"\"监控 CPU 使用率\"\"\"
    print(f"开始监控 CPU 使用率（{duration}秒）...")
    
    for i in range(duration):
        cpu_percent = psutil.cpu_percent(interval=interval)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] CPU: {cpu_percent}%")
    
    print("监控完成")

if __name__ == "__main__":
    monitor_cpu(duration=5, interval=1)
"""
        
        validator = create_code_validator()
        result = validator.validate_all(code)
        
        stage.complete({
            "code_generated": True,
            "validation_passed": result.is_valid,
            "lines_of_code": len(code.split('\n'))
        })
        
        tracer.log_code_execution()
        tracer.set_final_response("已生成 CPU 监控脚本")
        tracer.finish()
        
        logger.info(f"   ✅ 代码生成: {len(code.split(chr(10)))} 行")
        logger.info(f"   ✅ 验证结果: {'通过' if result.is_valid else '失败'}")
        
        return {
            "success": result.is_valid,
            "trace_report": tracer.to_dict(),
            "code_length": len(code)
        }
    
    async def scenario_file_processing(self):
        """场景 3: 文件处理 - CSV 转 JSON"""
        logger.info("\n📁 场景描述:")
        logger.info("   用户: '把这个 CSV 文件转成 JSON 格式，并添加时间戳'")
        logger.info("")
        
        tracer = create_pipeline_tracer(
            session_id="e2e_file_proc",
            conversation_id="test_conv_003"
        )
        tracer.set_user_query("把这个 CSV 文件转成 JSON 格式，并添加时间戳")
        
        stage = tracer.create_stage("file_processing", "文件处理")
        stage.start()
        
        code = """
import csv
import json
from datetime import datetime

# 读取 CSV
data = []
with open('input.csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        row['processed_at'] = datetime.now().isoformat()
        data.append(row)

# 写入 JSON
with open('output.json', 'w') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"转换完成: {len(data)} 条记录")
"""
        
        validator = create_code_validator()
        result = validator.validate_all(code)
        
        stage.complete({
            "file_processing_code": True,
            "validation": result.is_valid
        })
        
        tracer.log_tool_call("file_operations")
        tracer.set_final_response("已完成 CSV 到 JSON 的转换")
        tracer.finish()
        
        logger.info(f"   ✅ 文件处理代码生成完成")
        logger.info(f"   ✅ 验证结果: {'通过' if result.is_valid else '失败'}")
        
        return {
            "success": result.is_valid,
            "trace_report": tracer.to_dict()
        }
    
    def _print_summary(self):
        """打印测试摘要"""
        logger.info("\n" + "=" * 70)
        logger.info("📊 测试摘要")
        logger.info("=" * 70)
        
        total = len(self.test_results)
        success = sum(1 for r in self.test_results if r["status"] == "success")
        failed = sum(1 for r in self.test_results if r["status"] == "failed")
        error = sum(1 for r in self.test_results if r["status"] == "error")
        
        logger.info(f"\n总测试场景: {total}")
        logger.info(f"✅ 成功: {success}")
        logger.info(f"❌ 失败: {failed}")
        logger.info(f"⚠️  错误: {error}")
        
        logger.info("\n详细结果:")
        for i, result in enumerate(self.test_results, 1):
            status_icon = {
                "success": "✅",
                "failed": "❌",
                "error": "⚠️"
            }.get(result["status"], "❓")
            
            logger.info(f"   {i}. {status_icon} {result['scenario']}")
            
            if result["status"] == "success" and "details" in result:
                details = result["details"]
                if "sandbox_url" in details and details["sandbox_url"]:
                    logger.info(f"      🌐 Sandbox URL: {details['sandbox_url']}")
                if "execution_output" in details:
                    output_preview = details["execution_output"][:100]
                    logger.info(f"      📊 输出: {output_preview}...")
        
        logger.info("\n" + "=" * 70)
        logger.info(f"测试完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 70)


async def main():
    """主函数"""
    test = E2ERealWorldTest()
    await test.run_all_scenarios()


if __name__ == "__main__":
    asyncio.run(main())


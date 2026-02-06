"""
独立运行简单问答场景测试
绕过 pytest 路径冲突
"""

import sys
import os
import asyncio
from pathlib import Path

# 确保项目路径优先
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 加载环境变量
from dotenv import load_dotenv
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path, override=True)

# 直接导入测试文件（不通过 tests 包）
test_file_path = project_root / "tests" / "test_e2e_agent_pipeline.py"
sys.path.insert(0, str(project_root / "tests"))

import importlib.util
spec = importlib.util.spec_from_file_location("test_e2e_agent_pipeline", test_file_path)
test_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(test_module)

TestE2EAgentPipeline = test_module.TestE2EAgentPipeline
PipelineQualityTracer = test_module.PipelineQualityTracer
AnswerQualityEvaluator = test_module.AnswerQualityEvaluator
TEST_SCENARIOS = test_module.TEST_SCENARIOS


async def run_simple_qa_test():
    """运行简单问答场景测试"""
    print("=" * 80)
    print("【场景测试】简单知识问答")
    print("=" * 80)
    
    # 检查 API KEY
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ 缺少 ANTHROPIC_API_KEY，请配置 .env 文件")
        return False
    
    print(f"✅ API Key: {api_key[:20]}...")
    
    # 直接创建需要的对象（不使用 pytest fixture）
    tracer = PipelineQualityTracer()
    evaluator = AnswerQualityEvaluator()
    
    # 获取场景
    scenario = TEST_SCENARIOS[5]  # 简单知识问答
    print(f"\n场景: {scenario.name}")
    print(f"Query: {scenario.query}")
    
    try:
        # 创建测试实例并直接设置属性
        test = TestE2EAgentPipeline()
        test.tracer = tracer
        test.evaluator = evaluator
        test.results = []
        
        # 运行测试
        await test._run_scenario_test(scenario, use_real_api=True)
        print("\n" + "=" * 80)
        print("✅ 测试通过")
        print("=" * 80)
        return True
    except Exception as e:
        print("\n" + "=" * 80)
        print(f"❌ 测试失败: {e}")
        print("=" * 80)
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(run_simple_qa_test())
    sys.exit(0 if success else 1)

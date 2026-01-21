"""
E2B 集成测试

测试场景：
1. 基础代码执行
2. 自动包安装
3. 文件系统操作
4. 多轮对话（沙箱持久化）
5. 流式输出

运行方式：
  python tests/test_e2b_integration.py
"""

import asyncio
import os
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

RUN_E2B_TESTS = os.getenv("RUN_E2B_TESTS", "false").lower() == "true"
if not RUN_E2B_TESTS:
    pytest.skip("未启用 RUN_E2B_TESTS，跳过 E2B 集成测试", allow_module_level=True)

try:
    from infra.sandbox.e2b import E2B_AVAILABLE
except Exception as e:
    pytest.skip(f"E2B 依赖不可用: {e}", allow_module_level=True)

if not os.getenv("E2B_API_KEY"):
    pytest.skip("E2B_API_KEY 未设置，跳过 E2B 集成测试", allow_module_level=True)

if not E2B_AVAILABLE:
    pytest.skip("E2B SDK 未安装，跳过 E2B 集成测试", allow_module_level=True)

from logger import get_logger
from core.memory import WorkingMemory, E2BSandboxSession
try:
    from tools.e2b_sandbox import E2BPythonSandbox
except Exception as e:
    pytest.skip(f"E2B 工具不可用: {e}", allow_module_level=True)
from tools.e2b_template_manager import E2BTemplateManager

logger = get_logger("e2b_test")


class TestE2BIntegration:
    """E2B 集成测试"""
    
    def __init__(self):
        self.memory = WorkingMemory()
        self.workspace_dir = Path.cwd() / "workspace"
        
        # 检查 E2B API Key
        if not os.getenv("E2B_API_KEY"):
            logger.error("❌ E2B_API_KEY 环境变量未设置")
            logger.info("请在 .env 文件中添加: E2B_API_KEY=your_key")
            sys.exit(1)
        
        if not E2B_AVAILABLE:
            logger.error("❌ E2B SDK 未安装")
            logger.info("请运行: pip install e2b-code-interpreter")
            sys.exit(1)
        
        self.e2b_tool = E2BPythonSandbox(
            memory=self.memory,
            workspace_dir=str(self.workspace_dir)
        )
        
        self.template_manager = E2BTemplateManager()
        
        logger.info("✅ 测试环境已初始化")
    
    async def test_1_basic_execution(self):
        """测试1: 基础代码执行"""
        logger.info("\n" + "="*60)
        logger.info("🧪 测试 1: 基础代码执行")
        logger.info("="*60)
        
        code = """
print("Hello from E2B!")
print(f"Python version: {__import__('sys').version}")
print(f"2 + 2 = {2 + 2}")
"""
        
        result = await self.e2b_tool.execute(code=code)
        
        assert result["success"], f"执行失败: {result.get('error')}"
        assert "Hello from E2B!" in result["stdout"]
        assert "2 + 2 = 4" in result["stdout"]
        
        logger.info("✅ 测试通过：基础代码执行成功")
        logger.info(f"输出:\n{result['stdout']}")
    
    async def test_2_auto_install_packages(self):
        """测试2: 自动包安装"""
        logger.info("\n" + "="*60)
        logger.info("🧪 测试 2: 自动包安装")
        logger.info("="*60)
        
        code = """
import requests

response = requests.get('https://httpbin.org/json')
data = response.json()
print(f"成功获取数据: {list(data.keys())}")
"""
        
        result = await self.e2b_tool.execute(code=code, auto_install=True)
        
        assert result["success"], f"执行失败: {result.get('error')}"
        assert "成功获取数据" in result["stdout"]
        
        # 检查 Memory 中是否记录了安装的包
        session = self.memory.get_e2b_session()
        assert session is not None
        assert "requests" in session.installed_packages
        
        logger.info("✅ 测试通过：自动包安装成功")
        logger.info(f"已安装包: {session.installed_packages}")
    
    async def test_3_file_operations(self):
        """测试3: 文件系统操作"""
        logger.info("\n" + "="*60)
        logger.info("🧪 测试 3: 文件系统操作")
        logger.info("="*60)
        
        # 创建测试输入文件
        inputs_dir = self.workspace_dir / "inputs"
        inputs_dir.mkdir(parents=True, exist_ok=True)
        
        test_data = "name,age,city\nAlice,30,NYC\nBob,25,LA"
        test_file = inputs_dir / "test_data.csv"
        with open(test_file, 'w') as f:
            f.write(test_data)
        
        logger.info(f"📝 创建测试文件: {test_file}")
        
        # 测试代码：读取并处理文件
        code = """
import pandas as pd

# 读取输入文件
df = pd.read_csv('/home/user/input_data/test_data.csv')
print(f"读取到 {len(df)} 行数据")
print(df)

# 处理并保存输出
df['age'] = df['age'] + 1
df.to_csv('/home/user/output_data/processed_data.csv', index=False)
print("\\n处理完成，结果已保存到 output_data/")
"""
        
        result = await self.e2b_tool.execute(
            code=code,
            return_files=["/home/user/output_data/processed_data.csv"]
        )
        
        assert result["success"], f"执行失败: {result.get('error')}"
        assert "读取到 2 行数据" in result["stdout"]
        assert len(result["files"]) > 0
        
        # 验证输出文件
        output_file = self.workspace_dir / "outputs" / "processed_data.csv"
        assert output_file.exists(), "输出文件未生成"
        
        with open(output_file) as f:
            content = f.read()
            assert "Alice" in content
            assert "31" in content  # age +1
        
        logger.info("✅ 测试通过：文件系统操作成功")
        logger.info(f"输出文件: {output_file}")
        
        # 清理测试文件
        test_file.unlink()
        output_file.unlink()
    
    async def test_4_sandbox_persistence(self):
        """测试4: 沙箱持久化（多轮对话）"""
        logger.info("\n" + "="*60)
        logger.info("🧪 测试 4: 沙箱持久化")
        logger.info("="*60)
        
        # 第一次调用：创建变量
        code1 = """
data = {"message": "Hello from E2B!", "count": 42}
print(f"创建变量: data = {data}")
"""
        
        result1 = await self.e2b_tool.execute(code=code1)
        assert result1["success"]
        
        sandbox_id_1 = self.memory.get_e2b_session().sandbox_id
        logger.info(f"第一次调用 - Sandbox ID: {sandbox_id_1}")
        
        # 第二次调用：访问之前创建的变量（同一沙箱）
        code2 = """
# 变量应该还存在
print(f"读取变量: data = {data}")
print(f"count * 2 = {data['count'] * 2}")
"""
        
        result2 = await self.e2b_tool.execute(code=code2)
        assert result2["success"], "沙箱持久化失败：变量不存在"
        assert "count * 2 = 84" in result2["stdout"]
        
        sandbox_id_2 = self.memory.get_e2b_session().sandbox_id
        assert sandbox_id_1 == sandbox_id_2, "沙箱未复用"
        
        logger.info("✅ 测试通过：沙箱持久化成功（同一沙箱，变量保持）")
        logger.info(f"第二次调用 - Sandbox ID: {sandbox_id_2} (复用 ✅)")
    
    async def test_5_template_manager(self):
        """测试5: 模板管理器"""
        logger.info("\n" + "="*60)
        logger.info("🧪 测试 5: 模板管理器")
        logger.info("="*60)
        
        # 测试模板推荐
        recommended = self.template_manager.get_recommended_template("data_analysis")
        logger.info(f"推荐模板（数据分析）: {recommended}")
        assert recommended in ["data-analysis", "base"]
        
        recommended = self.template_manager.get_recommended_template("web_scraping")
        logger.info(f"推荐模板（网页抓取）: {recommended}")
        assert recommended in ["web-scraping", "base"]
        
        # 列出所有模板
        templates = self.template_manager.list_templates()
        logger.info(f"可用模板: {templates}")
        assert len(templates) > 0
        
        logger.info("✅ 测试通过：模板管理器工作正常")
    
    async def test_6_memory_integration(self):
        """测试6: Memory 集成"""
        logger.info("\n" + "="*60)
        logger.info("🧪 测试 6: Memory 集成")
        logger.info("="*60)
        
        # 执行代码
        code = """
import math
result = math.sqrt(16)
print(f"sqrt(16) = {result}")
"""
        
        initial_history_len = len(self.memory.e2b_execution_history)
        
        result = await self.e2b_tool.execute(code=code)
        assert result["success"]
        
        # 验证 Memory 记录
        session = self.memory.get_e2b_session()
        assert session is not None
        assert session.execution_count > 0
        
        # 验证执行历史
        assert len(self.memory.e2b_execution_history) > initial_history_len
        
        # 获取 LLM 上下文
        context = self.memory.get_e2b_context_for_llm()
        assert "E2B沙箱状态" in context
        assert session.sandbox_id in context
        
        logger.info("✅ 测试通过：Memory 集成成功")
        logger.info(f"执行历史记录数: {len(self.memory.e2b_execution_history)}")
        logger.info(f"LLM 上下文:\n{context}")
    
    async def cleanup(self):
        """清理测试环境"""
        logger.info("\n" + "="*60)
        logger.info("🧹 清理测试环境")
        logger.info("="*60)
        
        # 终止沙箱
        await self.e2b_tool.terminate_sandbox()
        
        logger.info("✅ 清理完成")


async def main():
    """运行所有测试"""
    logger.info("="*60)
    logger.info("🚀 E2B 集成测试开始")
    logger.info("="*60)
    
    tester = TestE2BIntegration()
    
    try:
        # 运行所有测试
        await tester.test_1_basic_execution()
        await tester.test_2_auto_install_packages()
        await tester.test_3_file_operations()
        await tester.test_4_sandbox_persistence()
        await tester.test_5_template_manager()
        await tester.test_6_memory_integration()
        
        logger.info("\n" + "="*60)
        logger.info("🎉 所有测试通过！")
        logger.info("="*60)
        
    except AssertionError as e:
        logger.error(f"\n❌ 测试失败: {e}")
        sys.exit(1)
    
    except Exception as e:
        logger.error(f"\n❌ 测试异常: {e}", exc_info=True)
        sys.exit(1)
    
    finally:
        await tester.cleanup()


if __name__ == "__main__":
    asyncio.run(main())


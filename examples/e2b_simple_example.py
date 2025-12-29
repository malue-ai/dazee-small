"""
E2B 简单使用示例

演示如何在代码中直接使用 E2B 沙箱工具

运行方式：
  python examples/e2b_simple_example.py
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.memory import WorkingMemory
from tools.e2b_sandbox import E2BPythonSandbox
from logger import get_logger

logger = get_logger("e2b_example")


async def example_1_hello_world():
    """示例 1: Hello World"""
    logger.info("\n" + "="*60)
    logger.info("📝 示例 1: Hello World")
    logger.info("="*60)
    
    memory = WorkingMemory()
    tool = E2BPythonSandbox(memory=memory)
    
    code = """
print("Hello from E2B!")
print("2 + 2 =", 2 + 2)
"""
    
    result = await tool.execute(code=code)
    
    logger.info(f"执行结果:\n{result['stdout']}")
    
    await tool.terminate_sandbox()


async def example_2_data_analysis():
    """示例 2: 数据分析"""
    logger.info("\n" + "="*60)
    logger.info("📝 示例 2: 数据分析（自动安装 pandas）")
    logger.info("="*60)
    
    memory = WorkingMemory()
    tool = E2BPythonSandbox(memory=memory)
    
    code = """
import pandas as pd
import numpy as np

# 创建示例数据
data = {
    'name': ['Alice', 'Bob', 'Charlie'],
    'age': [25, 30, 35],
    'salary': [50000, 60000, 70000]
}

df = pd.DataFrame(data)

print("数据概览:")
print(df)

print("\\n统计信息:")
print(df.describe())
"""
    
    result = await tool.execute(code=code, auto_install=True)
    
    if result['success']:
        logger.info(f"执行结果:\n{result['stdout']}")
    else:
        logger.error(f"执行失败: {result['error']}")
    
    await tool.terminate_sandbox()


async def example_3_web_request():
    """示例 3: 网络请求"""
    logger.info("\n" + "="*60)
    logger.info("📝 示例 3: 网络请求")
    logger.info("="*60)
    
    memory = WorkingMemory()
    tool = E2BPythonSandbox(memory=memory)
    
    code = """
import requests

# 获取 JSON 数据
response = requests.get('https://httpbin.org/json')
data = response.json()

print(f"获取数据成功！")
print(f"数据键: {list(data.keys())}")
"""
    
    result = await tool.execute(code=code, auto_install=True)
    
    if result['success']:
        logger.info(f"执行结果:\n{result['stdout']}")
    else:
        logger.error(f"执行失败: {result['error']}")
    
    await tool.terminate_sandbox()


async def example_4_multi_turn():
    """示例 4: 多轮对话（沙箱持久化）"""
    logger.info("\n" + "="*60)
    logger.info("📝 示例 4: 多轮对话（沙箱持久化）")
    logger.info("="*60)
    
    memory = WorkingMemory()
    tool = E2BPythonSandbox(memory=memory)
    
    # 第一轮：创建变量
    code1 = """
numbers = [1, 2, 3, 4, 5]
total = sum(numbers)
print(f"数字列表: {numbers}")
print(f"总和: {total}")
"""
    
    logger.info("第一轮执行：")
    result1 = await tool.execute(code=code1)
    logger.info(result1['stdout'])
    
    # 第二轮：使用之前的变量
    code2 = """
# 变量 numbers 和 total 仍然存在
average = total / len(numbers)
print(f"平均值: {average}")
print(f"最大值: {max(numbers)}")
"""
    
    logger.info("\n第二轮执行（使用之前的变量）：")
    result2 = await tool.execute(code=code2)
    
    if result2['success']:
        logger.info(result2['stdout'])
        logger.info("✅ 沙箱持久化成功：变量在多轮对话中保持")
    else:
        logger.error(f"执行失败: {result2['error']}")
    
    await tool.terminate_sandbox()


async def main():
    """运行所有示例"""
    logger.info("="*60)
    logger.info("🚀 E2B 使用示例")
    logger.info("="*60)
    
    try:
        await example_1_hello_world()
        await example_2_data_analysis()
        await example_3_web_request()
        await example_4_multi_turn()
        
        logger.info("\n" + "="*60)
        logger.info("✅ 所有示例运行完成")
        logger.info("="*60)
    
    except Exception as e:
        logger.error(f"❌ 示例运行失败: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())


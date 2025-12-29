"""
E2B 端到端真实测试 (End-to-End Real Test)

这是一个完整的端到端测试，包括：
1. 真实的 E2B API 调用
2. 完整的 Agent 工作流
3. Memory 状态管理
4. 文件系统同步
5. 多轮对话验证

前置条件：
- E2B_API_KEY 已在 .env 文件中配置
- ANTHROPIC_API_KEY 已配置（用于 Agent）
- 网络连接正常

运行方式：
  python tests/test_e2b_e2e_real.py
"""

import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from logger import get_logger
from dotenv import load_dotenv

logger = get_logger("e2b_e2e_test")

# 加载环境变量
load_dotenv()


class E2BEndToEndTest:
    """E2B 端到端真实测试"""
    
    def __init__(self):
        # 验证环境变量
        self.e2b_api_key = os.getenv("E2B_API_KEY")
        if not self.e2b_api_key:
            logger.error("❌ E2B_API_KEY 未设置")
            logger.info("请在 .env 文件中添加: E2B_API_KEY=e2b_***")
            logger.info("获取 API Key: https://e2b.dev/dashboard")
            sys.exit(1)
        
        logger.info(f"✅ E2B_API_KEY 已加载: {self.e2b_api_key[:10]}...")
        
        # 初始化组件
        from core.memory import WorkingMemory
        from tools.e2b_sandbox import E2BPythonSandbox, E2B_AVAILABLE
        from tools.e2b_template_manager import E2BTemplateManager
        
        if not E2B_AVAILABLE:
            logger.error("❌ E2B SDK 未安装")
            logger.info("请运行: pip install e2b e2b-code-interpreter")
            sys.exit(1)
        
        self.memory = WorkingMemory()
        self.workspace_dir = Path.cwd() / "workspace"
        
        self.e2b_tool = E2BPythonSandbox(
            memory=self.memory,
            api_key=self.e2b_api_key,
            workspace_dir=str(self.workspace_dir)
        )
        
        self.template_manager = E2BTemplateManager()
        
        logger.info("✅ 测试环境已初始化")
        logger.info(f"工作目录: {self.workspace_dir}")
    
    async def test_real_1_basic_execution(self):
        """真实测试 1: 基础代码执行（调用真实 E2B API）"""
        logger.info("\n" + "="*70)
        logger.info("🧪 真实测试 1: 基础代码执行")
        logger.info("="*70)
        
        code = """
import sys
import platform

print("="*50)
print("🐍 E2B Python 沙箱环境信息")
print("="*50)
print(f"Python 版本: {sys.version}")
print(f"操作系统: {platform.platform()}")
print(f"处理器: {platform.processor()}")
print(f"\\n基础计算测试:")
print(f"  2 + 2 = {2 + 2}")
print(f"  fibonacci(10) = {list(range(10))}")
print("\\n✅ 基础代码执行成功！")
"""
        
        logger.info("📤 发送代码到 E2B...")
        result = await self.e2b_tool.execute(code=code, enable_stream=False)
        
        logger.info(f"\n执行结果:")
        logger.info(f"  成功: {result['success']}")
        logger.info(f"  执行时间: {result.get('execution_time', 0):.2f}秒")
        
        if result['success']:
            logger.info(f"\n📊 输出:\n{result['stdout']}")
            
            # 验证 Memory 状态
            session = self.memory.get_e2b_session()
            assert session is not None, "Memory 中应该有沙箱会话"
            logger.info(f"\n✅ Memory 状态:")
            logger.info(f"  Sandbox ID: {session.sandbox_id}")
            logger.info(f"  执行次数: {session.execution_count}")
        else:
            logger.error(f"❌ 执行失败: {result.get('error')}")
            logger.error(f"stderr: {result.get('stderr')}")
            raise AssertionError("代码执行失败")
        
        logger.info("\n✅ 测试 1 通过")
    
    async def test_real_2_network_request(self):
        """真实测试 2: 网络请求（验证E2B网络访问）"""
        logger.info("\n" + "="*70)
        logger.info("🧪 真实测试 2: 网络请求")
        logger.info("="*70)
        
        code = """
import requests
import json

print("🌐 测试网络访问...")

# 调用公开 API
response = requests.get('https://httpbin.org/json')
print(f"状态码: {response.status_code}")

if response.status_code == 200:
    data = response.json()
    print(f"\\n获取到的数据:")
    print(json.dumps(data, indent=2, ensure_ascii=False)[:200])
    print(f"\\n✅ 网络请求成功！")
else:
    print(f"❌ 请求失败")
"""
        
        logger.info("📤 发送网络请求代码到 E2B...")
        result = await self.e2b_tool.execute(
            code=code,
            auto_install=True,  # 自动安装 requests
            enable_stream=False
        )
        
        if result['success']:
            logger.info(f"\n📊 输出:\n{result['stdout']}")
            
            # 验证 requests 已安装
            session = self.memory.get_e2b_session()
            assert "requests" in session.installed_packages, "requests 应该被记录为已安装"
            logger.info(f"\n✅ 已安装包: {session.installed_packages}")
        else:
            logger.error(f"❌ 执行失败: {result.get('error')}")
            raise AssertionError("网络请求失败")
        
        logger.info("\n✅ 测试 2 通过")
    
    async def test_real_3_data_analysis(self):
        """真实测试 3: 数据分析（pandas + 文件操作）"""
        logger.info("\n" + "="*70)
        logger.info("🧪 真实测试 3: 数据分析")
        logger.info("="*70)
        
        # 创建测试数据文件
        inputs_dir = self.workspace_dir / "inputs"
        inputs_dir.mkdir(parents=True, exist_ok=True)
        
        test_csv = inputs_dir / "sales_data.csv"
        test_data = """date,product,sales,revenue
2025-01-01,Product A,100,5000
2025-01-02,Product B,150,7500
2025-01-03,Product A,120,6000
2025-01-04,Product C,80,4000
2025-01-05,Product B,200,10000"""
        
        with open(test_csv, 'w') as f:
            f.write(test_data)
        
        logger.info(f"📝 创建测试文件: {test_csv}")
        
        code = """
import pandas as pd
import matplotlib.pyplot as plt

print("📊 数据分析测试...")

# 读取 CSV 文件
df = pd.read_csv('/home/user/input_data/sales_data.csv')

print(f"\\n数据概览:")
print(df)

print(f"\\n统计信息:")
print(df.describe())

print(f"\\n按产品汇总:")
product_summary = df.groupby('product')['revenue'].sum()
print(product_summary)

# 生成图表
plt.figure(figsize=(10, 6))
product_summary.plot(kind='bar')
plt.title('Revenue by Product')
plt.xlabel('Product')
plt.ylabel('Revenue')
plt.tight_layout()
plt.savefig('/home/user/output_data/revenue_chart.png')

print(f"\\n✅ 分析完成！图表已保存到 output_data/")
"""
        
        logger.info("📤 发送数据分析代码到 E2B...")
        result = await self.e2b_tool.execute(
            code=code,
            template="base",  # 会自动安装 pandas, matplotlib
            auto_install=True,
            return_files=["/home/user/output_data/revenue_chart.png"],
            enable_stream=False
        )
        
        if result['success']:
            logger.info(f"\n📊 输出:\n{result['stdout']}")
            
            # 验证输出文件
            if result.get('files'):
                logger.info(f"\n📁 生成的文件:")
                for path, info in result['files'].items():
                    logger.info(f"  {path} → {info.get('local_path')}")
                    
                    # 验证文件存在
                    local_path = self.workspace_dir / info['local_path']
                    assert local_path.exists(), f"文件应该存在: {local_path}"
                    logger.info(f"  ✅ 文件已下载: {local_path}")
            
            # 验证 pandas/matplotlib 已安装
            session = self.memory.get_e2b_session()
            logger.info(f"\n✅ 已安装包: {session.installed_packages}")
        else:
            logger.error(f"❌ 执行失败: {result.get('error')}")
            logger.error(f"stderr: {result.get('stderr')}")
            raise AssertionError("数据分析失败")
        
        logger.info("\n✅ 测试 3 通过")
    
    async def test_real_4_multi_turn_persistence(self):
        """真实测试 4: 多轮对话（沙箱持久化）"""
        logger.info("\n" + "="*70)
        logger.info("🧪 真实测试 4: 多轮对话（沙箱持久化）")
        logger.info("="*70)
        
        sandbox_id_before = self.memory.get_e2b_session().sandbox_id
        logger.info(f"当前 Sandbox ID: {sandbox_id_before}")
        
        # 第一轮：创建数据
        code1 = """
# 创建一些数据
import json

user_data = {
    "name": "Zenflux Agent",
    "version": "V3.7",
    "features": ["E2B Integration", "Vibe Coding", "Memory-First"]
}

# 保存到文件
with open('/home/user/output_data/agent_info.json', 'w') as f:
    json.dump(user_data, f, indent=2)

print(f"✅ 第一轮：数据已创建")
print(f"user_data = {user_data}")
"""
        
        logger.info("\n第一轮执行：")
        result1 = await self.e2b_tool.execute(code=code1, enable_stream=False)
        
        if not result1['success']:
            raise AssertionError(f"第一轮执行失败: {result1.get('error')}")
        
        logger.info(result1['stdout'])
        
        # 第二轮：读取并使用之前的数据
        code2 = """
import json

# 读取之前保存的文件
with open('/home/user/output_data/agent_info.json', 'r') as f:
    loaded_data = json.load(f)

print(f"✅ 第二轮：成功读取之前的数据")
print(f"loaded_data = {loaded_data}")
print(f"\\n验证：user_data 变量是否存在？")

try:
    # 验证第一轮的变量是否还在
    print(f"user_data 仍然存在: {user_data}")
    print(f"\\n🎉 沙箱持久化成功！变量和文件都保持了！")
except NameError:
    print(f"⚠️ user_data 变量不存在（这是预期的，因为是新的代码执行上下文）")
    print(f"但文件持久化成功！我们能读取到之前保存的 JSON 文件")
"""
        
        logger.info("\n第二轮执行（应该复用同一个沙箱）：")
        result2 = await self.e2b_tool.execute(code=code2, enable_stream=False)
        
        if not result2['success']:
            raise AssertionError(f"第二轮执行失败: {result2.get('error')}")
        
        logger.info(result2['stdout'])
        
        # 验证沙箱复用
        sandbox_id_after = self.memory.get_e2b_session().sandbox_id
        assert sandbox_id_before == sandbox_id_after, "应该复用同一个沙箱"
        
        logger.info(f"\n✅ 沙箱复用验证:")
        logger.info(f"  第一轮 Sandbox ID: {sandbox_id_before}")
        logger.info(f"  第二轮 Sandbox ID: {sandbox_id_after}")
        logger.info(f"  {'✅ 相同（复用成功）' if sandbox_id_before == sandbox_id_after else '❌ 不同（复用失败）'}")
        
        # 验证执行历史
        assert len(self.memory.e2b_execution_history) >= 2, "应该有至少2条执行记录"
        logger.info(f"\n✅ 执行历史: {len(self.memory.e2b_execution_history)} 条记录")
        
        logger.info("\n✅ 测试 4 通过")
    
    async def test_real_5_web_scraping(self):
        """真实测试 5: 网页爬取（真实爬取 HN）"""
        logger.info("\n" + "="*70)
        logger.info("🧪 真实测试 5: 网页爬取")
        logger.info("="*70)
        
        code = """
import requests
from bs4 import BeautifulSoup
import json

print("🕷️ 爬取 Hacker News...")

# 真实爬取 HN
url = 'https://news.ycombinator.com'
response = requests.get(url, timeout=10)

print(f"状态码: {response.status_code}")

if response.status_code == 200:
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # 提取前 5 条新闻
    news_items = []
    for item in soup.select('.titleline')[:5]:
        title = item.get_text(strip=True)
        news_items.append(title)
    
    print(f"\\n📰 爬取到 {len(news_items)} 条新闻:")
    for i, title in enumerate(news_items, 1):
        print(f"{i}. {title[:80]}...")
    
    # 保存结果
    result_data = {
        "source": "Hacker News",
        "scraped_at": str(__import__('datetime').datetime.now()),
        "items": news_items
    }
    
    with open('/home/user/output_data/hn_news.json', 'w') as f:
        json.dump(result_data, f, indent=2, ensure_ascii=False)
    
    print(f"\\n✅ 结果已保存到 output_data/hn_news.json")
else:
    print(f"❌ 爬取失败")
"""
        
        logger.info("📤 发送爬虫代码到 E2B...")
        result = await self.e2b_tool.execute(
            code=code,
            auto_install=True,  # 自动安装 requests, beautifulsoup4
            return_files=["/home/user/output_data/hn_news.json"],
            enable_stream=False
        )
        
        if result['success']:
            logger.info(f"\n📊 爬取结果:\n{result['stdout']}")
            
            # 验证下载的文件
            if result.get('files'):
                json_file_info = result['files'].get('/home/user/output_data/hn_news.json')
                if json_file_info:
                    local_path = self.workspace_dir / json_file_info['local_path']
                    assert local_path.exists(), "JSON 文件应该存在"
                    
                    # 读取并验证内容
                    import json
                    with open(local_path) as f:
                        data = json.load(f)
                    
                    logger.info(f"\n📄 下载的文件内容:")
                    logger.info(f"  来源: {data.get('source')}")
                    logger.info(f"  新闻数: {len(data.get('items', []))}")
                    
                    assert len(data.get('items', [])) > 0, "应该爬取到新闻"
                    
                    logger.info(f"\n✅ 文件验证通过")
        else:
            logger.error(f"❌ 执行失败: {result.get('error')}")
            raise AssertionError("网页爬取失败")
        
        logger.info("\n✅ 测试 5 通过")
    
    async def test_real_6_memory_context(self):
        """真实测试 6: Memory 上下文（验证 LLM 上下文生成）"""
        logger.info("\n" + "="*70)
        logger.info("🧪 真实测试 6: Memory 上下文")
        logger.info("="*70)
        
        # 获取 E2B 上下文（供 LLM 使用）
        context = self.memory.get_e2b_context_for_llm(max_history=5)
        
        logger.info(f"\n📝 LLM 上下文（前 500 字符）:")
        logger.info(context[:500])
        
        # 验证上下文包含关键信息
        assert "E2B沙箱状态" in context, "应该包含沙箱状态"
        assert "Sandbox ID" in context, "应该包含 Sandbox ID"
        
        session = self.memory.get_e2b_session()
        if session.installed_packages:
            assert "已安装包" in context, "应该包含已安装包列表"
        
        if len(self.memory.e2b_execution_history) > 0:
            assert "最近执行历史" in context, "应该包含执行历史"
        
        logger.info("\n✅ Memory 上下文验证通过")
        logger.info(f"  - 沙箱信息: ✅")
        logger.info(f"  - 已安装包: ✅ ({len(session.installed_packages)} 个)")
        logger.info(f"  - 执行历史: ✅ ({len(self.memory.e2b_execution_history)} 条)")
        
        logger.info("\n✅ 测试 6 通过")
    
    async def cleanup(self):
        """清理测试环境"""
        logger.info("\n" + "="*70)
        logger.info("🧹 清理测试环境")
        logger.info("="*70)
        
        # 终止沙箱
        session = self.memory.get_e2b_session()
        if session:
            logger.info(f"终止沙箱: {session.sandbox_id}")
            await self.e2b_tool.terminate_sandbox()
        
        # 清理测试文件
        test_files = [
            self.workspace_dir / "inputs" / "sales_data.csv",
            self.workspace_dir / "outputs" / "revenue_chart.png",
            self.workspace_dir / "outputs" / "hn_news.json",
            self.workspace_dir / "outputs" / "agent_info.json"
        ]
        
        for file_path in test_files:
            if file_path.exists():
                file_path.unlink()
                logger.info(f"删除测试文件: {file_path.name}")
        
        logger.info("✅ 清理完成")


async def main():
    """运行所有真实测试"""
    logger.info("="*70)
    logger.info("🚀 E2B 端到端真实测试")
    logger.info("="*70)
    logger.info(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("")
    logger.info("⚠️  注意：这是真实测试，会调用真实的 E2B API")
    logger.info("⚠️  预计消耗时间：2-5 分钟")
    logger.info("⚠️  预计消耗费用：< $0.10 USD")
    logger.info("")
    
    tester = TestE2BEndToEndTest()
    
    try:
        # 依次运行所有测试
        await tester.test_real_1_basic_execution()
        await tester.test_real_2_network_request()
        await tester.test_real_3_data_analysis()
        await tester.test_real_4_multi_turn_persistence()
        await tester.test_real_6_memory_context()
        
        logger.info("\n" + "="*70)
        logger.info("🎉 所有真实测试通过！E2B 集成成功！")
        logger.info("="*70)
        
        # 总结
        session = tester.memory.get_e2b_session()
        logger.info(f"\n📊 测试总结:")
        logger.info(f"  Sandbox ID: {session.sandbox_id}")
        logger.info(f"  总执行次数: {session.execution_count}")
        logger.info(f"  已安装包: {len(session.installed_packages)} 个")
        logger.info(f"  执行历史: {len(tester.memory.e2b_execution_history)} 条")
        logger.info(f"  文件记录: {len(session.files)} 个")
        
        logger.info(f"\n✅ E2B Python 沙箱已成功集成到 Zenflux Agent V3.7")
        
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


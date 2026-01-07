#!/usr/bin/env python3
"""
端到端 PPT 生成测试

验证完整的 ZenFlux Agent 管道：
1. 用户 Query 输入
2. 意图识别
3. 工具选择（exa_search / slidespeak）
4. 搜索结果精简 (compaction)
5. PPT 生成
6. 文件输出

注意：这是真实调用，不是 mock！
"""

import os
import sys
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载环境变量
load_dotenv(project_root / ".env")

# 配置详细日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("e2e_ppt_test")

# 设置各模块日志级别
logging.getLogger("zenflux").setLevel(logging.DEBUG)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


async def run_e2e_ppt_generation():
    """
    端到端 PPT 生成测试
    """
    print("\n" + "=" * 70)
    print("🚀 ZenFlux Agent 端到端 PPT 生成测试")
    print("=" * 70)
    
    # ===== 1. 检查环境变量 =====
    print("\n📋 Step 1: 检查环境变量")
    required_keys = ["ANTHROPIC_API_KEY", "E2B_API_KEY"]
    optional_keys = ["EXA_API_KEY", "SLIDESPEAK_API_KEY"]
    
    for key in required_keys:
        if os.getenv(key):
            print(f"   ✅ {key} 已配置")
        else:
            print(f"   ❌ {key} 未配置")
            return False
    
    for key in optional_keys:
        if os.getenv(key):
            print(f"   ✅ {key} 已配置（可选）")
        else:
            print(f"   ⚠️ {key} 未配置（可选，部分功能受限）")
    
    # ===== 2. 初始化 Agent =====
    print("\n📋 Step 2: 初始化 ZenFlux Agent")
    
    from core.agent.factory import AgentFactory
    from core.events import EventManager, get_memory_storage
    
    # 创建事件管理器（使用内存存储，适合测试）
    storage = get_memory_storage()
    event_manager = EventManager(storage)
    
    # 使用 system prompt 初始化
    system_prompt = """你是一位资深的商业演示文稿设计专家。

## 可用工具

### 搜索工具
1. **exa_search** - 高质量语义搜索，获取权威来源
2. **web_search** - 通用网络搜索

### PPT 生成工具
3. **slidespeak_render** - 🎯 首选！专业 PPT 渲染 API，支持复杂布局
4. **e2b_python_sandbox** - 备选：代码执行生成简单 PPT

## 工作流程

1. **理解需求** - 捕捉用户真正诉求
2. **搜索素材** - 使用 exa_search 获取权威数据
3. **组织结构** - 设计逻辑清晰的内容框架
4. **渲染 PPT** - 使用 slidespeak_render 生成专业 PPT

## 时效性策略

- 市场分析类：默认搜索最近 12 个月
- 如果用户指定年份（如"2024年"），添加对应时间过滤
- 如果用户说"最新"，搜索最近 3 个月

## 质量要求

- ✅ 所有数据必须有真实来源，标注引用
- ✅ 数据交叉验证，确保准确性
- ✅ 每页内容有明确价值，不堆砌
- ❌ 不要编造数据
"""
    
    # 使用 AgentFactory.from_prompt 创建（正确的异步方法）
    agent = await AgentFactory.from_prompt(
        system_prompt=system_prompt,
        event_manager=event_manager
    )
    print(f"   ✅ Agent 初始化成功")
    
    # 获取可用工具
    if hasattr(agent, 'tool_executor') and hasattr(agent.tool_executor, '_tool_instances'):
        tool_names = list(agent.tool_executor._tool_instances.keys())
    else:
        tool_names = []
    print(f"   📦 可用工具: {tool_names[:10]}..." if len(tool_names) > 10 else f"   📦 可用工具: {tool_names}")
    
    # ===== 3. 用户查询 =====
    print("\n📋 Step 3: 用户查询")
    
    # 真实用户查询
    user_query = """
    帮我做一个关于"2024年中国AI市场分析"的PPT，包含：
    1. 市场规模和增长趋势
    2. 主要玩家和竞争格局
    3. 关键技术趋势
    4. 投资机会
    
    请搜索最新数据，确保数据准确有来源。
    """
    
    print(f"   📝 用户查询: {user_query[:80]}...")
    
    # ===== 4. 执行 Agent =====
    print("\n📋 Step 4: 执行 Agent（全流程管道）")
    print("   " + "-" * 60)
    
    session_id = f"e2e_test_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    # 记录管道各阶段
    pipeline_stages = {
        "intent_analysis": None,
        "tool_selection": None,
        "search_calls": [],
        "compaction": [],
        "ppt_generation": None,
        "final_response": None
    }
    
    tool_call_count = 0
    search_results_raw_size = 0
    search_results_compacted_size = 0
    
    try:
        # chat() 方法需要 messages 列表格式
        messages = [{"role": "user", "content": user_query}]
        
        async for event in agent.chat(
            messages=messages,
            session_id=session_id,
            enable_stream=True
        ):
            event_type = event.get("type", "unknown")
            
            # 意图分析
            if event_type == "intent_analysis":
                pipeline_stages["intent_analysis"] = event.get("data", {})
                intent = event.get("data", {})
                print(f"\n   🎯 意图分析:")
                print(f"      - 任务类型: {intent.get('task_type', 'unknown')}")
                print(f"      - 需要计划: {intent.get('needs_plan', False)}")
                print(f"      - 能力需求: {intent.get('capabilities', [])}")
            
            # 工具选择
            elif event_type == "tool_selection":
                pipeline_stages["tool_selection"] = event.get("data", {})
                tools = event.get("data", {}).get("selected_tools", [])
                print(f"\n   🔧 工具选择:")
                for tool in tools:
                    print(f"      - {tool}")
            
            # 工具调用
            elif event_type == "tool_call":
                tool_call_count += 1
                tool_name = event.get("tool_name", "unknown")
                tool_input = event.get("input", {})
                
                print(f"\n   🔨 工具调用 #{tool_call_count}: {tool_name}")
                
                # 如果是搜索工具，记录详情
                if "search" in tool_name.lower():
                    query = tool_input.get("query", "")
                    print(f"      - 搜索查询: {query[:50]}...")
                    pipeline_stages["search_calls"].append({
                        "tool": tool_name,
                        "query": query
                    })
            
            # 工具结果
            elif event_type == "tool_result":
                tool_name = event.get("tool_name", "unknown")
                result = event.get("result", {})
                
                # 计算原始大小
                raw_size = len(json.dumps(result, ensure_ascii=False))
                
                print(f"\n   📊 工具结果: {tool_name}")
                print(f"      - 原始大小: {raw_size} 字符")
                
                # 如果是搜索结果，检查是否被精简
                if "search" in tool_name.lower():
                    search_results_raw_size += raw_size
                    
                    # 检查精简标记
                    if result.get("_compacted"):
                        compacted_size = result.get("_original_size", raw_size)
                        print(f"      - 精简后: {raw_size} 字符 (原 {compacted_size})")
                        print(f"      - 压缩率: {100 - (raw_size/compacted_size*100):.1f}%")
                        search_results_compacted_size += raw_size
                        pipeline_stages["compaction"].append({
                            "tool": tool_name,
                            "original": compacted_size,
                            "compacted": raw_size
                        })
                    else:
                        search_results_compacted_size += raw_size
                    
                    # 显示搜索结果数量
                    results = result.get("results", result.get("data", []))
                    if isinstance(results, list):
                        print(f"      - 结果数量: {len(results)} 条")
            
            # 思考过程
            elif event_type == "thinking":
                thinking = event.get("content", "")
                if thinking:
                    print(f"\n   💭 思考: {thinking[:100]}...")
            
            # 文本输出
            elif event_type == "text":
                content = event.get("content", "")
                if content and len(content) > 10:
                    # 检查是否包含 PPT 相关内容
                    if any(kw in content.lower() for kw in ["ppt", "slide", "幻灯片", "演示"]):
                        print(f"\n   📄 PPT 内容生成中...")
            
            # 完成
            elif event_type == "message_end":
                pipeline_stages["final_response"] = event.get("data", {})
                print(f"\n   ✅ Agent 执行完成")
                
    except Exception as e:
        logger.error(f"Agent 执行失败: {e}", exc_info=True)
        print(f"\n   ❌ 执行失败: {e}")
        return False
    
    # ===== 5. 管道总结 =====
    print("\n" + "=" * 70)
    print("📊 管道执行总结")
    print("=" * 70)
    
    print(f"\n   🎯 意图分析: {'✅' if pipeline_stages['intent_analysis'] else '❌'}")
    print(f"   🔧 工具选择: {'✅' if pipeline_stages['tool_selection'] else '❌'}")
    print(f"   🔍 搜索调用: {len(pipeline_stages['search_calls'])} 次")
    
    for i, search in enumerate(pipeline_stages["search_calls"], 1):
        print(f"      {i}. [{search['tool']}] {search['query'][:40]}...")
    
    print(f"\n   📦 搜索结果精简:")
    if pipeline_stages["compaction"]:
        total_original = sum(c["original"] for c in pipeline_stages["compaction"])
        total_compacted = sum(c["compacted"] for c in pipeline_stages["compaction"])
        compression_rate = (1 - total_compacted / total_original) * 100 if total_original > 0 else 0
        print(f"      - 原始总大小: {total_original} 字符")
        print(f"      - 精简后总大小: {total_compacted} 字符")
        print(f"      - 压缩率: {compression_rate:.1f}%")
        print(f"      ✅ 搜索压缩有效!")
    else:
        print(f"      ⚠️ 未检测到搜索结果精简")
    
    print(f"\n   🔨 工具调用总数: {tool_call_count} 次")
    
    # ===== 6. 检查输出文件 =====
    print("\n📋 Step 5: 检查输出文件")
    
    output_dir = project_root / "outputs"
    if output_dir.exists():
        ppt_files = list(output_dir.glob("*.pptx")) + list(output_dir.glob("*.ppt"))
        if ppt_files:
            print(f"   ✅ 找到 PPT 文件:")
            for f in ppt_files:
                print(f"      - {f.name} ({f.stat().st_size / 1024:.1f} KB)")
        else:
            print(f"   ⚠️ 未找到 PPT 文件（可能生成在其他位置）")
    
    # ===== 7. 获取追踪报告 =====
    print("\n📋 Step 6: 追踪报告")
    
    if hasattr(agent, 'get_trace_report'):
        trace_report = agent.get_trace_report()
        if trace_report:
            print(f"   📈 追踪统计:")
            stats = trace_report.get("stats", {})
            print(f"      - 总耗时: {stats.get('total_time_ms', 0):.1f}ms")
            print(f"      - 工具调用: {stats.get('tool_calls', 0)} 次")
            print(f"      - 代码执行: {stats.get('code_executions', 0)} 次")
    
    print("\n" + "=" * 70)
    print("🎉 端到端测试完成!")
    print("=" * 70)
    
    return True


async def test_exa_search_directly():
    """
    直接测试 Exa Search 工具
    """
    print("\n" + "=" * 70)
    print("🔍 直接测试 Exa Search")
    print("=" * 70)
    
    exa_api_key = os.getenv("EXA_API_KEY")
    if not exa_api_key:
        print("   ❌ EXA_API_KEY 未配置，跳过测试")
        return False
    
    # 直接导入，避免循环依赖
    import aiohttp
    
    class ExaSearchTool:
        """Exa Search 简化版"""
        def __init__(self, api_key: str):
            self.api_key = api_key
            self.base_url = "https://api.exa.ai"
        
        async def execute(self, query: str, num_results: int = 10, include_text: bool = True):
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/search",
                    headers={"x-api-key": self.api_key, "Content-Type": "application/json"},
                    json={
                        "query": query,
                        "numResults": num_results,
                        "contents": {"text": True} if include_text else {}
                    },
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {"success": True, "results": data.get("results", [])}
                    else:
                        text = await response.text()
                        return {"success": False, "error": f"HTTP {response.status}: {text}"}
    
    tool = ExaSearchTool(api_key=exa_api_key)
    
    query = "2024年中国AI市场规模 行业报告"
    print(f"   📝 搜索查询: {query}")
    
    result = await tool.execute(
        query=query,
        num_results=5,
        include_text=True
    )
    
    if result.get("success"):
        results = result.get("results", [])
        print(f"   ✅ 搜索成功，返回 {len(results)} 条结果")
        
        total_size = 0
        for i, r in enumerate(results[:3], 1):
            title = r.get("title", "无标题")[:50]
            text_len = len(r.get("text", ""))
            total_size += text_len
            print(f"      {i}. {title}... ({text_len} 字符)")
        
        print(f"\n   📊 结果统计:")
        print(f"      - 总文本大小: {total_size} 字符")
        print(f"      - 平均每条: {total_size // len(results) if results else 0} 字符")
        
        return True
    else:
        print(f"   ❌ 搜索失败: {result.get('error', '未知错误')}")
        return False


async def test_slidespeak_directly():
    """
    直接测试 SlideSpeak 工具
    """
    print("\n" + "=" * 70)
    print("📊 直接测试 SlideSpeak")
    print("=" * 70)
    
    slidespeak_api_key = os.getenv("SLIDESPEAK_API_KEY")
    if not slidespeak_api_key:
        print("   ❌ SLIDESPEAK_API_KEY 未配置，跳过测试")
        return False
    
    import aiohttp
    
    class SlideSpeakTool:
        """SlideSpeak 简化版"""
        def __init__(self, api_key: str):
            self.api_key = api_key
            self.base_url = "https://api.slidespeak.co/api/v1"
        
        async def execute(self, config: dict):
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/presentation/generate",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=config,
                    timeout=aiohttp.ClientTimeout(total=300)
                ) as response:
                    if response.status in [200, 201]:
                        data = await response.json()
                        return {"success": True, "download_url": data.get("url", ""), "task_id": data.get("task_id")}
                    else:
                        text = await response.text()
                        return {"success": False, "error": f"HTTP {response.status}: {text}"}
    
    tool = SlideSpeakTool(api_key=slidespeak_api_key)
    
    # 简单的测试配置
    config = {
        "template": "DEFAULT",
        "language": "CHINESE",
        "fetch_images": True,
        "slides": [
            {
                "title": "AI 市场概览",
                "layout": "ITEMS",
                "item_amount": 3,
                "content": "AI市场规模增长、关键技术趋势、投资机会分析"
            },
            {
                "title": "市场规模",
                "layout": "BIG_NUMBER",
                "item_amount": 1,
                "content": "2024年中国AI市场规模达到5000亿元"
            }
        ]
    }
    
    print(f"   📝 生成配置: {len(config['slides'])} 页 PPT")
    
    result = await tool.execute(config=config)
    
    if result.get("success"):
        print(f"   ✅ PPT 生成成功")
        print(f"      - 下载链接: {result.get('download_url', '无')[:50]}...")
        print(f"      - 本地路径: {result.get('local_path', '无')}")
        return True
    else:
        print(f"   ❌ PPT 生成失败: {result.get('error', '未知错误')}")
        return False


async def main():
    """
    运行所有测试
    """
    print("\n" + "=" * 70)
    print("🧪 ZenFlux Agent 端到端测试套件")
    print("=" * 70)
    
    # 解析参数
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--exa", action="store_true", help="测试 Exa Search")
    parser.add_argument("--slidespeak", action="store_true", help="测试 SlideSpeak")
    parser.add_argument("--full", action="store_true", help="完整端到端测试")
    args = parser.parse_args()
    
    results = {}
    
    if args.exa:
        results["Exa Search"] = await test_exa_search_directly()
    
    if args.slidespeak:
        results["SlideSpeak"] = await test_slidespeak_directly()
    
    if args.full or not (args.exa or args.slidespeak):
        results["端到端 PPT 生成"] = await run_e2e_ppt_generation()
    
    # 总结
    print("\n" + "=" * 70)
    print("📋 测试结果总结")
    print("=" * 70)
    
    for test_name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"   {test_name}: {status}")
    
    return all(results.values())


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)


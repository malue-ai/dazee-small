#!/usr/bin/env python3
"""
MCP 工具与 API Calling 端到端测试 - 独立运行脚本

此脚本不依赖项目内部模块，只通过 HTTP API 进行测试。

运行方式：
    # 确保服务已启动
    uvicorn main:app --host 0.0.0.0 --port 8000
    
    # 运行测试
    python scripts/run_e2e_test.py
    
    # 只测试特定功能
    python scripts/run_e2e_test.py --test mcp
    python scripts/run_e2e_test.py --test event
    python scripts/run_e2e_test.py --test intent
"""

import json
import time
import asyncio
import argparse
from typing import List, Dict, Any, Optional, Set, Tuple
from uuid import uuid4
from dataclasses import dataclass, field
from datetime import datetime

# 只依赖标准库和 httpx
try:
    import httpx
except ImportError:
    print("❌ 请安装 httpx: pip install httpx")
    exit(1)


# ==================== 配置 ====================

BASE_URL = "http://localhost:8000"
AGENT_ID = "dazee_agent"
TEST_TIMEOUT = 180.0
MAX_EVENTS = 5000

# 有效的 delta 类型
VALID_DELTA_TYPES = {
    "intent", "thinking", "response", "progress", "preface",
    "clue", "files", "mind", "sql", "data", "chart", "report",
    "interface", "application", "recommended", "billing",
    "search", "knowledge", "ppt",
}


# ==================== 数据结构 ====================

@dataclass
class TestResult:
    """测试结果"""
    name: str
    passed: bool
    events_count: int
    delta_types: Set[str]
    duration: float
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EventValidationResult:
    """事件验证结果"""
    has_start: bool = False
    has_done: bool = False
    seq_valid: bool = False
    seq_values: List[int] = field(default_factory=list)
    delta_types: Set[str] = field(default_factory=set)
    intent_data: Optional[Dict[str, Any]] = None
    errors: List[str] = field(default_factory=list)
    raw_events: List[Dict[str, Any]] = field(default_factory=list)


# ==================== SSE 解析器 ====================

async def parse_sse_events(response: httpx.Response, max_events: int = MAX_EVENTS) -> List[Dict[str, Any]]:
    """解析 SSE 事件流"""
    events = []
    event_count = 0
    
    async for line in response.aiter_lines():
        if event_count >= max_events:
            print(f"⚠️ 达到最大事件数 {max_events}，提前退出")
            break
            
        line = line.strip()
        if line.startswith("data: "):
            try:
                data = json.loads(line[6:])
                events.append(data)
                event_count += 1
                
                event_type = data.get("type", "")
                if event_type in ("message.assistant.done", "message.assistant.error", "session_end", "done"):
                    break
            except json.JSONDecodeError:
                continue
    
    return events


async def send_chat_request(
    message: str,
    user_id: str = None,
    agent_id: str = AGENT_ID,
    timeout: float = TEST_TIMEOUT
) -> Tuple[List[Dict[str, Any]], float]:
    """发送聊天请求并收集所有事件"""
    if user_id is None:
        user_id = str(uuid4())
    
    request_data = {
        "message": message,
        "userId": user_id,
        "agentId": agent_id,
        "stream": True
    }
    
    start_time = time.time()
    
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
        async with client.stream(
            "POST",
            f"{BASE_URL}/api/v1/chat",
            json=request_data,
            params={"format": "zeno"}
        ) as response:
            if response.status_code != 200:
                raise Exception(f"请求失败: {response.status_code}")
            events = await parse_sse_events(response)
    
    duration = time.time() - start_time
    return events, duration


# ==================== 事件验证器 ====================

def validate_events(events: List[Dict[str, Any]]) -> EventValidationResult:
    """验证事件列表"""
    result = EventValidationResult()
    result.raw_events = events
    
    if not events:
        result.errors.append("没有收到任何事件")
        return result
    
    # 提取 ZenO 事件
    zeno_events = [e for e in events if e.get("type", "").startswith("message.assistant.")]
    
    if not zeno_events:
        result.errors.append("没有收到 ZenO 格式的事件")
        return result
    
    event_types = [e.get("type") for e in zeno_events]
    
    # 检查 start 事件
    if event_types[0] == "message.assistant.start":
        result.has_start = True
    else:
        result.errors.append(f"第一个事件应该是 start，实际是 {event_types[0]}")
    
    # 检查 done 事件
    if event_types[-1] in ("message.assistant.done", "message.assistant.error"):
        result.has_done = True
    else:
        result.errors.append(f"最后一个事件应该是 done/error，实际是 {event_types[-1]}")
    
    # 验证 seq 递增
    result.seq_values = [e.get("seq") for e in zeno_events if e.get("seq") is not None]
    if result.seq_values:
        result.seq_valid = all(
            result.seq_values[i] < result.seq_values[i + 1]
            for i in range(len(result.seq_values) - 1)
        )
        if not result.seq_valid:
            result.errors.append(f"seq 不是单调递增")
    
    # 提取 delta 类型
    for event in zeno_events:
        if event.get("type") == "message.assistant.delta":
            delta = event.get("delta", {})
            delta_type = delta.get("type")
            if delta_type:
                result.delta_types.add(delta_type)
                
                if delta_type == "intent":
                    try:
                        content = delta.get("content", "")
                        if isinstance(content, str):
                            result.intent_data = json.loads(content)
                        else:
                            result.intent_data = content
                    except json.JSONDecodeError:
                        pass
    
    return result


# ==================== 测试执行 ====================

async def test_event_format():
    """测试事件格式"""
    print("\n" + "=" * 60)
    print("测试: 事件格式验证 (start -> delta* -> done)")
    print("=" * 60)
    
    try:
        events, duration = await send_chat_request("你好，请简短回复")
        validation = validate_events(events)
        
        print(f"   事件数: {len(events)}")
        print(f"   has_start: {validation.has_start}")
        print(f"   has_done: {validation.has_done}")
        print(f"   seq_valid: {validation.seq_valid}")
        print(f"   seq 范围: {validation.seq_values[0] if validation.seq_values else 'N/A'} - {validation.seq_values[-1] if validation.seq_values else 'N/A'}")
        print(f"   delta 类型: {validation.delta_types}")
        print(f"   耗时: {duration:.1f}s")
        
        passed = validation.has_start and validation.has_done and validation.seq_valid
        if passed:
            print("   ✅ 测试通过")
        else:
            print(f"   ❌ 测试失败: {validation.errors}")
        
        return TestResult(
            name="event_format",
            passed=passed,
            events_count=len(events),
            delta_types=validation.delta_types,
            duration=duration,
            error="; ".join(validation.errors) if validation.errors else None
        )
    except Exception as e:
        print(f"   ❌ 测试异常: {e}")
        return TestResult(
            name="event_format",
            passed=False,
            events_count=0,
            delta_types=set(),
            duration=0,
            error=str(e)
        )


async def test_intent_recognition():
    """测试意图识别"""
    print("\n" + "=" * 60)
    print("测试: 意图识别 (intent delta)")
    print("=" * 60)
    
    try:
        events, duration = await send_chat_request("帮我画一个流程图")
        validation = validate_events(events)
        
        print(f"   事件数: {len(events)}")
        print(f"   delta 类型: {validation.delta_types}")
        print(f"   intent 数据: {validation.intent_data}")
        print(f"   耗时: {duration:.1f}s")
        
        has_intent = "intent" in validation.delta_types
        intent_valid = False
        if validation.intent_data:
            intent_valid = "intent_id" in validation.intent_data and "intent_name" in validation.intent_data
            if intent_valid:
                print(f"   intent_id: {validation.intent_data.get('intent_id')}")
                print(f"   intent_name: {validation.intent_data.get('intent_name')}")
        
        passed = has_intent and intent_valid
        if passed:
            print("   ✅ 测试通过")
        else:
            print(f"   ❌ 测试失败: has_intent={has_intent}, intent_valid={intent_valid}")
        
        return TestResult(
            name="intent_recognition",
            passed=passed,
            events_count=len(events),
            delta_types=validation.delta_types,
            duration=duration,
            details={"intent_data": validation.intent_data}
        )
    except Exception as e:
        print(f"   ❌ 测试异常: {e}")
        return TestResult(
            name="intent_recognition",
            passed=False,
            events_count=0,
            delta_types=set(),
            duration=0,
            error=str(e)
        )


async def test_mcp_tool(name: str, message: str, description: str):
    """测试 MCP 工具"""
    print("\n" + "=" * 60)
    print(f"测试: {name}")
    print(f"描述: {description}")
    print("=" * 60)
    
    try:
        events, duration = await send_chat_request(message)
        validation = validate_events(events)
        
        print(f"   事件数: {len(events)}")
        print(f"   delta 类型: {validation.delta_types}")
        print(f"   耗时: {duration:.1f}s")
        
        # 基本验证
        passed = validation.has_start and validation.has_done and validation.seq_valid
        
        if passed:
            print("   ✅ 测试通过")
        else:
            print(f"   ❌ 测试失败: {validation.errors}")
        
        return TestResult(
            name=f"mcp_{name}",
            passed=passed,
            events_count=len(events),
            delta_types=validation.delta_types,
            duration=duration,
            error="; ".join(validation.errors) if validation.errors else None
        )
    except Exception as e:
        print(f"   ❌ 测试异常: {e}")
        return TestResult(
            name=f"mcp_{name}",
            passed=False,
            events_count=0,
            delta_types=set(),
            duration=0,
            error=str(e)
        )


async def run_mcp_tests():
    """运行所有 MCP 工具测试"""
    results = []
    
    mcp_tools = [
        ("ontology_text2chart", "请帮我画一个用户登录流程图，包含输入账号、验证、成功跳转首页", "Ontology TextToChart - 文本转流程图"),
        ("nano_banana", "请帮我生成一张可爱的猫咪图片", "Nano Banana - 图片生成"),
        ("chat_documents", "请帮我查询关于人工智能的基础知识", "Chat Documents - 文档问答"),
        ("text2document", "请把以下内容转成 Word 文档：\n# 标题\n这是正文内容", "Text2Document - 文档转换"),
        ("perplexity", "请研究一下 2024 年大语言模型的发展趋势", "Perplexity - AI 研究"),
    ]
    
    for name, message, description in mcp_tools:
        result = await test_mcp_tool(name, message, description)
        results.append(result)
    
    return results


def generate_report(results: List[TestResult]):
    """生成测试报告"""
    print("\n")
    print("=" * 60)
    print("MCP & API E2E Test Report")
    print("=" * 60)
    print(f"\nTest Environment:")
    print(f"  - Base URL: {BASE_URL}")
    print(f"  - Agent: {AGENT_ID}")
    print(f"  - Format: zeno")
    print(f"  - Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    print("\n" + "=" * 60)
    print("Test Results")
    print("=" * 60)
    
    for result in results:
        status = "✅ PASS" if result.passed else "❌ FAIL"
        print(f"\n{status} {result.name}")
        print(f"       Events: {result.events_count}")
        print(f"       Delta types: {sorted(result.delta_types)}")
        print(f"       Duration: {result.duration:.1f}s")
        if result.error:
            print(f"       Error: {result.error}")
    
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    total_duration = sum(r.duration for r in results)
    
    print(f"Total: {total} tests")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Duration: {total_duration:.1f}s")
    print("")


async def main():
    parser = argparse.ArgumentParser(description="MCP & API E2E Test")
    parser.add_argument("--test", choices=["all", "event", "intent", "mcp"], default="all", help="测试类型")
    args = parser.parse_args()
    
    results = []
    
    print("\n" + "=" * 60)
    print("开始 MCP & API E2E 测试")
    print("=" * 60)
    print(f"服务地址: {BASE_URL}")
    print(f"Agent: {AGENT_ID}")
    
    # 先检查服务是否可用
    print("\n检查服务状态...")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            resp = await client.get(f"{BASE_URL}/api/v1/agents")
            if resp.status_code == 200:
                print("✅ 服务可用")
            else:
                print(f"❌ 服务异常: {resp.status_code}")
                return
    except Exception as e:
        print(f"❌ 无法连接服务: {e}")
        print("请确保服务已启动: uvicorn main:app --host 0.0.0.0 --port 8000")
        return
    
    if args.test in ("all", "event"):
        results.append(await test_event_format())
    
    if args.test in ("all", "intent"):
        results.append(await test_intent_recognition())
    
    if args.test in ("all", "mcp"):
        mcp_results = await run_mcp_tests()
        results.extend(mcp_results)
    
    generate_report(results)


if __name__ == "__main__":
    asyncio.run(main())

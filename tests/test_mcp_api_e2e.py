"""
MCP 工具与 API Calling 端到端测试

测试目标：
1. 验证 5 个 MCP 工具功能正常
2. 验证 API Calling 功能正常（wenshu_api, coze_api）
3. 验证 ZenO 事件格式正确（start, delta, done）
4. 验证意图识别（intent delta）正确

运行方式：
    # 确保服务已启动
    uvicorn main:app --host 0.0.0.0 --port 8000
    
    # 运行全部测试
    pytest tests/test_mcp_api_e2e.py -v -s
    
    # 只运行 MCP 测试
    pytest tests/test_mcp_api_e2e.py -v -s -k "mcp"
    
    # 只运行事件格式测试
    pytest tests/test_mcp_api_e2e.py -v -s -k "event"

作者：ZenFlux Team
"""

import json
import time
import asyncio
import pytest
import httpx
from typing import List, Dict, Any, Optional, Set, Tuple
from uuid import uuid4
from dataclasses import dataclass, field
from datetime import datetime


# ==================== 配置 ====================

# 测试服务器地址
BASE_URL = "http://localhost:8000"

# Agent ID
AGENT_ID = "dazee_agent"

# 测试超时（秒）- MCP 工具调用可能较慢
TEST_TIMEOUT = 180.0

# 最大事件数
MAX_EVENTS = 5000

# ZenO 事件类型
ZENO_EVENT_TYPES = {
    "message.assistant.start",
    "message.assistant.delta",
    "message.assistant.done",
    "message.assistant.error"
}

# 有效的 delta 类型
VALID_DELTA_TYPES = {
    "intent",       # 意图识别
    "thinking",     # 思考过程
    "response",     # 回复内容
    "progress",     # 任务进度
    "preface",      # 前言
    "clue",         # 线索/确认
    "files",        # 文件
    "mind",         # Mermaid 图表
    "sql",          # SQL 语句
    "data",         # 数据结果
    "chart",        # 图表配置
    "report",       # 分析报告
    "interface",    # 系统配置
    "application",  # 应用数据
    "dashboard",    # 仪表盘数据
    "recommended",  # 推荐问题
    "billing",      # 计费信息
    "search",       # 搜索结果
    "knowledge",    # 知识库结果
    "ppt",          # PPT 生成
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


# ==================== SSE 解析器 ====================

async def parse_sse_events(
    response: httpx.Response,
    max_events: int = MAX_EVENTS
) -> List[Dict[str, Any]]:
    """
    解析 SSE 事件流
    
    Args:
        response: httpx 响应对象
        max_events: 最大事件数（防止无限循环）
        
    Returns:
        事件列表
    """
    events = []
    event_count = 0
    
    async for line in response.aiter_lines():
        if event_count >= max_events:
            print(f"⚠️ 达到最大事件数 {max_events}，提前退出")
            break
            
        # SSE 格式：data: {...}
        line = line.strip()
        if line.startswith("data: "):
            try:
                data = json.loads(line[6:])
                events.append(data)
                event_count += 1
                
                # 检查是否结束事件
                event_type = data.get("type", "")
                if event_type in ("message.assistant.done", "message.assistant.error", "session_end", "done"):
                    break
            except json.JSONDecodeError:
                # 忽略无法解析的行
                continue
    
    return events


async def send_chat_request(
    message: str,
    user_id: str = None,
    agent_id: str = AGENT_ID,
    conversation_id: str = None,
    timeout: float = TEST_TIMEOUT
) -> Tuple[List[Dict[str, Any]], float]:
    """
    发送聊天请求并收集所有事件
    
    Args:
        message: 用户消息
        user_id: 用户 ID（可选）
        agent_id: Agent ID
        conversation_id: 对话 ID（可选，用于多轮对话）
        timeout: 超时时间
        
    Returns:
        (事件列表, 耗时秒数)
    """
    if user_id is None:
        user_id = str(uuid4())
    
    request_data = {
        "message": message,
        "userId": user_id,
        "agentId": agent_id,
        "stream": True
    }
    
    if conversation_id:
        request_data["conversationId"] = conversation_id
    
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

class EventValidator:
    """ZenO 事件验证器"""
    
    @staticmethod
    def validate_events(events: List[Dict[str, Any]]) -> EventValidationResult:
        """
        验证事件列表
        
        Args:
            events: 事件列表
            
        Returns:
            验证结果
        """
        result = EventValidationResult()
        
        if not events:
            result.errors.append("没有收到任何事件")
            return result
        
        # 提取 ZenO 事件
        zeno_events = [
            e for e in events 
            if e.get("type", "").startswith("message.assistant.")
        ]
        
        if not zeno_events:
            result.errors.append("没有收到 ZenO 格式的事件")
            return result
        
        # 验证事件序列
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
                result.errors.append(f"seq 不是单调递增: {result.seq_values[:10]}...")
        
        # 提取 delta 类型
        for event in zeno_events:
            if event.get("type") == "message.assistant.delta":
                delta = event.get("delta", {})
                delta_type = delta.get("type")
                if delta_type:
                    result.delta_types.add(delta_type)
                    
                    # 提取 intent 数据
                    if delta_type == "intent":
                        try:
                            content = delta.get("content", "")
                            if isinstance(content, str):
                                result.intent_data = json.loads(content)
                            else:
                                result.intent_data = content
                        except json.JSONDecodeError:
                            result.errors.append(f"intent content 解析失败: {content[:50]}...")
        
        # 验证 delta 类型是否合法
        invalid_types = result.delta_types - VALID_DELTA_TYPES
        if invalid_types:
            result.errors.append(f"未知的 delta 类型: {invalid_types}")
        
        return result
    
    @staticmethod
    def validate_intent(intent_data: Optional[Dict[str, Any]]) -> Tuple[bool, str]:
        """
        验证意图数据格式
        
        Args:
            intent_data: 意图数据
            
        Returns:
            (是否有效, 错误信息)
        """
        if not intent_data:
            return False, "没有 intent 数据"
        
        # 必须包含的字段
        required_fields = ["intent_id", "intent_name"]
        missing = [f for f in required_fields if f not in intent_data]
        
        if missing:
            return False, f"intent 缺少字段: {missing}"
        
        return True, ""


# ==================== 测试报告生成器 ====================

class TestReportGenerator:
    """测试报告生成器"""
    
    def __init__(self):
        self.results: List[TestResult] = []
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
    
    def add_result(self, result: TestResult):
        """添加测试结果"""
        self.results.append(result)
    
    def generate_report(self) -> str:
        """
        生成测试报告
        
        Returns:
            格式化的报告字符串
        """
        lines = []
        lines.append("=" * 60)
        lines.append("MCP & API E2E Test Report")
        lines.append("=" * 60)
        lines.append("")
        lines.append("Test Environment:")
        lines.append(f"  - Base URL: {BASE_URL}")
        lines.append(f"  - Agent: {AGENT_ID}")
        lines.append(f"  - Format: zeno")
        lines.append(f"  - Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        
        # 分类结果
        mcp_results = [r for r in self.results if r.name.startswith("mcp_")]
        api_results = [r for r in self.results if r.name.startswith("api_")]
        other_results = [r for r in self.results if not r.name.startswith(("mcp_", "api_"))]
        
        # MCP 测试结果
        if mcp_results:
            lines.append("=" * 60)
            lines.append("MCP Tools Test Results")
            lines.append("=" * 60)
            for result in mcp_results:
                status = "[PASS]" if result.passed else "[FAIL]"
                lines.append(f"{status} {result.name}")
                lines.append(f"       - Events: {result.events_count}")
                lines.append(f"       - Delta types: {sorted(result.delta_types)}")
                lines.append(f"       - Duration: {result.duration:.1f}s")
                if result.error:
                    lines.append(f"       - Error: {result.error}")
                lines.append("")
        
        # API 测试结果
        if api_results:
            lines.append("=" * 60)
            lines.append("API Calling Test Results")
            lines.append("=" * 60)
            for result in api_results:
                status = "[PASS]" if result.passed else "[FAIL]"
                lines.append(f"{status} {result.name}")
                lines.append(f"       - Events: {result.events_count}")
                lines.append(f"       - Delta types: {sorted(result.delta_types)}")
                lines.append(f"       - Duration: {result.duration:.1f}s")
                if result.error:
                    lines.append(f"       - Error: {result.error}")
                lines.append("")
        
        # 其他测试结果
        if other_results:
            lines.append("=" * 60)
            lines.append("Event Format Validation")
            lines.append("=" * 60)
            for result in other_results:
                status = "[PASS]" if result.passed else "[FAIL]"
                lines.append(f"{status} {result.name}")
                if result.error:
                    lines.append(f"       - Error: {result.error}")
                for key, value in result.details.items():
                    lines.append(f"       - {key}: {value}")
                lines.append("")
        
        # 汇总
        lines.append("=" * 60)
        lines.append("Summary")
        lines.append("=" * 60)
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        total_duration = sum(r.duration for r in self.results)
        
        lines.append(f"Total: {total} tests")
        lines.append(f"Passed: {passed}")
        lines.append(f"Failed: {failed}")
        lines.append(f"Duration: {total_duration:.1f}s")
        lines.append("")
        
        return "\n".join(lines)


# ==================== 测试用例：MCP 工具 ====================

class TestMCPTools:
    """MCP 工具测试类"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """测试前检查服务是否可用"""
        # 简单的健康检查可以在这里添加
        pass
    
    @pytest.mark.asyncio
    async def test_mcp_ontology_text2chart(self):
        """
        测试 Ontology TextToChart 工具
        
        工具：mcp_dify_Ontology_TextToChart_zen0
        功能：文本转 Mermaid 流程图
        """
        print("\n" + "=" * 50)
        print("测试: mcp_dify_Ontology_TextToChart_zen0")
        print("=" * 50)
        
        message = """请帮我画一个用户登录的流程图，包含以下步骤：
        1. 用户输入账号密码
        2. 系统验证
        3. 验证成功则跳转首页
        4. 验证失败则提示错误"""
        
        events, duration = await send_chat_request(message)
        
        # 验证事件
        validation = EventValidator.validate_events(events)
        
        print(f"   事件数: {len(events)}")
        print(f"   Delta 类型: {validation.delta_types}")
        print(f"   耗时: {duration:.1f}s")
        
        # 断言
        assert validation.has_start, "缺少 start 事件"
        assert validation.has_done, "缺少 done 事件"
        assert validation.seq_valid, f"seq 不递增: {validation.errors}"
        
        # 验证包含必要的 delta 类型
        assert "thinking" in validation.delta_types or "response" in validation.delta_types, \
            f"应该包含 thinking 或 response，实际: {validation.delta_types}"
        
        print("   ✅ 测试通过")
    
    @pytest.mark.asyncio
    async def test_mcp_nano_banana_image(self):
        """
        测试图片生成工具
        
        工具：mcp_dify_nano_banana
        功能：文本生成图片
        """
        print("\n" + "=" * 50)
        print("测试: mcp_dify_nano_banana")
        print("=" * 50)
        
        message = "请帮我生成一张可爱的卡通猫咪图片"
        
        events, duration = await send_chat_request(message)
        
        # 验证事件
        validation = EventValidator.validate_events(events)
        
        print(f"   事件数: {len(events)}")
        print(f"   Delta 类型: {validation.delta_types}")
        print(f"   耗时: {duration:.1f}s")
        
        # 断言
        assert validation.has_start, "缺少 start 事件"
        assert validation.has_done, "缺少 done 事件"
        assert validation.seq_valid, f"seq 不递增: {validation.errors}"
        
        print("   ✅ 测试通过")
    
    @pytest.mark.asyncio
    async def test_mcp_chat_documents(self):
        """
        测试文档问答工具
        
        工具：mcp_dify_chatDocuments
        功能：知识库问答
        """
        print("\n" + "=" * 50)
        print("测试: mcp_dify_chatDocuments")
        print("=" * 50)
        
        message = "请帮我查询一下关于人工智能的基础知识"
        
        events, duration = await send_chat_request(message)
        
        # 验证事件
        validation = EventValidator.validate_events(events)
        
        print(f"   事件数: {len(events)}")
        print(f"   Delta 类型: {validation.delta_types}")
        print(f"   耗时: {duration:.1f}s")
        
        # 断言
        assert validation.has_start, "缺少 start 事件"
        assert validation.has_done, "缺少 done 事件"
        assert validation.seq_valid, f"seq 不递增: {validation.errors}"
        
        print("   ✅ 测试通过")
    
    @pytest.mark.asyncio
    async def test_mcp_text2document(self):
        """
        测试文档转换工具
        
        工具：mcp_dify_text2document
        功能：文本转文档（markdown→docx, csv→xlsx）
        """
        print("\n" + "=" * 50)
        print("测试: mcp_dify_text2document")
        print("=" * 50)
        
        message = """请把下面的 markdown 内容转换成 Word 文档：

# 项目报告

## 概述
这是一个测试项目。

## 进度
- 阶段1：已完成
- 阶段2：进行中
- 阶段3：待开始

## 总结
项目进展顺利。"""
        
        events, duration = await send_chat_request(message)
        
        # 验证事件
        validation = EventValidator.validate_events(events)
        
        print(f"   事件数: {len(events)}")
        print(f"   Delta 类型: {validation.delta_types}")
        print(f"   耗时: {duration:.1f}s")
        
        # 断言
        assert validation.has_start, "缺少 start 事件"
        assert validation.has_done, "缺少 done 事件"
        assert validation.seq_valid, f"seq 不递增: {validation.errors}"
        
        print("   ✅ 测试通过")
    
    @pytest.mark.asyncio
    async def test_mcp_perplexity_research(self):
        """
        测试 Perplexity 研究工具
        
        工具：mcp_dify_perplxity
        功能：调用 Perplexity AI 进行研究
        """
        print("\n" + "=" * 50)
        print("测试: mcp_dify_perplxity")
        print("=" * 50)
        
        message = "请帮我研究一下 2024 年大语言模型的最新发展趋势"
        
        events, duration = await send_chat_request(message)
        
        # 验证事件
        validation = EventValidator.validate_events(events)
        
        print(f"   事件数: {len(events)}")
        print(f"   Delta 类型: {validation.delta_types}")
        print(f"   耗时: {duration:.1f}s")
        
        # 断言
        assert validation.has_start, "缺少 start 事件"
        assert validation.has_done, "缺少 done 事件"
        assert validation.seq_valid, f"seq 不递增: {validation.errors}"
        
        print("   ✅ 测试通过")


# ==================== 测试用例：API Calling ====================

class TestAPICalling:
    """API Calling 测试类"""
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="需要真实数据文件，跳过自动测试")
    async def test_api_wenshu_analytics(self):
        """
        测试问数平台 API
        
        API：wenshu_api
        功能：数据分析问答
        
        注意：此测试需要真实的数据文件
        """
        print("\n" + "=" * 50)
        print("测试: wenshu_api (数据分析)")
        print("=" * 50)
        
        # 这个测试需要实际的数据文件
        message = "请分析一下销售数据，告诉我 2024 年的总销售额"
        
        events, duration = await send_chat_request(message)
        
        # 验证事件
        validation = EventValidator.validate_events(events)
        
        print(f"   事件数: {len(events)}")
        print(f"   Delta 类型: {validation.delta_types}")
        print(f"   耗时: {duration:.1f}s")
        
        # 断言
        assert validation.has_start, "缺少 start 事件"
        assert validation.has_done, "缺少 done 事件"
        
        # 验证 wenshu_api 返回的特殊 delta 类型
        expected_types = {"sql", "data", "chart", "report"}
        found_types = validation.delta_types & expected_types
        print(f"   找到的分析类型: {found_types}")
        
        print("   ✅ 测试通过")
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="需要先生成流程图，跳过自动测试")
    async def test_api_coze_ontology(self):
        """
        测试 Coze Ontology Builder API
        
        API：coze_api
        功能：流程图 → 系统配置
        
        注意：此测试需要先使用 mcp_dify_Ontology_TextToChart_zen0 生成流程图
        """
        print("\n" + "=" * 50)
        print("测试: coze_api (Ontology Builder)")
        print("=" * 50)
        
        # 这个测试需要先生成流程图 URL
        message = """我已经有了一个流程图，请根据它生成系统配置：
        流程图 URL: https://example.com/flowchart.txt
        系统名称: 用户管理系统"""
        
        events, duration = await send_chat_request(message)
        
        # 验证事件
        validation = EventValidator.validate_events(events)
        
        print(f"   事件数: {len(events)}")
        print(f"   Delta 类型: {validation.delta_types}")
        print(f"   耗时: {duration:.1f}s")
        
        # 断言
        assert validation.has_start, "缺少 start 事件"
        assert validation.has_done, "缺少 done 事件"
        
        print("   ✅ 测试通过")


# ==================== 测试用例：事件格式验证 ====================

class TestEventFormat:
    """ZenO 事件格式测试类"""
    
    @pytest.mark.asyncio
    async def test_event_sequence(self):
        """
        测试事件序列
        
        验证：start → delta* → done
        """
        print("\n" + "=" * 50)
        print("测试: 事件序列验证")
        print("=" * 50)
        
        message = "你好"
        
        events, duration = await send_chat_request(message)
        
        # 验证事件
        validation = EventValidator.validate_events(events)
        
        print(f"   事件数: {len(events)}")
        print(f"   has_start: {validation.has_start}")
        print(f"   has_done: {validation.has_done}")
        print(f"   seq_valid: {validation.seq_valid}")
        
        # 断言
        assert validation.has_start, "事件序列必须以 start 开始"
        assert validation.has_done, "事件序列必须以 done 结束"
        assert validation.seq_valid, f"seq 必须单调递增: {validation.errors}"
        
        # 验证中间都是 delta
        zeno_events = [
            e for e in events 
            if e.get("type", "").startswith("message.assistant.")
        ]
        middle_types = [e.get("type") for e in zeno_events[1:-1]]
        for t in middle_types:
            assert t == "message.assistant.delta", f"中间事件应该是 delta，实际是 {t}"
        
        print("   ✅ 事件序列验证通过")
    
    @pytest.mark.asyncio
    async def test_seq_incremental(self):
        """
        测试 seq 递增
        
        验证：每个事件的 seq 都比前一个大
        """
        print("\n" + "=" * 50)
        print("测试: seq 递增验证")
        print("=" * 50)
        
        message = "请简短回复"
        
        events, duration = await send_chat_request(message)
        
        # 验证事件
        validation = EventValidator.validate_events(events)
        
        print(f"   seq 值: {validation.seq_values[:10]}{'...' if len(validation.seq_values) > 10 else ''}")
        print(f"   seq_valid: {validation.seq_valid}")
        
        # 断言
        assert len(validation.seq_values) > 0, "没有收到带 seq 的事件"
        assert validation.seq_valid, f"seq 必须单调递增: {validation.seq_values}"
        
        # 验证 seq 从正整数开始
        assert validation.seq_values[0] > 0, f"seq 应该从正整数开始，实际是 {validation.seq_values[0]}"
        
        print("   ✅ seq 递增验证通过")
    
    @pytest.mark.asyncio
    async def test_delta_types_valid(self):
        """
        测试 delta 类型有效性
        
        验证：所有 delta.type 都是有效的类型
        """
        print("\n" + "=" * 50)
        print("测试: delta 类型有效性验证")
        print("=" * 50)
        
        message = "请帮我分析一下问题"
        
        events, duration = await send_chat_request(message)
        
        # 验证事件
        validation = EventValidator.validate_events(events)
        
        print(f"   收到的 delta 类型: {validation.delta_types}")
        
        # 检查是否有未知类型
        invalid_types = validation.delta_types - VALID_DELTA_TYPES
        assert not invalid_types, f"存在未知的 delta 类型: {invalid_types}"
        
        print("   ✅ delta 类型验证通过")


# ==================== 测试用例：意图识别验证 ====================

class TestIntentRecognition:
    """意图识别测试类"""
    
    @pytest.mark.asyncio
    async def test_intent_delta_exists(self):
        """
        测试 intent delta 存在
        
        验证：聊天响应中包含 intent 事件
        """
        print("\n" + "=" * 50)
        print("测试: intent delta 存在性验证")
        print("=" * 50)
        
        message = "请帮我画一个流程图"
        
        events, duration = await send_chat_request(message)
        
        # 验证事件
        validation = EventValidator.validate_events(events)
        
        print(f"   Delta 类型: {validation.delta_types}")
        print(f"   Intent 数据: {validation.intent_data}")
        
        # 验证 intent delta 存在
        assert "intent" in validation.delta_types, f"应该包含 intent delta，实际: {validation.delta_types}"
        
        print("   ✅ intent delta 存在性验证通过")
    
    @pytest.mark.asyncio
    async def test_intent_format(self):
        """
        测试 intent 数据格式
        
        验证：intent 包含 intent_id 和 intent_name 字段
        """
        print("\n" + "=" * 50)
        print("测试: intent 格式验证")
        print("=" * 50)
        
        message = "帮我分析数据"
        
        events, duration = await send_chat_request(message)
        
        # 验证事件
        validation = EventValidator.validate_events(events)
        
        print(f"   Intent 数据: {validation.intent_data}")
        
        # 验证 intent 格式
        if validation.intent_data:
            valid, error = EventValidator.validate_intent(validation.intent_data)
            assert valid, f"intent 格式无效: {error}"
            
            print(f"   intent_id: {validation.intent_data.get('intent_id')}")
            print(f"   intent_name: {validation.intent_data.get('intent_name')}")
            if "platform" in validation.intent_data:
                print(f"   platform: {validation.intent_data.get('platform')}")
        
        print("   ✅ intent 格式验证通过")


# ==================== 综合测试：完整流程 ====================

class TestFullWorkflow:
    """完整工作流测试"""
    
    @pytest.mark.asyncio
    async def test_ontology_builder_workflow(self):
        """
        测试 Ontology Builder 完整工作流
        
        流程：
        1. 使用 mcp_dify_Ontology_TextToChart_zen0 生成流程图
        2. （如果需要）使用 coze_api 生成系统配置
        """
        print("\n" + "=" * 50)
        print("测试: Ontology Builder 工作流")
        print("=" * 50)
        
        # 第一步：生成流程图
        message = """请帮我创建一个"个人健康记录管理系统"的流程图，包含：
        1. 用户注册登录
        2. 健康数据录入
        3. 数据统计分析
        4. 报告生成"""
        
        events, duration = await send_chat_request(message)
        
        # 验证事件
        validation = EventValidator.validate_events(events)
        
        print(f"   第一步 - 流程图生成:")
        print(f"      事件数: {len(events)}")
        print(f"      Delta 类型: {validation.delta_types}")
        print(f"      耗时: {duration:.1f}s")
        
        # 断言
        assert validation.has_start, "缺少 start 事件"
        assert validation.has_done, "缺少 done 事件"
        assert validation.seq_valid, f"seq 不递增: {validation.errors}"
        
        print("   ✅ Ontology Builder 工作流测试通过")


# ==================== 运行入口 ====================

async def run_all_tests_with_report():
    """
    运行所有测试并生成报告
    
    用于手动运行测试并查看详细报告
    """
    report = TestReportGenerator()
    
    print("\n" + "=" * 60)
    print("开始 MCP & API E2E 测试")
    print("=" * 60)
    
    # 测试配置
    test_cases = [
        # MCP 工具测试
        ("mcp_ontology_text2chart", "请帮我画一个用户登录流程图", {"thinking", "response"}),
        ("mcp_nano_banana", "请帮我生成一张猫咪图片", {"thinking", "response"}),
        ("mcp_chat_documents", "请帮我查询关于 AI 的知识", {"thinking", "response"}),
        ("mcp_text2document", "请把这段文字转成 Word 文档：# 标题\n内容", {"thinking", "response"}),
        ("mcp_perplexity", "请研究 AI 的最新发展", {"thinking", "response"}),
    ]
    
    for name, message, expected_types in test_cases:
        print(f"\n运行测试: {name}")
        try:
            events, duration = await send_chat_request(message)
            validation = EventValidator.validate_events(events)
            
            passed = (
                validation.has_start and 
                validation.has_done and 
                validation.seq_valid and
                len(validation.errors) == 0
            )
            
            result = TestResult(
                name=name,
                passed=passed,
                events_count=len(events),
                delta_types=validation.delta_types,
                duration=duration,
                error="; ".join(validation.errors) if validation.errors else None
            )
            
        except Exception as e:
            result = TestResult(
                name=name,
                passed=False,
                events_count=0,
                delta_types=set(),
                duration=0,
                error=str(e)
            )
        
        report.add_result(result)
        status = "✅" if result.passed else "❌"
        print(f"   {status} {name}: {'通过' if result.passed else '失败'}")
    
    # 事件格式验证
    print("\n运行事件格式验证...")
    try:
        events, duration = await send_chat_request("你好")
        validation = EventValidator.validate_events(events)
        
        result = TestResult(
            name="event_format_validation",
            passed=validation.has_start and validation.has_done and validation.seq_valid,
            events_count=len(events),
            delta_types=validation.delta_types,
            duration=duration,
            details={
                "has_start": validation.has_start,
                "has_done": validation.has_done,
                "seq_valid": validation.seq_valid,
                "seq_range": f"{validation.seq_values[0]}-{validation.seq_values[-1]}" if validation.seq_values else "N/A"
            }
        )
    except Exception as e:
        result = TestResult(
            name="event_format_validation",
            passed=False,
            events_count=0,
            delta_types=set(),
            duration=0,
            error=str(e)
        )
    
    report.add_result(result)
    
    # 生成报告
    print("\n")
    print(report.generate_report())


if __name__ == "__main__":
    # 运行 pytest
    # pytest.main([__file__, "-v", "-s"])
    
    # 或运行自定义测试并生成报告
    asyncio.run(run_all_tests_with_report())

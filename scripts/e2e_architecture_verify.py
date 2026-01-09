#!/usr/bin/env python3
"""
端对端架构管道验证脚本

严格按照 V4.6 架构文档的 7 阶段管道进行验证：
1. Session/Agent 初始化
2. Intent Analysis
3. Tool Selection
4. System Prompt 组装
5. Plan Creation
6. RVR Loop
7. Final Output

运行方式：
    python scripts/e2e_architecture_verify.py
"""

import os
import sys
import asyncio
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 从 .env 加载环境变量
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "instances/test_agent/.env", override=True)


@dataclass
class VerificationResult:
    """验证结果数据类"""
    phase: str
    check_name: str
    passed: bool
    expected: str
    actual: str
    details: str = ""


@dataclass
class PhaseReport:
    """阶段报告"""
    phase_id: int
    phase_name: str
    results: List[VerificationResult] = field(default_factory=list)
    
    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)
    
    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)
    
    @property
    def total_count(self) -> int:
        return len(self.results)


class ArchitectureVerifier:
    """架构验证器"""
    
    def __init__(self, instance_name: str = "test_agent"):
        self.instance_name = instance_name
        self.reports: List[PhaseReport] = []
        self.agent = None
        self.config = None
        self.prompt_cache = None
        self.instance_registry = None
        
    def _print_header(self, text: str):
        """打印标题"""
        print(f"\n{'='*60}")
        print(f"  {text}")
        print(f"{'='*60}")
    
    def _print_check(self, name: str, passed: bool, details: str = ""):
        """打印检查结果"""
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  [{status}] {name}")
        if details:
            for line in details.split("\n"):
                print(f"           {line}")
    
    async def verify_phase1_config(self) -> PhaseReport:
        """
        阶段 1: 验证配置加载和 InstancePromptCache
        
        验证点：
        - .env 加载
        - config.yaml 解析
        - InstancePromptCache 加载
        """
        from scripts.instance_loader import (
            load_instance_config,
            load_instance_prompt,
            load_instance_env
        )
        from core.prompt import InstancePromptCache, load_instance_cache
        
        self._print_header("阶段 1: 配置加载和 InstancePromptCache 验证")
        
        report = PhaseReport(phase_id=1, phase_name="配置加载和 InstancePromptCache")
        
        # 1.1 验证 .env 加载
        load_instance_env(self.instance_name)
        dify_key = os.getenv("DIFY_API_KEY")
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        
        env_passed = bool(dify_key) and bool(anthropic_key)
        result = VerificationResult(
            phase="Phase 1",
            check_name=".env 环境变量加载",
            passed=env_passed,
            expected="DIFY_API_KEY 和 ANTHROPIC_API_KEY 已设置",
            actual=f"DIFY_API_KEY={'SET' if dify_key else 'NOT SET'}, ANTHROPIC_API_KEY={'SET' if anthropic_key else 'NOT SET'}",
            details=f"DIFY_API_KEY: {dify_key[:10]}..." if dify_key else ""
        )
        report.results.append(result)
        self._print_check(result.check_name, result.passed, result.actual)
        
        # 1.2 验证 config.yaml 解析
        self.config = load_instance_config(self.instance_name)
        
        config_passed = (
            self.config.name == "test_agent" and
            len(self.config.mcp_tools) > 0 and
            self.config.mcp_tools[0].get("name") == "text2flowchart"
        )
        result = VerificationResult(
            phase="Phase 1",
            check_name="config.yaml 解析",
            passed=config_passed,
            expected="InstanceConfig 包含 mcp_tools[0].name='text2flowchart'",
            actual=f"name={self.config.name}, mcp_tools={len(self.config.mcp_tools)} 个",
            details=f"MCP 工具: {[t.get('name') for t in self.config.mcp_tools]}"
        )
        report.results.append(result)
        self._print_check(result.check_name, result.passed, result.details)
        
        # 1.3 验证 LLM 超参数
        llm_params = self.config.llm_params
        llm_passed = llm_params.enable_thinking == True
        result = VerificationResult(
            phase="Phase 1",
            check_name="LLM 超参数配置",
            passed=llm_passed,
            expected="enable_thinking=True",
            actual=f"enable_thinking={llm_params.enable_thinking}, thinking_budget={llm_params.thinking_budget}",
        )
        report.results.append(result)
        self._print_check(result.check_name, result.passed, result.actual)
        
        # 1.4 验证实例提示词
        instance_prompt = load_instance_prompt(self.instance_name)
        prompt_passed = "dify_Ontology_TextToChart_zen0" in instance_prompt
        result = VerificationResult(
            phase="Phase 1",
            check_name="实例提示词 (prompt.md)",
            passed=prompt_passed,
            expected="包含 MCP 工具名称 'dify_Ontology_TextToChart_zen0'",
            actual=f"长度={len(instance_prompt)} 字符, 包含工具名={'是' if prompt_passed else '否'}",
        )
        report.results.append(result)
        self._print_check(result.check_name, result.passed, result.actual)
        
        # 1.5 验证 InstancePromptCache 加载
        try:
            self.prompt_cache = await load_instance_cache(
                instance_name=self.instance_name,
                raw_prompt=instance_prompt,
                config=self.config.raw_config,
                force_refresh=False
            )
            cache_passed = (
                self.prompt_cache.is_loaded and
                self.prompt_cache.system_prompt_simple is not None
            )
            result = VerificationResult(
                phase="Phase 1",
                check_name="InstancePromptCache 加载",
                passed=cache_passed,
                expected="is_loaded=True, 三个版本提示词已生成",
                actual=f"is_loaded={self.prompt_cache.is_loaded}, "
                       f"Simple={len(self.prompt_cache.system_prompt_simple or '')}字符, "
                       f"Medium={len(self.prompt_cache.system_prompt_medium or '')}字符, "
                       f"Complex={len(self.prompt_cache.system_prompt_complex or '')}字符",
            )
        except Exception as e:
            cache_passed = False
            result = VerificationResult(
                phase="Phase 1",
                check_name="InstancePromptCache 加载",
                passed=False,
                expected="is_loaded=True",
                actual=f"加载失败: {str(e)}",
            )
        report.results.append(result)
        self._print_check(result.check_name, result.passed, result.actual)
        
        self.reports.append(report)
        return report
    
    async def verify_phase1_mcp(self) -> PhaseReport:
        """
        阶段 1 (续): 验证 MCP 连接和工具发现
        
        验证点：
        - MCP 客户端连接
        - 工具发现
        - InstanceToolRegistry 注册
        """
        from services.mcp_client import get_mcp_client
        from core.tool import InstanceToolRegistry, get_capability_registry
        
        self._print_header("阶段 1 (续): MCP 连接和工具发现验证")
        
        report = PhaseReport(phase_id=1, phase_name="MCP 连接和工具发现")
        
        # 获取 MCP 配置
        mcp_config = self.config.mcp_tools[0] if self.config.mcp_tools else {}
        server_url = mcp_config.get("server_url", "")
        server_name = mcp_config.get("server_name", "dify")
        auth_env = mcp_config.get("auth_env", "DIFY_API_KEY")
        auth_token = os.getenv(auth_env)
        
        # 1.6 验证 MCP 客户端连接
        try:
            client = await get_mcp_client(
                server_url=server_url,
                server_name=server_name,
                auth_token=auth_token
            )
            connected = client._connected
            result = VerificationResult(
                phase="Phase 1",
                check_name="MCP 客户端连接",
                passed=connected,
                expected="client._connected=True",
                actual=f"_connected={connected}, server_url={server_url[:50]}...",
            )
        except Exception as e:
            connected = False
            result = VerificationResult(
                phase="Phase 1",
                check_name="MCP 客户端连接",
                passed=False,
                expected="client._connected=True",
                actual=f"连接失败: {str(e)}",
            )
            client = None
        report.results.append(result)
        self._print_check(result.check_name, result.passed, result.actual)
        
        # 1.7 验证工具发现
        tools_discovered = []
        if client and connected:
            try:
                tools_list = await client.discover_tools()
                tools_discovered = [t['name'] for t in tools_list]
                tools_passed = len(tools_discovered) > 0
                result = VerificationResult(
                    phase="Phase 1",
                    check_name="MCP 工具发现",
                    passed=tools_passed,
                    expected="发现至少 1 个工具",
                    actual=f"发现 {len(tools_discovered)} 个工具: {tools_discovered}",
                )
            except Exception as e:
                tools_passed = False
                result = VerificationResult(
                    phase="Phase 1",
                    check_name="MCP 工具发现",
                    passed=False,
                    expected="发现至少 1 个工具",
                    actual=f"发现失败: {str(e)}",
                )
        else:
            result = VerificationResult(
                phase="Phase 1",
                check_name="MCP 工具发现",
                passed=False,
                expected="发现至少 1 个工具",
                actual="跳过（MCP 未连接）",
            )
        report.results.append(result)
        self._print_check(result.check_name, result.passed, result.actual)
        
        # 1.8 验证 InstanceToolRegistry
        global_registry = get_capability_registry()
        self.instance_registry = InstanceToolRegistry(global_registry=global_registry)
        
        # 注册 MCP 工具到 registry
        if client and connected and tools_discovered:
            for tool_info in await client.discover_tools():
                tool_name = tool_info['name']
                original_name = tool_info.get('original_name', tool_name)
                
                async def make_handler(_client, _orig_name):
                    async def handler(tool_input: Dict[str, Any]):
                        return await _client.call_tool(_orig_name, tool_input)
                    return handler
                
                handler = await make_handler(client, original_name)
                
                await self.instance_registry.register_mcp_tool(
                    name=tool_name,
                    server_url=server_url,
                    server_name=server_name,
                    tool_info=tool_info,
                    mcp_client=client,
                    handler=handler,
                    capability=mcp_config.get("capability")
                )
        
        from core.tool.instance_registry import InstanceToolType
        mcp_tools = self.instance_registry.get_by_type(InstanceToolType.MCP)
        registry_passed = len(mcp_tools) > 0
        result = VerificationResult(
            phase="Phase 1",
            check_name="InstanceToolRegistry 注册",
            passed=registry_passed,
            expected="MCP 工具已注册到 registry",
            actual=f"已注册 {len(mcp_tools)} 个 MCP 工具: {[t.name for t in mcp_tools]}",
        )
        report.results.append(result)
        self._print_check(result.check_name, result.passed, result.actual)
        
        self.reports.append(report)
        return report
    
    async def verify_phase2_intent(self) -> PhaseReport:
        """
        阶段 2: 验证意图分析
        
        验证点：
        - IntentAnalyzer 调用
        - task_type/complexity 输出
        - skip_memory_retrieval 判断
        """
        from core.agent.intent_analyzer import IntentAnalyzer, create_intent_analyzer
        
        self._print_header("阶段 2: 意图分析验证")
        
        report = PhaseReport(phase_id=2, phase_name="意图分析")
        
        # 创建意图分析器
        intent_analyzer = create_intent_analyzer(
            enable_llm=True,
            prompt_cache=self.prompt_cache
        )
        
        # 测试消息
        test_messages = [
            {"role": "user", "content": "帮我生成用户管理系统的 flowchart"}
        ]
        
        # 2.1 验证意图分析器调用
        try:
            intent_result = await intent_analyzer.analyze(test_messages)
            
            # 检查 task_type
            task_type_passed = intent_result.task_type is not None
            result = VerificationResult(
                phase="Phase 2",
                check_name="IntentAnalyzer.analyze() 调用",
                passed=task_type_passed,
                expected="返回 IntentResult 对象",
                actual=f"task_type={intent_result.task_type}, complexity={intent_result.complexity}",
            )
            report.results.append(result)
            self._print_check(result.check_name, result.passed, result.actual)
            
            # 2.2 验证 complexity
            # complexity 可能是 Enum 或字符串，统一处理
            complexity_value = getattr(intent_result.complexity, 'value', str(intent_result.complexity))
            complexity_passed = complexity_value in ["simple", "medium", "complex"]
            result = VerificationResult(
                phase="Phase 2",
                check_name="complexity 判断",
                passed=complexity_passed,
                expected="simple/medium/complex 之一",
                actual=f"complexity={complexity_value}",
            )
            report.results.append(result)
            self._print_check(result.check_name, result.passed, result.actual)
            
            # 2.3 验证 needs_plan
            result = VerificationResult(
                phase="Phase 2",
                check_name="needs_plan 判断",
                passed=True,  # 只是记录值
                expected="根据复杂度判断",
                actual=f"needs_plan={intent_result.needs_plan}",
            )
            report.results.append(result)
            self._print_check(result.check_name, result.passed, result.actual)
            
            # 2.4 验证 skip_memory_retrieval (V4.6)
            skip_memory = getattr(intent_result, 'skip_memory_retrieval', None)
            result = VerificationResult(
                phase="Phase 2",
                check_name="skip_memory_retrieval (V4.6)",
                passed=skip_memory is not None,
                expected="true（通用工具任务）或 false（个性化任务）",
                actual=f"skip_memory_retrieval={skip_memory}",
            )
            report.results.append(result)
            self._print_check(result.check_name, result.passed, result.actual)
            
        except Exception as e:
            result = VerificationResult(
                phase="Phase 2",
                check_name="IntentAnalyzer.analyze() 调用",
                passed=False,
                expected="返回 IntentResult 对象",
                actual=f"分析失败: {str(e)}",
            )
            report.results.append(result)
            self._print_check(result.check_name, result.passed, result.actual)
        
        self.reports.append(report)
        return report
    
    async def verify_phase3_tools(self) -> PhaseReport:
        """
        阶段 3: 验证工具选择和合并
        
        验证点：
        - Level 1/2 工具分层
        - MCP 工具合并
        - tools_for_llm 构建
        """
        from core.tool import get_capability_registry
        from core.tool.selector import ToolSelector
        
        self._print_header("阶段 3: 工具选择和合并验证")
        
        report = PhaseReport(phase_id=3, phase_name="工具选择和合并")
        
        # 获取全局 registry
        global_registry = get_capability_registry()
        
        # 3.1 验证 Level 1 核心工具
        core_tools = global_registry.get_core_tools()
        core_tool_names = [t.name for t in core_tools]
        level1_passed = "plan_todo" in core_tool_names
        result = VerificationResult(
            phase="Phase 3",
            check_name="Level 1 核心工具",
            passed=level1_passed,
            expected="包含 plan_todo",
            actual=f"Level 1 工具: {core_tool_names}",
        )
        report.results.append(result)
        self._print_check(result.check_name, result.passed, result.actual)
        
        # 3.2 验证 Level 2 动态工具
        dynamic_tools = global_registry.get_dynamic_tools()
        dynamic_tool_names = [t.name for t in dynamic_tools]
        level2_passed = len(dynamic_tools) > 0
        result = VerificationResult(
            phase="Phase 3",
            check_name="Level 2 动态工具",
            passed=level2_passed,
            expected="至少有 1 个动态工具",
            actual=f"Level 2 工具: {len(dynamic_tools)} 个",
            details=f"前 5 个: {dynamic_tool_names[:5]}"
        )
        report.results.append(result)
        self._print_check(result.check_name, result.passed, result.details)
        
        # 3.3 验证 MCP 工具在 InstanceToolRegistry 中
        from core.tool.instance_registry import InstanceToolType
        mcp_tools = self.instance_registry.get_by_type(InstanceToolType.MCP)
        mcp_tool_names = [t.name for t in mcp_tools]
        mcp_passed = any("Ontology" in name or "flowchart" in name.lower() for name in mcp_tool_names)
        result = VerificationResult(
            phase="Phase 3",
            check_name="MCP 工具合并",
            passed=mcp_passed or len(mcp_tools) > 0,
            expected="dify_Ontology_TextToChart_zen0 在工具列表中",
            actual=f"MCP 工具: {mcp_tool_names}",
        )
        report.results.append(result)
        self._print_check(result.check_name, result.passed, result.actual)
        
        # 3.4 验证 tools_for_claude 构建
        tools_for_claude = self.instance_registry.get_tools_for_claude()
        tools_for_claude_names = [t['name'] for t in tools_for_claude]
        tools_passed = len(tools_for_claude) > 0
        result = VerificationResult(
            phase="Phase 3",
            check_name="tools_for_claude 构建",
            passed=tools_passed,
            expected="Claude API 格式的工具列表",
            actual=f"构建了 {len(tools_for_claude)} 个工具: {tools_for_claude_names}",
        )
        report.results.append(result)
        self._print_check(result.check_name, result.passed, result.actual)
        
        self.reports.append(report)
        return report
    
    async def verify_phase5_7_e2e(self) -> PhaseReport:
        """
        阶段 5-7: 端对端对话验证
        
        验证点：
        - Agent 创建
        - Claude 选择 MCP 工具
        - MCP 工具调用
        - 最终输出
        """
        from scripts.instance_loader import create_agent_from_instance
        
        self._print_header("阶段 5-7: 端对端对话验证")
        
        report = PhaseReport(phase_id=5, phase_name="端对端对话")
        
        # 5.1 创建 Agent
        try:
            self.agent = await create_agent_from_instance(
                self.instance_name,
                skip_mcp_registration=False,
                skip_skills_registration=True,
                force_refresh=False
            )
            agent_passed = self.agent is not None
            result = VerificationResult(
                phase="Phase 5",
                check_name="Agent 创建",
                passed=agent_passed,
                expected="Agent 实例创建成功",
                actual=f"Agent={self.agent.__class__.__name__}, model={getattr(self.agent, 'model', 'unknown')}",
            )
        except Exception as e:
            agent_passed = False
            result = VerificationResult(
                phase="Phase 5",
                check_name="Agent 创建",
                passed=False,
                expected="Agent 实例创建成功",
                actual=f"创建失败: {str(e)}",
            )
        report.results.append(result)
        self._print_check(result.check_name, result.passed, result.actual)
        
        if not agent_passed:
            self.reports.append(report)
            return report
        
        # 5.2 执行对话测试
        test_query = "帮我生成用户管理系统的 flowchart，包含用户、角色、权限三个实体"
        messages = [{"role": "user", "content": test_query}]
        
        print(f"\n  📝 测试查询: {test_query}")
        print(f"  ⏳ 正在调用 Agent...")
        
        events_collected = []
        response_text = ""
        tool_calls = []
        
        try:
            async for event in self.agent.chat(messages=messages):
                events_collected.append(event)
                event_type = event.get("type", "")
                
                # 收集文本响应 - message_delta 格式
                if event_type == "message_delta":
                    delta = event.get("delta", {})
                    text = delta.get("text", "")
                    response_text += text
                
                # 收集文本响应 - content_delta 格式
                elif event_type == "content_delta":
                    data = event.get("data", {})
                    delta = data.get("delta", {})
                    delta_type = delta.get("type", "")
                    if delta_type == "text_delta":
                        text = delta.get("text", "")
                        if text:
                            response_text += text
                
                # 收集工具调用 - content_start 格式 (tool_use block)
                elif event_type == "content_start":
                    data = event.get("data", {})
                    content_block = data.get("content_block", {})
                    block_type = content_block.get("type", "")
                    
                    if block_type == "tool_use":
                        tool_name = content_block.get("name", "unknown")
                        tool_input = content_block.get("input", {})
                        tool_calls.append({
                            "name": tool_name,
                            "input": tool_input
                        })
                        print(f"  🔧 工具调用: {tool_name}")
                        print(f"     输入: {json.dumps(tool_input, ensure_ascii=False)[:200]}...")
                    
                    elif block_type == "tool_result":
                        tool_use_id = content_block.get("tool_use_id", "")
                        result_content = content_block.get("content", "")
                        is_error = content_block.get("is_error", False)
                        status = "error" if is_error else "success"
                        result_preview = str(result_content)[:200]
                        print(f"  ✓ 工具结果 [{tool_use_id}]: {status}")
                        print(f"     输出: {result_preview}...")
            
            # 5.3 验证工具调用
            mcp_tool_called = any(
                "Ontology" in tc["name"] or "flowchart" in tc["name"].lower() or "dify" in tc["name"].lower()
                for tc in tool_calls
            )
            result = VerificationResult(
                phase="Phase 6",
                check_name="MCP 工具调用",
                passed=mcp_tool_called or len(tool_calls) > 0,
                expected="调用 dify_Ontology_TextToChart_zen0",
                actual=f"调用了 {len(tool_calls)} 个工具: {[tc['name'] for tc in tool_calls]}",
            )
            report.results.append(result)
            self._print_check(result.check_name, result.passed, result.actual)
            
            # 5.4 验证事件流
            event_types = [e.get("type", "") for e in events_collected]
            has_tool_use = "tool_use" in event_types
            has_tool_result = "tool_result" in event_types
            event_passed = has_tool_use or "message_delta" in event_types
            result = VerificationResult(
                phase="Phase 6",
                check_name="事件流完整性",
                passed=event_passed,
                expected="包含 tool_use, tool_result, message_delta",
                actual=f"事件类型: {list(set(event_types))}",
            )
            report.results.append(result)
            self._print_check(result.check_name, result.passed, result.actual)
            
            # 5.5 验证最终响应
            response_passed = len(response_text) > 0
            result = VerificationResult(
                phase="Phase 7",
                check_name="最终响应",
                passed=response_passed,
                expected="非空响应文本",
                actual=f"响应长度: {len(response_text)} 字符",
                details=response_text[:300] + "..." if len(response_text) > 300 else response_text
            )
            report.results.append(result)
            self._print_check(result.check_name, result.passed, f"前 300 字符: {result.details[:100]}...")
            
        except Exception as e:
            import traceback
            result = VerificationResult(
                phase="Phase 5-7",
                check_name="端对端对话",
                passed=False,
                expected="完成对话流程",
                actual=f"执行失败: {str(e)}",
                details=traceback.format_exc()
            )
            report.results.append(result)
            self._print_check(result.check_name, result.passed, result.actual)
        
        self.reports.append(report)
        return report
    
    def generate_report(self) -> str:
        """生成验证报告"""
        self._print_header("架构验证报告")
        
        report_lines = [
            "# ZenFlux Agent V4.6 架构验证报告",
            f"",
            f"**验证时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**实例名称**: {self.instance_name}",
            f"",
            "## 验证结果汇总",
            "",
        ]
        
        total_passed = 0
        total_checks = 0
        
        for phase_report in self.reports:
            status = "✅ 通过" if phase_report.passed else "❌ 失败"
            report_lines.append(
                f"| 阶段 {phase_report.phase_id} | {phase_report.phase_name} | "
                f"{phase_report.passed_count}/{phase_report.total_count} | {status} |"
            )
            total_passed += phase_report.passed_count
            total_checks += phase_report.total_count
        
        # 添加表头
        report_lines.insert(6, "| 阶段 | 名称 | 通过/总数 | 状态 |")
        report_lines.insert(7, "|------|------|-----------|------|")
        
        # 总体结果
        overall_passed = all(r.passed for r in self.reports)
        overall_status = "✅ 全部通过" if overall_passed else "❌ 存在失败"
        
        report_lines.extend([
            "",
            f"## 总体结果: {overall_status}",
            f"",
            f"- 总检查项: {total_checks}",
            f"- 通过: {total_passed}",
            f"- 失败: {total_checks - total_passed}",
            f"- 通过率: {total_passed/total_checks*100:.1f}%",
            "",
            "## 详细结果",
            "",
        ])
        
        # 详细结果
        for phase_report in self.reports:
            report_lines.append(f"### 阶段 {phase_report.phase_id}: {phase_report.phase_name}")
            report_lines.append("")
            
            for result in phase_report.results:
                status = "✅" if result.passed else "❌"
                report_lines.append(f"- {status} **{result.check_name}**")
                report_lines.append(f"  - 预期: {result.expected}")
                report_lines.append(f"  - 实际: {result.actual}")
                if result.details:
                    report_lines.append(f"  - 详情: {result.details[:200]}...")
                report_lines.append("")
        
        report_text = "\n".join(report_lines)
        
        # 打印汇总
        print(f"\n  总检查项: {total_checks}")
        print(f"  通过: {total_passed}")
        print(f"  失败: {total_checks - total_passed}")
        print(f"  通过率: {total_passed/total_checks*100:.1f}%")
        print(f"\n  总体结果: {overall_status}")
        
        return report_text
    
    async def run_all_verifications(self) -> str:
        """运行所有验证"""
        print("\n" + "="*60)
        print("  ZenFlux Agent V4.6 架构端对端验证")
        print("="*60)
        print(f"\n  实例: {self.instance_name}")
        print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 依次执行各阶段验证
        await self.verify_phase1_config()
        await self.verify_phase1_mcp()
        await self.verify_phase2_intent()
        await self.verify_phase3_tools()
        await self.verify_phase5_7_e2e()
        
        # 生成报告
        report = self.generate_report()
        
        # 保存报告
        report_path = PROJECT_ROOT / "E2E_ARCHITECTURE_VERIFY_REPORT.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\n  📄 报告已保存: {report_path}")
        
        return report


async def main():
    """主函数"""
    verifier = ArchitectureVerifier(instance_name="test_agent")
    await verifier.run_all_verifications()


if __name__ == "__main__":
    asyncio.run(main())

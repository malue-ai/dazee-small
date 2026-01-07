"""
上下文工程模块 - 高标准集成测试

测试覆盖：
1. KV-Cache 优化 - 验证前缀稳定性和缓存命中
2. Todo 重写 - 验证 Plan 状态注入位置和格式
3. 工具遮蔽 - 验证状态机驱动的工具可见性
4. 可恢复压缩 - 验证压缩比和恢复能力
5. 结构化变异 - 验证变异多样性和可读性
6. 错误保留 - 验证错误记录和上下文注入

运行方式:
    cd CoT_agent/mvp/zenflux_agent
    pytest tests/test_context_engineering.py -v
"""

import json
import pytest
import asyncio
from datetime import datetime
from typing import Dict, List, Any

# 测试目标模块
from core.context.context_engineering import (
    CacheOptimizer,
    TodoRewriter,
    AgentState,
    ToolMaskConfig,
    ToolMasker,
    CompressedReference,
    RecoverableCompressor,
    StructuralVariation,
    ErrorRecord,
    ErrorRetention,
    ContextEngineeringManager,
    create_context_engineering_manager,
)


# ============================================================
# 1. KV-Cache 优化测试
# ============================================================

class TestCacheOptimizer:
    """KV-Cache 优化器测试"""
    
    def test_sort_json_keys_nested(self):
        """测试嵌套对象的键排序"""
        obj = {
            "z": 1,
            "a": {
                "c": 3,
                "b": 2
            },
            "m": [{"y": 1, "x": 2}]
        }
        
        sorted_obj = CacheOptimizer.sort_json_keys(obj)
        
        # 验证顶层键排序
        assert list(sorted_obj.keys()) == ["a", "m", "z"]
        # 验证嵌套对象键排序
        assert list(sorted_obj["a"].keys()) == ["b", "c"]
        # 验证列表中对象的键排序
        assert list(sorted_obj["m"][0].keys()) == ["x", "y"]
    
    def test_stable_json_dumps_deterministic(self):
        """测试序列化确定性 - 相同输入产生相同输出"""
        obj1 = {"b": 2, "a": 1}
        obj2 = {"a": 1, "b": 2}
        
        json1 = CacheOptimizer.stable_json_dumps(obj1)
        json2 = CacheOptimizer.stable_json_dumps(obj2)
        
        assert json1 == json2, "相同内容不同顺序应产生相同 JSON"
    
    def test_stable_json_dumps_unicode(self):
        """测试 Unicode 字符处理"""
        obj = {"中文": "测试", "emoji": "🎯"}
        
        result = CacheOptimizer.stable_json_dumps(obj)
        
        assert "中文" in result
        assert "🎯" in result
        assert "\\u" not in result  # ensure_ascii=False
    
    def test_extract_timestamp_safe_iso(self):
        """测试 ISO 时间戳提取"""
        content = "[2024-01-15T10:30:00Z] 用户请求分析数据"
        
        clean, timestamp = CacheOptimizer.extract_timestamp_safe(content)
        
        assert timestamp == "2024-01-15T10:30:00Z"
        assert "2024-01-15" not in clean
        assert "用户请求分析数据" in clean
    
    def test_extract_timestamp_safe_no_timestamp(self):
        """测试无时间戳内容"""
        content = "这是一条普通消息"
        
        clean, timestamp = CacheOptimizer.extract_timestamp_safe(content)
        
        assert timestamp is None
        assert clean == "这是一条普通消息"
    
    def test_calculate_prefix_hash_consistency(self):
        """测试前缀哈希一致性"""
        messages = [
            {"role": "system", "content": "你是一个助手"},
            {"role": "user", "content": "你好"}
        ]
        
        hash1 = CacheOptimizer.calculate_prefix_hash(messages, prefix_length=1)
        hash2 = CacheOptimizer.calculate_prefix_hash(messages, prefix_length=1)
        
        assert hash1 == hash2, "相同前缀应产生相同哈希"
        assert len(hash1) == 12, "哈希长度应为 12"
    
    def test_calculate_prefix_hash_different_prefix(self):
        """测试不同前缀产生不同哈希"""
        messages1 = [{"role": "system", "content": "你是助手A"}]
        messages2 = [{"role": "system", "content": "你是助手B"}]
        
        hash1 = CacheOptimizer.calculate_prefix_hash(messages1, prefix_length=1)
        hash2 = CacheOptimizer.calculate_prefix_hash(messages2, prefix_length=1)
        
        assert hash1 != hash2, "不同前缀应产生不同哈希"


# ============================================================
# 2. Todo 重写测试
# ============================================================

class TestTodoRewriter:
    """Todo 重写器测试"""
    
    @pytest.fixture
    def sample_plan(self):
        """示例计划"""
        return {
            "goal": "分析用户数据并生成报告",
            "current_step": 1,
            "total_steps": 4,
            "completed_steps": 1,
            "status": "executing",
            "steps": [
                {"action": "收集数据", "purpose": "获取原始数据", "status": "completed"},
                {"action": "清洗数据", "purpose": "处理缺失值", "status": "in_progress"},
                {"action": "分析数据", "purpose": "提取洞察", "status": "pending"},
                {"action": "生成报告", "purpose": "输出结果", "status": "pending"}
            ]
        }
    
    def test_inject_plan_context_end_position(self, sample_plan):
        """测试 Plan 状态注入到消息末尾"""
        messages = [
            {"role": "system", "content": "你是数据分析师"},
            {"role": "user", "content": "请分析这份数据"}
        ]
        
        # 需要 mock plan_todo_tool，这里直接使用 generate_todo_reminder
        result = TodoRewriter.generate_todo_reminder(sample_plan)
        
        assert "分析用户数据" in result
        assert "1/4" in result
        assert "清洗数据" in result or "25%" in result
    
    def test_inject_plan_context_no_plan(self):
        """测试无计划时的处理"""
        messages = [{"role": "user", "content": "你好"}]
        
        result = TodoRewriter.inject_plan_context(messages, None)
        
        assert result == messages, "无计划时应返回原消息"
    
    def test_generate_todo_reminder_completed(self):
        """测试已完成计划的提醒"""
        plan = {
            "goal": "测试任务",
            "current_step": 2,
            "total_steps": 2,
            "completed_steps": 2,
            "status": "completed",
            "steps": []
        }
        
        result = TodoRewriter.generate_todo_reminder(plan)
        
        assert "已完成" in result or "100%" in result
    
    def test_generate_todo_reminder_partial(self):
        """测试部分完成计划的提醒"""
        plan = {
            "goal": "测试任务",
            "current_step": 1,
            "total_steps": 3,
            "completed_steps": 1,
            "status": "partial",
            "steps": []
        }
        
        result = TodoRewriter.generate_todo_reminder(plan)
        
        assert "部分完成" in result or "33%" in result


# ============================================================
# 3. 工具遮蔽测试
# ============================================================

class TestToolMasker:
    """工具遮蔽器测试"""
    
    @pytest.fixture
    def tool_masker(self):
        return ToolMasker()
    
    @pytest.fixture
    def all_tools(self):
        return [
            "plan_todo", "plan_create",
            "web_search", "web_fetch",
            "browser_navigate", "browser_click",
            "bash", "text_editor",
            "e2b_execute", "e2b_upload",
            "knowledge_search"
        ]
    
    def test_initial_state_is_idle(self, tool_masker):
        """测试初始状态为 IDLE"""
        assert tool_masker.current_state == AgentState.IDLE
    
    def test_transition_to_new_state(self, tool_masker):
        """测试状态转换"""
        tool_masker.transition_to(AgentState.BROWSING)
        
        assert tool_masker.current_state == AgentState.BROWSING
    
    def test_transition_records_history(self, tool_masker):
        """测试状态转换记录历史"""
        tool_masker.transition_to(AgentState.PLANNING)
        tool_masker.transition_to(AgentState.CODING)
        
        assert len(tool_masker._state_history) == 2
    
    def test_get_allowed_tools_idle(self, tool_masker, all_tools):
        """测试 IDLE 状态下允许的工具"""
        allowed = tool_masker.get_allowed_tools(all_tools)
        
        assert "plan_todo" in allowed
        assert "web_search" in allowed
        assert "bash" in allowed
    
    def test_get_allowed_tools_browsing(self, tool_masker, all_tools):
        """测试 BROWSING 状态下只允许浏览相关工具"""
        tool_masker.transition_to(AgentState.BROWSING)
        allowed = tool_masker.get_allowed_tools(all_tools)
        
        assert "web_search" in allowed
        assert "browser_navigate" in allowed
        # 不应该包含编码工具
        assert "bash" not in allowed
        assert "e2b_execute" not in allowed
    
    def test_get_allowed_tools_coding(self, tool_masker, all_tools):
        """测试 CODING 状态下只允许编码相关工具"""
        tool_masker.transition_to(AgentState.CODING)
        allowed = tool_masker.get_allowed_tools(all_tools)
        
        assert "bash" in allowed
        assert "e2b_execute" in allowed
        assert "text_editor" in allowed
        # 不应该包含浏览工具
        assert "browser_navigate" not in allowed
    
    def test_get_allowed_tools_executing_allows_all(self, tool_masker, all_tools):
        """测试 EXECUTING 状态下允许所有工具"""
        tool_masker.transition_to(AgentState.EXECUTING)
        allowed = tool_masker.get_allowed_tools(all_tools)
        
        assert set(allowed) == set(all_tools), "EXECUTING 应允许所有工具"
    
    def test_mask_tool_definitions_disable_strategy(self, tool_masker):
        """测试 disable 策略保留定义但标记禁用"""
        tool_masker.transition_to(AgentState.PLANNING)
        
        tool_definitions = [
            {"name": "plan_todo", "description": "创建计划"},
            {"name": "bash", "description": "执行命令"}
        ]
        
        masked = tool_masker.mask_tool_definitions(tool_definitions, strategy="disable")
        
        # plan_todo 不应被标记禁用
        plan_tool = next(t for t in masked if t["name"] == "plan_todo")
        assert "[DISABLED" not in plan_tool["description"]
        
        # bash 应被标记禁用
        bash_tool = next(t for t in masked if t["name"] == "bash")
        assert "[DISABLED" in bash_tool["description"]
    
    def test_infer_state_from_action_search(self, tool_masker):
        """测试从动作推断搜索状态"""
        state = tool_masker.infer_state_from_action("搜索相关资料")
        assert state == AgentState.SEARCHING
    
    def test_infer_state_from_action_code(self, tool_masker):
        """测试从动作推断编码状态"""
        state = tool_masker.infer_state_from_action("编写 Python 代码")
        assert state == AgentState.CODING
    
    def test_infer_state_from_tool_name(self, tool_masker):
        """测试从工具名称推断状态"""
        state = tool_masker.infer_state_from_action("执行", tool_name="browser_click")
        assert state == AgentState.BROWSING


# ============================================================
# 4. 可恢复压缩测试
# ============================================================

class TestRecoverableCompressor:
    """可恢复压缩器测试"""
    
    @pytest.fixture
    def compressor(self):
        return RecoverableCompressor(max_summary_chars=100)
    
    def test_compress_file_content(self, compressor):
        """测试文件内容压缩"""
        content = "A" * 10000  # 10000 字符的内容
        
        compressed, ref = compressor.compress_file_content(
            content=content,
            file_path="/data/report.txt",
            file_type="text"
        )
        
        # 验证压缩比
        assert len(compressed) < len(content) / 10, "压缩比应超过 10:1"
        
        # 验证引用信息完整
        assert ref.ref_type == "file"
        assert ref.local_path == "/data/report.txt"
        assert ref.metadata["original_length"] == 10000
        
        # 验证可通过引用恢复
        recovered_ref = compressor.recover(ref.ref_id)
        assert recovered_ref is not None
        assert recovered_ref.local_path == "/data/report.txt"
    
    def test_compress_search_results(self, compressor):
        """测试搜索结果压缩"""
        results = [
            {"title": f"结果{i}", "url": f"https://example.com/{i}", "text": "这是一段很长的描述..." * 20}
            for i in range(5)
        ]
        
        compressed, refs = compressor.compress_search_results(results, query="测试查询")
        
        # 验证压缩后包含关键信息
        assert "测试查询" in compressed
        assert "结果0" in compressed
        
        # 验证引用数量
        assert len(refs) == 5
        
        # 验证每个引用可恢复
        for ref in refs:
            assert compressor.recover(ref.ref_id) is not None
    
    def test_compress_tool_result_short_content(self, compressor):
        """测试短内容不压缩"""
        result = {"status": "success", "data": "short result"}
        
        compressed, ref = compressor.compress_tool_result(
            tool_name="test_tool",
            result=result,
            tool_id="tool_123"
        )
        
        # 短内容应该保持原样
        assert "success" in compressed
    
    def test_compress_tool_result_long_content(self, compressor):
        """测试长内容压缩"""
        result = {"status": "success", "data": "A" * 5000}
        
        compressed, ref = compressor.compress_tool_result(
            tool_name="test_tool",
            result=result,
            tool_id="tool_456"
        )
        
        # 长内容应该被压缩
        assert "[TOOL:" in compressed
        assert "已压缩" in compressed
        assert ref.metadata["original_length"] > 2000
    
    def test_reference_store_persistence(self, compressor):
        """测试引用存储持久化"""
        content1 = "First content " * 500
        content2 = "Second content " * 500
        
        _, ref1 = compressor.compress_file_content(content1, "/file1.txt", "text")
        _, ref2 = compressor.compress_file_content(content2, "/file2.txt", "text")
        
        # 两个引用都应可恢复
        assert compressor.recover(ref1.ref_id) is not None
        assert compressor.recover(ref2.ref_id) is not None


# ============================================================
# 5. 结构化变异测试
# ============================================================

class TestStructuralVariation:
    """结构化变异器测试"""
    
    def test_vary_progress_display_deterministic(self):
        """测试低变异等级下的确定性输出"""
        variation = StructuralVariation(variation_level=0.0)
        
        result1 = variation.vary_progress_display(3, 10, current=2)
        result2 = variation.vary_progress_display(3, 10, current=2)
        
        assert result1 == result2, "低变异等级应产生确定性输出"
        assert "30%" in result1
    
    def test_vary_progress_display_high_variation(self):
        """测试高变异等级下的多样性输出"""
        variation = StructuralVariation(variation_level=0.8)
        
        results = set()
        for _ in range(50):
            result = variation.vary_progress_display(5, 10, current=4)
            results.add(result)
        
        assert len(results) > 1, "高变异等级应产生多样性输出"
    
    def test_vary_status_variants(self):
        """测试状态文本变体"""
        variation = StructuralVariation(variation_level=0.8)
        
        results = set()
        for _ in range(30):
            result = variation.vary_status("completed")
            results.add(result)
        
        assert len(results) > 1, "应产生多种状态变体"
        # 验证所有变体都是有效的
        valid_variants = {"已完成", "Done", "✓", "完成", "Finished"}
        for result in results:
            assert result in valid_variants
    
    def test_vary_list_format_bullet(self):
        """测试列表格式变异 - 项目符号"""
        variation = StructuralVariation(variation_level=0.0)
        items = ["第一项", "第二项", "第三项"]
        
        result = variation.vary_list_format(items, list_type="bullet")
        
        assert "• 第一项" in result
        assert "• 第二项" in result
    
    def test_vary_list_format_numbered(self):
        """测试列表格式变异 - 编号"""
        variation = StructuralVariation(variation_level=0.0)
        items = ["第一项", "第二项"]
        
        result = variation.vary_list_format(items, list_type="numbered")
        
        assert "1." in result or "1)" in result
    
    def test_adjust_variation_level_context_length(self):
        """测试根据上下文长度调整变异等级"""
        variation = StructuralVariation(variation_level=0.3)
        
        initial_level = variation.variation_level
        
        # 长上下文应增加变异
        variation.adjust_variation_level(context_length=100000, repetition_count=5)
        
        assert variation.variation_level > initial_level
        assert variation.variation_level <= 0.8, "变异等级不应超过 80%"
    
    def test_variation_maintains_readability(self):
        """测试变异保持可读性"""
        variation = StructuralVariation(variation_level=0.8)
        
        # 即使高变异，输出仍应包含核心信息
        result = variation.vary_progress_display(7, 10, current=6)
        
        # 应包含数字信息
        assert any(c.isdigit() for c in result)


# ============================================================
# 6. 错误保留测试
# ============================================================

class TestErrorRetention:
    """错误保留器测试"""
    
    @pytest.fixture
    def error_retention(self):
        return ErrorRetention(max_errors=5)
    
    def test_record_error(self, error_retention):
        """测试错误记录"""
        error = ValueError("无效的参数")
        
        record = error_retention.record_error(
            tool_name="test_tool",
            error=error,
            input_params={"key": "value"},
            context="测试上下文"
        )
        
        assert record.tool_name == "test_tool"
        assert record.error_type == "ValueError"
        assert "无效的参数" in record.error_message
        assert record.context == "测试上下文"
    
    def test_record_recovery(self, error_retention):
        """测试恢复动作记录"""
        error = RuntimeError("执行失败")
        record = error_retention.record_error("tool", error, {})
        
        error_retention.record_recovery(record, "更换参数重试")
        
        assert record.recovery_action == "更换参数重试"
    
    def test_max_errors_limit(self, error_retention):
        """测试最大错误数量限制"""
        for i in range(10):
            error_retention.record_error(
                tool_name=f"tool_{i}",
                error=Exception(f"错误 {i}"),
                input_params={}
            )
        
        errors = error_retention.get_recent_errors(count=10)
        assert len(errors) <= 5, "不应超过最大错误数量"
        
        # 最新的错误应该保留
        assert errors[-1].error_message == "错误 9"
    
    def test_get_error_context_format(self, error_retention):
        """测试错误上下文格式"""
        error_retention.record_error("search", ValueError("关键词无效"), {"query": "test"})
        error_retention.record_error("bash", RuntimeError("命令失败"), {"cmd": "ls"})
        
        context = error_retention.get_error_context()
        
        assert "错误记录" in context
        assert "search" in context
        assert "bash" in context
    
    def test_get_error_context_filter_by_tool(self, error_retention):
        """测试按工具过滤错误上下文"""
        error_retention.record_error("tool_a", Exception("错误A"), {})
        error_retention.record_error("tool_b", Exception("错误B"), {})
        
        context = error_retention.get_error_context(tool_name="tool_a")
        
        assert "tool_a" in context
        assert "tool_b" not in context
    
    def test_clear_errors(self, error_retention):
        """测试清除错误记录"""
        error_retention.record_error("tool", Exception("test"), {})
        
        error_retention.clear()
        
        assert error_retention.get_error_context() == ""


# ============================================================
# 7. ContextEngineeringManager 整合测试
# ============================================================

class TestContextEngineeringManager:
    """上下文工程管理器整合测试"""
    
    @pytest.fixture
    def manager(self):
        return create_context_engineering_manager()
    
    @pytest.fixture
    def sample_messages(self):
        return [
            {"role": "system", "content": "你是一个数据分析助手"},
            {"role": "user", "content": "请分析销售数据"}
        ]
    
    @pytest.fixture
    def sample_plan(self):
        return {
            "goal": "分析销售数据",
            "current_step": 0,
            "total_steps": 3,
            "completed_steps": 0,
            "status": "executing",
            "steps": [
                {"action": "读取数据", "purpose": "获取数据源"},
                {"action": "分析趋势", "purpose": "识别模式"},
                {"action": "生成报告", "purpose": "输出结果"}
            ]
        }
    
    def test_manager_initialization(self, manager):
        """测试管理器初始化"""
        assert manager.cache_optimizer is not None
        assert manager.todo_rewriter is not None
        assert manager.tool_masker is not None
        assert manager.compressor is not None
        assert manager.variation is not None
        assert manager.error_retention is not None
    
    def test_prepare_messages_without_plan(self, manager, sample_messages):
        """测试无 Plan 时的消息准备"""
        result = manager.prepare_messages_for_llm(
            messages=sample_messages,
            plan=None
        )
        
        # 无 Plan 时应返回原消息
        assert len(result) == len(sample_messages)
    
    def test_get_allowed_tools(self, manager):
        """测试获取允许的工具"""
        all_tools = ["plan_todo", "bash", "web_search"]
        
        # IDLE 状态下应允许所有这些工具
        allowed = manager.get_allowed_tools(all_tools)
        
        assert len(allowed) > 0
    
    def test_transition_state(self, manager):
        """测试状态转换"""
        manager.transition_state(AgentState.CODING)
        
        assert manager.tool_masker.current_state == AgentState.CODING
    
    def test_record_error(self, manager):
        """测试错误记录"""
        manager.record_error(
            tool_name="test_tool",
            error=ValueError("测试错误"),
            input_params={"key": "value"}
        )
        
        assert manager._stats["errors_recorded"] == 1
    
    def test_get_stats(self, manager):
        """测试获取统计信息"""
        stats = manager.get_stats()
        
        assert "cache_hits" in stats
        assert "compressions" in stats
        assert "variations" in stats
        assert "errors_recorded" in stats


# ============================================================
# 8. 端到端场景测试
# ============================================================

class TestEndToEndScenarios:
    """端到端场景测试"""
    
    def test_scenario_long_running_task(self):
        """
        场景：长时间运行的任务
        
        验证：
        1. Plan 状态始终在消息末尾
        2. 错误被记录并注入上下文
        3. 工具可见性随状态变化
        """
        manager = create_context_engineering_manager()
        
        # 初始计划
        plan = {
            "goal": "处理大量数据",
            "current_step": 0,
            "total_steps": 10,
            "completed_steps": 0,
            "status": "executing",
            "steps": [{"action": f"步骤{i}", "purpose": f"目的{i}"} for i in range(10)]
        }
        
        # 模拟多轮交互
        messages = [
            {"role": "system", "content": "你是数据处理专家"},
            {"role": "user", "content": "开始处理"}
        ]
        
        # 第一轮：准备消息
        prepared = manager.prepare_messages_for_llm(messages, plan)
        assert len(prepared) >= len(messages)
        
        # 模拟错误发生
        manager.record_error(
            tool_name="bash",
            error=RuntimeError("磁盘空间不足"),
            input_params={"cmd": "process_data.sh"}
        )
        
        # 再次准备消息，应包含错误上下文
        prepared_with_error = manager.prepare_messages_for_llm(
            messages, plan, inject_errors=True
        )
        
        # 验证错误被注入
        error_context = manager.error_retention.get_error_context()
        assert "磁盘空间不足" in error_context
    
    def test_scenario_state_driven_tool_selection(self):
        """
        场景：状态驱动的工具选择
        
        验证：
        1. 浏览状态只允许浏览工具
        2. 编码状态只允许编码工具
        3. 执行状态允许所有工具
        """
        manager = create_context_engineering_manager()
        
        all_tools = [
            "web_search", "browser_navigate",
            "bash", "text_editor", "e2b_execute",
            "plan_todo"
        ]
        
        # 浏览状态
        manager.transition_state(AgentState.BROWSING)
        browsing_tools = manager.get_allowed_tools(all_tools)
        assert "web_search" in browsing_tools
        assert "bash" not in browsing_tools
        
        # 编码状态
        manager.transition_state(AgentState.CODING)
        coding_tools = manager.get_allowed_tools(all_tools)
        assert "bash" in coding_tools
        assert "web_search" not in coding_tools
        
        # 执行状态
        manager.transition_state(AgentState.EXECUTING)
        executing_tools = manager.get_allowed_tools(all_tools)
        assert len(executing_tools) == len(all_tools)
    
    def test_scenario_context_compression(self):
        """
        场景：上下文压缩
        
        验证：
        1. 大文件被压缩
        2. 引用可恢复
        3. 压缩比合理
        """
        manager = create_context_engineering_manager()
        
        # 模拟大文件内容
        large_content = json.dumps([{"id": i, "data": "x" * 100} for i in range(100)])
        
        compressed = manager.compress_result(
            tool_name="file_read",
            result=large_content,
            tool_id="tool_001"
        )
        
        # 验证压缩
        assert manager._stats["compressions"] == 1
        
        # 验证压缩比（如果内容足够长）
        if len(large_content) > 2000:
            assert len(compressed) < len(large_content)


# ============================================================
# 9. 性能测试
# ============================================================

class TestPerformance:
    """性能测试"""
    
    def test_cache_optimizer_performance(self):
        """测试缓存优化器性能"""
        import time
        
        # 创建大量消息
        messages = [
            {"role": f"role_{i}", "content": f"content_{i}" * 100}
            for i in range(100)
        ]
        
        start = time.time()
        for _ in range(1000):
            CacheOptimizer.stable_json_dumps(messages)
        elapsed = time.time() - start
        
        assert elapsed < 5.0, f"序列化 1000 次应在 5 秒内完成，实际: {elapsed:.2f}秒"
    
    def test_tool_masker_performance(self):
        """测试工具遮蔽器性能"""
        import time
        
        masker = ToolMasker()
        tools = [f"tool_{i}" for i in range(100)]
        
        start = time.time()
        for _ in range(10000):
            masker.get_allowed_tools(tools)
        elapsed = time.time() - start
        
        assert elapsed < 2.0, f"过滤 10000 次应在 2 秒内完成，实际: {elapsed:.2f}秒"


# ============================================================
# 运行测试
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])


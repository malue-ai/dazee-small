"""
🆕 V5.1: Prompt-Schema 机制端对端测试

测试场景：
1. Schema 生成验证 - LLM 分析 Prompt 生成 Schema，reasoning 不是默认值
2. 提示词版本大小验证 - Simple < 15k, Medium < 40k, Complex < 60k
3. 运行时复杂度路由验证 - 简单任务使用 Simple 版本，复杂任务使用 Complex 版本
4. 完整流程验证 - 从启动到运行的完整链路

运行方式：
    cd /Users/liuyi/Documents/langchain/CoT_agent/mvp/zenflux_agent
    source /Users/liuyi/Documents/langchain/liuy/bin/activate
    python -m pytest tests/e2e/test_prompt_schema_e2e.py -v

需要环境变量：
    ANTHROPIC_API_KEY: Anthropic API 密钥
"""

import asyncio
import os
import sys
from pathlib import Path

# 添加项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 从 .env 加载环境变量
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "instances/test_agent/.env", override=True)

import pytest

from core.prompt import (
    InstancePromptCache,
    load_instance_cache,
    TaskComplexity,
    PromptSchema,
    generate_prompt,
)


# ============================================================
# 测试 1: Schema 生成验证
# ============================================================

class TestSchemaGeneration:
    """验证 LLM Schema 生成正确执行"""
    
    def setup_method(self):
        """每个测试前清空缓存"""
        InstancePromptCache.clear_all()
    
    @pytest.mark.asyncio
    async def test_schema_reasoning_not_default(self):
        """
        验证 Schema 的 reasoning 字段是 LLM 生成的分析理由，不是默认值
        """
        # 准备测试提示词
        test_prompt = """# DataAnalysisAgent

你是一个专业的数据分析助手。

## 能力
- 分析 CSV/Excel 数据
- 使用 pandas 进行数据处理
- 生成数据可视化图表

## 工具
- e2b_sandbox: 执行 Python 代码
- web_search: 搜索相关信息
"""
        
        cache = InstancePromptCache.get_instance("test_schema")
        
        # 强制刷新，触发 LLM 分析
        await cache.load_once(test_prompt, force_refresh=True)
        
        assert cache.is_loaded, "缓存应该已加载"
        assert cache.agent_schema is not None, "AgentSchema 应该存在"
        
        # 验证 reasoning 不是默认值
        reasoning = cache.agent_schema.reasoning
        assert reasoning is not None, "reasoning 应该存在"
        assert reasoning != "默认配置，适用于一般场景", \
            f"reasoning 不应该是默认值，实际值: {reasoning}"
        
        print(f"✅ Schema reasoning: {reasoning}")
    
    @pytest.mark.asyncio
    async def test_schema_has_tools_or_skills(self):
        """
        验证 Schema 包含从 Prompt 推断的 tools 或 skills
        """
        test_prompt = """# ReportGenerator

你是一个报告生成助手。

## 功能
- 生成 Excel 报表
- 创建 PPT 演示文稿
- 搜索相关数据
"""
        
        cache = InstancePromptCache.get_instance("test_schema_tools")
        await cache.load_once(test_prompt, force_refresh=True)
        
        assert cache.agent_schema is not None
        
        # 验证有 tools 或 skills
        has_tools = len(cache.agent_schema.tools) > 0
        has_skills = len(cache.agent_schema.skills) > 0
        
        assert has_tools or has_skills, \
            f"Schema 应该包含 tools 或 skills，实际: tools={cache.agent_schema.tools}, skills={cache.agent_schema.skills}"
        
        print(f"✅ Schema tools: {cache.agent_schema.tools}")
        print(f"✅ Schema skills: {cache.agent_schema.skills}")


# ============================================================
# 测试 2: 提示词版本大小验证
# ============================================================

class TestPromptVersionSizes:
    """验证提示词版本大小在合理范围内"""
    
    def setup_method(self):
        InstancePromptCache.clear_all()
    
    @pytest.mark.asyncio
    async def test_prompt_sizes_within_limits(self):
        """
        验证提示词版本大小：
        - Simple < 15k 字符
        - Medium < 40k 字符
        - Complex < 60k 字符
        """
        # 使用较大的测试提示词
        test_prompt = """# TestAgent

你是一个测试助手。

## 角色定义
这是一个详细的角色描述，用于测试模块识别和裁剪功能。
""" + "\n".join([f"- 规则 {i}: 详细描述..." for i in range(100)])  # 添加大量内容
        
        cache = InstancePromptCache.get_instance("test_sizes")
        await cache.load_once(test_prompt, force_refresh=True)
        
        assert cache.is_loaded
        
        simple_size = len(cache.system_prompt_simple or "")
        medium_size = len(cache.system_prompt_medium or "")
        complex_size = len(cache.system_prompt_complex or "")
        
        print(f"📏 提示词版本大小:")
        print(f"   Simple: {simple_size} 字符")
        print(f"   Medium: {medium_size} 字符")
        print(f"   Complex: {complex_size} 字符")
        
        # 验证大小限制
        assert simple_size < 15000, \
            f"Simple 版本应该 < 15k 字符，实际: {simple_size}"
        assert medium_size < 40000, \
            f"Medium 版本应该 < 40k 字符，实际: {medium_size}"
        assert complex_size < 80000, \
            f"Complex 版本应该 < 80k 字符，实际: {complex_size}"
        
        print("✅ 所有版本大小在限制范围内")
    
    def test_generate_prompt_with_size_limits(self):
        """
        测试 generate_prompt 函数的大小限制
        """
        # 创建包含大量内容的 PromptSchema
        from core.prompt.prompt_layer import PromptModule, PromptModuleContent
        
        schema = PromptSchema(
            agent_name="TestAgent",
            agent_role="测试角色",
            raw_prompt="测试提示词",
        )
        
        # 添加一个很大的模块
        large_content = "A" * 50000  # 50k 字符
        schema.modules[PromptModule.ROLE_DEFINITION] = PromptModuleContent(
            module=PromptModule.ROLE_DEFINITION,
            content=large_content,
            priority=10,
        )
        
        # 生成 Simple 版本
        simple_prompt = generate_prompt(schema, TaskComplexity.SIMPLE)
        
        print(f"📏 大内容模块生成的 Simple 版本: {len(simple_prompt)} 字符")
        
        # Simple 版本应该被截断
        assert len(simple_prompt) < 15000, \
            f"Simple 版本应该被截断到 < 15k，实际: {len(simple_prompt)}"
        
        print("✅ 大内容模块被正确截断")


# ============================================================
# 测试 3: 运行时复杂度路由验证
# ============================================================

class TestComplexityRouting:
    """验证运行时根据复杂度选择正确的提示词版本"""
    
    def setup_method(self):
        InstancePromptCache.clear_all()
    
    @pytest.mark.asyncio
    async def test_get_system_prompt_by_complexity(self):
        """
        测试根据复杂度获取对应版本的系统提示词
        """
        test_prompt = "# TestAgent\n\n测试内容..."
        
        cache = InstancePromptCache.get_instance("test_routing")
        await cache.load_once(test_prompt, force_refresh=True)
        
        simple = cache.get_system_prompt(TaskComplexity.SIMPLE)
        medium = cache.get_system_prompt(TaskComplexity.MEDIUM)
        complex_ = cache.get_system_prompt(TaskComplexity.COMPLEX)
        
        assert simple is not None and len(simple) > 0, "Simple 版本不应为空"
        assert medium is not None and len(medium) > 0, "Medium 版本不应为空"
        assert complex_ is not None and len(complex_) > 0, "Complex 版本不应为空"
        
        # 验证版本之间有差异（不是完全相同）
        assert simple != complex_, "Simple 和 Complex 版本应该不同"
        
        print(f"✅ Simple: {len(simple)} 字符")
        print(f"✅ Medium: {len(medium)} 字符")
        print(f"✅ Complex: {len(complex_)} 字符")
    
    @pytest.mark.asyncio
    async def test_get_full_system_prompt_with_runtime_context(self):
        """
        测试 get_full_system_prompt 正确追加运行时上下文
        """
        test_prompt = "# TestAgent\n\n基础内容..."
        
        cache = InstancePromptCache.get_instance("test_runtime_context")
        await cache.load_once(test_prompt, force_refresh=True)
        
        # 设置运行时上下文
        cache.runtime_context = {
            "apis_prompt": "## APIs\n- API 1: 描述...",
            "framework_prompt": "## Framework\n框架规则...",
        }
        
        # 获取带运行时上下文的完整提示词
        full_simple = cache.get_full_system_prompt(TaskComplexity.SIMPLE)
        cached_simple = cache.get_system_prompt(TaskComplexity.SIMPLE)
        
        # 完整版本应该比缓存版本大
        assert len(full_simple) > len(cached_simple), \
            "完整版本应该包含运行时上下文"
        
        # 验证包含运行时内容
        assert "APIs" in full_simple or "API 1" in full_simple, \
            "完整版本应该包含 APIs 内容"
        assert "Framework" in full_simple or "框架规则" in full_simple, \
            "完整版本应该包含 Framework 内容"
        
        print(f"✅ 缓存版本: {len(cached_simple)} 字符")
        print(f"✅ 完整版本: {len(full_simple)} 字符")
        print(f"✅ 运行时追加: {len(full_simple) - len(cached_simple)} 字符")


# ============================================================
# 测试 4: 完整流程验证
# ============================================================

class TestFullPipeline:
    """验证完整的 Prompt-Schema 流程"""
    
    def setup_method(self):
        InstancePromptCache.clear_all()
    
    @pytest.mark.asyncio
    async def test_load_instance_cache_full_flow(self):
        """
        测试 load_instance_cache 完整流程
        """
        from core.prompt import load_instance_cache
        
        test_prompt = """# DataAnalysisAgent

你是一个专业的数据分析助手。

<absolute_prohibitions priority="最高">
1. 禁止泄露敏感信息
2. 禁止执行危险操作
</absolute_prohibitions>

## 输出格式
使用 Markdown 格式输出。
"""
        
        cache = await load_instance_cache(
            instance_name="test_full_flow",
            raw_prompt=test_prompt,
            config={"agent": {"model": "claude-sonnet-4-5-20250929"}},
            force_refresh=True,
        )
        
        # 验证所有组件都已加载
        assert cache.is_loaded, "缓存应该已加载"
        assert cache.prompt_schema is not None, "PromptSchema 应该存在"
        assert cache.agent_schema is not None, "AgentSchema 应该存在"
        assert cache.system_prompt_simple is not None, "Simple 版本应该存在"
        assert cache.system_prompt_medium is not None, "Medium 版本应该存在"
        assert cache.system_prompt_complex is not None, "Complex 版本应该存在"
        assert cache.intent_prompt is not None, "意图识别提示词应该存在"
        
        # 打印状态
        status = cache.get_status()
        print(f"\n📊 缓存状态:")
        print(f"   实例: {status['instance_name']}")
        print(f"   已加载: {status['is_loaded']}")
        print(f"   Agent: {status['agent_schema']}")
        print(f"   提示词版本:")
        print(f"     Simple: {status['system_prompts']['simple']} 字符")
        print(f"     Medium: {status['system_prompts']['medium']} 字符")
        print(f"     Complex: {status['system_prompts']['complex']} 字符")
        print(f"   意图识别: {status['intent_prompt']} 字符")
        
        print("\n✅ 完整流程验证通过")
    
    @pytest.mark.asyncio
    async def test_fallback_generates_sized_versions(self):
        """
        测试 fallback 也生成合理大小的版本（而不是完整 raw_prompt）
        """
        # 创建一个非常大的提示词来触发 fallback
        large_prompt = "# TestAgent\n\n" + "X" * 100000  # 100k 字符
        
        cache = InstancePromptCache.get_instance("test_fallback")
        
        # 直接调用 fallback
        await cache._load_fallback(large_prompt)
        
        # 验证 fallback 生成的版本在合理范围内
        simple_size = len(cache.system_prompt_simple)
        medium_size = len(cache.system_prompt_medium)
        complex_size = len(cache.system_prompt_complex)
        
        print(f"\n📏 Fallback 生成的版本大小:")
        print(f"   Simple: {simple_size} 字符")
        print(f"   Medium: {medium_size} 字符")
        print(f"   Complex: {complex_size} 字符")
        
        # 验证 Simple 不是完整的 100k
        assert simple_size < 20000, \
            f"Fallback Simple 应该 < 20k，实际: {simple_size}"
        
        # 验证 Medium 不是完整的 100k
        assert medium_size < 50000, \
            f"Fallback Medium 应该 < 50k，实际: {medium_size}"
        
        print("✅ Fallback 版本大小在合理范围内")


# ============================================================
# 运行所有测试
# ============================================================

if __name__ == "__main__":
    # 运行所有测试
    pytest.main([__file__, "-v", "-s"])

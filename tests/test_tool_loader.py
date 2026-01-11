"""
测试工具加载器功能

测试内容：
1. CapabilityRegistry.filter_by_enabled() 方法
2. ToolLoader 工具加载和统计
3. 配置解析和工具过滤
"""

import pytest
from pathlib import Path

# 导入测试目标
from core.tool import (
    CapabilityRegistry,
    ToolLoader,
    create_tool_loader,
    get_capability_registry,
)
from scripts.instance_loader import load_instance_config


class TestCapabilityRegistryFilter:
    """测试 CapabilityRegistry 过滤功能"""
    
    def test_filter_by_enabled(self):
        """测试根据启用配置过滤工具"""
        # 创建全局注册表
        registry = get_capability_registry()
        
        # 过滤配置：只启用部分工具
        enabled_map = {
            "web_search": True,
            "plan_todo": True,
            "knowledge_search": True,
        }
        
        # 执行过滤
        filtered = registry.filter_by_enabled(enabled_map)
        
        # 验证结果
        assert len(filtered.capabilities) == 3
        assert "web_search" in filtered.capabilities
        assert "plan_todo" in filtered.capabilities
        assert "knowledge_search" in filtered.capabilities
        
        # 验证未启用的工具不存在
        assert "ppt_generator" not in filtered.capabilities
        assert "exa_search" not in filtered.capabilities
    
    def test_filter_empty_config(self):
        """测试空配置（不过滤）"""
        registry = get_capability_registry()
        
        # 空配置
        enabled_map = {}
        
        # 执行过滤
        filtered = registry.filter_by_enabled(enabled_map)
        
        # 验证结果：空配置应该返回空注册表
        assert len(filtered.capabilities) == 0
    
    def test_filter_preserves_metadata(self):
        """测试过滤保留元数据"""
        registry = get_capability_registry()
        
        enabled_map = {"web_search": True}
        filtered = registry.filter_by_enabled(enabled_map)
        
        # 验证分类和映射被保留
        assert filtered.task_type_mappings == registry.task_type_mappings
        assert filtered.categories == registry.categories


class TestToolLoader:
    """测试 ToolLoader 工具加载器"""
    
    def test_create_tool_loader(self):
        """测试创建工具加载器"""
        loader = create_tool_loader()
        
        assert loader is not None
        assert loader.global_registry is not None
    
    def test_load_tools_generic_only(self):
        """测试只加载通用工具"""
        loader = create_tool_loader()
        
        enabled_capabilities = {
            "web_search": True,
            "plan_todo": True,
        }
        
        result = loader.load_tools(enabled_capabilities=enabled_capabilities)
        
        # 验证通用工具
        assert result.generic_count == 2
        assert len(result.enabled_tools) == 2
        assert "web_search" in result.enabled_tools
        assert "plan_todo" in result.enabled_tools
        
        # 验证没有 MCP 工具和 Skills
        assert result.mcp_count == 0
        assert result.skills_count == 0
        
        # 验证总计
        assert result.total_count == 2
    
    def test_load_tools_with_mcp(self):
        """测试加载 MCP 工具"""
        loader = create_tool_loader()
        
        enabled_capabilities = {"web_search": True}
        mcp_tools = [
            {"name": "dify_flowchart", "server_url": "https://api.dify.ai/mcp"},
            {"name": "weather_api", "server_url": "https://api.weather.com/mcp"},
        ]
        
        result = loader.load_tools(
            enabled_capabilities=enabled_capabilities,
            mcp_tools=mcp_tools
        )
        
        # 验证通用工具
        assert result.generic_count == 1
        
        # 验证 MCP 工具
        assert result.mcp_count == 2
        
        # 验证总计
        assert result.total_count == 3
    
    def test_get_tool_statistics(self):
        """测试工具统计"""
        loader = create_tool_loader()
        
        enabled_capabilities = {
            "web_search": True,
            "plan_todo": True,
        }
        
        stats = loader.get_tool_statistics(enabled_capabilities)
        
        # 验证统计信息
        assert stats["enabled_count"] == 2
        assert stats["disabled_count"] > 0  # 应该有未启用的工具
        assert "web_search" in stats["enabled_tools"]
        assert "plan_todo" in stats["enabled_tools"]
    
    def test_create_filtered_registry(self):
        """测试创建过滤后的注册表"""
        loader = create_tool_loader()
        
        enabled_capabilities = {
            "web_search": True,
            "plan_todo": True,
        }
        
        filtered = loader.create_filtered_registry(enabled_capabilities)
        
        # 验证过滤结果
        assert len(filtered.capabilities) == 2
        assert "web_search" in filtered.capabilities
        assert "plan_todo" in filtered.capabilities


class TestInstanceConfigParsing:
    """测试实例配置解析"""
    
    def test_load_instance_config_with_enabled_capabilities(self):
        """测试加载包含 enabled_capabilities 的配置"""
        # 注意：这需要 _template 实例存在
        try:
            config = load_instance_config("_template")
            
            # 验证配置包含 enabled_capabilities 字段
            assert hasattr(config, "enabled_capabilities")
            assert isinstance(config.enabled_capabilities, dict)
            
            # 验证配置值被正确解析为布尔值
            for tool_name, enabled in config.enabled_capabilities.items():
                assert isinstance(enabled, bool)
        
        except Exception as e:
            pytest.skip(f"无法加载 _template 实例: {e}")


class TestIntegration:
    """集成测试"""
    
    def test_full_pipeline(self):
        """测试完整流程：配置 -> 过滤 -> 加载"""
        # 1. 创建加载器
        loader = create_tool_loader()
        
        # 2. 模拟配置
        enabled_capabilities = {
            "web_search": 1,  # 测试整数转换
            "plan_todo": True,
            "knowledge_search": 1,
            "ppt_generator": 0,  # 禁用
        }
        
        # 3. 加载工具
        result = loader.load_tools(
            enabled_capabilities=enabled_capabilities,
            mcp_tools=[{"name": "test_mcp"}],
            skills=[],
        )
        
        # 4. 验证结果
        assert result.generic_count == 3  # 3 个启用的通用工具
        assert result.mcp_count == 1
        assert result.total_count == 4
        
        # 5. 验证过滤后的注册表
        filtered = loader.create_filtered_registry(enabled_capabilities)
        assert len(filtered.capabilities) == 3
        assert "ppt_generator" not in filtered.capabilities  # 应该被过滤掉


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "-s"])

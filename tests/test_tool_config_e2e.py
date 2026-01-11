"""
端到端测试：验证工具配置加载功能

测试 test_agent 实例的工具配置：
1. 配置加载正确
2. enabled_capabilities 被正确解析
3. 工具加载器正确过滤工具
4. Agent 初始化时只包含启用的工具
"""

import pytest
import asyncio
import logging
import sys
from pathlib import Path

# 确保可以导入项目模块
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.instance_loader import (
    load_instance_config,
    load_instance_env,
    get_instances_dir,
)
from core.tool import (
    ToolLoader,
    create_tool_loader,
    get_capability_registry,
    CapabilityRegistry,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestToolConfigE2E:
    """端到端测试：工具配置功能"""
    
    INSTANCE_NAME = "test_agent"  # 测试实例名称
    
    # ==================== 测试 1: 配置加载 ====================
    
    def test_load_instance_config(self):
        """测试加载实例配置"""
        logger.info("=" * 60)
        logger.info("测试 1: 加载实例配置")
        logger.info("=" * 60)
        
        # 加载配置
        config = load_instance_config(self.INSTANCE_NAME)
        
        # 验证基本信息
        assert config.name == "test_agent"
        assert config.version == "1.0.0"
        logger.info(f"✅ 实例名称: {config.name}")
        logger.info(f"✅ 版本: {config.version}")
        
        # 验证 enabled_capabilities 字段存在
        assert hasattr(config, "enabled_capabilities")
        assert isinstance(config.enabled_capabilities, dict)
        logger.info(f"✅ enabled_capabilities 字段存在")
        
        return config
    
    # ==================== 测试 2: enabled_capabilities 解析 ====================
    
    def test_enabled_capabilities_parsing(self):
        """测试 enabled_capabilities 配置解析"""
        logger.info("=" * 60)
        logger.info("测试 2: enabled_capabilities 配置解析")
        logger.info("=" * 60)
        
        config = load_instance_config(self.INSTANCE_NAME)
        enabled = config.enabled_capabilities
        
        # 验证配置被正确解析
        assert len(enabled) > 0, "enabled_capabilities 不应为空"
        logger.info(f"✅ 解析到 {len(enabled)} 个工具配置")
        
        # 验证值被转换为布尔值
        for tool_name, is_enabled in enabled.items():
            assert isinstance(is_enabled, bool), f"{tool_name} 的值应为布尔值"
        logger.info("✅ 所有配置值已转换为布尔值")
        
        # 打印启用和禁用的工具
        enabled_tools = [name for name, val in enabled.items() if val]
        disabled_tools = [name for name, val in enabled.items() if not val]
        
        logger.info(f"\n📋 启用的工具 ({len(enabled_tools)}):")
        for tool in enabled_tools:
            logger.info(f"   ✓ {tool}")
        
        logger.info(f"\n📋 禁用的工具 ({len(disabled_tools)}):")
        for tool in disabled_tools:
            logger.info(f"   ✗ {tool}")
        
        # 验证预期的工具启用状态
        expected_enabled = ["web_search", "knowledge_search", "plan_todo", "api_calling"]
        expected_disabled = ["pptx", "xlsx", "docx", "pdf", "ppt_generator"]
        
        for tool in expected_enabled:
            if tool in enabled:
                assert enabled[tool] is True, f"{tool} 应该被启用"
                logger.info(f"✅ {tool} 状态正确（启用）")
        
        for tool in expected_disabled:
            if tool in enabled:
                assert enabled[tool] is False, f"{tool} 应该被禁用"
                logger.info(f"✅ {tool} 状态正确（禁用）")
        
        return enabled
    
    # ==================== 测试 3: ToolLoader 过滤 ====================
    
    def test_tool_loader_filtering(self):
        """测试 ToolLoader 工具过滤功能"""
        logger.info("=" * 60)
        logger.info("测试 3: ToolLoader 工具过滤")
        logger.info("=" * 60)
        
        config = load_instance_config(self.INSTANCE_NAME)
        
        # 创建 ToolLoader
        loader = create_tool_loader()
        logger.info("✅ 创建 ToolLoader")
        
        # 加载工具
        result = loader.load_tools(
            enabled_capabilities=config.enabled_capabilities,
            mcp_tools=config.mcp_tools,
            skills=[s for s in config.skills if s.enabled] if config.skills else [],
        )
        
        logger.info(f"\n📊 工具加载结果:")
        logger.info(f"   通用工具: {result.generic_count} 个")
        logger.info(f"   MCP 工具: {result.mcp_count} 个")
        logger.info(f"   Claude Skills: {result.skills_count} 个")
        logger.info(f"   总计: {result.total_count} 个")
        
        # 🆕 V5.1: 核心工具自动启用，所以数量 >= 用户配置数量
        from core.tool import CORE_TOOLS
        user_enabled_count = sum(1 for v in config.enabled_capabilities.values() if v)
        min_expected = user_enabled_count  # 至少有用户配置的工具
        
        # 核心工具会被自动添加
        assert result.generic_count >= min_expected, \
            f"通用工具数量应 >= {min_expected}，实际 {result.generic_count}"
        logger.info(f"✅ 通用工具数量正确: {result.generic_count} (包含核心工具)")
        
        # 验证核心工具被自动启用
        for core_tool in CORE_TOOLS:
            if core_tool in [cap.name for cap in result.generic_tools]:
                logger.info(f"   ✅ 核心工具 {core_tool} 已自动启用")
        
        # 验证 MCP 工具数量
        expected_mcp = len(config.mcp_tools) if config.mcp_tools else 0
        assert result.mcp_count == expected_mcp, \
            f"MCP 工具数量应为 {expected_mcp}，实际 {result.mcp_count}"
        logger.info(f"✅ MCP 工具数量正确: {result.mcp_count}")
        
        # 打印启用的工具列表
        logger.info(f"\n📋 启用的通用工具:")
        for tool in result.enabled_tools:
            logger.info(f"   ✓ {tool}")
        
        return result
    
    # ==================== 测试 4: 过滤后的注册表 ====================
    
    def test_filtered_registry(self):
        """测试创建过滤后的注册表"""
        logger.info("=" * 60)
        logger.info("测试 4: 过滤后的注册表")
        logger.info("=" * 60)
        
        config = load_instance_config(self.INSTANCE_NAME)
        
        # 获取全局注册表
        global_registry = get_capability_registry()
        total_tools = len(global_registry.capabilities)
        logger.info(f"📋 全局注册表工具数量: {total_tools}")
        
        # 创建过滤后的注册表
        loader = create_tool_loader(global_registry)
        filtered_registry = loader.create_filtered_registry(config.enabled_capabilities)
        
        filtered_count = len(filtered_registry.capabilities)
        logger.info(f"📋 过滤后注册表工具数量: {filtered_count}")
        
        # 🆕 V5.1: 验证过滤结果（核心工具自动启用）
        from core.tool import CORE_TOOLS
        user_enabled_count = sum(1 for v in config.enabled_capabilities.values() if v)
        
        # 过滤后数量应该 >= 用户启用数量（因为核心工具自动启用）
        assert filtered_count >= user_enabled_count, \
            f"过滤后工具数量应 >= {user_enabled_count}，实际 {filtered_count}"
        logger.info(f"✅ 过滤后工具数量正确（包含自动启用的核心工具）")
        
        # 验证核心工具被自动添加
        for core_tool in CORE_TOOLS:
            if core_tool in filtered_registry.capabilities:
                logger.info(f"   ✅ 核心工具 {core_tool} 已自动启用")
        
        # 🆕 V5.1: 验证类别配置展开（如果有的话）
        from core.tool import TOOL_CATEGORIES
        for category, tools in TOOL_CATEGORIES.items():
            if config.enabled_capabilities.get(category, False):
                logger.info(f"   📦 类别 {category} 已启用，展开工具:")
                for tool in tools:
                    if tool in filtered_registry.capabilities:
                        logger.info(f"      ✓ {tool}")
        
        # 打印过滤后的工具
        logger.info(f"\n📋 过滤后的工具列表:")
        for tool_name, cap in filtered_registry.capabilities.items():
            is_core = "🔧 核心" if tool_name in CORE_TOOLS else ""
            logger.info(f"   ✓ {tool_name} ({cap.type.value}) {is_core}")
        
        return filtered_registry
    
    # ==================== 测试 5: 统计信息 ====================
    
    def test_tool_statistics(self):
        """测试工具统计信息"""
        logger.info("=" * 60)
        logger.info("测试 5: 工具统计信息")
        logger.info("=" * 60)
        
        config = load_instance_config(self.INSTANCE_NAME)
        loader = create_tool_loader()
        
        stats = loader.get_tool_statistics(config.enabled_capabilities)
        
        logger.info(f"\n📊 工具统计:")
        logger.info(f"   可用工具总数: {stats['total_available']}")
        logger.info(f"   已启用: {stats['enabled_count']}")
        logger.info(f"   已禁用: {stats['disabled_count']}")
        
        # 验证统计数据
        assert stats['enabled_count'] + stats['disabled_count'] <= stats['total_available']
        logger.info("✅ 统计数据一致")
        
        return stats


def run_all_tests():
    """运行所有端到端测试"""
    print("\n" + "=" * 70)
    print("🚀 开始端到端测试：test_agent 实例工具配置")
    print("=" * 70 + "\n")
    
    test = TestToolConfigE2E()
    
    try:
        # 测试 1
        test.test_load_instance_config()
        
        # 测试 2
        test.test_enabled_capabilities_parsing()
        
        # 测试 3
        test.test_tool_loader_filtering()
        
        # 测试 4
        test.test_filtered_registry()
        
        # 测试 5
        test.test_tool_statistics()
        
        print("\n" + "=" * 70)
        print("✅ 所有端到端测试通过！")
        print("=" * 70 + "\n")
        return True
        
    except AssertionError as e:
        print("\n" + "=" * 70)
        print(f"❌ 测试失败: {e}")
        print("=" * 70 + "\n")
        return False
    except Exception as e:
        print("\n" + "=" * 70)
        print(f"❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        print("=" * 70 + "\n")
        return False


if __name__ == "__main__":
    # 切换到项目目录
    import os
    os.chdir(project_root)
    
    # 运行测试
    success = run_all_tests()
    sys.exit(0 if success else 1)

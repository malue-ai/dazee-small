"""
冒烟测试：验证修改后的代码能正常运行

目标：不是测试复杂逻辑，只是确保修改后的代码不会崩溃！
"""

import pytest


class TestRefactorSmokeTest:
    """冒烟测试：修改后的代码能正常导入和基本调用"""
    
    def test_compaction_import_and_basic_call(self):
        """测试：上下文压缩模块（删除了关键词判断）"""
        # 导入不崩溃
        from core.context.compaction import ContextStrategy, trim_history_messages
        
        # 创建简单的测试数据
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        # 使用默认策略
        strategy = ContextStrategy()
        
        # 调用函数不崩溃（关键：验证删除关键词后不会崩溃）
        result = trim_history_messages(messages, strategy)
        
        # 基本验证
        assert isinstance(result, list)
        print(f"✅ compaction模块工作正常，返回 {len(result)} 条消息")
    
    def test_formatter_import_and_basic_call(self):
        """测试：记忆格式化模块（删除了关键词分类）"""
        # 导入不崩溃
        from core.memory.mem0.retrieval.formatter import format_memories_by_category
        
        # 创建简单的测试数据
        memories = [
            {"memory": "测试记忆1", "created_at": "2024-01-01"},
            {"memory": "测试记忆2", "created_at": "2024-01-02"},
        ]
        
        # 调用函数不崩溃
        result = format_memories_by_category(memories)
        
        # 基本验证
        assert isinstance(result, str)
        assert "测试记忆1" in result
        assert "测试记忆2" in result
        print(f"✅ formatter模块工作正常，返回格式化文本长度: {len(result)}")
    
    @pytest.mark.asyncio
    async def test_agent_manager_basic_structure(self):
        """测试：AgentManager基本结构（改用LLM任务分解）"""
        try:
            # 只测试导入，不测试实际执行（避免复杂依赖）
            from core.agent_manager import AgentManager
            print("✅ agent_manager模块导入成功")
            assert AgentManager is not None
        except ImportError as e:
            pytest.fail(f"❌ agent_manager导入失败: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

"""
测试 messages_to_dict_list 修复：过滤空内容消息

验证修复了 Claude API 错误：
"messages.1: all messages must have non-empty content except for the optional final assistant message"
"""

import pytest
from core.llm import Message
from utils.message_utils import messages_to_dict_list


class TestMessagesToDictListFix:
    """测试消息转换函数过滤空内容"""
    
    def test_filter_empty_user_message(self):
        """测试过滤掉空内容的 user 消息"""
        messages = [
            Message(role="user", content="第一条消息"),
            Message(role="assistant", content="回复1"),
            Message(role="user", content=""),  # 空内容，应该被过滤
            Message(role="assistant", content="回复2"),
        ]
        
        result = messages_to_dict_list(messages)
        
        # 应该只有 3 条消息（空的被过滤）
        assert len(result) == 3
        assert result[0]["content"] == "第一条消息"
        assert result[1]["content"] == "回复1"
        assert result[2]["content"] == "回复2"
    
    def test_filter_empty_assistant_message_not_last(self):
        """测试过滤掉非最后的空 assistant 消息"""
        messages = [
            Message(role="user", content="问题"),
            Message(role="assistant", content=""),  # 空内容，不是最后一条，应被过滤
            Message(role="user", content="继续"),
        ]
        
        result = messages_to_dict_list(messages)
        
        # 应该只有 2 条消息
        assert len(result) == 2
        assert result[0]["content"] == "问题"
        assert result[1]["content"] == "继续"
    
    def test_keep_empty_assistant_message_if_last(self):
        """测试保留最后的空 assistant 消息（Claude 允许）"""
        messages = [
            Message(role="user", content="问题"),
            Message(role="assistant", content=""),  # 空内容，但是最后一条，应保留
        ]
        
        result = messages_to_dict_list(messages)
        
        # 应该有 2 条消息
        assert len(result) == 2
        assert result[0]["content"] == "问题"
        assert result[1]["content"] == ""
        assert result[1]["role"] == "assistant"
    
    def test_filter_whitespace_only_content(self):
        """测试过滤只有空白字符的消息"""
        messages = [
            Message(role="user", content="正常消息"),
            Message(role="user", content="   "),  # 只有空格，应被过滤
            Message(role="assistant", content="\n\t  "),  # 只有换行和空格，应被过滤
            Message(role="user", content="继续"),
        ]
        
        result = messages_to_dict_list(messages)
        
        # 应该只有 2 条消息
        assert len(result) == 2
        assert result[0]["content"] == "正常消息"
        assert result[1]["content"] == "继续"
    
    def test_keep_valid_messages(self):
        """测试保留所有有效消息"""
        messages = [
            Message(role="user", content="问题1"),
            Message(role="assistant", content="回答1"),
            Message(role="user", content="问题2"),
            Message(role="assistant", content="回答2"),
        ]
        
        result = messages_to_dict_list(messages)
        
        # 所有消息都应保留
        assert len(result) == 4
        assert all(msg["content"] for msg in result)
    
    def test_none_content(self):
        """测试 None content 的情况"""
        messages = [
            Message(role="user", content="正常消息"),
            Message(role="user", content=None),  # None，应被过滤
            Message(role="assistant", content="回复"),
        ]
        
        result = messages_to_dict_list(messages)
        
        # 应该只有 2 条消息
        assert len(result) == 2
        assert result[0]["content"] == "正常消息"
        assert result[1]["content"] == "回复"
    
    def test_complex_content_format(self):
        """测试复杂格式的 content（列表、字典等）"""
        messages = [
            Message(role="user", content=[{"type": "text", "text": "你好"}]),
            Message(role="assistant", content=[{"type": "text", "text": "回复"}]),
        ]
        
        result = messages_to_dict_list(messages)
        
        # 复杂格式应保留（非空）
        assert len(result) == 2
        assert isinstance(result[0]["content"], list)
        assert isinstance(result[1]["content"], list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

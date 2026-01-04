"""
测试消息工具函数

测试场景：
1. 消息格式标准化
2. 文本内容提取
3. 历史消息加载（含压缩）
"""

import pytest
from utils.message_utils import (
    normalize_message_format,
    extract_text_from_message,
)


class TestNormalizeMessageFormat:
    """测试消息格式标准化"""
    
    def test_already_normalized_format(self):
        """测试已经是标准格式的消息"""
        message = [{"type": "text", "text": "你好"}]
        result = normalize_message_format(message)
        assert result == message
    
    def test_string_format(self):
        """测试纯文本字符串"""
        message = "你好，请帮我写一个 Python 脚本"
        result = normalize_message_format(message)
        assert result == [{"type": "text", "text": message}]
    
    def test_empty_string(self):
        """测试空字符串"""
        message = ""
        result = normalize_message_format(message)
        assert result == [{"type": "text", "text": ""}]
    
    def test_mixed_content_blocks(self):
        """测试混合内容块（标准格式）"""
        message = [
            {"type": "text", "text": "查看这个图片"},
            {"type": "image", "source": {"type": "url", "url": "https://..."}}
        ]
        result = normalize_message_format(message)
        assert result == message
    
    def test_invalid_list_format(self):
        """测试无效的列表格式（转换为字符串）"""
        message = ["string1", "string2"]
        result = normalize_message_format(message)
        # 应该转换为字符串
        assert len(result) == 1
        assert result[0]["type"] == "text"
        assert "string1" in result[0]["text"]


class TestExtractTextFromMessage:
    """测试文本内容提取"""
    
    def test_extract_from_string(self):
        """测试从字符串提取"""
        message = "你好，世界"
        result = extract_text_from_message(message)
        assert result == "你好，世界"
    
    def test_extract_from_content_blocks(self):
        """测试从 content blocks 提取"""
        message = [
            {"type": "text", "text": "第一段文本"},
            {"type": "image", "source": {"type": "url", "url": "https://..."}},
            {"type": "text", "text": "第二段文本"}
        ]
        result = extract_text_from_message(message)
        # 应该提取第一个 text block
        assert result == "第一段文本"
    
    def test_extract_from_empty_message(self):
        """测试从空消息提取"""
        message = ""
        result = extract_text_from_message(message)
        assert result == ""
    
    def test_extract_from_non_text_blocks(self):
        """测试只包含非文本块的消息"""
        message = [
            {"type": "image", "source": {"type": "url", "url": "https://..."}}
        ]
        result = extract_text_from_message(message)
        assert result == ""
    
    def test_extract_from_list_without_text(self):
        """测试没有 text 类型的列表"""
        message = [
            {"type": "other", "data": "something"}
        ]
        result = extract_text_from_message(message)
        assert result == ""


class TestMessageUtilsIntegration:
    """集成测试：测试函数组合使用"""
    
    def test_normalize_then_extract(self):
        """测试先标准化再提取"""
        # 输入纯文本
        original = "你好，请帮我写代码"
        
        # 标准化
        normalized = normalize_message_format(original)
        assert len(normalized) == 1
        assert normalized[0]["type"] == "text"
        
        # 提取文本
        extracted = extract_text_from_message(normalized)
        assert extracted == original
    
    def test_round_trip_conversion(self):
        """测试往返转换"""
        # 标准格式 → 提取 → 标准化 → 应该得到相同结果
        original = [{"type": "text", "text": "测试消息"}]
        
        # 提取
        text = extract_text_from_message(original)
        
        # 重新标准化
        normalized = normalize_message_format(text)
        
        # 应该得到相同结果
        assert normalized == original


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])


"""
工具调用兼容性测试
"""

from core.llm.adaptor import OpenAIAdaptor
from core.llm.base import LLMConfig, LLMProvider
from core.llm.qwen import QwenLLMService


class TestToolCallsCompat:
    """工具调用格式兼容测试"""
    
    def test_openai_adaptor_tool_calls_type_and_parse(self):
        """OpenAI 响应的 tool_calls 应补齐 type 并解析入参"""
        adaptor = OpenAIAdaptor()
        response = {
            "choices": [{
                "message": {
                    "content": "",
                    "tool_calls": [{
                        "id": "call_1",
                        "function": {
                            "name": "plan_todo",
                            "arguments": "{\"operation\": \"create_plan\"}"
                        }
                    }]
                },
                "finish_reason": "tool_calls"
            }]
        }
        
        result = adaptor.convert_response_to_claude(response)
        assert result.tool_calls is not None
        assert result.tool_calls[0]["type"] == "tool_use"
        assert result.tool_calls[0]["input"]["operation"] == "create_plan"
    
    def test_openai_adaptor_tool_calls_invalid_json(self):
        """OpenAI 响应的非法 JSON 入参应安全降级"""
        adaptor = OpenAIAdaptor()
        response = {
            "choices": [{
                "message": {
                    "content": "",
                    "tool_calls": [{
                        "id": "call_1",
                        "function": {
                            "name": "plan_todo",
                            "arguments": "{invalid_json}"
                        }
                    }]
                },
                "finish_reason": "tool_calls"
            }]
        }
        
        result = adaptor.convert_response_to_claude(response)
        assert result.tool_calls is not None
        assert result.tool_calls[0]["type"] == "tool_use"
        assert result.tool_calls[0]["input"] == {}
    
    def test_qwen_tool_calls_normalized(self):
        """Qwen tool_calls 应规范化为内部格式"""
        config = LLMConfig(
            provider=LLMProvider.QWEN,
            model="qwen-max",
            api_key="test_key"
        )
        service = QwenLLMService(config)
        
        response = {
            "status_code": 200,
            "output": {
                "choices": [{
                    "message": {
                        "content": "",
                        "tool_calls": [{
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "plan_todo",
                                "arguments": "{\"operation\": \"create_plan\"}"
                            }
                        }]
                    }
                }]
            }
        }
        
        result = service._parse_response(response)
        assert result.tool_calls is not None
        assert result.tool_calls[0]["type"] == "tool_use"
        assert result.tool_calls[0]["name"] == "plan_todo"
        assert result.tool_calls[0]["input"]["operation"] == "create_plan"

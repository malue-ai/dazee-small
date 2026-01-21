"""
测试工具调用格式规范化
"""

from core.llm.tool_call_utils import normalize_tool_calls


class TestToolCallUtils:
    """工具调用规范化测试"""
    
    def test_normalize_function_arguments(self):
        """function.arguments JSON 应解析为 input"""
        tool_calls = [{
            "id": "call_1",
            "function": {
                "name": "plan_todo",
                "arguments": "{\"operation\": \"create_plan\"}"
            }
        }]
        
        result = normalize_tool_calls(tool_calls)
        assert result is not None
        assert result[0]["name"] == "plan_todo"
        assert result[0]["input"]["operation"] == "create_plan"
        assert result[0]["type"] == "tool_use"
    
    def test_normalize_invalid_arguments(self):
        """非法 JSON 入参应降级为空对象"""
        tool_calls = [{
            "id": "call_1",
            "function": {
                "name": "plan_todo",
                "arguments": "{invalid_json}"
            }
        }]
        
        result = normalize_tool_calls(tool_calls)
        assert result is not None
        assert result[0]["input"] == {}
    
    def test_normalize_input_string(self):
        """input 为 JSON 字符串时应解析"""
        tool_calls = [{
            "id": "call_1",
            "name": "plan_todo",
            "input": "{\"operation\": \"create_plan\"}"
        }]
        
        result = normalize_tool_calls(tool_calls)
        assert result is not None
        assert result[0]["input"]["operation"] == "create_plan"
    
    def test_normalize_parameters(self):
        """parameters 字段应转为 input"""
        tool_calls = [{
            "id": "call_1",
            "name": "plan_todo",
            "parameters": "{\"operation\": \"create_plan\"}"
        }]
        
        result = normalize_tool_calls(tool_calls)
        assert result is not None
        assert result[0]["input"]["operation"] == "create_plan"
    
    def test_preserve_server_tool_use(self):
        """server_tool_use 类型应保留"""
        tool_calls = [{
            "id": "call_1",
            "name": "web_search",
            "input": {},
            "type": "server_tool_use"
        }]
        
        result = normalize_tool_calls(tool_calls)
        assert result is not None
        assert result[0]["type"] == "server_tool_use"
    
    def test_generate_missing_id(self):
        """缺失 id 时生成默认 id"""
        tool_calls = [{
            "name": "plan_todo",
            "input": {}
        }]
        
        result = normalize_tool_calls(tool_calls)
        assert result is not None
        assert result[0]["id"].startswith("tool_")
    
    def test_skip_invalid_entries(self):
        """非 dict 工具调用应被跳过"""
        result = normalize_tool_calls(["invalid", 123])
        assert result is None

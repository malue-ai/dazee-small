"""
测试 adaptor.py 消息转换逻辑

验证：
1. prepare_messages_from_db() - 数据库消息 → LLM 格式
2. ensure_tool_pairs() - 确保 tool_use/tool_result 配对
3. 去重逻辑
4. 排序逻辑
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 确保可以正确导入
os.chdir(project_root)

from core.llm.adaptor import ClaudeAdaptor


def test_simple_text_message():
    """测试简单文本消息"""
    print("测试: 简单文本消息...")
    
    db_messages = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！有什么可以帮助你的？"}
    ]
    
    result = ClaudeAdaptor.prepare_messages_from_db(db_messages)
    
    assert len(result) == 2, f"期望 2 条消息，实际 {len(result)}"
    assert result[0]["role"] == "user"
    assert result[0]["content"] == "你好"
    assert result[1]["role"] == "assistant"
    assert result[1]["content"] == "你好！有什么可以帮助你的？"
    
    print("✅ 通过")


def test_content_blocks_with_thinking():
    """测试包含 thinking 块的消息（应被过滤）"""
    print("测试: thinking 块过滤...")
    
    db_messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "让我思考一下..."},
                {"type": "text", "text": "答案是 42"}
            ]
        }
    ]
    
    result = ClaudeAdaptor.prepare_messages_from_db(db_messages)
    
    assert len(result) == 1
    assert result[0]["role"] == "assistant"
    # thinking 块应被过滤
    assert len(result[0]["content"]) == 1, f"期望 1 个块，实际 {len(result[0]['content'])}"
    assert result[0]["content"][0]["type"] == "text"
    
    print("✅ 通过")


def test_tool_result_separation():
    """测试 tool_result 分离到 user 消息"""
    print("测试: tool_result 分离...")
    
    db_messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "让我查一下"},
                {"type": "tool_use", "id": "tool_1", "name": "search", "input": {"q": "test"}},
                {"type": "tool_result", "tool_use_id": "tool_1", "content": "搜索结果"}
            ]
        }
    ]
    
    result = ClaudeAdaptor.prepare_messages_from_db(db_messages)
    
    # 应该分离为 2 条消息：assistant + user(tool_result)
    assert len(result) == 2, f"期望 2 条消息，实际 {len(result)}"
    
    # 第一条：assistant 消息（text + tool_use）
    assert result[0]["role"] == "assistant"
    assert len(result[0]["content"]) == 2
    assert result[0]["content"][0]["type"] == "text"
    assert result[0]["content"][1]["type"] == "tool_use"
    
    # 第二条：user 消息（tool_result）
    assert result[1]["role"] == "user"
    assert len(result[1]["content"]) == 1
    assert result[1]["content"][0]["type"] == "tool_result"
    
    print("✅ 通过")


def test_index_field_removed():
    """测试 index 字段被移除"""
    print("测试: index 字段移除...")
    
    db_messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "测试", "index": 0},
                {"type": "tool_use", "id": "t1", "name": "test", "input": {}, "index": 1}
            ]
        }
    ]
    
    result = ClaudeAdaptor.prepare_messages_from_db(db_messages)
    
    # 检查 index 字段已被移除
    for block in result[0]["content"]:
        assert "index" not in block, f"index 字段未移除: {block}"
    
    print("✅ 通过")


def test_index_sorting():
    """测试按 index 排序"""
    print("测试: index 排序...")
    
    db_messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "第二", "index": 2},
                {"type": "text", "text": "第一", "index": 1},
                {"type": "text", "text": "第三", "index": 3}
            ]
        }
    ]
    
    result = ClaudeAdaptor.prepare_messages_from_db(db_messages)
    
    # 应该按 index 排序
    assert result[0]["content"][0]["text"] == "第一", f"第一个应为 '第一'，实际 {result[0]['content'][0]['text']}"
    assert result[0]["content"][1]["text"] == "第二"
    assert result[0]["content"][2]["text"] == "第三"
    
    print("✅ 通过")


def test_duplicate_tool_use_removed():
    """测试重复的 tool_use 被去重"""
    print("测试: 重复 tool_use 去重...")
    
    db_messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "tool_1", "name": "search", "input": {}},
                {"type": "tool_use", "id": "tool_1", "name": "search", "input": {}},  # 重复
                {"type": "tool_result", "tool_use_id": "tool_1", "content": "结果"}
            ]
        }
    ]
    
    result = ClaudeAdaptor.prepare_messages_from_db(db_messages)
    
    # 统计 tool_use 数量
    tool_use_count = sum(
        1 for msg in result 
        for block in (msg.get("content", []) if isinstance(msg.get("content"), list) else [])
        if isinstance(block, dict) and block.get("type") == "tool_use"
    )
    
    # 应该只有 1 个 tool_use
    assert tool_use_count == 1, f"期望 1 个 tool_use，实际 {tool_use_count}"
    
    print("✅ 通过")


def test_paired_tool_use_and_result():
    """测试配对的 tool_use 和 tool_result 保留"""
    print("测试: 配对的 tool_use/tool_result 保留...")
    
    messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "查询中"},
                {"type": "tool_use", "id": "t1", "name": "search", "input": {}}
            ]
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "结果"}
            ]
        }
    ]
    
    result = ClaudeAdaptor.ensure_tool_pairs(messages)
    
    # 配对的应该保留
    assert len(result) == 2
    
    # 检查 tool_use 存在
    assistant_content = result[0]["content"]
    has_tool_use = any(b.get("type") == "tool_use" for b in assistant_content)
    assert has_tool_use, "tool_use 应保留"
    
    # 检查 tool_result 存在
    user_content = result[1]["content"]
    has_tool_result = any(b.get("type") == "tool_result" for b in user_content)
    assert has_tool_result, "tool_result 应保留"
    
    print("✅ 通过")


def test_unpaired_tool_use_removed():
    """测试未配对的 tool_use 被移除"""
    print("测试: 未配对 tool_use 移除...")
    
    messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "查询中"},
                {"type": "tool_use", "id": "t1", "name": "search", "input": {}}
            ]
        }
        # 没有对应的 tool_result
    ]
    
    result = ClaudeAdaptor.ensure_tool_pairs(messages)
    
    # 未配对的 tool_use 应被移除，只保留 text
    assert len(result) == 1
    content = result[0]["content"]
    assert len(content) == 1, f"期望 1 个块（text），实际 {len(content)}"
    assert content[0]["type"] == "text"
    
    print("✅ 通过")


def test_unpaired_tool_result_removed():
    """测试未配对的 tool_result 被移除"""
    print("测试: 未配对 tool_result 移除...")
    
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "t_nonexistent", "content": "结果"}
            ]
        }
        # 没有对应的 tool_use
    ]
    
    result = ClaudeAdaptor.ensure_tool_pairs(messages)
    
    # 未配对的 tool_result 应被移除，消息为空则不添加
    assert len(result) == 0, f"期望 0 条消息，实际 {len(result)}"
    
    print("✅ 通过")


def test_mixed_paired_and_unpaired():
    """测试混合配对和未配对的情况"""
    print("测试: 混合配对/未配对...")
    
    messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "查询中"},
                {"type": "tool_use", "id": "t1", "name": "search", "input": {}},
                {"type": "tool_use", "id": "t2", "name": "calc", "input": {}}  # 未配对
            ]
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "结果1"}
                # t2 没有对应的 tool_result
            ]
        }
    ]
    
    result = ClaudeAdaptor.ensure_tool_pairs(messages)
    
    # 检查 t1 保留，t2 被移除
    assistant_content = result[0]["content"]
    tool_uses = [b for b in assistant_content if b.get("type") == "tool_use"]
    
    assert len(tool_uses) == 1, f"期望 1 个 tool_use，实际 {len(tool_uses)}"
    assert tool_uses[0]["id"] == "t1"
    
    print("✅ 通过")


def test_multi_turn_with_tools():
    """测试多轮对话 + 工具调用（集成测试）"""
    print("测试: 多轮对话 + 工具调用（集成）...")
    
    # 模拟数据库中的消息（包含多轮对话和工具调用）
    db_messages = [
        # 第一轮：用户提问
        {"role": "user", "content": [{"type": "text", "text": "今天北京天气怎么样？"}]},
        # 第一轮：Assistant 调用工具
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "需要查询天气", "index": 0},
                {"type": "text", "text": "让我查一下", "index": 1},
                {"type": "tool_use", "id": "weather_1", "name": "get_weather", "input": {"city": "北京"}, "index": 2},
                {"type": "tool_result", "tool_use_id": "weather_1", "content": "晴天，25°C", "index": 3},
                {"type": "text", "text": "北京今天天气晴朗，气温25°C。", "index": 4}
            ]
        },
        # 第二轮：用户追问
        {"role": "user", "content": [{"type": "text", "text": "明天呢？"}]},
        # 第二轮：Assistant 再次调用工具
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "weather_2", "name": "get_weather", "input": {"city": "北京", "date": "tomorrow"}, "index": 0},
                {"type": "tool_result", "tool_use_id": "weather_2", "content": "多云，22°C", "index": 1},
                {"type": "text", "text": "明天北京多云，气温22°C。", "index": 2}
            ]
        }
    ]
    
    result = ClaudeAdaptor.prepare_messages_from_db(db_messages)
    
    # 验证基本结构
    assert len(result) > 0, "结果不应为空"
    
    # 验证 thinking 块被移除
    for msg in result:
        content = msg.get("content", [])
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    assert block.get("type") != "thinking", "thinking 块应被移除"
    
    # 验证 tool_result 在 user 消息中
    for msg in result:
        content = msg.get("content", [])
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    assert msg["role"] == "user", "tool_result 应在 user 消息中"
    
    # 验证 tool_use 在 assistant 消息中
    for msg in result:
        content = msg.get("content", [])
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    assert msg["role"] == "assistant", "tool_use 应在 assistant 消息中"
    
    # 验证所有 tool_use/tool_result 都配对
    tool_use_ids = set()
    tool_result_ids = set()
    
    for msg in result:
        content = msg.get("content", [])
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "tool_use":
                        tool_use_ids.add(block.get("id"))
                    elif block.get("type") == "tool_result":
                        tool_result_ids.add(block.get("tool_use_id"))
    
    # 所有 tool_use 都应有对应的 tool_result
    assert tool_use_ids == tool_result_ids, f"tool_use/tool_result 不配对: {tool_use_ids} vs {tool_result_ids}"
    
    print(f"✅ 通过")
    print(f"   原始消息数: {len(db_messages)}")
    print(f"   处理后消息数: {len(result)}")
    print(f"   工具调用数: {len(tool_use_ids)}")


def test_conversation_convert_to_agent_format():
    """测试 conversation.py 的 _convert_to_agent_format 方法"""
    print("测试: conversation._convert_to_agent_format()...")
    
    from core.context.conversation import Context
    import json
    
    # 创建 Context 实例
    ctx = Context()
    
    # 测试 1: 处理 JSON 字符串格式的 content
    db_messages_json = [
        {
            "role": "user",
            "content": json.dumps([{"type": "text", "text": "你好"}], ensure_ascii=False)
        },
        {
            "role": "assistant",
            "content": json.dumps([
                {"type": "text", "text": "你好！", "index": 0},
                {"type": "tool_use", "id": "t1", "name": "search", "input": {}, "index": 1},
                {"type": "tool_result", "tool_use_id": "t1", "content": "结果", "index": 2}
            ], ensure_ascii=False)
        }
    ]
    
    result = ctx._convert_to_agent_format(db_messages_json)
    
    # 验证 JSON 字符串被正确解析
    assert len(result) > 0, "结果不应为空"
    
    # 验证 tool_result 被分离到 user 消息
    tool_result_in_user = False
    for msg in result:
        content = msg.get("content", [])
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    assert msg["role"] == "user", "tool_result 应在 user 消息中"
                    tool_result_in_user = True
    
    assert tool_result_in_user, "应有 tool_result 在 user 消息中"
    
    # 测试 2: 处理纯文本格式（旧格式）
    db_messages_text = [
        {"role": "user", "content": "这是纯文本"},
        {"role": "assistant", "content": "这也是纯文本"}
    ]
    
    result_text = ctx._convert_to_agent_format(db_messages_text)
    
    assert len(result_text) == 2
    assert result_text[0]["content"] == "这是纯文本"
    assert result_text[1]["content"] == "这也是纯文本"
    
    print("✅ 通过")


def test_conversation_with_db_objects():
    """测试 conversation.py 处理数据库对象格式"""
    print("测试: conversation 处理数据库对象...")
    
    from core.context.conversation import Context
    import json
    
    # 模拟数据库对象（有 .content 和 .role 属性）
    class MockDBMessage:
        def __init__(self, role, content):
            self.role = role
            self.content = content
    
    ctx = Context()
    
    db_objects = [
        MockDBMessage("user", "用户消息"),
        MockDBMessage("assistant", json.dumps([
            {"type": "text", "text": "助手回复"}
        ], ensure_ascii=False))
    ]
    
    result = ctx._convert_to_agent_format(db_objects)
    
    assert len(result) == 2
    assert result[0]["role"] == "user"
    assert result[0]["content"] == "用户消息"
    assert result[1]["role"] == "assistant"
    
    print("✅ 通过")


def test_runtime_message_append():
    """测试运行时新消息追加不受影响"""
    print("测试: 运行时消息追加...")
    
    # 模拟运行时场景：已有历史消息，追加新消息
    history_messages = [
        {"role": "user", "content": "第一个问题"},
        {"role": "assistant", "content": [{"type": "text", "text": "第一个回答"}]}
    ]
    
    # 追加新的用户消息
    new_user_message = {"role": "user", "content": "第二个问题"}
    all_messages = history_messages + [new_user_message]
    
    # 使用 adaptor 处理（模拟 chat_service 的处理流程）
    result = ClaudeAdaptor.prepare_messages_from_db(all_messages)
    
    # 验证消息完整性
    assert len(result) == 3, f"期望 3 条消息，实际 {len(result)}"
    
    # 验证顺序正确
    assert result[0]["role"] == "user"
    assert result[0]["content"] == "第一个问题"
    assert result[1]["role"] == "assistant"
    assert result[2]["role"] == "user"
    assert result[2]["content"] == "第二个问题"
    
    print("✅ 通过")


def test_interleaved_tool_separation():
    """测试交错分离：数据库存储的多轮工具调用正确分离"""
    print("测试: 交错分离多轮工具调用...")
    
    # 数据库存储格式：assistant 消息包含多轮 [text, tool_use, tool_result, tool_use, tool_result]
    db_messages = [
        {"role": "user", "content": [{"type": "text", "text": "帮我创建一个应用"}]},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "好的，我来帮您创建！", "index": 0},
                {"type": "tool_use", "id": "t1", "name": "plan_todo", "input": {}, "index": 1},
                {"type": "tool_result", "tool_use_id": "t1", "content": "Plan created", "index": 2},
                {"type": "tool_use", "id": "t2", "name": "create_project", "input": {}, "index": 3},
                {"type": "tool_result", "tool_use_id": "t2", "content": "Project created", "index": 4},
                {"type": "text", "text": "项目已创建完成！", "index": 5}
            ]
        }
    ]
    
    result = ClaudeAdaptor.prepare_messages_from_db(db_messages)
    
    # 验证消息数量：user + assistant + user + assistant + user + assistant = 6
    # user: 帮我创建
    # assistant: [text, tool_use t1]
    # user: [tool_result t1]
    # assistant: [tool_use t2]
    # user: [tool_result t2]
    # assistant: [text 项目已创建]
    assert len(result) == 6, f"期望 6 条消息，实际 {len(result)}"
    
    # 验证消息顺序
    assert result[0]["role"] == "user"
    assert result[1]["role"] == "assistant"
    assert result[2]["role"] == "user"
    assert result[3]["role"] == "assistant"
    assert result[4]["role"] == "user"
    assert result[5]["role"] == "assistant"
    
    # 验证每个 assistant 后面紧跟的 user 是对应的 tool_result
    # result[1] assistant 包含 tool_use t1
    assistant_1_content = result[1]["content"]
    has_t1_tool_use = any(b.get("type") == "tool_use" and b.get("id") == "t1" for b in assistant_1_content)
    assert has_t1_tool_use, "result[1] 应包含 tool_use t1"
    
    # result[2] user 包含 tool_result t1
    user_2_content = result[2]["content"]
    has_t1_tool_result = any(b.get("type") == "tool_result" and b.get("tool_use_id") == "t1" for b in user_2_content)
    assert has_t1_tool_result, "result[2] 应包含 tool_result t1"
    
    # result[3] assistant 包含 tool_use t2
    assistant_3_content = result[3]["content"]
    has_t2_tool_use = any(b.get("type") == "tool_use" and b.get("id") == "t2" for b in assistant_3_content)
    assert has_t2_tool_use, "result[3] 应包含 tool_use t2"
    
    # result[4] user 包含 tool_result t2
    user_4_content = result[4]["content"]
    has_t2_tool_result = any(b.get("type") == "tool_result" and b.get("tool_use_id") == "t2" for b in user_4_content)
    assert has_t2_tool_result, "result[4] 应包含 tool_result t2"
    
    print(f"✅ 通过")
    print(f"   原始消息数: {len(db_messages)}")
    print(f"   交错分离后: {len(result)} 条消息")


def test_runtime_with_tool_workflow():
    """测试运行时工具调用工作流"""
    print("测试: 运行时工具调用工作流...")
    
    # 模拟完整的工具调用工作流
    # 场景：用户提问 -> 助手调用工具 -> 工具返回结果 -> 助手回复 -> 用户追问
    
    workflow_messages = [
        # 用户第一个问题
        {"role": "user", "content": [{"type": "text", "text": "查一下北京天气"}]},
        # 助手调用工具并返回结果（数据库存储格式）
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "好的，让我查一下", "index": 0},
                {"type": "tool_use", "id": "w1", "name": "weather", "input": {"city": "北京"}, "index": 1},
                {"type": "tool_result", "tool_use_id": "w1", "content": "晴天 25°C", "index": 2},
                {"type": "text", "text": "北京今天晴天，25°C", "index": 3}
            ]
        },
        # 用户追问
        {"role": "user", "content": [{"type": "text", "text": "明天呢？"}]},
    ]
    
    result = ClaudeAdaptor.prepare_messages_from_db(workflow_messages)
    
    # 验证消息结构正确
    # 期望结构：user -> assistant(text+tool_use) -> user(tool_result) -> assistant(text) -> user
    
    # 统计各角色消息数
    user_count = sum(1 for m in result if m["role"] == "user")
    assistant_count = sum(1 for m in result if m["role"] == "assistant")
    
    # user 消息应该包含：原始用户消息 + tool_result + 追问
    assert user_count >= 2, f"期望至少 2 条 user 消息，实际 {user_count}"
    
    # 验证 tool_use 和 tool_result 配对
    tool_use_ids = set()
    tool_result_ids = set()
    
    for msg in result:
        content = msg.get("content", [])
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "tool_use":
                        tool_use_ids.add(block.get("id"))
                    elif block.get("type") == "tool_result":
                        tool_result_ids.add(block.get("tool_use_id"))
    
    assert tool_use_ids == tool_result_ids, f"配对不匹配: {tool_use_ids} vs {tool_result_ids}"
    
    print(f"✅ 通过")
    print(f"   处理后消息数: {len(result)}")
    print(f"   user 消息: {user_count}, assistant 消息: {assistant_count}")


def main():
    """运行所有测试"""
    print("=" * 60)
    print("🧪 消息转换逻辑测试")
    print("=" * 60)
    print()
    
    tests = [
        # adaptor 单元测试
        test_simple_text_message,
        test_content_blocks_with_thinking,
        test_tool_result_separation,
        test_index_field_removed,
        test_index_sorting,
        test_duplicate_tool_use_removed,
        test_paired_tool_use_and_result,
        test_unpaired_tool_use_removed,
        test_unpaired_tool_result_removed,
        test_mixed_paired_and_unpaired,
        test_multi_turn_with_tools,
        # conversation.py 集成测试
        test_conversation_convert_to_agent_format,
        test_conversation_with_db_objects,
        # 运行时测试
        test_runtime_message_append,
        test_interleaved_tool_separation,
        test_runtime_with_tool_workflow,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"❌ 失败: {e}")
            failed += 1
        except Exception as e:
            print(f"❌ 错误: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
        print()
    
    print("=" * 60)
    print(f"结果: {passed} 通过, {failed} 失败")
    print("=" * 60)
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit(main())

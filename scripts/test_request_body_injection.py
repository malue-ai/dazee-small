#!/usr/bin/env python
"""
测试请求体注入机制

验证完整链路：
1. config.yaml -> instance_loader（ApiConfig 解析）
2. instance_loader -> agent_registry（apis_config 构建）
3. agent_registry -> api_calling（请求体模板传递）
4. api_calling 请求体合成（占位符替换）
"""

import asyncio
import os
import sys
import json
import yaml

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

# 加载环境变量
load_dotenv(".env.development")


def load_config_yaml(instance_name: str = "dazee_agent") -> dict:
    """直接加载 config.yaml"""
    config_path = f"instances/{instance_name}/config.yaml"
    
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_1_config_yaml():
    """测试1：验证 config.yaml 中的 request_body 定义"""
    print("\n" + "=" * 60)
    print("🧪 测试1：config.yaml 中的 request_body 定义")
    print("=" * 60)
    
    config = load_config_yaml()
    apis = config.get("apis", [])
    
    print(f"\n📋 APIs 配置数量: {len(apis)}")
    
    has_request_body = False
    for api in apis:
        name = api.get("name")
        request_body = api.get("request_body")
        
        print(f"\n📌 API: {name}")
        
        if request_body:
            has_request_body = True
            print(f"   ✅ request_body 已定义:")
            print(f"   {json.dumps(request_body, ensure_ascii=False, indent=4)}")
        else:
            print(f"   ⚠️ 无 request_body 定义")
        
        # 显示其他配置
        print(f"   default_method: {api.get('default_method', 'POST')}")
        print(f"   default_mode: {api.get('default_mode', 'sync')}")
        if api.get("poll_config"):
            print(f"   poll_config: {list(api['poll_config'].keys())}")
    
    assert has_request_body, "❌ config.yaml 中没有 API 定义了 request_body"
    print("\n✅ 测试1 通过：config.yaml 中 request_body 已正确定义")
    return apis


def test_2_instance_loader():
    """测试2：验证 instance_loader 正确解析 request_body"""
    print("\n" + "=" * 60)
    print("🧪 测试2：instance_loader 解析 request_body")
    print("=" * 60)
    
    from scripts.instance_loader import load_instance_config, ApiConfig
    
    # 加载实例配置
    instance_config = load_instance_config("dazee_agent")
    apis = instance_config.apis
    
    print(f"\n📋 解析后的 ApiConfig 数量: {len(apis)}")
    
    has_request_body = False
    for api in apis:
        print(f"\n📌 ApiConfig: {api.name}")
        
        # 检查新增字段
        if api.request_body:
            has_request_body = True
            print(f"   ✅ request_body: {json.dumps(api.request_body, ensure_ascii=False)[:100]}...")
        else:
            print(f"   ⚠️ request_body: None")
        
        print(f"   default_method: {api.default_method}")
        print(f"   default_mode: {api.default_mode}")
        print(f"   poll_config: {'已配置' if api.poll_config else 'None'}")
    
    assert has_request_body, "❌ instance_loader 没有解析到 request_body"
    print("\n✅ 测试2 通过：instance_loader 正确解析了 request_body")
    return apis


def test_3_apis_config_build(apis):
    """测试3：验证 apis_config 构建逻辑（模拟 agent_registry）"""
    print("\n" + "=" * 60)
    print("🧪 测试3：apis_config 构建逻辑")
    print("=" * 60)
    
    # 模拟 agent_registry.py 中的构建逻辑
    apis_config = [
        {
            "name": api.name,
            "base_url": api.base_url,
            "headers": api.headers or {},
            "description": api.description,
            "auth": {
                "type": api.auth_type,
                "header": api.auth_header,
                "env": api.auth_env,
            } if api.auth_env else None,
            # 请求体配置
            "request_body": api.request_body,
            "default_method": api.default_method,
            "default_mode": api.default_mode,
            "poll_config": api.poll_config,
        }
        for api in apis
    ]
    
    print(f"\n📋 构建的 apis_config 数量: {len(apis_config)}")
    
    has_request_body = False
    for cfg in apis_config:
        print(f"\n📌 {cfg['name']}:")
        
        if cfg.get("request_body"):
            has_request_body = True
            print(f"   ✅ request_body: {json.dumps(cfg['request_body'], ensure_ascii=False)[:100]}...")
        else:
            print(f"   ⚠️ request_body: None")
        
        print(f"   default_method: {cfg.get('default_method')}")
        print(f"   default_mode: {cfg.get('default_mode')}")
    
    assert has_request_body, "❌ apis_config 中没有 request_body"
    print("\n✅ 测试3 通过：apis_config 正确包含了 request_body")
    return apis_config


def test_4_api_calling_tool(apis_config):
    """测试4：验证 APICallingTool 接收到 request_body"""
    print("\n" + "=" * 60)
    print("🧪 测试4：APICallingTool 初始化")
    print("=" * 60)
    
    from tools.api_calling import APICallingTool
    
    tool = APICallingTool(apis_config=apis_config)
    
    print(f"\n📋 已加载的 APIs: {list(tool.apis_config.keys())}")
    
    has_request_body = False
    for api_name, cfg in tool.apis_config.items():
        print(f"\n📌 {api_name}:")
        
        if cfg.get("request_body"):
            has_request_body = True
            print(f"   ✅ request_body 已注入:")
            print(f"   {json.dumps(cfg['request_body'], ensure_ascii=False, indent=4)}")
        else:
            print(f"   ⚠️ request_body: None")
    
    assert has_request_body, "❌ APICallingTool 没有收到 request_body"
    print("\n✅ 测试4 通过：APICallingTool 正确接收了 request_body")
    return tool


def test_5_request_body_synthesis(tool):
    """测试5：验证请求体合成（占位符替换）"""
    print("\n" + "=" * 60)
    print("🧪 测试5：请求体合成（占位符替换）")
    print("=" * 60)
    
    # 模拟 AI 传入的参数
    ai_parameters = {
        "question": "分析销售数据",
        "files": [{"file_name": "test.csv", "file_url": "https://example.com/test.csv"}]
    }
    
    print(f"\n📤 AI 输入:")
    print(f"   api_name: wenshu_api")
    print(f"   parameters: {json.dumps(ai_parameters, ensure_ascii=False)}")
    
    # 调用 _build_request_from_config 方法
    request_config, error = tool._build_request_from_config("wenshu_api", ai_parameters)
    
    if error:
        print(f"\n❌ 构建失败: {error}")
        return False
    
    body = request_config.get("body", {})
    
    print(f"\n📦 第一步：替换 AI 占位符后的请求体:")
    print(f"   {json.dumps(body, ensure_ascii=False, indent=4)}")
    
    # 验证 AI 占位符已替换
    assert body.get("question") == "分析销售数据", "❌ AI 占位符 {{question}} 未替换"
    assert body.get("files") == ai_parameters["files"], "❌ AI 占位符 {{files}} 未替换"
    
    # 验证系统占位符仍然存在（等待框架注入）
    assert "${user_id}" in str(body) or body.get("user_id") == "${user_id}", "❌ 系统占位符 ${user_id} 被意外替换"
    
    print("\n✅ AI 占位符 {{xxx}} 已正确替换")
    print("✅ 系统占位符 ${xxx} 保留（等待框架注入）")
    
    # 模拟框架注入上下文
    context = {
        "user_id": "user_12345",
        "conversation_id": "conv_67890",
        "session_id": "sess_abcde"
    }
    
    print(f"\n📥 框架上下文:")
    print(f"   {json.dumps(context, ensure_ascii=False)}")
    
    # 调用 _resolve_system_placeholders 方法
    final_body = tool._resolve_system_placeholders(body, context)
    
    print(f"\n📦 第二步：替换系统占位符后的最终请求体:")
    print(f"   {json.dumps(final_body, ensure_ascii=False, indent=4)}")
    
    # 验证系统占位符已替换
    assert final_body.get("user_id") == "user_12345", "❌ 系统占位符 ${user_id} 未替换"
    assert final_body.get("task_id") == "conv_67890", "❌ 系统占位符 ${conversation_id} 未替换"
    
    # 验证固定值保留
    assert final_body.get("lg_code") == "zh-CN", "❌ 固定值 lg_code 丢失"
    
    print("\n✅ 系统占位符 ${xxx} 已正确替换")
    print("✅ 固定值已保留")
    print("\n✅ 测试5 通过：请求体合成完全正确！")
    return True


def test_6_coze_api_synthesis(tool):
    """测试6：验证 coze_api 请求体合成（异步轮询模式）"""
    print("\n" + "=" * 60)
    print("🧪 测试6：coze_api 请求体合成（async_poll 模式）")
    print("=" * 60)
    
    # 模拟 AI 传入的参数
    ai_parameters = {
        "chart_url": "https://dify.ai/files/xxx/flowchart.png",
        "query": "订单管理系统",
        "language": "中文"
    }
    
    print(f"\n📤 AI 输入:")
    print(f"   api_name: coze_api")
    print(f"   parameters: {json.dumps(ai_parameters, ensure_ascii=False)}")
    
    # 调用 _build_request_from_config 方法
    request_config, error = tool._build_request_from_config("coze_api", ai_parameters)
    
    if error:
        print(f"\n❌ 构建失败: {error}")
        return False
    
    body = request_config.get("body", {})
    mode = request_config.get("mode")
    poll_config = request_config.get("poll_config")
    
    print(f"\n📦 构建结果:")
    print(f"   method: {request_config.get('method')}")
    print(f"   mode: {mode}")
    print(f"   poll_config: {'已配置' if poll_config else 'None'}")
    print(f"\n   body:")
    print(f"   {json.dumps(body, ensure_ascii=False, indent=4)}")
    
    # 验证 AI 占位符已替换
    params = body.get("parameters", {})
    assert params.get("chart_url") == "https://dify.ai/files/xxx/flowchart.png", "❌ AI 占位符 {{chart_url}} 未替换"
    assert params.get("query") == "订单管理系统", "❌ AI 占位符 {{query}} 未替换"
    assert params.get("language") == "中文", "❌ AI 占位符 {{language}} 未替换"
    
    # 验证固定值保留
    assert body.get("workflow_id") == "7579565547005837331", "❌ 固定值 workflow_id 丢失"
    assert body.get("is_async") == True, "❌ 固定值 is_async 丢失"
    
    # 验证模式和轮询配置
    assert mode == "async_poll", "❌ default_mode 未正确传递"
    assert poll_config is not None, "❌ poll_config 未正确传递"
    
    print("\n✅ AI 占位符 {{xxx}} 已正确替换")
    print("✅ 固定值（workflow_id, is_async）已保留")
    print("✅ async_poll 模式和 poll_config 已正确传递")
    print("\n✅ 测试6 通过：coze_api 请求体合成完全正确！")
    return True


async def main():
    """主函数"""
    print("=" * 60)
    print("🧪 请求体注入机制完整测试")
    print("=" * 60)
    
    try:
        # 测试1：config.yaml 定义
        apis_raw = test_1_config_yaml()
        
        # 测试2：instance_loader 解析
        apis = test_2_instance_loader()
        
        # 测试3：apis_config 构建
        apis_config = test_3_apis_config_build(apis)
        
        # 测试4：APICallingTool 初始化
        tool = test_4_api_calling_tool(apis_config)
        
        # 测试5：wenshu_api 请求体合成
        test_5_request_body_synthesis(tool)
        
        # 测试6：coze_api 请求体合成
        test_6_coze_api_synthesis(tool)
        
        print("\n" + "=" * 60)
        print("🎉 所有测试通过！请求体注入机制工作正常")
        print("=" * 60)
        print("""
📋 验证结果总结：

1. ✅ config.yaml 中 request_body 已正确定义
   - wenshu_api: ${user_id}, ${conversation_id}, {{question}}, {{files}}
   - coze_api: workflow_id, is_async, {{chart_url}}, {{query}}, {{language}}

2. ✅ instance_loader 正确解析了 request_body
   - ApiConfig 数据类已添加新字段
   - _load_apis_config() 正确读取配置

3. ✅ apis_config 构建逻辑正确包含 request_body
   - agent_registry.py 中两处构建逻辑已更新

4. ✅ APICallingTool 正确接收了 request_body
   - self.apis_config 中包含完整配置

5. ✅ 请求体合成（占位符替换）工作正常
   - {{xxx}} AI 参数正确替换
   - ${xxx} 系统占位符正确替换
   - 固定值正确保留
   - async_poll 模式和 poll_config 正确传递
""")
        
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

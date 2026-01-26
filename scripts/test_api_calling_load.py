#!/usr/bin/env python
"""
测试 APICallingTool 是否能正确加载配置

验证：
1. 配置文件解析
2. API 配置加载
3. wenshu_api 调用
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


def load_instance_config(instance_name: str = "dazee_agent") -> dict:
    """加载实例配置"""
    config_path = f"instances/{instance_name}/config.yaml"
    
    print(f"📁 加载配置: {config_path}")
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    return config


def test_config_parse():
    """测试1：配置解析"""
    print("\n" + "=" * 60)
    print("🧪 测试1：配置文件解析")
    print("=" * 60)
    
    config = load_instance_config()
    
    # 检查 APIs 配置
    apis = config.get("apis", [])
    print(f"\n📋 APIs 配置数量: {len(apis)}")
    
    for api in apis:
        print(f"\n  📌 API: {api.get('name')}")
        print(f"     base_url: {api.get('base_url', 'N/A')[:50]}...")
        print(f"     capability: {api.get('capability', 'N/A')}")
        print(f"     doc: {api.get('doc', 'N/A')}")
        
        # 检查 body_template
        body_template = api.get("body_template", {})
        if body_template:
            print(f"     body_template 字段: {list(body_template.keys())}")
    
    return apis


def test_api_calling_tool_init(apis: list):
    """测试2：APICallingTool 初始化"""
    print("\n" + "=" * 60)
    print("🧪 测试2：APICallingTool 初始化")
    print("=" * 60)
    
    from tools.api_calling import APICallingTool
    
    tool = APICallingTool(apis_config=apis)
    
    print(f"\n✅ APICallingTool 初始化成功")
    print(f"📋 已加载的 APIs: {list(tool.apis_config.keys())}")
    
    # 检查每个 API 配置
    for api_name, api_config in tool.apis_config.items():
        print(f"\n📌 {api_name} 配置详情:")
        print(f"   base_url: {api_config.get('base_url', 'N/A')[:50]}...")
        
        # 显示 request_body 结构
        request_body = api_config.get("request_body", {})
        if request_body:
            print(f"   request_body:")
            print(f"   {json.dumps(request_body, ensure_ascii=False, indent=4)}")
    
    # 打印工具描述（这是 AI 看到的）
    print(f"\n{'=' * 60}")
    print("📝 工具描述（AI 看到的内容）:")
    print("=" * 60)
    print(tool.description)
    
    return tool


async def test_wenshu_api_call(tool):
    """测试3：调用 wenshu_api"""
    print("\n" + "=" * 60)
    print("🧪 测试3：调用 wenshu_api")
    print("=" * 60)
    
    # 检查环境变量
    api_key = os.environ.get("WENSHU_API_KEY")
    if not api_key:
        print("\n❌ WENSHU_API_KEY 环境变量未设置!")
        print("   请在 .env.development 中设置")
        return None
    
    print(f"\n✅ WENSHU_API_KEY 已设置: {api_key[:10]}...")
    
    # 测试文件
    test_file = {
        "file_name": "1fb6734f-cbe4-4228-8f18-bc0023b8314f.csv",
        "file_url": "https://dify-storage-zenflux.s3.amazonaws.com/chat-attachments/user_1768475079723/20260126/ea17e881-7104-40a4-86a3-98b4e00bca25_1fb6734f-cbe4-4228-8f18-bc0023b8314f.csv?AWSAccessKeyId=AKIAUPUSDVE22NYLK4XE&Signature=wjj9Eah4qxyRWwwRBQcgCt085R4%3D&Expires=1769498088"
    }
    
    # 构建参数（AI 会传的参数）
    parameters = {
        "question": "帮我分析一下这个数据文件",
        "files": [test_file]
    }
    
    # 模拟框架注入的上下文
    context = {
        "user_id": "user_test_001",
        "conversation_id": "conv_test_001",
        "session_id": "sess_test_001"
    }
    
    print(f"\n📤 调用参数:")
    print(f"   api_name: wenshu_api")
    print(f"   parameters: {json.dumps(parameters, ensure_ascii=False)[:200]}...")
    print(f"   context: {context}")
    
    print("\n🚀 开始调用...")
    
    try:
        result = await tool.execute(
            api_name="wenshu_api",
            parameters=parameters,
            **context  # 框架注入的上下文
        )
        
        print("\n📦 调用结果:")
        result_str = json.dumps(result, ensure_ascii=False, indent=2)
        if len(result_str) > 2000:
            print(result_str[:2000] + "...")
        else:
            print(result_str)
        
        # 检查结果
        if result.get("error"):
            print(f"\n❌ 调用失败: {result.get('error')}")
        else:
            print(f"\n✅ 调用成功!")
        
        return result
    
    except Exception as e:
        print(f"\n❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        return None


async def main():
    """主函数"""
    import sys
    
    print("=" * 60)
    print("🧪 APICallingTool 配置加载测试")
    print("=" * 60)
    
    # 测试1：配置解析
    apis = test_config_parse()
    
    # 测试2：工具初始化
    tool = test_api_calling_tool_init(apis)
    
    # 测试3：实际调用（需要 --call 参数）
    if "--call" in sys.argv:
        await test_wenshu_api_call(tool)
    else:
        print("\n💡 提示：添加 --call 参数可执行实际 API 调用测试")
    
    print("\n" + "=" * 60)
    print("🏁 测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

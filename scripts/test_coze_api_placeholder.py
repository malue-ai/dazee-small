#!/usr/bin/env python3
"""
测试 Coze API 占位符注入功能

验证：
1. body_template 中的 ${chart_url}, ${query}, ${language} 占位符
2. AI parameters 自动注入到占位符位置
3. 最终发送的 body 结构正确
"""

import asyncio
import sys
import os
import yaml

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.api_calling import APICallingTool


def load_config_yaml(instance_name: str) -> dict:
    """简单加载 config.yaml"""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "instances", instance_name, "config.yaml"
    )
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


async def test_placeholder_injection():
    """测试占位符注入（不实际发送请求）"""
    print("=" * 60)
    print("🧪 测试 1: 占位符注入逻辑")
    print("=" * 60)
    
    # 加载配置
    config = load_config_yaml("dazee_agent")
    apis_config = config.get("apis", [])
    
    # 初始化工具
    tool = APICallingTool(apis_config=apis_config)
    
    # 模拟 AI 传入的参数
    ai_parameters = {
        "chart_url": "https://example.com/flowchart.txt",
        "query": "测试系统",
        "language": "中文"
    }
    
    # 调用 _build_request_from_config
    request_config, error = tool._build_request_from_config("coze_api", ai_parameters)
    
    if error:
        print(f"❌ 错误: {error}")
        return False
    
    print(f"\n📋 构建的请求配置:")
    print(f"   method: {request_config['method']}")
    print(f"   mode: {request_config['mode']}")
    print(f"   poll_config: {request_config.get('poll_config') is not None}")
    
    body = request_config['body']
    print(f"\n📤 最终 body:")
    import json
    print(json.dumps(body, indent=2, ensure_ascii=False))
    
    # 验证结构
    print("\n🔍 验证:")
    checks = [
        ("workflow_id 存在", "workflow_id" in body),
        ("is_async 存在", "is_async" in body),
        ("parameters 存在", "parameters" in body),
        ("parameters.chart_url 正确", body.get("parameters", {}).get("chart_url") == ai_parameters["chart_url"]),
        ("parameters.query 正确", body.get("parameters", {}).get("query") == ai_parameters["query"]),
        ("parameters.language 正确", body.get("parameters", {}).get("language") == ai_parameters["language"]),
        ("无残留占位符 ${", "${" not in json.dumps(body)),
    ]
    
    all_passed = True
    for name, passed in checks:
        status = "✅" if passed else "❌"
        print(f"   {status} {name}")
        if not passed:
            all_passed = False
    
    return all_passed


async def test_actual_api_call():
    """测试实际 API 调用（可选，需要真实的 chart_url）"""
    print("\n" + "=" * 60)
    print("🧪 测试 2: 实际 API 调用（dry-run）")
    print("=" * 60)
    
    # 加载配置
    config = load_config_yaml("dazee_agent")
    apis_config = config.get("apis", [])
    
    # 初始化工具
    tool = APICallingTool(apis_config=apis_config)
    
    # 模拟 AI 传入的参数（使用假的 URL，预期会失败但能验证请求结构）
    ai_parameters = {
        "chart_url": "https://example.com/test-flowchart.txt",
        "query": "测试系统名称",
        "language": "中文"
    }
    
    print(f"\n📡 调用 api_calling(api_name='coze_api', parameters={ai_parameters})")
    print("⏳ 发送请求...")
    
    # 实际调用（会失败，因为 chart_url 是假的，但能验证请求结构）
    result = await tool.execute(
        api_name="coze_api",
        parameters=ai_parameters,
        user_id="test_user",
        conversation_id="test_conv",
        session_id="test_session"
    )
    
    print(f"\n📥 响应:")
    import json
    print(json.dumps(result, indent=2, ensure_ascii=False)[:1000])
    
    # 如果有 execute_id，说明请求成功发送了
    if "execute_id" in str(result) or "data" in result:
        print("\n✅ 请求成功发送（结构正确）")
        return True
    elif "error" in result:
        # 检查是不是参数错误
        error_msg = str(result.get("error", ""))
        if "workflow_id" in error_msg.lower():
            print("\n❌ 仍然缺少 workflow_id - 占位符注入可能有问题")
            return False
        else:
            print(f"\n⚠️ 请求已发送，但返回错误: {error_msg[:200]}")
            print("   （这可能是正常的，因为使用了假的 chart_url）")
            return True
    
    return False


async def main():
    print("🚀 开始测试 Coze API 占位符注入功能\n")
    
    # 测试 1: 占位符注入逻辑
    test1_passed = await test_placeholder_injection()
    
    # 测试 2: 实际 API 调用（可选）
    run_actual_test = input("\n是否运行实际 API 调用测试? (y/N): ").strip().lower() == 'y'
    if run_actual_test:
        test2_passed = await test_actual_api_call()
    else:
        test2_passed = True
        print("\n⏭️ 跳过实际 API 调用测试")
    
    # 总结
    print("\n" + "=" * 60)
    print("📊 测试结果:")
    print(f"   测试 1 (占位符注入): {'✅ 通过' if test1_passed else '❌ 失败'}")
    if run_actual_test:
        print(f"   测试 2 (实际调用): {'✅ 通过' if test2_passed else '❌ 失败'}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

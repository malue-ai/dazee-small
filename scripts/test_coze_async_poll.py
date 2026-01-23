#!/usr/bin/env python3
"""
Coze API 异步轮询测试脚本

测试 api_calling 工具的 async_poll 模式

使用方法:
    # 单元测试（mock 模式，无需真实 API）
    python scripts/test_coze_async_poll.py --mock
    
    # 真实 API 测试（自动从 .env 加载 COZE_API_KEY）
    python scripts/test_coze_async_poll.py --real --chart-url "https://xxx.com/chart.txt"
"""

import argparse
import asyncio
import json
import sys
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 从 .env 文件加载环境变量（按优先级尝试）
from dotenv import load_dotenv
_env_candidates = [
    PROJECT_ROOT / ".env",
    PROJECT_ROOT / ".env.development",
    PROJECT_ROOT / ".env.staging",
]
for _env_path in _env_candidates:
    if _env_path.exists():
        load_dotenv(dotenv_path=_env_path, override=True)
        print(f"✅ 已从 {_env_path} 加载环境变量")
        break

from tools.api_calling import APICallingTool


# ==================== Mock 测试 ====================

async def test_get_nested_value():
    """测试 _get_nested_value 辅助方法"""
    print("\n📋 测试 _get_nested_value...")
    
    tool = APICallingTool()
    
    # 测试用例
    test_cases = [
        # (数据, 路径, 期望值)
        ({"data": {"execute_id": "123"}}, "data.execute_id", "123"),
        ({"data": {"status": "Success"}}, "data.status", "Success"),
        ({"code": 0, "msg": "ok"}, "code", 0),
        ({"a": {"b": {"c": "deep"}}}, "a.b.c", "deep"),
        ({"data": None}, "data.execute_id", None),
        ({}, "data.execute_id", None),
        ({"data": {"execute_id": "123"}}, "nonexistent", None),
    ]
    
    passed = 0
    for data, path, expected in test_cases:
        result = tool._get_nested_value(data, path)
        status = "✅" if result == expected else "❌"
        print(f"  {status} _get_nested_value({data}, '{path}') = {result} (期望: {expected})")
        if result == expected:
            passed += 1
    
    print(f"\n  结果: {passed}/{len(test_cases)} 通过")
    return passed == len(test_cases)


async def test_poll_url_template():
    """测试 URL 模板变量替换"""
    print("\n📋 测试 URL 模板变量替换...")
    
    tool = APICallingTool()
    tool.max_polls = 1  # 只轮询一次
    tool.poll_interval = 0.1  # 缩短间隔
    
    # 模拟初始响应
    initial_response = {
        "code": 0,
        "data": {
            "execute_id": "exec_12345"
        }
    }
    
    # 请求体
    request_body = {
        "workflow_id": "wf_67890",
        "parameters": {"test": "value"},
        "is_async": True
    }
    
    # 轮询配置
    poll_config = {
        "execute_id_field": "data.execute_id",
        "status_url_template": "https://api.coze.cn/v1/workflows/{workflow_id}/run_histories/{execute_id}",
        "body_vars": ["workflow_id"],
        "status_field": "data.status",
        "success_status": "Success",
        "failed_status": "Fail"
    }
    
    # Mock aiohttp session
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={
        "code": 0,
        "data": {
            "status": "Success",
            "output": '{"entities": [], "relationships": []}'
        }
    })
    
    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_response)))
    
    # 执行测试
    result = await tool._poll_for_result(
        session=mock_session,
        initial_response=initial_response,
        poll_config=poll_config,
        headers={"Authorization": "Bearer test"},
        request_body=request_body
    )
    
    # 验证 URL 构建
    expected_url = "https://api.coze.cn/v1/workflows/wf_67890/run_histories/exec_12345"
    actual_call = mock_session.get.call_args
    
    if actual_call:
        actual_url = actual_call[0][0] if actual_call[0] else actual_call[1].get('url')
        url_correct = actual_url == expected_url
        print(f"  {'✅' if url_correct else '❌'} URL 构建: {actual_url}")
        print(f"     期望: {expected_url}")
    else:
        url_correct = False
        print(f"  ❌ 未调用 session.get")
    
    # 验证结果
    result_correct = result is not None
    print(f"  {'✅' if result_correct else '❌'} 返回结果: {result}")
    
    return url_correct and result_correct


async def test_poll_status_check():
    """测试轮询状态检查"""
    print("\n📋 测试轮询状态检查...")
    
    tool = APICallingTool()
    tool.max_polls = 5
    tool.poll_interval = 0.1
    
    # 模拟多次轮询
    poll_count = 0
    
    async def mock_json():
        nonlocal poll_count
        poll_count += 1
        if poll_count < 3:
            return {"code": 0, "data": {"status": "Running"}}
        else:
            return {
                "code": 0,
                "data": {
                    "status": "Success",
                    "output": '{"result": "done"}'
                }
            }
    
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = mock_json
    
    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_response)))
    
    result = await tool._poll_for_result(
        session=mock_session,
        initial_response={"data": {"execute_id": "test_123"}},
        poll_config={
            "execute_id_field": "data.execute_id",
            "status_url_template": "https://api.test.com/status/{execute_id}",
            "status_field": "data.status",
            "success_status": "Success"
        },
        headers={},
        request_body={}
    )
    
    print(f"  轮询次数: {poll_count}")
    print(f"  {'✅' if poll_count == 3 else '❌'} 预期轮询 3 次后成功")
    print(f"  {'✅' if result else '❌'} 返回结果: {result}")
    
    return poll_count == 3 and result is not None


async def run_mock_tests():
    """运行所有 Mock 测试"""
    print("=" * 60)
    print("🧪 运行 Mock 测试（无需真实 API）")
    print("=" * 60)
    
    results = []
    
    results.append(("_get_nested_value", await test_get_nested_value()))
    results.append(("URL 模板变量替换", await test_poll_url_template()))
    results.append(("轮询状态检查", await test_poll_status_check()))
    
    print("\n" + "=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)
    
    passed = sum(1 for _, r in results if r)
    for name, result in results:
        print(f"  {'✅' if result else '❌'} {name}")
    
    print(f"\n总计: {passed}/{len(results)} 通过")
    return passed == len(results)


# ==================== 真实 API 测试 ====================

async def test_real_coze_api(chart_url: str):
    """测试真实 Coze API（需要有效的 API Key）"""
    print("=" * 60)
    print("🌐 运行真实 API 测试")
    print("=" * 60)
    
    # 检查环境变量
    api_key = os.environ.get("COZE_API_KEY")
    if not api_key:
        print("❌ 未设置 COZE_API_KEY 环境变量")
        return False
    
    print(f"✅ COZE_API_KEY 已设置")
    print(f"📊 Chart URL: {chart_url}")
    
    # 加载 API 配置
    apis_config = [
        {
            "name": "coze_api",
            "base_url": "https://api.coze.cn/v1",
            "auth": {
                "type": "bearer",
                "header": "Authorization",
                "env": "COZE_API_KEY"
            }
        }
    ]
    
    tool = APICallingTool(apis_config=apis_config)
    
    # 调用参数
    result = await tool.execute(
        api_name="coze_api",
        path="/workflow/run",
        method="POST",
        mode="async_poll",
        body={
            "workflow_id": "7579565547005837331",
            "parameters": {
                "chart_url": chart_url,
                "query": "测试系统",
                "language": "中文"
            },
            "is_async": True
        },
        poll_config={
            "execute_id_field": "execute_id",
            "status_url_template": "https://api.coze.cn/v1/workflows/{workflow_id}/run_histories/{execute_id}",
            "body_vars": ["workflow_id"],
            "status_field": "data.status",
            "result_field": "data.output",
            "success_status": "Success",
            "failed_status": "Fail"
        }
    )
    
    print("\n📥 API 响应:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    if "error" in result:
        print(f"\n❌ 测试失败: {result.get('error')}")
        return False
    
    print("\n✅ 测试成功!")
    return True


def main():
    parser = argparse.ArgumentParser(description="Coze API 异步轮询测试")
    parser.add_argument("--mock", action="store_true", help="运行 Mock 测试（默认）")
    parser.add_argument("--real", action="store_true", help="运行真实 API 测试")
    parser.add_argument("--chart-url", help="真实测试时的 chart_url 参数")
    
    args = parser.parse_args()
    
    # 默认运行 mock 测试
    if not args.real:
        args.mock = True
    
    success = True
    
    if args.mock:
        success = asyncio.run(run_mock_tests())
    
    if args.real:
        if not args.chart_url:
            print("❌ 真实 API 测试需要 --chart-url 参数")
            sys.exit(1)
        success = asyncio.run(test_real_coze_api(args.chart_url))
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

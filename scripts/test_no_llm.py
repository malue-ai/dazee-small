#!/usr/bin/env python3
"""
无 LLM 功能测试脚本

测试内容：
1. HITL 确认流程：创建请求 → 等待响应 → 返回结果

运行方式：
    python scripts/test_no_llm.py
"""

import asyncio
import sys
import os

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from typing import Dict, Any


# ============================================================
# 测试 1: HITL 数据模型（无外部依赖）
# ============================================================

async def test_hitl_models():
    """测试 HITL 数据模型"""
    print("\n" + "=" * 60)
    print("测试 1: HITL 数据模型")
    print("=" * 60)
    
    # 直接导入数据模型（无外部依赖）
    from models.hitl import ConfirmationType, ConfirmationRequest
    
    # 1.1 测试 ConfirmationType 枚举
    print("\n📝 1.1 测试 ConfirmationType 枚举...")
    assert ConfirmationType.FORM.value == "form"
    assert ConfirmationType.TEXT_INPUT.value == "text_input"
    print(f"   ✅ FORM = '{ConfirmationType.FORM.value}'")
    print(f"   ✅ TEXT_INPUT = '{ConfirmationType.TEXT_INPUT.value}'")
    
    # 1.2 创建 ConfirmationRequest
    print("\n📝 1.2 创建 ConfirmationRequest...")
    request = ConfirmationRequest(
        request_id="test-req-001",
        question="是否确认删除文件？",
        options=["confirm", "cancel"],
        timeout=60,
        confirmation_type=ConfirmationType.FORM,
        metadata={"file_path": "/tmp/test.txt"},
        session_id="test-session-123",
        created_at=datetime.now()
    )
    
    print(f"   ✅ request_id: {request.request_id}")
    print(f"   ✅ question: {request.question}")
    print(f"   ✅ options: {request.options}")
    print(f"   ✅ timeout: {request.timeout}s")
    print(f"   ✅ confirmation_type: {request.confirmation_type.value}")
    
    # 1.3 测试 is_expired
    print("\n📝 1.3 测试 is_expired...")
    assert request.is_expired() == False, "新创建的请求不应该过期"
    print(f"   ✅ is_expired() = False (正确)")
    
    # 1.4 测试 to_dict
    print("\n📝 1.4 测试 to_dict...")
    request_dict = request.to_dict()
    assert request_dict["request_id"] == "test-req-001"
    assert request_dict["type"] == "form"
    print(f"   ✅ to_dict() 正常工作")
    
    # 1.5 测试 set_response 和 event
    print("\n📝 1.5 测试 set_response 和 asyncio.Event...")
    
    async def wait_for_response():
        """等待响应"""
        await request.wait(timeout=5)
        return request.response
    
    async def simulate_response():
        """模拟用户响应"""
        await asyncio.sleep(0.5)
        request.set_response("confirm", {"clicked_at": datetime.now().isoformat()})
    
    # 并发执行
    results = await asyncio.gather(
        wait_for_response(),
        simulate_response()
    )
    
    assert results[0] == "confirm", "响应应该是 confirm"
    assert request.response_metadata is not None, "应该有响应元数据"
    print(f"   ✅ response = '{request.response}'")
    print(f"   ✅ response_metadata = {request.response_metadata}")
    
    print("\n✅ HITL 数据模型测试全部通过！")
    return True


# ============================================================
# 测试 2: HITL 确认管理器
# ============================================================

async def test_hitl_manager():
    """测试 HITL 确认管理器"""
    print("\n" + "=" * 60)
    print("测试 2: HITL 确认管理器")
    print("=" * 60)
    
    # 注意：这需要 logger 模块，可能会有依赖
    try:
        from services.confirmation_service import (
            ConfirmationManager,
            get_confirmation_manager,
            reset_confirmation_manager
        )
        from models.hitl import ConfirmationType
    except ImportError as e:
        print(f"   ⚠️ 导入失败（可能缺少 logger 依赖）: {e}")
        print("   ⏭️ 跳过此测试")
        return None
    
    # 重置管理器
    reset_confirmation_manager()
    manager = get_confirmation_manager()
    
    test_session_id = "test-session-mgr"
    
    # 2.1 创建确认请求
    print("\n📝 2.1 通过 Manager 创建确认请求...")
    request = manager.create_request(
        question="是否继续操作？",
        options=["yes", "no"],
        timeout=5,
        confirmation_type=ConfirmationType.FORM,
        session_id=test_session_id,
        metadata={"action": "test"}
    )
    
    print(f"   ✅ 请求已创建: request_id={request.request_id}")
    
    # 2.2 获取请求
    print("\n📝 2.2 获取请求...")
    retrieved = manager.get_request(test_session_id)
    assert retrieved is not None, "应该能获取到请求"
    assert retrieved.request_id == test_session_id
    print(f"   ✅ 成功获取请求")
    
    # 2.3 获取待处理请求列表
    print("\n📝 2.3 获取待处理请求列表...")
    pending = manager.get_pending_requests()
    assert len(pending) == 1, "应该有 1 个待处理请求"
    print(f"   ✅ 待处理请求数: {len(pending)}")
    
    # 2.4 模拟响应流程
    print("\n📝 2.4 模拟响应流程...")
    
    async def wait_response():
        return await manager.wait_for_response(test_session_id, timeout=5)
    
    async def send_response():
        await asyncio.sleep(0.5)
        return manager.set_response(test_session_id, "yes", {"from": "test"})
    
    results = await asyncio.gather(wait_response(), send_response())
    
    response_result = results[0]
    set_success = results[1]
    
    assert set_success == True, "设置响应应该成功"
    assert response_result["success"] == True, "等待结果应该成功"
    assert response_result["response"] == "yes", "响应应该是 yes"
    assert response_result["timed_out"] == False, "不应该超时"
    
    print(f"   ✅ 响应设置成功: {set_success}")
    print(f"   ✅ 等待结果: success={response_result['success']}, response={response_result['response']}")
    
    # 2.5 验证请求已被清理
    print("\n📝 2.5 验证请求已被清理...")
    cleaned = manager.get_request(test_session_id)
    assert cleaned is None, "响应后请求应该被清理"
    print(f"   ✅ 请求已被清理")
    
    # 2.6 测试超时
    print("\n📝 2.6 测试超时...")
    reset_confirmation_manager()
    manager = get_confirmation_manager()
    
    manager.create_request(
        question="这个会超时",
        timeout=1,
        session_id="timeout-test"
    )
    
    timeout_result = await manager.wait_for_response("timeout-test", timeout=1)
    assert timeout_result["timed_out"] == True, "应该超时"
    print(f"   ✅ 超时测试通过: timed_out={timeout_result['timed_out']}")
    
    # 2.7 测试取消
    print("\n📝 2.7 测试取消请求...")
    reset_confirmation_manager()
    manager = get_confirmation_manager()
    
    manager.create_request(
        question="这个会被取消",
        timeout=60,
        session_id="cancel-test"
    )
    
    cancel_success = manager.cancel_request("cancel-test")
    assert cancel_success == True, "取消应该成功"
    
    cancelled_req = manager.get_request("cancel-test")
    assert cancelled_req is None, "取消后请求应该被清理"
    print(f"   ✅ 取消测试通过")
    
    # 2.8 统计信息
    print("\n📝 2.8 统计信息...")
    stats = manager.stats()
    print(f"   ✅ 统计: {stats}")
    
    print("\n✅ HITL 确认管理器测试全部通过！")
    return True


# ============================================================
# 测试 3: 简单的异步事件测试
# ============================================================

async def test_async_event():
    """测试 asyncio.Event 机制（HITL 的核心）"""
    print("\n" + "=" * 60)
    print("测试 3: asyncio.Event 机制")
    print("=" * 60)
    
    event = asyncio.Event()
    result = {"value": None}
    
    async def waiter():
        print("   ⏳ 等待事件...")
        await asyncio.wait_for(event.wait(), timeout=5)
        print("   ✅ 事件已触发")
        return "received"
    
    async def setter():
        await asyncio.sleep(0.3)
        print("   🔔 触发事件...")
        result["value"] = "set"
        event.set()
    
    print("\n📝 3.1 测试 asyncio.Event 等待和触发...")
    
    await asyncio.gather(waiter(), setter())
    
    assert result["value"] == "set"
    print(f"   ✅ 事件机制正常工作")
    
    print("\n✅ asyncio.Event 测试通过！")
    return True


# ============================================================
# 主函数
# ============================================================

async def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("🧪 无 LLM 功能测试")
    print("=" * 60)
    print(f"时间: {datetime.now().isoformat()}")
    
    results = {}
    
    # 测试 1: HITL 数据模型
    try:
        results["HITL 数据模型"] = await test_hitl_models()
    except Exception as e:
        print(f"\n❌ HITL 数据模型测试失败: {e}")
        import traceback
        traceback.print_exc()
        results["HITL 数据模型"] = False
    
    # 测试 2: HITL 管理器
    try:
        result = await test_hitl_manager()
        if result is None:
            results["HITL 管理器"] = "跳过"
        else:
            results["HITL 管理器"] = result
    except Exception as e:
        print(f"\n❌ HITL 管理器测试失败: {e}")
        import traceback
        traceback.print_exc()
        results["HITL 管理器"] = False
    
    # 测试 3: asyncio.Event
    try:
        results["asyncio.Event 机制"] = await test_async_event()
    except Exception as e:
        print(f"\n❌ asyncio.Event 测试失败: {e}")
        import traceback
        traceback.print_exc()
        results["asyncio.Event 机制"] = False
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results.items():
        if passed == "跳过":
            status = "⏭️ 跳过"
        elif passed:
            status = "✅ 通过"
        else:
            status = "❌ 失败"
            all_passed = False
        print(f"   {status} - {name}")
    
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 所有测试通过！")
    else:
        print("⚠️ 部分测试失败，请检查上方错误信息")
    print("=" * 60 + "\n")
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

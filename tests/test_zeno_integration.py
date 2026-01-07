"""
ZenO 集成测试 - 端到端测试

功能：
1. 测试从 Chat API 到 ZenO 适配器的完整流程
2. 验证事件是否正确发送到外部 ZenO 服务器

使用方法：
    # 确保 ZenO Mock Server 正在运行
    python tests/test_zeno_server.py
    
    # 在另一个终端运行集成测试
    python tests/test_zeno_integration.py
"""

import asyncio
import httpx
import time
from logger import get_logger

logger = get_logger("test_zeno_integration")

AGENT_URL = "http://localhost:8000"
ZENO_SERVER_URL = "http://localhost:8080"


async def check_zeno_server():
    """检查 ZenO Mock Server 是否在运行"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{ZENO_SERVER_URL}/", timeout=2.0)
            if response.status_code == 200:
                logger.info("✅ ZenO Mock Server 正在运行")
                return True
    except Exception as e:
        logger.error(f"❌ 无法连接到 ZenO Mock Server: {e}")
        logger.info("请先启动模拟服务器: python tests/test_zeno_server.py")
        return False
    return False


async def check_agent():
    """检查 Zenflux Agent 是否在运行"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{AGENT_URL}/health", timeout=2.0)
            if response.status_code == 200:
                logger.info("✅ Zenflux Agent 正在运行")
                return True
    except Exception as e:
        logger.error(f"❌ 无法连接到 Zenflux Agent: {e}")
        logger.info("请先启动 Agent: uvicorn main:app --reload")
        return False
    return False


async def clear_events():
    """清空之前的事件"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.delete(f"{ZENO_SERVER_URL}/events")
            if response.status_code == 200:
                data = response.json()
                logger.info(f"🗑️  已清空 {data.get('cleared', 0)} 个旧事件")
    except Exception as e:
        logger.warning(f"清空事件失败: {e}")


async def send_message(message: str, user_id: str = "test_user"):
    """
    发送消息到 Chat API（非流式模式）
    
    Args:
        message: 用户消息
        user_id: 用户ID
        
    Returns:
        响应数据
    """
    logger.info(f"\n📤 发送消息: {message}")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{AGENT_URL}/api/v1/chat",
                json={
                    "message": message,
                    "userId": user_id,
                    "stream": False  # 非流式模式，测试更简单
                },
                timeout=30.0
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"✅ 消息发送成功")
                logger.info(f"Task ID: {data.get('data', {}).get('task_id')}")
                return data
            else:
                logger.error(f"❌ 消息发送失败: {response.status_code}")
                logger.error(f"响应: {response.text}")
                return None
                
    except Exception as e:
        logger.error(f"❌ 发送消息异常: {e}")
        return None


async def get_events_summary():
    """获取事件摘要"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{ZENO_SERVER_URL}/events/summary")
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        logger.error(f"获取事件摘要失败: {e}")
    return None


async def display_events():
    """显示接收到的事件"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{ZENO_SERVER_URL}/events")
            if response.status_code == 200:
                data = response.json()
                events = data.get("events", [])
                
                logger.info(f"\n{'='*60}")
                logger.info(f"📋 接收到的事件 (共 {len(events)} 个)")
                logger.info(f"{'='*60}\n")
                
                for i, item in enumerate(events, 1):
                    event = item["event"]
                    validation = item["validation"]
                    
                    logger.info(f"事件 {i}:")
                    logger.info(f"  类型: {event.get('type')}")
                    logger.info(f"  消息ID: {event.get('message_id', 'N/A')}")
                    
                    if "delta" in event:
                        delta_type = event["delta"].get("type")
                        logger.info(f"  Delta 类型: {delta_type}")
                    
                    logger.info(f"  验证: {'✅ 通过' if validation['valid'] else '❌ 失败'}")
                    
                    if not validation["valid"]:
                        logger.warning(f"  错误:")
                        for error in validation["errors"]:
                            logger.warning(f"    - {error}")
                    
                    logger.info("")
                
    except Exception as e:
        logger.error(f"获取事件列表失败: {e}")


async def run_integration_test():
    """运行集成测试"""
    logger.info("\n" + "="*60)
    logger.info("🧪 ZenO 集成测试")
    logger.info("="*60 + "\n")
    
    # 1. 检查服务
    logger.info("步骤 1: 检查服务状态...")
    
    if not await check_zeno_server():
        return False
    
    if not await check_agent():
        return False
    
    # 2. 清空旧事件
    logger.info("\n步骤 2: 清空旧事件...")
    await clear_events()
    
    # 3. 发送测试消息
    logger.info("\n步骤 3: 发送测试消息...")
    result = await send_message("你好，请介绍一下你自己")
    
    if not result:
        logger.error("❌ 消息发送失败")
        return False
    
    # 4. 等待事件处理
    logger.info("\n步骤 4: 等待事件处理...")
    logger.info("等待 5 秒让 Agent 处理并发送事件...")
    await asyncio.sleep(5)
    
    # 5. 查看事件摘要
    logger.info("\n步骤 5: 查看事件摘要...")
    summary = await get_events_summary()
    
    if summary:
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 事件摘要")
        logger.info(f"{'='*60}")
        logger.info(f"总数: {summary['total']}")
        logger.info(f"\n按类型统计:")
        for event_type, count in summary.get("by_type", {}).items():
            logger.info(f"  {event_type}: {count}")
        
        if summary.get("by_delta_type"):
            logger.info(f"\n按 Delta 类型统计:")
            for delta_type, count in summary["by_delta_type"].items():
                logger.info(f"  {delta_type}: {count}")
        
        validation = summary.get("validation", {})
        logger.info(f"\n验证结果:")
        logger.info(f"  ✅ 有效: {validation.get('valid', 0)}")
        logger.info(f"  ❌ 无效: {validation.get('invalid', 0)}")
        logger.info(f"{'='*60}\n")
    
    # 6. 显示详细事件
    logger.info("\n步骤 6: 显示详细事件...")
    await display_events()
    
    # 7. 验证结果
    logger.info("\n步骤 7: 验证测试结果...")
    
    if not summary or summary["total"] == 0:
        logger.error("❌ 未接收到任何事件")
        logger.warning("请检查:")
        logger.warning("  1. config/webhooks.yaml 中 zeno_integration 是否已启用")
        logger.warning("  2. endpoint 是否正确 (http://localhost:8080/api/sse/events)")
        logger.warning("  3. Agent 日志中是否有事件发送错误")
        return False
    
    if summary.get("validation", {}).get("invalid", 0) > 0:
        logger.warning(f"⚠️  有 {summary['validation']['invalid']} 个事件验证失败")
    
    logger.info(f"\n✅ 集成测试完成！")
    logger.info(f"成功接收并验证了 {summary['total']} 个事件")
    
    return True


async def run_comprehensive_test():
    """运行综合测试 - 测试多种消息类型"""
    logger.info("\n" + "="*60)
    logger.info("🔬 综合测试 - 多种消息类型")
    logger.info("="*60 + "\n")
    
    test_messages = [
        "你好，请介绍一下你自己",
        "帮我生成一个关于 AI 的 PPT",
        "解释一下什么是机器学习",
    ]
    
    for i, message in enumerate(test_messages, 1):
        logger.info(f"\n--- 测试 {i}/{len(test_messages)} ---")
        await send_message(message, user_id=f"test_user_{i}")
        await asyncio.sleep(3)  # 等待事件处理
    
    # 等待所有事件处理完成
    logger.info("\n等待所有事件处理完成...")
    await asyncio.sleep(5)
    
    # 显示最终摘要
    summary = await get_events_summary()
    if summary:
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 综合测试摘要")
        logger.info(f"{'='*60}")
        logger.info(f"总事件数: {summary['total']}")
        logger.info(f"事件类型: {len(summary.get('by_type', {}))}")
        logger.info(f"Delta 类型: {len(summary.get('by_delta_type', {}))}")
        logger.info(f"验证通过: {summary.get('validation', {}).get('valid', 0)}")
        logger.info(f"{'='*60}\n")


if __name__ == "__main__":
    import sys
    
    # 解析命令行参数
    mode = "basic"
    if len(sys.argv) > 1:
        mode = sys.argv[1]
    
    if mode == "comprehensive":
        asyncio.run(run_comprehensive_test())
    else:
        success = asyncio.run(run_integration_test())
        sys.exit(0 if success else 1)


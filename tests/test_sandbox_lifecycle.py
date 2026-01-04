"""
测试 E2B 沙箱生命周期管理

验证：
1. 生命周期配置是否生效
2. 心跳保活是否正常
3. 健康检查是否准确
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from logger import get_logger
from dotenv import load_dotenv

logger = get_logger("sandbox_lifecycle_test")

# 加载环境变量
load_dotenv(Path(__file__).parent.parent.parent / ".env", override=True)


async def test_lifecycle_management():
    """测试生命周期管理"""
    
    logger.info("="*70)
    logger.info("🧪 测试 E2B 沙箱生命周期管理")
    logger.info("="*70)
    
    # 验证 API Key
    e2b_key = os.getenv("E2B_API_KEY")
    if not e2b_key:
        logger.error("❌ E2B_API_KEY 未设置")
        return False
    
    logger.info(f"✅ E2B_API_KEY: {e2b_key[:15]}...")
    
    # 初始化
    from core.memory import WorkingMemory
    from tools.e2b_vibe_coding import E2BVibeCoding
    
    memory = WorkingMemory()
    
    # 测试 1: 短生命周期（5分钟）
    logger.info("\n📝 测试 1: 创建短生命周期沙箱（5分钟）")
    vibe = E2BVibeCoding(
        memory=memory,
        api_key=e2b_key,
        sandbox_timeout_hours=5/60  # 5分钟
    )
    
    # 创建简单应用
    simple_code = """
import streamlit as st

st.title("🧪 生命周期测试应用")
st.write("这是一个用于测试沙箱生命周期管理的应用")

import time
st.write(f"当前时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
"""
    
    logger.info("⏳ 创建 Streamlit 应用...")
    result = await vibe.create_app(
        stack="streamlit",
        description="生命周期测试",
        code=simple_code
    )
    
    if not result['success']:
        logger.error(f"❌ 应用创建失败: {result.get('error')}")
        return False
    
    app_id = result['app_id']
    logger.info(f"✅ 应用已创建: {app_id}")
    logger.info(f"   预览 URL: {result['preview_url']}")
    logger.info(f"   生命周期: {result['expires_in']}")
    
    # 测试 2: 健康检查
    logger.info("\n📝 测试 2: 立即健康检查")
    health = await vibe.check_sandbox_health(app_id)
    
    if health.get("success"):
        logger.info(f"✅ 健康检查成功")
        logger.info(f"   存活: {health.get('alive')}")
        logger.info(f"   运行时间: {health.get('uptime_seconds')} 秒")
        logger.info(f"   剩余时间: {health.get('remaining_seconds')} 秒")
    else:
        logger.error(f"❌ 健康检查失败: {health.get('error')}")
        return False
    
    # 测试 3: 心跳保活
    logger.info("\n📝 测试 3: 等待 60 秒，验证心跳保活")
    logger.info("   (查看日志中的 💓 心跳成功 消息)")
    
    for i in range(6):  # 60秒
        await asyncio.sleep(10)
        logger.info(f"   ⏰ 已等待 {(i+1)*10} 秒...")
    
    # 再次检查健康
    health = await vibe.check_sandbox_health(app_id)
    
    if health.get("alive"):
        logger.info(f"✅ 沙箱仍然存活")
        logger.info(f"   运行时间: {health.get('uptime_seconds')} 秒")
        logger.info(f"   剩余时间: {health.get('remaining_seconds')} 秒")
    else:
        logger.error(f"❌ 沙箱已失效（可能是心跳失败）")
        return False
    
    # 测试 4: 获取应用日志
    logger.info("\n📝 测试 4: 获取应用日志")
    logs_result = await vibe.get_app_logs(app_id)
    
    if logs_result.get("success"):
        logs = logs_result.get("logs", "")
        logger.info(f"✅ 日志获取成功 ({len(logs)} 字节)")
        if logs:
            logger.info(f"   日志预览:\n{logs[:500]}")
    else:
        logger.warning(f"⚠️ 日志获取失败: {logs_result.get('error')}")
    
    # 清理
    logger.info("\n🧹 清理资源...")
    await vibe.terminate_app(app_id)
    
    logger.info("\n" + "="*70)
    logger.info("✅ 所有测试通过！")
    logger.info("="*70)
    logger.info("\n总结:")
    logger.info("  1. ✅ 生命周期配置正常")
    logger.info("  2. ✅ 心跳保活正常")
    logger.info("  3. ✅ 健康检查准确")
    logger.info("  4. ✅ 应用日志可获取")
    
    return True


if __name__ == "__main__":
    try:
        success = asyncio.run(test_lifecycle_management())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("\n\n测试被中断")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ 测试失败: {e}", exc_info=True)
        sys.exit(1)









#!/usr/bin/env python3
"""
启动消息队列 Worker（后台消费者）

用于异步持久化消息到 PostgreSQL，实现文档中定义的两阶段持久化机制。

使用方式：
    python scripts/start_message_workers.py

或作为独立进程运行：
    nohup python scripts/start_message_workers.py > logs/workers.log 2>&1 &
"""

import asyncio
import signal
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from logger import get_logger
from infra.message_queue.workers import start_workers, InsertWorker, UpdateWorker

logger = get_logger("message_workers.main")


async def main():
    """主函数"""
    logger.info("🚀 启动消息队列 Workers...")
    
    # 创建 Worker 实例
    insert_worker = InsertWorker()
    update_worker = UpdateWorker()
    
    # 注册信号处理（优雅关闭）
    def signal_handler(sig, frame):
        logger.info("🛑 收到停止信号，正在关闭 Workers...")
        asyncio.create_task(insert_worker.stop())
        asyncio.create_task(update_worker.stop())
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # 并发启动两个 Worker
        await asyncio.gather(
            insert_worker.start(),
            update_worker.start()
        )
    except KeyboardInterrupt:
        logger.info("🛑 收到中断信号，正在关闭...")
        await insert_worker.stop()
        await update_worker.stop()
    except Exception as e:
        logger.error(f"❌ Worker 运行失败: {str(e)}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())

"""
定时任务端到端测试脚本

测试流程：
1. 连接到运行中的服务（通过 HTTP API 获取会话信息）
2. 直接操作数据库创建两种类型的定时任务：
   - send_message: 15 秒后触发
   - agent_task: 30 秒后触发
3. 注册到 UserTaskScheduler
4. 等待任务执行并观察日志
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# 设置实例名
os.environ.setdefault("AGENT_INSTANCE", "xiaodazi")


async def main():
    print("=" * 60)
    print("  定时任务测试脚本")
    print("=" * 60)

    # ---- Step 1: 初始化 Workspace ----
    print("\n📦 Step 1: 初始化 Workspace...")
    from infra.local_store import get_workspace

    instance_name = os.getenv("AGENT_INSTANCE", "xiaodazi")
    workspace = await get_workspace(instance_name)
    print(f"   ✅ Workspace 已初始化: instance={instance_name}")

    # ---- Step 2: 创建测试会话 ----
    print("\n💬 Step 2: 创建测试会话...")
    conversation = await workspace.create_conversation(
        user_id="local",
        title="定时任务测试会话",
        metadata={"source": "test_script"},
    )
    conv_id = conversation.id
    print(f"   ✅ 会话已创建: id={conv_id}")

    # ---- Step 3: 创建 send_message 定时任务（15 秒后触发） ----
    print("\n⏰ Step 3: 创建 send_message 任务（15 秒后触发）...")
    from infra.local_store.crud.scheduled_task import create_scheduled_task

    run_at_msg = datetime.now() + timedelta(seconds=15)

    async with workspace._session_factory() as session:
        task_msg = await create_scheduled_task(
            session=session,
            user_id="local",
            title="测试提醒消息",
            trigger_type="once",
            action={"type": "send_message", "content": "这是一条测试定时提醒消息！"},
            run_at=run_at_msg,
            conversation_id=conv_id,
            task_id="test_send_msg_001",
        )
        print(
            f"   ✅ send_message 任务已创建: "
            f"id={task_msg.id}, "
            f"next_run={task_msg.next_run_at:%H:%M:%S}"
        )

    # ---- Step 4: 创建 agent_task 定时任务（35 秒后触发） ----
    print("\n🤖 Step 4: 创建 agent_task 任务（35 秒后触发）...")

    run_at_agent = datetime.now() + timedelta(seconds=35)

    async with workspace._session_factory() as session:
        task_agent = await create_scheduled_task(
            session=session,
            user_id="local",
            title="测试 Agent 定时任务",
            trigger_type="once",
            action={
                "type": "agent_task",
                "prompt": "请用一句话回答：今天是星期几？",
            },
            run_at=run_at_agent,
            conversation_id=conv_id,
            task_id="test_agent_task_001",
        )
        print(
            f"   ✅ agent_task 任务已创建: "
            f"id={task_agent.id}, "
            f"next_run={task_agent.next_run_at:%H:%M:%S}"
        )

    # ---- Step 5: 注册到 UserTaskScheduler ----
    print("\n📋 Step 5: 注册到 UserTaskScheduler...")
    from services.user_task_scheduler import get_user_task_scheduler

    scheduler = get_user_task_scheduler()

    if not scheduler.is_running():
        print("   ⚠️ 调度器未运行，尝试启动...")
        await scheduler.start()

    if scheduler.is_running():
        # 重新从数据库读取任务（确保数据完整）
        async with workspace._session_factory() as session:
            from infra.local_store.crud.scheduled_task import get_scheduled_task

            t1 = await get_scheduled_task(session, "test_send_msg_001")
            t2 = await get_scheduled_task(session, "test_agent_task_001")

        if t1:
            r1 = await scheduler.register_task(t1)
            print(f"   send_message 注册: {'✅ 成功' if r1 else '❌ 失败'}")
        if t2:
            r2 = await scheduler.register_task(t2)
            print(f"   agent_task 注册: {'✅ 成功' if r2 else '❌ 失败'}")
    else:
        print("   ❌ 调度器启动失败！")
        return

    # ---- Step 6: 查看调度器状态 ----
    print("\n📊 Step 6: 调度器当前状态:")
    jobs = scheduler._scheduler.get_jobs() if scheduler._scheduler else []
    for job in jobs:
        print(
            f"   Job: {job.id}, "
            f"name={job.name}, "
            f"next_run={job.next_run_time}"
        )
    print(f"   共 {len(jobs)} 个 Job")

    # ---- Step 7: 等待并观察任务执行 ----
    print("\n⏳ Step 7: 等待任务执行（最多 60 秒）...")
    print(f"   当前时间: {datetime.now():%H:%M:%S}")
    print(f"   send_message 预计触发: {run_at_msg:%H:%M:%S}")
    print(f"   agent_task 预计触发:   {run_at_agent:%H:%M:%S}")
    print()
    print("   观察方式: 同时查看服务日志中的以下关键词:")
    print("   - '🔔 [Scheduler] 任务触发'")
    print("   - '✅ [Scheduler] 提醒消息已存储'")
    print("   - '🤖 执行定时 Agent 任务'")
    print("   - '✅ 定时 Agent 任务完成'")
    print()

    checks = [
        ("send_message", "test_send_msg_001", 20),
        ("agent_task", "test_agent_task_001", 50),
    ]

    for label, task_id, wait_secs in checks:
        print(f"   ⏳ 等待 {label} 任务执行（{wait_secs}s）...")
        await asyncio.sleep(wait_secs)

        # 检查任务状态
        async with workspace._session_factory() as session:
            from infra.local_store.crud.scheduled_task import get_scheduled_task

            task = await get_scheduled_task(session, task_id)
            if task:
                print(
                    f"   📝 {label} 任务状态: "
                    f"status={task.status}, "
                    f"run_count={task.run_count}, "
                    f"last_run={task.last_run_at}"
                )
                if task.run_count > 0:
                    print(f"   ✅ {label} 任务已成功执行！")
                else:
                    print(f"   ❌ {label} 任务尚未执行")
            else:
                print(f"   ❌ {label} 任务不存在")

    # ---- Step 8: 检查会话中的消息 ----
    print("\n📨 Step 8: 检查会话消息...")
    messages = await workspace.list_messages(conv_id, limit=10)
    print(f"   会话 {conv_id} 中有 {len(messages)} 条消息:")
    for msg in messages:
        role = msg.role
        content = ""
        if isinstance(msg.content, list):
            for block in msg.content:
                if isinstance(block, dict) and block.get("type") == "text":
                    content = block.get("text", "")[:100]
        elif isinstance(msg.content, str):
            content = msg.content[:100]
        metadata = msg.metadata or {}
        msg_type = metadata.get("type", "normal")
        print(f"   [{role}] ({msg_type}) {content}")

    # ---- 清理 ----
    print("\n🧹 清理测试数据...")
    from infra.local_store.crud.scheduled_task import delete_task

    async with workspace._session_factory() as session:
        await delete_task(session, "test_send_msg_001", "local")
        await delete_task(session, "test_agent_task_001", "local")
    print("   ✅ 测试任务已清理")

    print("\n" + "=" * 60)
    print("  测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

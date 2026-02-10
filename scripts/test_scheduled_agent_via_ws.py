"""
通过 WebSocket 测试定时 Agent 任务

向运行中的服务发送 WebSocket 消息，让 Agent 创建一个 30 秒后触发的 agent_task 定时任务，
然后监听 WebSocket 通知来验证任务是否执行。

使用方式:
    conda activate zeno
    python scripts/test_scheduled_agent_via_ws.py
"""

import asyncio
import json
import sys
import uuid

try:
    import websockets
except ImportError:
    print("需要 websockets 库: pip install websockets")
    sys.exit(1)


BASE_PORT = "8000"
WS_URL = f"ws://127.0.0.1:{BASE_PORT}/api/v1/ws/chat"
API_BASE = f"http://127.0.0.1:{BASE_PORT}"
USER_ID = "local"


async def main():
    print("=" * 60)
    print("  通过 WebSocket 测试 Agent 定时任务")
    print("=" * 60)

    # Step 1: 连接 WebSocket
    print("\n📡 Step 1: 连接 WebSocket...")
    try:
        ws = await websockets.connect(WS_URL, ping_interval=20, ping_timeout=30)
    except Exception as e:
        print(f"   ❌ WebSocket 连接失败: {e}")
        print("   请确保服务正在运行: uvicorn main:app --host 0.0.0.0 --port 8000")
        return

    print("   ✅ WebSocket 已连接")

    # Step 2: 创建会话
    print("\n💬 Step 2: 通过 API 创建会话...")
    import httpx

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{API_BASE}/api/v1/conversations",
            params={"user_id": USER_ID, "title": "定时任务测试"},
        )
        if resp.status_code == 200:
            resp_json = resp.json()
            conv_data = resp_json.get("data", resp_json)
            conv_id = conv_data.get("id") or conv_data.get("conversation_id")
            print(f"   ✅ 会话已创建: {conv_id}")
        else:
            print(f"   ❌ 创建会话失败: {resp.status_code} {resp.text}")
            await ws.close()
            return

    # Step 3: 发送聊天消息，让 Agent 创建定时任务
    print("\n🤖 Step 3: 发送消息让 Agent 创建定时 Agent 任务...")
    message = (
        "请帮我创建一个定时任务：30 秒后执行一次 agent 任务，"
        "让 AI 回答「今天是星期几？现在几点了？」。"
        "任务标题叫「测试定时Agent」。"
    )

    req_id = str(uuid.uuid4())[:8]
    chat_frame = {
        "type": "req",
        "id": req_id,
        "method": "chat.send",
        "params": {
            "message": message,
            "conversation_id": conv_id,
            "user_id": USER_ID,
        },
    }

    await ws.send(json.dumps(chat_frame))
    print(f"   📤 已发送消息: {message[:60]}...")

    # Step 4: 接收 Agent 的流式响应
    print("\n📥 Step 4: 接收 Agent 响应...")
    full_response = ""
    got_stop = False

    try:
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=60)
            except asyncio.TimeoutError:
                print("   ⚠️ 接收超时 (60s)")
                break

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")

            # req/res 协议：event 帧
            if msg_type == "event":
                event_name = msg.get("event", "")
                payload = msg.get("payload", {})

                if event_name == "content_delta":
                    delta = payload.get("delta", "")
                    full_response += delta
                    sys.stdout.write(delta)
                    sys.stdout.flush()

                elif event_name == "message_stop":
                    got_stop = True
                    print("\n\n   ✅ Agent 响应完成")
                    break

                elif event_name == "tool_use_start":
                    tool_name = payload.get("name", "")
                    print(f"\n   🔧 Agent 调用工具: {tool_name}")

                elif event_name == "tool_result":
                    result = payload.get("result", "")
                    result_str = json.dumps(result, ensure_ascii=False)[:200] if isinstance(result, dict) else str(result)[:200]
                    print(f"   📋 工具结果: {result_str}")

                elif event_name == "error":
                    error = payload.get("message", str(payload))
                    print(f"\n   ❌ Agent 错误: {error}")
                    break

                elif event_name in ("session_start", "conversation_start", "message_start", "content_start", "content_stop", "tick"):
                    pass  # 静默

                else:
                    print(f"\n   📩 事件: {event_name}")

            elif msg_type == "res":
                ok = msg.get("ok", False)
                if not ok:
                    error = msg.get("error", {})
                    print(f"\n   ❌ 请求失败: {error}")
                    break

            elif msg_type == "pong":
                pass

    except websockets.exceptions.ConnectionClosed as e:
        print(f"\n   ⚠️ WebSocket 连接关闭: {e}")

    if not got_stop:
        print("   ⚠️ 未收到 message_stop 信号")

    # Step 5: 等待定时任务触发
    print("\n⏳ Step 5: 等待定时任务触发（最多 90 秒）...")
    print("   同时监听 WebSocket 通知...")

    notification_received = False
    try:
        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < 90:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
                msg = json.loads(raw)
                msg_type = msg.get("type", "")

                if msg_type == "notification":
                    data = msg.get("data", {})
                    print(f"\n   📢 [通知] type={data.get('notification_type')}")
                    print(f"       title={data.get('title')}")
                    print(f"       message={data.get('message', '')[:200]}")
                    print(f"       task_id={data.get('task_id')}")
                    notification_received = True
                    # 收到定时任务通知后，再等几秒看有没有更多
                    await asyncio.sleep(3)
                    break
                elif msg_type in ("chat.delta", "chat.stop", "chat.tool_use", "chat.tool_result"):
                    # Agent 执行定时任务时会产生新的聊天事件
                    if msg_type == "chat.delta":
                        delta = msg.get("data", {}).get("delta", "")
                        sys.stdout.write(delta)
                        sys.stdout.flush()
                    elif msg_type == "chat.stop":
                        print("\n   ✅ 定时 Agent 任务执行完成 (chat.stop)")
                else:
                    elapsed = int(asyncio.get_event_loop().time() - start_time)
                    # 每 10 秒打印等待状态
                    if elapsed % 10 == 0 and elapsed > 0:
                        print(f"   ⏳ 等待中... ({elapsed}s)")

            except asyncio.TimeoutError:
                elapsed = int(asyncio.get_event_loop().time() - start_time)
                if elapsed % 10 == 0:
                    print(f"   ⏳ 等待中... ({elapsed}s)")
                continue

    except websockets.exceptions.ConnectionClosed:
        print("   ⚠️ WebSocket 连接关闭")

    # Step 6: 检查会话消息
    print("\n📨 Step 6: 检查会话消息（通过 API）...")
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE}/api/v1/conversations/{conv_id}/messages",
            params={"limit": 20},
        )
        if resp.status_code == 200:
            data = resp.json()
            messages = data if isinstance(data, list) else data.get("messages", [])
            print(f"   会话中有 {len(messages)} 条消息:")
            for m in messages:
                role = m.get("role", "?")
                content = m.get("content", "")
                if isinstance(content, list):
                    text_parts = [
                        b.get("text", "")[:80]
                        for b in content
                        if isinstance(b, dict) and b.get("type") == "text"
                    ]
                    content = " ".join(text_parts)
                elif isinstance(content, str):
                    content = content[:120]
                metadata = m.get("metadata", {})
                msg_type_tag = metadata.get("type", "")
                if msg_type_tag:
                    print(f"   [{role}] ({msg_type_tag}) {content}")
                else:
                    print(f"   [{role}] {content}")
        else:
            print(f"   ❌ 获取消息失败: {resp.status_code}")

    # 关闭
    await ws.close()

    if notification_received:
        print("\n✅ 测试完成：定时任务已触发并广播通知！")
    else:
        print("\n⚠️ 测试完成：未收到 WebSocket 通知。请查看服务日志确认任务是否执行。")

    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

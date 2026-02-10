"""
Test Playbook Extraction via WebSocket - with raw event logging
"""

import asyncio
import json
import time
import uuid

import httpx
import websockets

BASE_URL = "http://127.0.0.1:8000"
WS_URL = "ws://127.0.0.1:8000/api/v1/ws/chat"
USER_ID = "test_playbook_user_3"


async def create_conversation() -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/api/v1/conversations",
            params={"user_id": USER_ID, "title": "Playbook测试v3"},
        )
        resp.raise_for_status()
        data = resp.json()
        conv_data = data.get("data", data)
        conv_id = conv_data.get("id") or conv_data.get("conversation_id")
        print(f"[INFO] 创建对话: {conv_id}")
        return conv_id


async def main():
    print("=" * 60)
    print("Playbook 提取测试 v3 (原始事件日志)")
    print("=" * 60)

    conv_id = await create_conversation()
    if not conv_id:
        return

    session_id = str(uuid.uuid4())
    print(f"[INFO] session_id: {session_id}")

    ws_url = f"{WS_URL}?session_id={session_id}"

    events_received = []
    playbook_event = asyncio.Event()

    async with websockets.connect(ws_url) as ws:
        print("[INFO] WebSocket 连接成功")

        query = "请执行 echo hello_playbook_test 命令"

        chat_msg = {
            "type": "req",
            "id": str(uuid.uuid4()),
            "method": "chat.send",
            "params": {
                "conversation_id": conv_id,
                "message": query,
                "user_id": USER_ID,
            },
        }

        print(f"\n[SEND] {query}")
        await ws.send(json.dumps(chat_msg))

        print("\n[INFO] 监听事件 (打印前 20 个原始事件)...")
        print("-" * 60)

        start_time = time.time()
        timeout = 180
        raw_count = 0
        message_stopped = False
        message_stop_time = None
        tool_events = []

        try:
            while time.time() - start_time < timeout:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                except asyncio.TimeoutError:
                    if message_stopped:
                        wait = int(time.time() - message_stop_time)
                        if wait > 45:
                            break
                        print(f"  [WAIT] playbook... ({wait}s)")
                    continue

                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                events_received.append(data)
                raw_count += 1

                frame_type = data.get("type")
                event_name = data.get("event", "")

                # Print first 20 raw events for debugging
                if raw_count <= 20:
                    truncated = json.dumps(data, ensure_ascii=False)
                    if len(truncated) > 300:
                        truncated = truncated[:300] + "..."
                    print(f"  [{raw_count}] {truncated}")

                # Track tool events
                if "tool" in event_name.lower():
                    tool_events.append(data)
                    print(f"  [TOOL EVENT] {event_name}: {json.dumps(data.get('payload', {}), ensure_ascii=False)[:200]}")

                # Track message stop
                if event_name == "message_stop":
                    message_stopped = True
                    message_stop_time = time.time()
                    print(f"\n  [DONE] message_stop 收到")

                # Track playbook
                if event_name == "playbook_suggestion":
                    print(f"\n  [PLAYBOOK] 收到!")
                    print(json.dumps(data, ensure_ascii=False, indent=2))
                    playbook_event.set()
                    break

                # Track notification (from scheduled tasks etc)
                if event_name == "notification":
                    msg = data.get("payload", {}).get("message", "")
                    print(f"  [NOTIFY] {msg}")

        except websockets.exceptions.ConnectionClosed as e:
            print(f"\n[WARN] WebSocket 断开: {e}")

    # Summary
    print("\n" + "=" * 60)
    print("汇总")
    print("=" * 60)
    print(f"总帧数: {len(events_received)}")

    # Event distribution
    event_types = {}
    for e in events_received:
        ft = e.get("type", "?")
        if ft == "event":
            en = e.get("event", "?")
            key = f"{en}"
        else:
            key = ft
        event_types[key] = event_types.get(key, 0) + 1
    print(f"事件分布: {json.dumps(event_types, ensure_ascii=False, indent=2)}")

    print(f"\n工具事件: {len(tool_events)} 个")
    for te in tool_events:
        print(f"  - {te.get('event')}: {json.dumps(te.get('payload', {}), ensure_ascii=False)[:200]}")

    if playbook_event.is_set():
        print("\n✅ Playbook 事件已收到！")
    else:
        print("\n⚠️  未收到 playbook_suggestion")

    # Check playbook dir
    import os
    pb_dir = "data/instances/xiaodazi/playbooks"
    if os.path.exists(pb_dir):
        files = os.listdir(pb_dir)
        print(f"\n📁 Playbook 目录: {files if files else '空'}")


if __name__ == "__main__":
    asyncio.run(main())

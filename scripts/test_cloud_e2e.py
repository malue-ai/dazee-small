"""
云端 Agent E2E 连通性测试

验证 CloudClient 能否成功调用远端 /api/v1/chat?format=zenflux，
收到完整 SSE 事件流并提取最终文本。

用法:
    python scripts/test_cloud_e2e.py
    python scripts/test_cloud_e2e.py --url https://agent.dazee.ai
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.cloud_client import CloudClient, CloudClientError


async def test_health(client: CloudClient) -> bool:
    """测试健康检查"""
    print("[1/3] 健康检查...")
    healthy = await client.health_check()
    if healthy:
        print("  OK: 云端可达")
    else:
        print("  FAIL: 云端不可达")
    return healthy


async def test_chat_stream(client: CloudClient) -> bool:
    """测试流式对话"""
    print("[2/3] 流式对话测试...")
    events = []
    final_text = ""
    current_block_type = None
    start = time.time()

    try:
        async for event in client.chat_stream("简单回复两个字：收到"):
            event_type = event.get("type", "")
            seq = event.get("seq", "?")
            events.append(event)

            if event_type == "content_start":
                block = event.get("data", {}).get("content_block", {})
                current_block_type = block.get("type")
                print(f"  seq={seq}  {event_type} ({current_block_type})")
            elif event_type == "content_delta":
                delta = event.get("data", {}).get("delta", "")
                if current_block_type == "text" and isinstance(delta, str):
                    final_text += delta
            elif event_type == "content_stop":
                current_block_type = None
            elif event_type in ("session_start", "message_start", "message_stop", "conversation_start"):
                print(f"  seq={seq}  {event_type}")
            elif event_type == "message_stop":
                print(f"  seq={seq}  {event_type}")
                break

    except CloudClientError as e:
        print(f"  FAIL: {e}")
        return False

    elapsed = time.time() - start
    print(f"  收到 {len(events)} 个事件，耗时 {elapsed:.1f}s")
    print(f"  最终文本: {final_text[:200]!r}")

    has_message_stop = any(e.get("type") == "message_stop" for e in events)
    has_text = bool(final_text.strip())

    if has_message_stop and has_text:
        print("  OK: SSE 流完整，文本已提取")
        return True
    else:
        if not has_message_stop:
            print("  FAIL: 未收到 message_stop 事件")
        if not has_text:
            print("  FAIL: 未提取到文本内容")
        return False


async def test_event_format(client: CloudClient) -> bool:
    """验证 zenflux 格式事件结构"""
    print("[3/3] 事件格式验证...")
    expected_types = {"session_start", "message_start", "content_start", "content_delta", "content_stop", "message_stop"}
    seen_types = set()

    try:
        async for event in client.chat_stream("回复一个字：好"):
            seen_types.add(event.get("type", ""))
            if event.get("type") == "message_stop":
                break
    except CloudClientError as e:
        print(f"  FAIL: {e}")
        return False

    missing = expected_types - seen_types
    if not missing:
        print(f"  OK: 所有期望事件类型均已收到 ({len(seen_types)} 种)")
        return True
    else:
        print(f"  WARN: 缺少事件类型: {missing}")
        print(f"  收到的类型: {seen_types}")
        return len(missing) <= 1


async def main(cloud_url: str, username: str = "", password: str = ""):
    print(f"云端 E2E 测试 — 目标: {cloud_url}")
    print("=" * 60)

    client = CloudClient(
        cloud_url=cloud_url,
        username=username or None,
        password=password or None,
    )

    results = []
    try:
        results.append(("健康检查", await test_health(client)))
        if results[-1][1]:
            if username and password:
                print("[*] 使用凭据登录...")
                try:
                    await client.login()
                    print(f"  OK: 登录成功, user_id={client.user_id}")
                    results.append(("登录认证", True))
                except CloudClientError as e:
                    print(f"  FAIL: 登录失败: {e}")
                    results.append(("登录认证", False))

            results.append(("流式对话", await test_chat_stream(client)))
            results.append(("事件格式", await test_event_format(client)))
        else:
            print("\n跳过后续测试（云端不可达）")
    finally:
        await client.close()

    print("\n" + "=" * 60)
    print("测试结果汇总:")
    all_pass = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        if not passed:
            all_pass = False

    if all_pass:
        print("\n所有测试通过")
    else:
        print("\n存在失败项")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="云端 Agent E2E 连通性测试")
    parser.add_argument(
        "--url",
        default="https://agent.dazee.ai",
        help="云端 Agent URL（默认: https://agent.dazee.ai）",
    )
    parser.add_argument("--username", default="", help="云端用户名（可选）")
    parser.add_argument("--password", default="", help="云端密码（可选）")
    args = parser.parse_args()
    asyncio.run(main(args.url, args.username, args.password))

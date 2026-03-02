"""
飞书电话加急测试脚本

使用方式：
  1. 填入 APP_ID / APP_SECRET
  2. 填入目标用户的 open_id（在飞书开放平台的日志中可以看到）
  3. 运行: .venv/bin/python scripts/test_feishu_urgent_phone.py
"""

import json
import sys

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    UrgentPhoneMessageRequest,
    UrgentReceivers,
)

# ============ 填入你的配置 ============
APP_ID = "cli_a92e5790ec799bcd"
APP_SECRET = "TwG3hNqKNJsEACClBceEmgsZwjQqEW6o"
TARGET_USER_OPEN_ID = "ou_5e6863a9588e4c91d5e7512519b2d7dd"  # 汪康成
# ======================================

MESSAGE_TEXT = "这是一条电话加急测试消息"


def main():
    if not APP_ID or not APP_SECRET:
        print("请先填入 APP_ID 和 APP_SECRET")
        sys.exit(1)
    if not TARGET_USER_OPEN_ID:
        print("请先填入 TARGET_USER_OPEN_ID")
        sys.exit(1)

    client = lark.Client.builder() \
        .app_id(APP_ID) \
        .app_secret(APP_SECRET) \
        .log_level(lark.LogLevel.DEBUG) \
        .build()

    # Step 1: 先给用户发一条消息
    print(f"[1/2] 发送消息给 {TARGET_USER_OPEN_ID} ...")

    send_req = CreateMessageRequest.builder() \
        .receive_id_type("open_id") \
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(TARGET_USER_OPEN_ID)
            .msg_type("text")
            .content(json.dumps({"text": MESSAGE_TEXT}))
            .build()
        ).build()

    send_resp = client.im.v1.message.create(send_req)

    if not send_resp.success():
        print(f"发送消息失败: code={send_resp.code}, msg={send_resp.msg}")
        sys.exit(1)

    message_id = send_resp.data.message_id
    print(f"  消息发送成功, message_id={message_id}")

    # Step 2: 对该消息发起电话加急
    print(f"[2/2] 对消息发起电话加急 ...")

    urgent_req = UrgentPhoneMessageRequest.builder() \
        .message_id(message_id) \
        .user_id_type("open_id") \
        .request_body(
            UrgentReceivers.builder()
            .user_id_list([TARGET_USER_OPEN_ID])
            .build()
        ).build()

    urgent_resp = client.im.v1.message.urgent_phone(urgent_req)

    if not urgent_resp.success():
        print(f"电话加急失败: code={urgent_resp.code}, msg={urgent_resp.msg}")
        sys.exit(1)

    print("电话加急发送成功！对方应该会收到电话通知。")


if __name__ == "__main__":
    main()

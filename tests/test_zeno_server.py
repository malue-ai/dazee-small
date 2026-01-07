"""
模拟 ZenO 服务器 - 接收并验证事件

功能：
1. 启动 HTTP 服务器监听 8080 端口
2. 接收来自 Zenflux Agent 的事件
3. 验证事件格式是否符合 ZenO 规范

使用方法：
    # 终端 1: 启动模拟服务器
    python tests/test_zeno_server.py
    
    # 终端 2: 启动 Zenflux Agent 并发送消息
    # Agent 会自动将事件推送到此服务器
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn
from datetime import datetime
from logger import get_logger

logger = get_logger("zeno_mock_server")

app = FastAPI(title="ZenO Mock Server")

# 存储接收到的事件
received_events = []


@app.get("/")
async def root():
    """首页"""
    return {
        "service": "ZenO Mock Server",
        "status": "running",
        "received_events": len(received_events),
        "endpoint": "/api/sse/events"
    }


@app.post("/api/sse/events")
async def receive_event(request: Request):
    """
    接收来自 Zenflux Agent 的事件
    
    验证事件格式是否符合 ZenO SSE 规范 v2.0.1
    """
    try:
        # 解析请求体
        event = await request.json()
        
        # 记录接收时间
        event["_received_at"] = datetime.now().isoformat()
        
        # 获取请求头
        headers = dict(request.headers)
        
        logger.info(f"\n{'='*60}")
        logger.info(f"📥 接收到事件")
        logger.info(f"{'='*60}")
        logger.info(f"类型: {event.get('type')}")
        logger.info(f"消息ID: {event.get('message_id', 'N/A')}")
        logger.info(f"时间戳: {event.get('timestamp', 'N/A')}")
        
        if "delta" in event:
            delta_type = event["delta"].get("type")
            logger.info(f"Delta 类型: {delta_type}")
        
        logger.info(f"请求头:")
        logger.info(f"  X-Source: {headers.get('x-source', 'N/A')}")
        logger.info(f"  X-Version: {headers.get('x-version', 'N/A')}")
        
        # 验证事件格式
        validation_result = validate_zeno_event(event)
        
        if validation_result["valid"]:
            logger.info(f"✅ 事件格式验证通过")
        else:
            logger.warning(f"⚠️  事件格式验证失败:")
            for error in validation_result["errors"]:
                logger.warning(f"   - {error}")
        
        # 保存事件
        received_events.append({
            "event": event,
            "headers": headers,
            "validation": validation_result
        })
        
        logger.info(f"{'='*60}\n")
        
        # 返回成功响应
        return JSONResponse(
            status_code=200,
            content={
                "status": "received",
                "event_type": event.get("type"),
                "valid": validation_result["valid"]
            }
        )
        
    except Exception as e:
        logger.error(f"❌ 处理事件失败: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


def validate_zeno_event(event: dict) -> dict:
    """
    验证事件是否符合 ZenO SSE 规范 v2.0.1
    
    Returns:
        {"valid": bool, "errors": list}
    """
    errors = []
    
    # 检查必填字段
    if "type" not in event:
        errors.append("缺少 type 字段")
    else:
        event_type = event["type"]
        
        # 验证事件类型
        valid_types = [
            "message.assistant.created",
            "message.assistant.start",
            "message.assistant.delta",
            "message.assistant.done",
            "message.assistant.error"
        ]
        
        if event_type not in valid_types:
            errors.append(f"无效的事件类型: {event_type}")
    
    if "message_id" not in event:
        errors.append("缺少 message_id 字段")
    
    if "timestamp" not in event:
        errors.append("缺少 timestamp 字段")
    
    # 如果是 delta 事件，检查 delta 字段
    if event.get("type") == "message.assistant.delta":
        if "delta" not in event:
            errors.append("delta 事件缺少 delta 字段")
        else:
            delta = event["delta"]
            if "type" not in delta:
                errors.append("delta 缺少 type 字段")
            else:
                # 验证 delta 类型
                valid_delta_types = [
                    "intent", "preface", "thinking", "response",
                    "progress", "clue", "files", "mind",
                    "sql", "data", "chart", "recommended", "application"
                ]
                if delta["type"] not in valid_delta_types:
                    errors.append(f"无效的 delta 类型: {delta['type']}")
            
            if "content" not in delta:
                errors.append("delta 缺少 content 字段")
    
    # 如果是 error 事件，检查 error 字段
    if event.get("type") == "message.assistant.error":
        if "error" not in event:
            errors.append("error 事件缺少 error 字段")
        else:
            error_obj = event["error"]
            required_error_fields = ["type", "code", "message"]
            for field in required_error_fields:
                if field not in error_obj:
                    errors.append(f"error 对象缺少 {field} 字段")
    
    return {
        "valid": len(errors) == 0,
        "errors": errors
    }


@app.get("/events")
async def list_events():
    """
    查看接收到的所有事件
    """
    return {
        "total": len(received_events),
        "events": received_events
    }


@app.delete("/events")
async def clear_events():
    """
    清空接收到的事件
    """
    count = len(received_events)
    received_events.clear()
    logger.info(f"🗑️  已清空 {count} 个事件")
    return {"cleared": count}


@app.get("/events/summary")
async def events_summary():
    """
    事件摘要统计
    """
    summary = {
        "total": len(received_events),
        "by_type": {},
        "by_delta_type": {},
        "validation": {
            "valid": 0,
            "invalid": 0
        }
    }
    
    for item in received_events:
        event = item["event"]
        event_type = event.get("type", "unknown")
        
        # 统计事件类型
        summary["by_type"][event_type] = summary["by_type"].get(event_type, 0) + 1
        
        # 统计 delta 类型
        if event_type == "message.assistant.delta":
            delta_type = event.get("delta", {}).get("type", "unknown")
            summary["by_delta_type"][delta_type] = summary["by_delta_type"].get(delta_type, 0) + 1
        
        # 统计验证结果
        if item["validation"]["valid"]:
            summary["validation"]["valid"] += 1
        else:
            summary["validation"]["invalid"] += 1
    
    return summary


if __name__ == "__main__":
    logger.info("="*60)
    logger.info("🚀 启动 ZenO 模拟服务器")
    logger.info("="*60)
    logger.info("监听地址: http://localhost:8080")
    logger.info("事件接收端点: http://localhost:8080/api/sse/events")
    logger.info("查看事件: http://localhost:8080/events")
    logger.info("事件摘要: http://localhost:8080/events/summary")
    logger.info("="*60 + "\n")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8080,
        log_level="info"
    )


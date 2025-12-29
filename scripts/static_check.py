"""
静态检查脚本 - 验证文件和代码结构（不需要导入）
"""

import os
import re


def check_file_exists(filepath):
    """检查文件是否存在"""
    return os.path.exists(filepath)


def check_file_contains(filepath, patterns):
    """检查文件是否包含指定的模式"""
    if not os.path.exists(filepath):
        return False, []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    results = []
    for pattern_name, pattern in patterns:
        if re.search(pattern, content, re.MULTILINE):
            results.append((pattern_name, True))
        else:
            results.append((pattern_name, False))
    
    return True, results


def main():
    print("=" * 70)
    print("SSE 重连机制 - 静态完整性检查")
    print("=" * 70)
    
    base_dir = "/Users/wangkangcheng/projects/zenflux_agent"
    
    checks_passed = 0
    checks_total = 0
    
    # 1. 检查文件是否存在
    print("\n" + "=" * 70)
    print("1. 检查文件是否存在")
    print("=" * 70)
    
    files_to_check = [
        ("services/redis_manager.py", "Redis Session 管理器"),
        ("services/chat_service.py", "Chat Service"),
        ("routers/chat.py", "Chat Router"),
        ("requirements.txt", "依赖配置"),
        ("docs/04-SESSION-RECONNECT-DESIGN.md", "设计文档"),
        ("docs/CHATSERVICE_REFACTOR.md", "Service 重构文档"),
        ("docs/ROUTER_REFACTOR.md", "Router 重构文档"),
        ("docs/QUICK_START.md", "快速开始"),
        ("docs/IMPLEMENTATION_SUMMARY.md", "实现总结"),
    ]
    
    for filepath, description in files_to_check:
        full_path = os.path.join(base_dir, filepath)
        checks_total += 1
        if check_file_exists(full_path):
            size = os.path.getsize(full_path)
            print(f"✅ {description}: {filepath} ({size:,} bytes)")
            checks_passed += 1
        else:
            print(f"❌ {description}: {filepath} - 文件不存在")
    
    # 2. 检查 RedisSessionManager 的方法
    print("\n" + "=" * 70)
    print("2. 检查 RedisSessionManager 关键方法")
    print("=" * 70)
    
    redis_manager_path = os.path.join(base_dir, "services/redis_manager.py")
    redis_methods = [
        ("create_session", r"def create_session\("),
        ("get_session_status", r"def get_session_status\("),
        ("update_session_status", r"def update_session_status\("),
        ("complete_session", r"def complete_session\("),
        ("update_heartbeat", r"def update_heartbeat\("),
        ("generate_event_id", r"def generate_event_id\("),
        ("buffer_event", r"def buffer_event\("),
        ("get_events", r"def get_events\("),
        ("get_user_sessions", r"def get_user_sessions\("),
        ("cleanup_timeout_sessions", r"def cleanup_timeout_sessions\("),
    ]
    
    exists, results = check_file_contains(redis_manager_path, redis_methods)
    if exists:
        for method_name, found in results:
            checks_total += 1
            if found:
                print(f"✅ {method_name}")
                checks_passed += 1
            else:
                print(f"❌ {method_name} - 未找到")
    else:
        print(f"❌ 文件不存在: {redis_manager_path}")
        checks_total += len(redis_methods)
    
    # 3. 检查 ChatService 的关键方法
    print("\n" + "=" * 70)
    print("3. 检查 ChatService 关键方法")
    print("=" * 70)
    
    chat_service_path = os.path.join(base_dir, "services/chat_service.py")
    chat_service_methods = [
        ("create_session", r"def create_session\("),
        ("get_session_status", r"def get_session_status\("),
        ("get_session_events", r"def get_session_events\("),
        ("get_user_sessions", r"def get_user_sessions\("),
        ("chat_sync", r"async def chat_sync\("),
        ("chat_stream", r"async def chat_stream\("),
        ("end_session", r"def end_session\("),
        ("Redis 集成", r"from services\.redis_manager import get_redis_manager"),
        ("Redis 初始化", r"self\.redis = get_redis_manager\(\)"),
    ]
    
    exists, results = check_file_contains(chat_service_path, chat_service_methods)
    if exists:
        for method_name, found in results:
            checks_total += 1
            if found:
                print(f"✅ {method_name}")
                checks_passed += 1
            else:
                print(f"❌ {method_name} - 未找到")
    else:
        print(f"❌ 文件不存在: {chat_service_path}")
        checks_total += len(chat_service_methods)
    
    # 4. 检查 Router 的新端点
    print("\n" + "=" * 70)
    print("4. 检查 Router 新增的端点")
    print("=" * 70)
    
    router_path = os.path.join(base_dir, "routers/chat.py")
    router_endpoints = [
        ("GET /chat/stream", r'@router\.get\(["\']\/chat\/stream'),
        ("GET /session/{id}/status", r'@router\.get\(["\']\/session\/\{session_id\}\/status'),
        ("GET /session/{id}/events", r'@router\.get\(["\']\/session\/\{session_id\}\/events'),
        ("GET /user/{id}/sessions", r'@router\.get\(["\']\/user\/\{user_id\}\/sessions'),
        ("user_id 验证", r'if not request\.user_id:'),
        ("Query 导入", r'from fastapi import.*Query'),
    ]
    
    exists, results = check_file_contains(router_path, router_endpoints)
    if exists:
        for endpoint_name, found in results:
            checks_total += 1
            if found:
                print(f"✅ {endpoint_name}")
                checks_passed += 1
            else:
                print(f"❌ {endpoint_name} - 未找到")
    else:
        print(f"❌ 文件不存在: {router_path}")
        checks_total += len(router_endpoints)
    
    # 5. 检查 requirements.txt
    print("\n" + "=" * 70)
    print("5. 检查 requirements.txt")
    print("=" * 70)
    
    requirements_path = os.path.join(base_dir, "requirements.txt")
    requirements = [
        ("redis", r'redis>='),
        ("fastapi", r'fastapi=='),
        ("anthropic", r'anthropic>='),
    ]
    
    exists, results = check_file_contains(requirements_path, requirements)
    if exists:
        for req_name, found in results:
            checks_total += 1
            if found:
                print(f"✅ {req_name}")
                checks_passed += 1
            else:
                print(f"❌ {req_name} - 未添加")
    else:
        print(f"❌ 文件不存在: {requirements_path}")
        checks_total += len(requirements)
    
    # 6. 统计代码行数
    print("\n" + "=" * 70)
    print("6. 代码统计")
    print("=" * 70)
    
    code_files = [
        "services/redis_manager.py",
        "services/chat_service.py",
        "routers/chat.py",
    ]
    
    total_lines = 0
    for filepath in code_files:
        full_path = os.path.join(base_dir, filepath)
        if os.path.exists(full_path):
            with open(full_path, 'r', encoding='utf-8') as f:
                lines = len(f.readlines())
                total_lines += lines
                print(f"📄 {filepath}: {lines} 行")
    
    print(f"\n总计代码行数: {total_lines} 行")
    
    # 7. 统计文档大小
    print("\n" + "=" * 70)
    print("7. 文档统计")
    print("=" * 70)
    
    doc_files = [
        "docs/04-SESSION-RECONNECT-DESIGN.md",
        "docs/CHATSERVICE_REFACTOR.md",
        "docs/ROUTER_REFACTOR.md",
        "docs/QUICK_START.md",
        "docs/IMPLEMENTATION_SUMMARY.md",
    ]
    
    total_doc_size = 0
    for filepath in doc_files:
        full_path = os.path.join(base_dir, filepath)
        if os.path.exists(full_path):
            size = os.path.getsize(full_path)
            total_doc_size += size
            with open(full_path, 'r', encoding='utf-8') as f:
                lines = len(f.readlines())
            print(f"📝 {os.path.basename(filepath)}: {size:,} bytes ({lines} 行)")
    
    print(f"\n总计文档大小: {total_doc_size:,} bytes")
    
    # 总结
    print("\n" + "=" * 70)
    print("检查总结")
    print("=" * 70)
    
    percentage = (checks_passed / checks_total * 100) if checks_total > 0 else 0
    
    print(f"\n通过率: {checks_passed}/{checks_total} ({percentage:.1f}%)")
    
    if checks_passed == checks_total:
        print("\n🎉 所有检查通过！")
        print("\n实现完成：")
        print(f"  • 代码文件: 3 个 ({total_lines} 行)")
        print(f"  • 文档文件: 5 个 ({total_doc_size:,} bytes)")
        print(f"  • 新增 API: 4 个")
        print(f"  • Redis 方法: 10+ 个")
        print("\n下一步：")
        print("  1. 安装依赖: pip install redis")
        print("  2. 启动 Redis: docker run -d --name zenflux-redis -p 6379:6379 redis:latest")
        print("  3. 启动服务: python main.py")
        return 0
    else:
        print(f"\n⚠️ {checks_total - checks_passed} 项检查未通过")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())


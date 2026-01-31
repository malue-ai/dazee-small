"""
快速检查脚本 - 验证 SSE 重连机制的所有组件
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def check_imports():
    """检查所有必要的模块是否可以导入"""
    print("=" * 60)
    print("1. 检查模块导入")
    print("=" * 60)
    
    try:
        from services.redis_manager import RedisSessionManager, get_redis_manager
        print("✅ redis_manager 模块导入成功")
    except ImportError as e:
        print(f"❌ redis_manager 模块导入失败: {e}")
        return False
    
    try:
        from services.chat_service import ChatService, get_chat_service
        print("✅ chat_service 模块导入成功")
    except ImportError as e:
        print(f"❌ chat_service 模块导入失败: {e}")
        return False
    
    try:
        from routers.chat import router
        print("✅ chat router 模块导入成功")
    except ImportError as e:
        print(f"❌ chat router 模块导入失败: {e}")
        return False
    
    return True


def check_redis_manager():
    """检查 RedisSessionManager 的方法"""
    print("\n" + "=" * 60)
    print("2. 检查 RedisSessionManager 方法")
    print("=" * 60)
    
    from services.redis_manager import RedisSessionManager
    
    required_methods = [
        'create_session',
        'get_session_status',
        'update_session_status',
        'complete_session',
        'update_heartbeat',
        'generate_event_id',
        'buffer_event',
        'get_events',
        'get_user_sessions',
        'get_user_sessions_detail',
        'cleanup_timeout_sessions'
    ]
    
    for method in required_methods:
        if hasattr(RedisSessionManager, method):
            print(f"✅ {method}")
        else:
            print(f"❌ {method} - 缺失")
            return False
    
    return True


def check_chat_service():
    """检查 ChatService 的方法"""
    print("\n" + "=" * 60)
    print("3. 检查 ChatService 方法")
    print("=" * 60)
    
    from services.chat_service import ChatService
    
    required_methods = [
        'create_session',
        'get_agent',
        'end_session',
        'get_session_status',
        'get_session_events',
        'get_user_sessions',
        'chat_sync',
        'chat_stream',
        'cleanup_inactive_sessions'
    ]
    
    for method in required_methods:
        if hasattr(ChatService, method):
            print(f"✅ {method}")
        else:
            print(f"❌ {method} - 缺失")
            return False
    
    return True


def check_router_endpoints():
    """检查 Router 的端点"""
    print("\n" + "=" * 60)
    print("4. 检查 Router 端点")
    print("=" * 60)
    
    from routers.chat import router
    
    # 获取所有路由
    routes = []
    for route in router.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            for method in route.methods:
                routes.append(f"{method} {route.path}")
    
    required_endpoints = [
        "POST /chat",
        "GET /chat/stream",
        "GET /session/{session_id}/status",
        "GET /session/{session_id}/events",
        "GET /user/{user_id}/sessions",
    ]
    
    for endpoint in required_endpoints:
        if any(endpoint in route for route in routes):
            print(f"✅ {endpoint}")
        else:
            print(f"❌ {endpoint} - 缺失")
            return False
    
    return True


def check_dependencies():
    """检查 Python 依赖"""
    print("\n" + "=" * 60)
    print("5. 检查 Python 依赖")
    print("=" * 60)
    
    try:
        import redis
        print(f"✅ redis - 版本 {redis.__version__}")
    except ImportError:
        print("❌ redis - 未安装")
        print("   请运行: pip install redis")
        return False
    
    try:
        import fastapi
        print(f"✅ fastapi - 版本 {fastapi.__version__}")
    except ImportError:
        print("❌ fastapi - 未安装")
        return False
    
    try:
        import pydantic
        print(f"✅ pydantic - 版本 {pydantic.__version__}")
    except ImportError:
        print("❌ pydantic - 未安装")
        return False
    
    return True


def check_documentation():
    """检查文档文件"""
    print("\n" + "=" * 60)
    print("6. 检查文档文件")
    print("=" * 60)
    
    docs_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs")
    
    required_docs = [
        "04-SSE-CONNECTION-MANAGEMENT.md",
        "CHATSERVICE_REFACTOR.md",
        "ROUTER_REFACTOR.md",
        "QUICK_START.md",
        "IMPLEMENTATION_SUMMARY.md"
    ]
    
    for doc in required_docs:
        doc_path = os.path.join(docs_path, doc)
        if os.path.exists(doc_path):
            size = os.path.getsize(doc_path)
            print(f"✅ {doc} ({size:,} bytes)")
        else:
            print(f"❌ {doc} - 缺失")
            return False
    
    return True


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("SSE 重连机制 - 完整性检查")
    print("=" * 60)
    
    checks = [
        ("模块导入", check_imports),
        ("RedisSessionManager", check_redis_manager),
        ("ChatService", check_chat_service),
        ("Router 端点", check_router_endpoints),
        ("Python 依赖", check_dependencies),
        ("文档文件", check_documentation),
    ]
    
    results = []
    for name, check_func in checks:
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ {name} 检查失败: {str(e)}")
            results.append((name, False))
    
    # 总结
    print("\n" + "=" * 60)
    print("检查总结")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status} - {name}")
    
    print("\n" + "=" * 60)
    print(f"总计: {passed}/{total} 项通过")
    print("=" * 60)
    
    if passed == total:
        print("\n🎉 所有检查通过！系统已准备就绪。")
        print("\n下一步：")
        print("1. 启动 Redis: docker run -d --name zenflux-redis -p 6379:6379 redis:latest")
        print("2. 启动服务: python main.py")
        print("3. 测试: curl -N 'http://localhost:8000/api/v1/chat/stream?message=测试&user_id=user_001'")
        return 0
    else:
        print("\n⚠️ 部分检查未通过，请查看上面的错误信息。")
        return 1


if __name__ == "__main__":
    sys.exit(main())


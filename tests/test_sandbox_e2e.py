"""
沙盒工具端到端测试

测试流程：
1. sandbox_create_project - 初始化项目骨架（Initialize project）
2. sandbox_run_project - 运行项目并获取 preview_url（推荐方式）
"""

import asyncio
import sys
import os

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.sandbox_tools import SandboxCreateProject, SandboxRunProject


async def test_sandbox_tools():
    """测试沙盒工具"""
    conversation_id = f"test_e2e_{int(asyncio.get_event_loop().time())}"
    project_name = "test_vue_app"
    project_path = f"/home/user/{project_name}"
    
    print("=" * 60)
    print("🧪 沙盒工具端到端测试")
    print("=" * 60)
    print(f"📌 conversation_id: {conversation_id}")
    print(f"📁 project_path: {project_path}")
    print()
    
    # 1. 初始化项目
    print("1️⃣ 测试 sandbox_create_project...")
    create_tool = SandboxCreateProject()
    result = await create_tool.execute(
        conversation_id=conversation_id,
        project_name=project_name,
        stack="vue",
        overwrite=True,
    )
    print(f"   初始化项目: {'✅' if result['success'] else '❌'}")
    if not result["success"]:
        print(f"   错误: {result.get('error')}")
        return False

    # 2. 运行项目
    print("2️⃣ 测试 sandbox_run_project...")
    run_tool = SandboxRunProject()
    result = await run_tool.execute(
        conversation_id=conversation_id,
        project_path=project_path,
        stack="vue",
    )
    
    print(f"   运行项目: {'✅' if result['success'] else '❌'}")
    if result["success"]:
        print(f"   🌐 预览 URL: {result.get('preview_url')}")
    else:
        print(f"   错误: {result.get('error') or result.get('message')}")
    
    print()
    print("=" * 60)
    print("✅ 测试完成!" if result["success"] else "❌ 测试失败")
    print("=" * 60)
    
    return result["success"]


if __name__ == "__main__":
    # 加载环境变量
    from dotenv import load_dotenv
    load_dotenv()
    
    # 检查 E2B_API_KEY
    if not os.getenv("E2B_API_KEY"):
        print("❌ 错误: E2B_API_KEY 未设置")
        print("请在 .env 文件中设置 E2B_API_KEY")
        sys.exit(1)
    
    # 运行测试
    success = asyncio.run(test_sandbox_tools())
    sys.exit(0 if success else 1)


"""
验证 bash 工具是否正确在沙盒中执行

测试目标：
1. 确认 bash 命令在 E2B 沙盒中执行，而不是本地
2. 确认 str_replace_based_edit_tool 在沙盒中写文件
3. 确认返回的路径是沙盒路径（/home/user），而不是本地路径
"""

import asyncio
import os
import sys

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from logger import get_logger

logger = get_logger("test_sandbox_bash")


async def test_sandbox_bash():
    """测试 bash 工具在沙盒中执行"""
    
    print("\n" + "=" * 60)
    print("🧪 测试 1: 验证 bash 工具在沙盒中执行")
    print("=" * 60)
    
    # 检查 E2B API Key
    e2b_key = os.getenv("E2B_API_KEY")
    if not e2b_key:
        print("❌ E2B_API_KEY 未设置，跳过测试")
        return False
    print(f"✅ E2B_API_KEY: {e2b_key[:15]}...")
    
    # 导入沙盒模块
    from infra.sandbox import get_sandbox_provider, sandbox_run_command
    
    sandbox = get_sandbox_provider()
    print(f"✅ 沙盒提供者: {sandbox.provider_name}")
    print(f"✅ 沙盒可用: {sandbox.is_available}")
    
    if not sandbox.is_available:
        print("❌ 沙盒服务不可用")
        return False
    
    # 测试会话 ID
    test_conv_id = "test_bash_" + str(int(asyncio.get_event_loop().time()))
    test_user_id = "test_user"
    
    try:
        # 1. 创建沙盒
        print("\n📦 创建沙盒...")
        sandbox_info = await sandbox.ensure_sandbox(test_conv_id, test_user_id)
        print(f"   沙盒 ID: {sandbox_info.provider_sandbox_id}")
        print(f"   状态: {sandbox_info.status}")
        
        # 2. 测试 bash 命令 - 打印当前工作目录
        print("\n🐚 测试 bash: pwd")
        result = await sandbox.run_command(test_conv_id, "pwd")
        print(f"   成功: {result.success}")
        print(f"   输出: {result.output.strip()}")
        
        # 验证是沙盒路径，不是本地路径
        if "/home/user" in result.output or "/root" in result.output:
            print("   ✅ 确认是沙盒路径！")
        elif "/Users/" in result.output or "/home/" in result.output:
            print("   ❌ 警告：可能是本地路径！")
            return False
        
        # 3. 测试 bash 命令 - 打印用户名
        print("\n🐚 测试 bash: whoami")
        result = await sandbox.run_command(test_conv_id, "whoami")
        print(f"   输出: {result.output.strip()}")
        
        # 验证不是本地用户
        local_user = os.getenv("USER", "")
        if local_user and local_user in result.output:
            print(f"   ❌ 警告：返回了本地用户名 '{local_user}'！")
            return False
        else:
            print(f"   ✅ 用户名不是本地用户 '{local_user}'")
        
        # 4. 测试写入文件
        print("\n📄 测试写入文件到 /home/user/test.txt")
        await sandbox.write_file(test_conv_id, "/home/user/test.txt", "Hello from sandbox!")
        
        # 5. 验证文件存在
        print("\n🔍 测试读取文件")
        content = await sandbox.read_file(test_conv_id, "/home/user/test.txt")
        print(f"   内容: {content}")
        
        if content == "Hello from sandbox!":
            print("   ✅ 文件内容正确！")
        else:
            print("   ❌ 文件内容不匹配")
            return False
        
        # 6. 测试 ls 命令
        print("\n🐚 测试 bash: ls -la /home/user/")
        result = await sandbox.run_command(test_conv_id, "ls -la /home/user/")
        print(f"   输出:\n{result.output}")
        
        # 验证 test.txt 存在
        if "test.txt" in result.output:
            print("   ✅ 文件 test.txt 存在于沙盒中！")
        else:
            print("   ❌ 文件 test.txt 不存在")
            return False
        
        # 7. 清理 - 销毁沙盒
        print("\n🗑️ 清理沙盒...")
        await sandbox.destroy_sandbox(test_conv_id)
        print("   ✅ 沙盒已销毁")
        
        print("\n" + "=" * 60)
        print("✅ 所有测试通过！bash 命令确实在 E2B 沙盒中执行")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        
        # 尝试清理
        try:
            await sandbox.destroy_sandbox(test_conv_id)
        except:
            pass
        
        return False


async def test_executor_bash():
    """测试通过 ToolExecutor 执行 bash"""
    
    print("\n" + "=" * 60)
    print("🧪 测试 2: 验证 ToolExecutor 的 bash 工具")
    print("=" * 60)
    
    from core.tool.executor import ToolExecutor
    
    # 创建 executor
    executor = ToolExecutor()
    
    test_conv_id = "test_executor_" + str(int(asyncio.get_event_loop().time()))
    
    # 测试 bash 工具
    print("\n🐚 通过 ToolExecutor 执行 bash: pwd")
    result = await executor.execute(
        tool_name="bash",
        tool_input={
            "command": "pwd && whoami && echo $HOME",
            "conversation_id": test_conv_id,
            "user_id": "test_user"
        }
    )
    
    print(f"   结果: {result}")
    
    if result.get("success"):
        output = result.get("output", "")
        print(f"   输出: {output}")
        
        # 验证是沙盒路径
        if "/Users/" in output or os.getenv("USER", "") in output:
            print("   ❌ 警告：可能在本地执行！")
            return False
        else:
            print("   ✅ 看起来是在沙盒中执行的")
    else:
        print(f"   ❌ 执行失败: {result.get('error')}")
        return False
    
    # 清理
    try:
        from infra.sandbox import get_sandbox_provider
        await get_sandbox_provider().destroy_sandbox(test_conv_id)
    except:
        pass
    
    return True


async def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("🚀 沙盒 bash 工具验证测试")
    print("=" * 60)
    
    results = []
    
    # 测试 1: 直接测试沙盒
    results.append(await test_sandbox_bash())
    
    # 测试 2: 通过 Executor 测试
    results.append(await test_executor_bash())
    
    # 总结
    print("\n" + "=" * 60)
    print("📊 测试总结")
    print("=" * 60)
    print(f"   测试 1 (直接沙盒): {'✅ 通过' if results[0] else '❌ 失败'}")
    print(f"   测试 2 (Executor): {'✅ 通过' if results[1] else '❌ 失败'}")
    
    if all(results):
        print("\n🎉 所有测试通过！bash 工具已正确路由到 E2B 沙盒")
    else:
        print("\n⚠️ 部分测试失败，请检查代码")


if __name__ == "__main__":
    asyncio.run(main())


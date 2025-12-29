#!/usr/bin/env python3
"""
E2B 配置辅助脚本

功能：
1. 检查 E2B API Key 是否配置
2. 引导用户设置 API Key
3. 验证 E2B 连接
4. 运行简单测试

运行方式：
  python scripts/configure_e2b.py
"""

import os
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv, set_key

# 加载环境变量
load_dotenv()


def check_e2b_sdk():
    """检查 E2B SDK 是否安装"""
    try:
        import e2b_code_interpreter
        print("✅ E2B SDK 已安装")
        return True
    except ImportError:
        print("❌ E2B SDK 未安装")
        print("\n请运行以下命令安装:")
        print("  pip install e2b e2b-code-interpreter")
        return False


def check_api_key():
    """检查 API Key 是否配置"""
    api_key = os.getenv("E2B_API_KEY")
    
    if api_key:
        print(f"✅ E2B_API_KEY 已配置: {api_key[:10]}...")
        return api_key
    else:
        print("❌ E2B_API_KEY 未配置")
        return None


def configure_api_key():
    """配置 API Key"""
    print("\n" + "="*70)
    print("📝 配置 E2B API Key")
    print("="*70)
    
    print("\n步骤:")
    print("1. 访问 https://e2b.dev/dashboard")
    print("2. 注册/登录账号")
    print("3. 创建 API Key")
    print("4. 复制 API Key（格式：e2b_***）")
    
    print("\n请输入您的 E2B API Key:")
    api_key = input("> ").strip()
    
    if not api_key.startswith("e2b_"):
        print("⚠️ API Key 格式可能不正确（应该以 e2b_ 开头）")
        confirm = input("是否继续? (y/n): ").strip().lower()
        if confirm != 'y':
            print("❌ 配置已取消")
            sys.exit(0)
    
    # 保存到 .env 文件
    env_file = Path(__file__).parent.parent / ".env"
    
    if env_file.exists():
        # 更新现有文件
        set_key(env_file, "E2B_API_KEY", api_key)
        print(f"✅ API Key 已更新到: {env_file}")
    else:
        # 创建新文件
        with open(env_file, 'w') as f:
            f.write(f"# E2B Configuration\n")
            f.write(f"E2B_API_KEY={api_key}\n")
        print(f"✅ API Key 已保存到: {env_file}")
    
    return api_key


async def test_connection(api_key: str):
    """测试 E2B 连接"""
    print("\n" + "="*70)
    print("🔌 测试 E2B 连接")
    print("="*70)
    
    try:
        from e2b_code_interpreter import Sandbox
        
        print("创建测试沙箱...")
        sandbox = await asyncio.to_thread(
            Sandbox.create,
            api_key=api_key
        )
        
        print(f"✅ 沙箱创建成功: {sandbox.sandbox_id}")
        
        # 运行简单测试
        print("\n运行测试代码...")
        execution = await asyncio.to_thread(
            sandbox.run_code,
            "print('Hello from E2B!')\nprint(f'2 + 2 = {2 + 2}')"
        )
        
        stdout = "\n".join([log.line for log in execution.logs.stdout])
        print(f"\n输出:\n{stdout}")
        
        # 关闭沙箱
        await asyncio.to_thread(sandbox.close)
        print("\n✅ E2B 连接测试成功！")
        
        return True
    
    except Exception as e:
        print(f"\n❌ E2B 连接测试失败: {e}")
        return False


async def main():
    """主函数"""
    print("="*70)
    print("🚀 E2B 配置向导")
    print("="*70)
    
    # 1. 检查 SDK
    if not check_e2b_sdk():
        sys.exit(1)
    
    # 2. 检查 API Key
    api_key = check_api_key()
    
    if not api_key:
        print("\n需要配置 E2B API Key")
        api_key = configure_api_key()
    
    # 3. 测试连接
    print("\n是否测试 E2B 连接? (y/n):")
    test = input("> ").strip().lower()
    
    if test == 'y':
        import asyncio
        success = await test_connection(api_key)
        
        if success:
            print("\n" + "="*70)
            print("🎉 E2B 配置完成！现在可以运行完整测试:")
            print("="*70)
            print("\n  python tests/test_e2b_e2e_real.py")
            print("\n或运行简单示例:")
            print("  python examples/e2b_simple_example.py")
        else:
            print("\n⚠️ 连接测试失败，请检查 API Key 是否正确")
    else:
        print("\n✅ 配置完成")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())


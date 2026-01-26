"""
对比测试 e2b 和 e2b_code_interpreter 两个包

测试内容：
1. 两个包创建的沙盒环境有什么不同
2. 预装软件对比（Node.js、Python、npm 等）
3. 环境变量和工作目录
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


async def test_e2b_basic():
    """测试 e2b 基础包"""
    print("=" * 60)
    print("📦 测试 1: e2b 基础包")
    print("=" * 60)
    
    from e2b import AsyncSandbox
    
    sandbox = await AsyncSandbox.create(timeout=10 * 60)
    print(f"✅ 沙盒创建成功: {sandbox.sandbox_id}")
    
    try:
        # 检查环境
        commands = [
            ("Python 版本", "python3 --version 2>&1 || echo '未安装'"),
            ("Node.js 版本", "node --version 2>&1 || echo '未安装'"),
            ("npm 版本", "npm --version 2>&1 || echo '未安装'"),
            ("pnpm 版本", "pnpm --version 2>&1 || echo '未安装'"),
            ("pip 版本", "pip --version 2>&1 || echo '未安装'"),
            ("工作目录", "pwd"),
            ("用户", "whoami"),
            ("系统信息", "cat /etc/os-release | head -2"),
        ]
        
        results = {}
        for name, cmd in commands:
            result = await sandbox.commands.run(cmd, timeout=30)
            output = (result.stdout or "").strip() or (result.stderr or "").strip() or "(无输出)"
            results[name] = output
            print(f"   {name}: {output[:100]}")
        
        # 获取完整的 Python 包列表
        print("\n   📦 已安装的 Python 包:")
        pkg_result = await sandbox.commands.run("pip list 2>/dev/null || echo '无法列出'", timeout=30)
        pkg_output = (pkg_result.stdout or "").strip()
        results["python_packages"] = pkg_output
        
        for line in pkg_output.split("\n"):
            print(f"      {line}")
        
        pkg_count = len([l for l in pkg_output.split("\n") if l.strip() and not l.startswith("Package") and not l.startswith("-")])
        results["pkg_count"] = pkg_count
        print(f"\n   📊 Python 包总数: {pkg_count}")
        
        return results
        
    finally:
        await sandbox.kill()
        print("✅ 沙盒已关闭\n")


async def test_e2b_code_interpreter():
    """测试 e2b_code_interpreter 包"""
    print("=" * 60)
    print("📦 测试 2: e2b_code_interpreter 包")
    print("=" * 60)
    
    from e2b_code_interpreter import AsyncSandbox
    
    sandbox = await AsyncSandbox.create(timeout=10 * 60)
    print(f"✅ 沙盒创建成功: {sandbox.sandbox_id}")
    
    try:
        # 检查环境
        commands = [
            ("Python 版本", "python3 --version 2>&1 || echo '未安装'"),
            ("Node.js 版本", "node --version 2>&1 || echo '未安装'"),
            ("npm 版本", "npm --version 2>&1 || echo '未安装'"),
            ("pnpm 版本", "pnpm --version 2>&1 || echo '未安装'"),
            ("pip 版本", "pip --version 2>&1 || echo '未安装'"),
            ("工作目录", "pwd"),
            ("用户", "whoami"),
            ("系统信息", "cat /etc/os-release | head -2"),
        ]
        
        results = {}
        for name, cmd in commands:
            result = await sandbox.commands.run(cmd, timeout=30)
            output = (result.stdout or "").strip() or (result.stderr or "").strip() or "(无输出)"
            results[name] = output
            print(f"   {name}: {output[:100]}")
        
        # 获取完整的 Python 包列表
        print("\n   📦 已安装的 Python 包:")
        pkg_result = await sandbox.commands.run("pip list 2>/dev/null || echo '无法列出'", timeout=30)
        pkg_output = (pkg_result.stdout or "").strip()
        results["python_packages"] = pkg_output
        
        for line in pkg_output.split("\n"):
            print(f"      {line}")
        
        pkg_count = len([l for l in pkg_output.split("\n") if l.strip() and not l.startswith("Package") and not l.startswith("-")])
        results["pkg_count"] = pkg_count
        print(f"\n   📊 Python 包总数: {pkg_count}")
        
        return results
        
    finally:
        await sandbox.kill()
        print("✅ 沙盒已关闭\n")


async def main():
    print("\n🧪 E2B 包对比测试\n")
    
    # 测试两个包
    results_basic = await test_e2b_basic()
    results_interpreter = await test_e2b_code_interpreter()
    
    # 对比结果
    print("=" * 60)
    print("📊 对比结果摘要")
    print("=" * 60)
    print()
    print(f"{'项目':<20} {'e2b 基础包':<30} {'e2b_code_interpreter':<30}")
    print("-" * 80)
    
    compare_keys = ["Python 版本", "Node.js 版本", "npm 版本", "pnpm 版本", "工作目录", "用户"]
    for key in compare_keys:
        val1 = results_basic.get(key, "N/A")[:25]
        val2 = results_interpreter.get(key, "N/A")[:25]
        print(f"{key:<20} {val1:<30} {val2:<30}")
    
    # 包数量对比
    print(f"{'Python 包数量':<20} {results_basic.get('pkg_count', 0):<30} {results_interpreter.get('pkg_count', 0):<30}")
    
    print()
    print("=" * 60)
    print("📦 Python 包对比")
    print("=" * 60)
    
    # 解析包列表
    def parse_packages(pkg_str):
        packages = set()
        for line in pkg_str.split("\n"):
            if line.strip() and not line.startswith("Package") and not line.startswith("-"):
                parts = line.split()
                if parts:
                    packages.add(parts[0].lower())
        return packages
    
    pkgs_basic = parse_packages(results_basic.get("python_packages", ""))
    pkgs_interpreter = parse_packages(results_interpreter.get("python_packages", ""))
    
    # 找出差异
    only_in_basic = pkgs_basic - pkgs_interpreter
    only_in_interpreter = pkgs_interpreter - pkgs_basic
    common = pkgs_basic & pkgs_interpreter
    
    print(f"\n共同包数量: {len(common)}")
    print(f"仅 e2b 基础包有: {len(only_in_basic)}")
    print(f"仅 e2b_code_interpreter 有: {len(only_in_interpreter)}")
    
    if only_in_interpreter:
        print(f"\n🔥 e2b_code_interpreter 额外的包 ({len(only_in_interpreter)} 个):")
        for pkg in sorted(only_in_interpreter):
            print(f"   - {pkg}")
    
    if only_in_basic:
        print(f"\n📦 e2b 基础包额外的包 ({len(only_in_basic)} 个):")
        for pkg in sorted(only_in_basic):
            print(f"   - {pkg}")
    
    print()
    print("=" * 60)
    print("✅ 对比测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

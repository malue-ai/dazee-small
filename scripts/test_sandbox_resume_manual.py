#!/usr/bin/env python3
"""
沙盒恢复功能手动测试脚本

测试场景：
1. 创建沙盒，初始化项目，启动服务
2. 等待沙盒自动过期（E2B 当前 2 分钟，测试用）
3. 恢复沙盒后，验证服务自动重启

运行方式：
    cd /Users/kens0n/projects/zenflux_agent
    python scripts/test_sandbox_resume_manual.py
"""

import asyncio
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

# 加载环境变量
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from services.sandbox_service import get_sandbox_service
from tools.project_templates import get_template_files
from infra.sandbox import get_sandbox_provider


async def wait_for_service(url: str, timeout: float = 30.0) -> bool:
    """等待服务可用"""
    start = time.time()
    async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
        while time.time() - start < timeout:
            try:
                resp = await client.get(url)
                if resp.status_code < 500:
                    return True
            except Exception:
                pass
            await asyncio.sleep(2)
    return False


async def test_static_html():
    """
    测试 1：静态 HTML 项目（简单的 HTTP 服务器）
    
    这个测试验证非 Node.js 项目的沙盒恢复
    """
    conversation_id = f"test_static_{uuid4().hex[:8]}"
    user_id = f"test_user_{uuid4().hex[:8]}"
    
    service = get_sandbox_service()
    provider = get_sandbox_provider()
    
    print(f"\n{'='*60}")
    print(f"测试 1：静态 HTML 项目沙盒恢复")
    print(f"{'='*60}")
    
    try:
        # 1. 创建沙盒
        print(f"\n📦 创建沙盒: {conversation_id}")
        sandbox_info = await service.get_or_create_sandbox(conversation_id, user_id)
        print(f"✅ 沙盒已创建: {sandbox_info.e2b_sandbox_id}")
        
        # 2. 写入 index.html
        print("\n📝 写入 index.html")
        html_content = """<!DOCTYPE html>
<html>
<head>
    <title>Test Page</title>
</head>
<body>
    <h1>Hello from Static HTML!</h1>
    <p>Time: """ + time.strftime("%Y-%m-%d %H:%M:%S") + """</p>
</body>
</html>"""
        await service.write_file(conversation_id, "/home/user/project/index.html", html_content)
        print("✅ index.html 已写入")
        
        # 3. 启动 HTTP 服务器
        print("\n🚀 启动 HTTP 服务器（端口 8000）")
        sandbox = await provider._get_sandbox_obj(conversation_id)
        try:
            await sandbox.commands.run(
                "cd /home/user/project && python3 -m http.server 8000 > /tmp/server.log 2>&1",
                background=True,
                timeout=10
            )
        except Exception as e:
            if "timeout" not in str(e).lower():
                print(f"⚠️ 启动命令异常: {e}")
        
        await asyncio.sleep(3)
        
        # 4. 获取 URL 并验证
        host = sandbox.get_host(8000)
        url = f"https://{host}"
        print(f"\n🌐 服务 URL: {url}")
        
        is_available = await wait_for_service(url)
        print(f"服务状态: {'✅ 可访问' if is_available else '❌ 不可访问'}")
        
        if not is_available:
            print("❌ 服务无法访问，测试失败")
            return
        
        # 5. 等待沙盒过期
        print(f"\n⏳ 请等待沙盒自动过期...")
        print(f"   E2B 沙盒当前 2 分钟超时（测试用）")
        print(f"   你可以等待 5+ 分钟，或者手动在 E2B 控制台暂停沙盒")
        print(f"   沙盒 ID: {sandbox_info.e2b_sandbox_id}")
        
        input("\n按 Enter 继续（在沙盒过期/暂停后）...")
        
        # 6. 尝试恢复沙盒
        print("\n▶️ 恢复沙盒...")
        try:
            resumed_info = await service.resume_sandbox(conversation_id)
            print(f"✅ 沙盒已恢复: status={resumed_info.status}")
        except Exception as e:
            print(f"❌ 恢复失败: {e}")
            return
        
        # 7. 验证服务状态
        print(f"\n🔍 验证服务状态...")
        await asyncio.sleep(5)  # 等待服务启动
        
        # 重新获取 sandbox 对象
        sandbox = await provider._get_sandbox_obj(conversation_id)
        host = sandbox.get_host(8000)
        url = f"https://{host}"
        
        is_available = await wait_for_service(url, timeout=30)
        print(f"服务状态: {'✅ 可访问' if is_available else '❌ 不可访问'}")
        
        if is_available:
            print("\n✅ 测试通过：沙盒恢复后服务正常")
        else:
            print("\n⚠️ 注意：静态 HTML 项目不会自动重启服务（没有 package.json）")
            print("   这是预期行为，需要手动重启或扩展自动重启逻辑")
        
    finally:
        # 清理
        print("\n🗑️ 清理：销毁沙盒")
        await service.kill_sandbox(conversation_id)
        print("✅ 沙盒已销毁")


async def test_react_fullstack():
    """
    测试 2：React 全栈项目（前端 5173 + 后端 3000）
    
    这个测试验证 Node.js 项目的沙盒恢复和自动重启 dev server
    """
    conversation_id = f"test_react_{uuid4().hex[:8]}"
    user_id = f"test_user_{uuid4().hex[:8]}"
    
    service = get_sandbox_service()
    provider = get_sandbox_provider()
    
    print(f"\n{'='*60}")
    print(f"测试 2：React 全栈项目沙盒恢复")
    print(f"{'='*60}")
    
    try:
        # 1. 创建沙盒
        print(f"\n📦 创建沙盒: {conversation_id}")
        sandbox_info = await service.get_or_create_sandbox(conversation_id, user_id)
        print(f"✅ 沙盒已创建: {sandbox_info.e2b_sandbox_id}")
        
        # 2. 初始化 react_fullstack 模板
        print("\n📝 初始化 react_fullstack 模板...")
        files = get_template_files("react_fullstack")
        print(f"   模板包含 {len(files)} 个文件")
        
        sandbox = await provider._get_sandbox_obj(conversation_id)
        
        # 创建目录
        dirs = set()
        for file_path in files.keys():
            dir_path = "/".join(f"/home/user/project/{file_path}".split("/")[:-1])
            if dir_path:
                dirs.add(dir_path)
        
        if dirs:
            await sandbox.commands.run(f"mkdir -p {' '.join(sorted(dirs))}", timeout=30)
        
        # 写入文件
        for file_path, content in files.items():
            await sandbox.files.write(f"/home/user/project/{file_path}", content)
        
        print(f"✅ 已写入 {len(files)} 个文件")
        
        # 3. 安装依赖
        print("\n📦 安装依赖（npm install）...")
        print("   这可能需要几分钟...")
        result = await sandbox.commands.run(
            "cd /home/user/project && npm install",
            timeout=300
        )
        if result.exit_code != 0:
            print(f"⚠️ npm install 失败: {result.stderr or result.stdout}")
        else:
            print("✅ 依赖安装完成")
        
        # 4. 启动开发服务器
        print("\n🚀 启动开发服务器（npm run dev）...")
        try:
            await sandbox.commands.run(
                "cd /home/user/project && npm run dev > /tmp/app.log 2>&1",
                background=True,
                timeout=10
            )
        except Exception as e:
            if "timeout" not in str(e).lower():
                print(f"⚠️ 启动命令异常: {e}")
        
        print("⏳ 等待服务启动（60秒）...")
        await asyncio.sleep(60)
        
        # 5. 获取 URL 并验证
        backend_host = sandbox.get_host(3000)
        frontend_host = sandbox.get_host(5173)
        backend_url = f"https://{backend_host}"
        frontend_url = f"https://{frontend_host}"
        
        print(f"\n🌐 后端 URL: {backend_url}")
        print(f"🌐 前端 URL: {frontend_url}")
        
        backend_ok = await wait_for_service(f"{backend_url}/api/health", timeout=30)
        frontend_ok = await wait_for_service(frontend_url, timeout=30)
        
        print(f"后端状态: {'✅ 可访问' if backend_ok else '❌ 不可访问'}")
        print(f"前端状态: {'✅ 可访问' if frontend_ok else '❌ 不可访问'}")
        
        # 6. 等待沙盒过期
        print(f"\n⏳ 请等待沙盒自动过期...")
        print(f"   E2B 沙盒当前 2 分钟超时（测试用）")
        print(f"   沙盒 ID: {sandbox_info.e2b_sandbox_id}")
        
        input("\n按 Enter 继续（在沙盒过期/暂停后）...")
        
        # 7. 恢复沙盒
        print("\n▶️ 恢复沙盒（预期自动重启 dev server）...")
        try:
            resumed_info = await service.resume_sandbox(conversation_id)
            print(f"✅ 沙盒已恢复: status={resumed_info.status}")
        except Exception as e:
            print(f"❌ 恢复失败: {e}")
            return
        
        # 8. 等待服务自动重启
        print("\n⏳ 等待服务自动重启（60秒）...")
        await asyncio.sleep(60)
        
        # 9. 验证服务状态
        print("\n🔍 验证服务状态...")
        sandbox = await provider._get_sandbox_obj(conversation_id)
        backend_host = sandbox.get_host(3000)
        frontend_host = sandbox.get_host(5173)
        backend_url = f"https://{backend_host}"
        frontend_url = f"https://{frontend_host}"
        
        backend_ok = await wait_for_service(f"{backend_url}/api/health", timeout=30)
        frontend_ok = await wait_for_service(frontend_url, timeout=30)
        
        print(f"后端状态: {'✅ 已重启' if backend_ok else '❌ 未重启'}")
        print(f"前端状态: {'✅ 已重启' if frontend_ok else '❌ 未重启'}")
        
        if backend_ok or frontend_ok:
            print("\n✅ 测试通过：沙盒恢复后服务自动重启成功")
        else:
            print("\n❌ 测试失败：服务未自动重启")
            # 检查日志
            print("\n📋 检查应用日志...")
            try:
                log_result = await sandbox.commands.run("cat /tmp/app.log | tail -50", timeout=10)
                print(log_result.stdout or "（无日志）")
            except Exception as e:
                print(f"无法读取日志: {e}")
        
    finally:
        # 清理
        print("\n🗑️ 清理：销毁沙盒")
        await service.kill_sandbox(conversation_id)
        print("✅ 沙盒已销毁")


async def test_react_frontend_only():
    """
    测试 3：React 前端项目（只启动前端，端口 5173）
    
    这个测试验证只启动前端时的沙盒恢复
    """
    conversation_id = f"test_react_fe_{uuid4().hex[:8]}"
    user_id = f"test_user_{uuid4().hex[:8]}"
    
    service = get_sandbox_service()
    provider = get_sandbox_provider()
    
    print(f"\n{'='*60}")
    print(f"测试 3：React 前端项目沙盒恢复（只启动前端）")
    print(f"{'='*60}")
    
    try:
        # 1. 创建沙盒
        print(f"\n📦 创建沙盒: {conversation_id}")
        sandbox_info = await service.get_or_create_sandbox(conversation_id, user_id)
        print(f"✅ 沙盒已创建: {sandbox_info.e2b_sandbox_id}")
        
        # 2. 初始化 react_fullstack 模板
        print("\n📝 初始化 react_fullstack 模板...")
        files = get_template_files("react_fullstack")
        print(f"   模板包含 {len(files)} 个文件")
        
        sandbox = await provider._get_sandbox_obj(conversation_id)
        
        # 创建目录
        dirs = set()
        for file_path in files.keys():
            dir_path = "/".join(f"/home/user/project/{file_path}".split("/")[:-1])
            if dir_path:
                dirs.add(dir_path)
        
        if dirs:
            await sandbox.commands.run(f"mkdir -p {' '.join(sorted(dirs))}", timeout=30)
        
        # 写入文件
        for file_path, content in files.items():
            await sandbox.files.write(f"/home/user/project/{file_path}", content)
        
        print(f"✅ 已写入 {len(files)} 个文件")
        
        # 3. 安装依赖
        print("\n📦 安装依赖（npm install）...")
        print("   这可能需要几分钟...")
        result = await sandbox.commands.run(
            "cd /home/user/project && npm install",
            timeout=300
        )
        if result.exit_code != 0:
            print(f"⚠️ npm install 失败: {result.stderr or result.stdout}")
        else:
            print("✅ 依赖安装完成")
        
        # 4. 只启动前端（npm run dev:client）
        print("\n🚀 启动前端开发服务器（npm run dev:client）...")
        try:
            await sandbox.commands.run(
                "cd /home/user/project && npm run dev:client > /tmp/frontend.log 2>&1",
                background=True,
                timeout=10
            )
        except Exception as e:
            if "timeout" not in str(e).lower():
                print(f"⚠️ 启动命令异常: {e}")
        
        print("⏳ 等待前端服务启动（30秒）...")
        await asyncio.sleep(30)
        
        # 5. 获取 URL 并验证
        frontend_host = sandbox.get_host(5173)
        frontend_url = f"https://{frontend_host}"
        
        print(f"\n🌐 前端 URL: {frontend_url}")
        
        frontend_ok = await wait_for_service(frontend_url, timeout=30)
        print(f"前端状态: {'✅ 可访问' if frontend_ok else '❌ 不可访问'}")
        
        if not frontend_ok:
            print("\n❌ 前端服务无法访问")
            # 检查日志
            print("\n📋 检查前端日志...")
            try:
                log_result = await sandbox.commands.run("cat /tmp/frontend.log | tail -30", timeout=10)
                print(log_result.stdout or "（无日志）")
            except Exception as e:
                print(f"无法读取日志: {e}")
            return
        
        # 6. 等待沙盒过期
        print(f"\n⏳ 请等待沙盒自动过期...")
        print(f"   E2B 沙盒当前 2 分钟超时（测试用）")
        print(f"   沙盒 ID: {sandbox_info.e2b_sandbox_id}")
        print(f"   前端 URL: {frontend_url}")
        print(f"\n   你可以在浏览器中访问上面的 URL 验证服务正常")
        
        input("\n按 Enter 继续（在沙盒过期/暂停后）...")
        
        # 7. 恢复沙盒
        print("\n▶️ 恢复沙盒（预期自动重启 dev server）...")
        try:
            resumed_info = await service.resume_sandbox(conversation_id)
            print(f"✅ 沙盒已恢复: status={resumed_info.status}")
        except Exception as e:
            print(f"❌ 恢复失败: {e}")
            return
        
        # 8. 等待服务自动重启
        print("\n⏳ 等待前端服务自动重启（60秒）...")
        await asyncio.sleep(60)
        
        # 9. 验证服务状态
        print("\n🔍 验证前端服务状态...")
        sandbox = await provider._get_sandbox_obj(conversation_id)
        frontend_host = sandbox.get_host(5173)
        frontend_url = f"https://{frontend_host}"
        
        print(f"🌐 前端 URL: {frontend_url}")
        
        frontend_ok = await wait_for_service(frontend_url, timeout=30)
        print(f"前端状态: {'✅ 已重启' if frontend_ok else '❌ 未重启'}")
        
        if frontend_ok:
            print("\n✅ 测试通过：沙盒恢复后前端服务自动重启成功")
            print(f"   你可以在浏览器中访问: {frontend_url}")
        else:
            print("\n❌ 测试失败：前端服务未自动重启")
            # 检查日志
            print("\n📋 检查前端日志...")
            try:
                log_result = await sandbox.commands.run("cat /tmp/frontend.log | tail -30", timeout=10)
                print(log_result.stdout or "（无日志）")
            except Exception as e:
                print(f"无法读取日志: {e}")
            
            # 检查 npm run dev 是否在运行
            print("\n📋 检查进程状态...")
            try:
                ps_result = await sandbox.commands.run("ps aux | grep -E 'node|npm|vite' | grep -v grep", timeout=10)
                print(ps_result.stdout or "（无相关进程）")
            except Exception as e:
                print(f"无法检查进程: {e}")
        
    finally:
        # 清理
        print("\n🗑️ 清理：销毁沙盒")
        await service.kill_sandbox(conversation_id)
        print("✅ 沙盒已销毁")


async def main():
    """主函数"""
    print("=" * 60)
    print("沙盒恢复功能测试")
    print("=" * 60)
    
    print("\n选择测试:")
    print("1. 静态 HTML 项目（简单）")
    print("2. React 全栈项目（前端+后端）")
    print("3. React 前端项目（只启动前端）")
    print("4. 全部测试")
    print("\n⏰ 注意：E2B 沙盒当前 2 分钟超时（测试用），等待过期后按 Enter 恢复")
    
    choice = input("\n请选择 (1/2/3/4): ").strip()
    
    if choice == "1":
        await test_static_html()
    elif choice == "2":
        await test_react_fullstack()
    elif choice == "3":
        await test_react_frontend_only()
    elif choice == "4":
        await test_static_html()
        await test_react_fullstack()
        await test_react_frontend_only()
    else:
        print("无效选择")


if __name__ == "__main__":
    asyncio.run(main())

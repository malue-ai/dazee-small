"""
测试 E2B 前端沙盒

测试内容：
1. 创建沙盒（使用前端模板或默认模板）
2. 检查 Node.js 环境
3. 创建简单的前端项目
4. 启动开发服务器
5. 获取预览 URL

使用方法：
    python scripts/test_frontend_sandbox.py [--template TEMPLATE]
    
参数：
    --template: 模板名称（默认使用 zenflux-frontend，如果不存在则使用默认模板）
"""

import os
import sys
import asyncio
import argparse

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


async def test_sandbox(template: str = None):
    """
    测试沙盒功能
    
    Args:
        template: 模板名称（可选）
    """
    # 动态导入，确保环境变量已加载
    # 使用项目实际用的包：e2b_code_interpreter
    from e2b_code_interpreter import AsyncSandbox
    
    print("=" * 60)
    print("🧪 E2B 前端沙盒测试")
    print("=" * 60)
    print()
    
    # 1. 创建沙盒
    print("📦 步骤 1: 创建沙盒...")
    try:
        if template:
            print(f"   使用模板: {template}")
            sandbox = await AsyncSandbox.create(template=template, timeout=30 * 60)
        else:
            print("   使用默认模板")
            sandbox = await AsyncSandbox.create(timeout=30 * 60)
        print(f"   ✅ 沙盒创建成功: {sandbox.sandbox_id}")
    except Exception as e:
        print(f"   ❌ 沙盒创建失败: {e}")
        print()
        print("   提示：如果模板不存在，请先运行构建脚本：")
        print("   python scripts/build_frontend_template.py")
        return
    
    print()
    
    try:
        # 2. 检查 Node.js 环境
        print("🔍 步骤 2: 检查 Node.js 环境...")
        
        commands = [
            ("Node.js 版本", "node --version"),
            ("npm 版本", "npm --version"),
            ("pnpm 版本", "pnpm --version 2>/dev/null || echo '未安装'"),
            ("工作目录", "pwd"),
            ("用户", "whoami"),
        ]
        
        for name, cmd in commands:
            result = await sandbox.commands.run(cmd, timeout=30)
            output = (result.stdout or "").strip() or (result.stderr or "").strip() or "(无输出)"
            print(f"   {name}: {output}")
        
        print()
        
        # 3. 创建简单的 HTML 项目
        print("📝 步骤 3: 创建测试项目...")
        
        # 创建项目目录
        await sandbox.commands.run("mkdir -p /home/user/test-app", timeout=10)
        
        # 写入 HTML 文件
        html_content = '''<!DOCTYPE html>
<html>
<head>
    <title>E2B 沙盒测试</title>
    <style>
        body { 
            font-family: system-ui; 
            display: flex; 
            justify-content: center; 
            align-items: center; 
            height: 100vh; 
            margin: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .container { text-align: center; }
        h1 { font-size: 3rem; margin-bottom: 1rem; }
        p { font-size: 1.2rem; opacity: 0.8; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎉 E2B 沙盒运行成功！</h1>
        <p>Node.js 前端环境已就绪</p>
    </div>
</body>
</html>'''
        
        await sandbox.files.write("/home/user/test-app/index.html", html_content)
        print("   ✅ 创建 index.html")
        
        print()
        
        # 4. 启动 HTTP 服务器
        print("🚀 步骤 4: 启动 HTTP 服务器...")
        
        # 使用 Python 的 http.server（更快，不需要下载）
        # background=True 让命令在后台运行
        await sandbox.commands.run(
            "cd /home/user/test-app && python3 -m http.server 3000",
            background=True,  # 关键：后台运行
            timeout=60
        )
        
        # 等待服务器启动
        await asyncio.sleep(2)
        print("   ✅ 服务器已启动（使用 Python http.server）")
        
        print()
        
        # 5. 获取预览 URL
        print("🌐 步骤 5: 获取预览 URL...")
        host = sandbox.get_host(3000)
        preview_url = f"https://{host}"
        print(f"   ✅ 预览地址: {preview_url}")
        
        print()
        print("=" * 60)
        print("✅ 测试完成！")
        print()
        print(f"🔗 预览地址: {preview_url}")
        print(f"📦 沙盒 ID: {sandbox.sandbox_id}")
        print()
        print("提示：沙盒将在 30 分钟后自动关闭")
        print("=" * 60)
        
        # 保持运行一会儿让用户可以访问
        print()
        print("按 Ctrl+C 关闭沙盒...")
        try:
            while True:
                await asyncio.sleep(10)
        except KeyboardInterrupt:
            print("\n正在关闭沙盒...")
            
    finally:
        await sandbox.kill()
        print("✅ 沙盒已关闭")


def main():
    parser = argparse.ArgumentParser(description="测试 E2B 前端沙盒")
    parser.add_argument(
        "--template",
        type=str,
        default=None,
        help="模板名称（默认使用基础模板测试）"
    )
    
    args = parser.parse_args()
    asyncio.run(test_sandbox(template=args.template))


if __name__ == "__main__":
    main()

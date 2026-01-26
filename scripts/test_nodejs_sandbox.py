"""
快速测试 Node.js 在 E2B 沙盒中的支持

使用原生 Node.js http 模块，无需 npm install
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from e2b_code_interpreter import AsyncSandbox


async def test_native_nodejs():
    """测试原生 Node.js HTTP 服务器（无需安装依赖）"""
    print("=" * 50)
    print("测试 Node.js 原生 HTTP 服务器")
    print("=" * 50)
    
    sandbox = None
    try:
        # 1. 创建沙盒
        print("\n[1/4] 创建沙盒...")
        sandbox = await AsyncSandbox.create(timeout=60)
        print(f"✅ 沙盒 ID: {sandbox.sandbox_id}")
        
        # 2. 检查 Node.js
        print("\n[2/4] 检查 Node.js...")
        result = await sandbox.commands.run("node --version")
        print(f"✅ Node.js 版本: {result.stdout.strip()}")
        
        # 3. 创建并启动服务器（原生 http，无需依赖）
        print("\n[3/4] 创建并启动服务器...")
        
        server_js = """
const http = require('http')

const server = http.createServer((req, res) => {
  res.writeHead(200, { 'Content-Type': 'application/json' })
  res.end(JSON.stringify({ message: 'Hello from Node.js!', path: req.url }))
})

server.listen(3000, '0.0.0.0', () => {
  console.log('Server running on port 3000')
})
"""
        await sandbox.files.write("/home/user/server.js", server_js)
        
        # 启动服务器
        await sandbox.commands.run(
            "node /home/user/server.js",
            background=True,
            timeout=5
        )
        await asyncio.sleep(2)
        print("✅ 服务器已启动")
        
        # 4. 验证
        print("\n[4/4] 验证服务...")
        result = await sandbox.commands.run("curl -s http://localhost:3000")
        
        host = sandbox.get_host(3000)
        preview_url = f"https://{host}"
        
        if "Hello from Node.js" in result.stdout:
            print(f"✅ 响应: {result.stdout.strip()}")
            print(f"✅ 预览 URL: {preview_url}")
            print("\n🎉 测试通过！Node.js 沙盒支持正常")
            return True
        else:
            print(f"❌ 响应异常: {result.stdout or result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False
    finally:
        if sandbox:
            await sandbox.kill()


if __name__ == "__main__":
    asyncio.run(test_native_nodejs())

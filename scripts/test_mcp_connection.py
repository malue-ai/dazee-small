#!/usr/bin/env python3
"""
MCP 连接测试脚本

测试 MCP Server 连接和工具调用

使用方法：
1. 先启动 MCP Proxy：
   npx @punkpeye/mcp-proxy --server "npx @modelcontextprotocol/server-filesystem /tmp" --port 3100

2. 运行此脚本：
   python scripts/test_mcp_connection.py
"""

import asyncio
import httpx
import json
from typing import Dict, Any, List, Optional


class SimpleMCPClient:
    """
    简单的 MCP HTTP 客户端（用于测试）
    
    支持 MCP over HTTP/SSE 协议
    """
    
    def __init__(self, server_url: str):
        """
        Args:
            server_url: MCP Server 的 HTTP 端点，如 "http://localhost:3100"
        """
        self.server_url = server_url.rstrip("/")
        self._tools: Dict[str, Dict] = {}
    
    async def connect(self) -> bool:
        """测试连接并获取服务器信息"""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                # 尝试获取服务器信息
                response = await client.post(
                    f"{self.server_url}/",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {},
                            "clientInfo": {
                                "name": "zenflux-test-client",
                                "version": "1.0.0"
                            }
                        }
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"✅ 连接成功！")
                    print(f"   服务器信息: {json.dumps(data, indent=2, ensure_ascii=False)}")
                    return True
                else:
                    print(f"❌ 连接失败: HTTP {response.status_code}")
                    print(f"   响应: {response.text}")
                    return False
                    
        except Exception as e:
            print(f"❌ 连接异常: {str(e)}")
            return False
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """获取 MCP Server 提供的工具列表"""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    f"{self.server_url}/",
                    json={
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/list",
                        "params": {}
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    tools = data.get("result", {}).get("tools", [])
                    
                    print(f"\n📋 发现 {len(tools)} 个工具:")
                    for tool in tools:
                        print(f"   - {tool['name']}: {tool.get('description', '无描述')[:50]}...")
                        self._tools[tool['name']] = tool
                    
                    return tools
                else:
                    print(f"❌ 获取工具列表失败: HTTP {response.status_code}")
                    return []
                    
        except Exception as e:
            print(f"❌ 获取工具列表异常: {str(e)}")
            return []
    
    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """调用工具"""
        try:
            print(f"\n🔧 调用工具: {tool_name}")
            print(f"   参数: {json.dumps(arguments, ensure_ascii=False)}")
            
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.server_url}/",
                    json={
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {
                            "name": tool_name,
                            "arguments": arguments
                        }
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    result = data.get("result", {})
                    
                    print(f"✅ 工具执行成功!")
                    print(f"   结果: {json.dumps(result, indent=2, ensure_ascii=False)[:500]}...")
                    
                    return result
                else:
                    print(f"❌ 工具执行失败: HTTP {response.status_code}")
                    print(f"   响应: {response.text}")
                    return {"error": response.text}
                    
        except Exception as e:
            print(f"❌ 工具执行异常: {str(e)}")
            return {"error": str(e)}


async def test_filesystem_mcp():
    """测试 Filesystem MCP Server"""
    print("=" * 60)
    print("🧪 测试 MCP 连接 - Filesystem Server")
    print("=" * 60)
    
    # 连接到本地 MCP Proxy
    client = SimpleMCPClient("http://localhost:3100")
    
    # 1. 测试连接
    print("\n[1/3] 测试连接...")
    connected = await client.connect()
    if not connected:
        print("\n💡 提示: 请先启动 MCP Proxy:")
        print('   npx @punkpeye/mcp-proxy --server "npx @modelcontextprotocol/server-filesystem /tmp" --port 3100')
        return
    
    # 2. 获取工具列表
    print("\n[2/3] 获取工具列表...")
    tools = await client.list_tools()
    
    if not tools:
        print("⚠️ 没有发现工具")
        return
    
    # 3. 测试工具调用
    print("\n[3/3] 测试工具调用...")
    
    # 尝试调用 list_directory 或 read_directory
    if "list_directory" in client._tools:
        result = await client.call_tool("list_directory", {"path": "/tmp"})
    elif "read_directory" in client._tools:
        result = await client.call_tool("read_directory", {"path": "/tmp"})
    elif "list_allowed_directories" in client._tools:
        result = await client.call_tool("list_allowed_directories", {})
    else:
        print("⚠️ 没有找到可测试的工具")
        print(f"   可用工具: {list(client._tools.keys())}")
    
    print("\n" + "=" * 60)
    print("✅ MCP 测试完成!")
    print("=" * 60)


async def test_custom_mcp(server_url: str):
    """测试自定义 MCP Server"""
    print("=" * 60)
    print(f"🧪 测试 MCP 连接 - {server_url}")
    print("=" * 60)
    
    client = SimpleMCPClient(server_url)
    
    # 1. 测试连接
    print("\n[1/2] 测试连接...")
    connected = await client.connect()
    if not connected:
        return
    
    # 2. 获取工具列表
    print("\n[2/2] 获取工具列表...")
    tools = await client.list_tools()
    
    print("\n" + "=" * 60)
    print("✅ 连接测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # 测试指定的 MCP Server
        server_url = sys.argv[1]
        asyncio.run(test_custom_mcp(server_url))
    else:
        # 默认测试本地 Filesystem MCP
        asyncio.run(test_filesystem_mcp())


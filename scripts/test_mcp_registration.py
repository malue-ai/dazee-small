#!/usr/bin/env python3
"""
MCP 注册和 Agent 关联接口测试脚本

测试流程：
1. 注册全局 MCP 模板
2. 列出全局 MCP 模板
3. 获取全局 MCP 详情
4. 为 Agent 启用 MCP
5. 列出 Agent 的 MCP
6. 更新 Agent 的 MCP 配置
7. 禁用 Agent 的 MCP
8. 删除全局 MCP 模板
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

import httpx

# 测试配置
BASE_URL = "http://localhost:8000"
TEST_AGENT_ID = "test_agent"  # 需要存在的 Agent


async def test_mcp_registration():
    """测试 MCP 注册流程"""
    
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        print("=" * 60)
        print("MCP 注册和 Agent 关联接口测试")
        print("=" * 60)
        
        # ============================================================
        # 1. 注册全局 MCP 模板
        # ============================================================
        print("\n📝 1. 注册全局 MCP 模板...")
        
        mcp_data = {
            "server_url": "http://localhost:3100",
            "server_name": "notion_test",
            "auth_type": "bearer",
            "auth_config": {"token_env": "NOTION_API_KEY"},
        }
        
        response = await client.post("/api/v1/tools/mcp/register", json=mcp_data)
        print(f"   状态码: {response.status_code}")
        print(f"   响应: {response.json()}")
        
        if response.status_code == 200:
            print("   ✅ 全局 MCP 模板注册成功")
        elif response.status_code == 409:
            print("   ⚠️ MCP 已存在（跳过）")
        else:
            print(f"   ❌ 注册失败: {response.text}")
            return
        
        # ============================================================
        # 2. 列出全局 MCP 模板
        # ============================================================
        print("\n📋 2. 列出全局 MCP 模板...")
        
        response = await client.get("/api/v1/tools/mcp")
        print(f"   状态码: {response.status_code}")
        data = response.json()
        print(f"   总数: {data.get('total', 0)}")
        
        if data.get("servers"):
            for server in data["servers"]:
                print(f"   - {server.get('server_name')}: {server.get('server_url')}")
        
        # ============================================================
        # 3. 获取全局 MCP 详情
        # ============================================================
        print("\n🔍 3. 获取全局 MCP 详情...")
        
        response = await client.get("/api/v1/tools/mcp/notion_test")
        print(f"   状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"   名称: {data.get('server_name')}")
            print(f"   URL: {data.get('server_url')}")
            print(f"   认证类型: {data.get('auth_type')}")
            print(f"   是否全局: {data.get('is_global')}")
        else:
            print(f"   ❌ 获取失败: {response.text}")
        
        # ============================================================
        # 4. 检查 Agent 是否存在
        # ============================================================
        print(f"\n🔍 4. 检查 Agent '{TEST_AGENT_ID}' 是否存在...")
        
        response = await client.get(f"/api/v1/agents/{TEST_AGENT_ID}")
        
        if response.status_code != 200:
            print(f"   ⚠️ Agent '{TEST_AGENT_ID}' 不存在，跳过 Agent-MCP 测试")
            print("   提示: 请先创建 Agent 或修改 TEST_AGENT_ID 变量")
            
            # 列出可用的 Agent
            response = await client.get("/api/v1/agents")
            if response.status_code == 200:
                agents = response.json().get("agents", [])
                if agents:
                    print(f"   可用的 Agent: {[a.get('agent_id') for a in agents]}")
                else:
                    print("   没有可用的 Agent")
            
            # 跳到清理步骤
            await cleanup_test_mcp(client)
            return
        
        print(f"   ✅ Agent '{TEST_AGENT_ID}' 存在")
        
        # ============================================================
        # 5. 为 Agent 启用 MCP
        # ============================================================
        print(f"\n🔗 5. 为 Agent '{TEST_AGENT_ID}' 启用 MCP...")
        
        enable_data = {
            "auth_env": "MY_AGENT_NOTION_TOKEN",
            "metadata": {"custom_config": "test"}
        }
        
        response = await client.post(
            f"/api/v1/agents/{TEST_AGENT_ID}/mcp/notion_test",
            json=enable_data
        )
        print(f"   状态码: {response.status_code}")
        print(f"   响应: {response.json()}")
        
        if response.status_code == 201:
            print("   ✅ MCP 启用成功")
        elif response.status_code == 409:
            print("   ⚠️ MCP 已启用（跳过）")
        else:
            print(f"   ❌ 启用失败: {response.text}")
        
        # ============================================================
        # 6. 列出 Agent 的 MCP
        # ============================================================
        print(f"\n📋 6. 列出 Agent '{TEST_AGENT_ID}' 的 MCP...")
        
        response = await client.get(f"/api/v1/agents/{TEST_AGENT_ID}/mcp")
        print(f"   状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"   总数: {data.get('total', 0)}")
            
            if data.get("mcps"):
                for mcp in data["mcps"]:
                    print(f"   - {mcp.get('original_name')}: auth_env={mcp.get('auth_env')}")
        
        # ============================================================
        # 7. 获取 Agent 的 MCP 配置
        # ============================================================
        print(f"\n🔍 7. 获取 Agent '{TEST_AGENT_ID}' 的 MCP 'notion_test' 配置...")
        
        response = await client.get(f"/api/v1/agents/{TEST_AGENT_ID}/mcp/notion_test")
        print(f"   状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"   认证环境变量: {data.get('auth_env')}")
            print(f"   元数据: {data.get('metadata')}")
        
        # ============================================================
        # 8. 获取可用的全局 MCP（带启用状态标注）
        # ============================================================
        print(f"\n📋 8. 获取可用的全局 MCP（带启用状态）...")
        
        response = await client.get(f"/api/v1/agents/{TEST_AGENT_ID}/mcp/available")
        print(f"   状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"   总数: {data.get('total', 0)}")
            print(f"   已启用数: {data.get('enabled_count', 0)}")
            
            if data.get("mcps"):
                for mcp in data["mcps"]:
                    status = "✅已启用" if mcp.get("is_enabled_by_agent") else "⬜未启用"
                    print(f"   - {mcp.get('server_name')}: {status}")
        
        # ============================================================
        # 9. 更新 Agent 的 MCP 配置
        # ============================================================
        print(f"\n📝 9. 更新 Agent '{TEST_AGENT_ID}' 的 MCP 配置...")
        
        update_data = {
            "auth_env": "UPDATED_NOTION_TOKEN",
            "metadata": {"updated": True}
        }
        
        response = await client.put(
            f"/api/v1/agents/{TEST_AGENT_ID}/mcp/notion_test",
            json=update_data
        )
        print(f"   状态码: {response.status_code}")
        
        if response.status_code == 200:
            print("   ✅ MCP 配置更新成功")
        else:
            print(f"   ❌ 更新失败: {response.text}")
        
        # ============================================================
        # 10. 禁用 Agent 的 MCP
        # ============================================================
        print(f"\n🗑️ 10. 禁用 Agent '{TEST_AGENT_ID}' 的 MCP...")
        
        response = await client.delete(f"/api/v1/agents/{TEST_AGENT_ID}/mcp/notion_test")
        print(f"   状态码: {response.status_code}")
        
        if response.status_code == 200:
            print("   ✅ MCP 禁用成功")
        else:
            print(f"   ❌ 禁用失败: {response.text}")
        
        # ============================================================
        # 11. 清理：删除全局 MCP 模板
        # ============================================================
        await cleanup_test_mcp(client)
        
        print("\n" + "=" * 60)
        print("测试完成！")
        print("=" * 60)


async def cleanup_test_mcp(client):
    """清理测试创建的 MCP"""
    print("\n🧹 清理：删除全局 MCP 模板 'notion_test'...")
    
    response = await client.delete("/api/v1/tools/mcp/notion_test")
    print(f"   状态码: {response.status_code}")
    
    if response.status_code == 200:
        print("   ✅ 清理成功")
    elif response.status_code == 404:
        print("   ⚠️ MCP 不存在（已清理）")
    else:
        print(f"   ❌ 清理失败: {response.text}")


async def main():
    """主函数"""
    print("🚀 开始测试...")
    print(f"   服务器地址: {BASE_URL}")
    print(f"   测试 Agent: {TEST_AGENT_ID}")
    
    # 检查服务器是否可用
    try:
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=5.0) as client:
            response = await client.get("/")
            if response.status_code != 200:
                print(f"❌ 服务器健康检查失败: {response.status_code}")
                return
    except Exception as e:
        print(f"❌ 无法连接到服务器: {e}")
        print("   请确保服务器正在运行: python main.py")
        return
    
    print("   ✅ 服务器连接正常")
    
    await test_mcp_registration()


if __name__ == "__main__":
    asyncio.run(main())


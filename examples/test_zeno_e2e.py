"""
端到端测试 - 模拟 Zeno 前端输入，查看原始返回信息

使用方法：
1. 启动后端服务：python main.py
2. 运行测试：python examples/test_zeno_e2e.py
"""

import asyncio
import httpx
import json
import time
from datetime import datetime
from typing import Optional


# ==================== 配置 ====================

BASE_URL = "http://localhost:8000/api"

# 测试配置
TEST_CONFIG = {
    "user_id": f"test_zeno_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    "agent_id": None,  # None 使用默认 Agent，或指定如 "dazee_agent"
    "format": "zeno",  # "zeno" 或 "zenflux"
}


# ==================== 测试场景 ====================

class TestScenario:
    """测试场景定义"""
    
    @staticmethod
    def simple_question():
        """场景1：简单问答（无工具调用）"""
        return {
            "name": "简单问答",
            "request": {
                "message": "你好，请简单介绍一下自己",
                "user_id": TEST_CONFIG["user_id"],
                "agent_id": TEST_CONFIG["agent_id"],
                "stream": True
            },
            "description": "测试基础对话能力，不涉及工具调用"
        }
    
    @staticmethod
    def tool_call():
        """场景2：需要工具调用"""
        return {
            "name": "工具调用",
            "request": {
                "message": "北京现在的天气怎么样？",
                "user_id": TEST_CONFIG["user_id"],
                "agent_id": TEST_CONFIG["agent_id"],
                "stream": True
            },
            "description": "测试工具调用能力（如天气查询）"
        }
    
    @staticmethod
    def complex_task():
        """场景3：复杂任务（多工具调用）"""
        return {
            "name": "复杂任务",
            "request": {
                "message": "帮我搜索一下 FastAPI 的最新版本，并告诉我主要的新特性",
                "user_id": TEST_CONFIG["user_id"],
                "agent_id": TEST_CONFIG["agent_id"],
                "stream": True
            },
            "description": "测试复杂任务处理能力（需要搜索和分析）"
        }
    
    @staticmethod
    def with_files():
        """场景4：带文件附件的请求"""
        return {
            "name": "文件处理",
            "request": {
                "message": "请分析这个文件的内容",
                "user_id": TEST_CONFIG["user_id"],
                "agent_id": TEST_CONFIG["agent_id"],
                "stream": True,
                "files": [
                    {
                        "file_url": "https://example.com/doc.pdf",
                        "file_name": "示例文档.pdf",
                        "file_size": 102400,
                        "file_type": "application/pdf"
                    }
                ]
            },
            "description": "测试文件处理能力"
        }
    
    @staticmethod
    def with_context():
        """场景5：带上下文变量的请求"""
        return {
            "name": "上下文感知",
            "request": {
                "message": "根据我当前的位置，推荐一些适合的活动",
                "user_id": TEST_CONFIG["user_id"],
                "agent_id": TEST_CONFIG["agent_id"],
                "stream": True,
                "variables": {
                    "location": "北京市朝阳区",
                    "timezone": "Asia/Shanghai",
                    "locale": "zh-CN",
                    "device": "mobile",
                    "currentTime": datetime.now().isoformat()
                }
            },
            "description": "测试上下文变量注入能力"
        }
    
    @staticmethod
    def multi_turn():
        """场景6：多轮对话"""
        return {
            "name": "多轮对话",
            "request": {
                "message": "继续上一个话题，详细说说",
                "user_id": TEST_CONFIG["user_id"],
                "agent_id": TEST_CONFIG["agent_id"],
                "conversation_id": None,  # 会在运行时填充
                "stream": True
            },
            "description": "测试多轮对话上下文延续能力"
        }
    
    @staticmethod
    def hitl_request():
        """场景7：需要人工确认的请求"""
        return {
            "name": "人工确认",
            "request": {
                "message": "请帮我发送一封邮件给 test@example.com，标题是'测试邮件'",
                "user_id": TEST_CONFIG["user_id"],
                "agent_id": TEST_CONFIG["agent_id"],
                "stream": True
            },
            "description": "测试 HITL（人工在环）流程"
        }
    
    @staticmethod
    def thinking_task():
        """场景8：需要深度思考的任务"""
        return {
            "name": "深度思考",
            "request": {
                "message": "分析一下量子计算对未来人工智能发展的影响",
                "user_id": TEST_CONFIG["user_id"],
                "agent_id": TEST_CONFIG["agent_id"],
                "stream": True
            },
            "description": "测试 Extended Thinking（思考块）能力"
        }


# ==================== 测试执行器 ====================

class E2ETestRunner:
    """端到端测试执行器"""
    
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=120.0)
        self.results = []
        self.conversation_id = None
    
    async def close(self):
        """关闭客户端"""
        await self.client.aclose()
    
    async def test_scenario(self, scenario: dict, print_raw: bool = True):
        """
        执行测试场景
        
        Args:
            scenario: 测试场景定义
            print_raw: 是否打印原始返回信息
        """
        print("\n" + "=" * 80)
        print(f"🧪 测试场景：{scenario['name']}")
        print("=" * 80)
        print(f"📝 描述：{scenario['description']}")
        print(f"📤 请求体：")
        print(json.dumps(scenario['request'], indent=2, ensure_ascii=False))
        print("\n" + "-" * 80)
        print("📥 原始返回信息：")
        print("-" * 80 + "\n")
        
        # 如果是多轮对话，使用之前的 conversation_id
        if scenario['name'] == "多轮对话" and self.conversation_id:
            scenario['request']['conversation_id'] = self.conversation_id
        
        # 记录开始时间
        start_time = time.time()
        event_count = 0
        error_occurred = False
        
        try:
            # 发送流式请求
            async with self.client.stream(
                "POST",
                f"{BASE_URL}/v1/chat",
                json=scenario['request'],
                params={"format": TEST_CONFIG["format"]},
                headers={"Accept": "text/event-stream"}
            ) as response:
                if response.status_code != 200:
                    print(f"❌ 请求失败: HTTP {response.status_code}")
                    print(await response.aread())
                    error_occurred = True
                    return
                
                print(f"✅ SSE 连接已建立: HTTP {response.status_code}\n")
                
                # 接收并打印所有事件
                async for line in response.aiter_lines():
                    if print_raw:
                        # 打印原始 SSE 行
                        print(line)
                    
                    # 解析事件
                    if line.startswith('data:'):
                        event_count += 1
                        data_str = line[5:].strip()  # 去掉 "data:" 前缀
                        
                        if not data_str or data_str == "{}":
                            continue
                        
                        try:
                            event_data = json.loads(data_str)
                            event_type = event_data.get('type', '')
                            
                            # 提取关键信息
                            if event_type == 'message_start' or event_type == 'message.assistant.start':
                                session_id = event_data.get('session_id') or event_data.get('data', {}).get('session_id')
                                conv_id = event_data.get('conversation_id') or event_data.get('data', {}).get('conversation_id')
                                if conv_id:
                                    self.conversation_id = conv_id
                                print(f"\n[事件 #{event_count}] {event_type}")
                                print(f"  session_id: {session_id}")
                                print(f"  conversation_id: {conv_id}")
                            
                            elif event_type == 'content_start' or event_type == 'message.assistant.content_start':
                                content = event_data.get('content') or event_data.get('data', {}).get('content')
                                content_type = content.get('type') if content else None
                                print(f"\n[事件 #{event_count}] {event_type}")
                                print(f"  content_type: {content_type}")
                            
                            elif 'error' in event_type:
                                print(f"\n[事件 #{event_count}] ❌ {event_type}")
                                error_info = event_data.get('error') or event_data.get('data', {}).get('error')
                                print(f"  错误信息: {error_info}")
                                error_occurred = True
                            
                            elif event_type in ('message_stop', 'message.assistant.done'):
                                print(f"\n[事件 #{event_count}] {event_type}")
                                usage = event_data.get('usage') or event_data.get('data', {}).get('usage')
                                if usage:
                                    print(f"  usage: {usage}")
                                break
                            
                        except json.JSONDecodeError:
                            pass
                    
                    elif line.startswith('event:'):
                        if print_raw:
                            event_name = line[6:].strip()
                            if event_name == 'done':
                                print("\n[SSE 协议] event: done (流结束)")
        
        except httpx.TimeoutException:
            print(f"\n❌ 请求超时")
            error_occurred = True
        except Exception as e:
            print(f"\n❌ 请求失败: {e}")
            import traceback
            traceback.print_exc()
            error_occurred = True
        
        # 打印统计信息
        elapsed = time.time() - start_time
        print("\n" + "-" * 80)
        print("📊 测试统计：")
        print("-" * 80)
        print(f"  总耗时：{elapsed:.2f}s")
        print(f"  事件数量：{event_count}")
        print(f"  状态：{'❌ 失败' if error_occurred else '✅ 成功'}")
        
        # 记录结果
        self.results.append({
            "scenario": scenario['name'],
            "success": not error_occurred,
            "event_count": event_count,
            "elapsed": elapsed
        })
    
    def print_summary(self):
        """打印测试总结"""
        print("\n\n" + "=" * 80)
        print("📈 测试总结")
        print("=" * 80 + "\n")
        
        total = len(self.results)
        success = sum(1 for r in self.results if r['success'])
        
        print(f"总测试数：{total}")
        print(f"成功：{success}")
        print(f"失败：{total - success}")
        print()
        
        print("详细结果：")
        print("-" * 80)
        for r in self.results:
            status = "✅" if r['success'] else "❌"
            print(f"{status} {r['scenario']:20s} | 事件数: {r['event_count']:4d} | 耗时: {r['elapsed']:6.2f}s")


# ==================== 主函数 ====================

async def main():
    """主测试流程"""
    print("=" * 80)
    print("🚀 Zeno 端到端测试")
    print("=" * 80)
    print(f"📍 后端地址: {BASE_URL}")
    print(f"👤 测试用户: {TEST_CONFIG['user_id']}")
    print(f"🤖 Agent ID: {TEST_CONFIG['agent_id'] or '默认'}")
    print(f"📋 事件格式: {TEST_CONFIG['format']}")
    print("=" * 80)
    
    # 初始化测试执行器
    runner = E2ETestRunner()
    
    try:
        # 检查服务是否可用
        print("\n🔍 检查服务状态...")
        try:
            response = await runner.client.get(f"{BASE_URL}/../health")
            if response.status_code == 200:
                print("✅ 服务正常运行")
            else:
                print(f"⚠️ 服务响应异常: HTTP {response.status_code}")
        except Exception as e:
            print(f"❌ 无法连接到服务: {e}")
            print("\n请确保后端服务已启动：")
            print("  python main.py")
            return
        
        # 选择测试场景
        print("\n📋 可用的测试场景：")
        scenarios = [
            ("1", "简单问答", TestScenario.simple_question),
            ("2", "工具调用", TestScenario.tool_call),
            ("3", "复杂任务", TestScenario.complex_task),
            ("4", "文件处理", TestScenario.with_files),
            ("5", "上下文感知", TestScenario.with_context),
            ("6", "多轮对话", TestScenario.multi_turn),
            ("7", "人工确认", TestScenario.hitl_request),
            ("8", "深度思考", TestScenario.thinking_task),
            ("0", "自定义消息", None),
            ("9", "全部场景", None),
        ]
        
        for num, name, _ in scenarios:
            print(f"  {num}. {name}")
        
        print("\n请选择测试场景（输入数字，默认1）: ", end="")
        
        choice = input().strip() or "1"
        
        if choice == "0":
            # 自定义消息
            print("\n💬 请输入您的消息内容: ", end="")
            custom_message = input().strip()
            
            if not custom_message:
                print("❌ 消息内容不能为空")
                return
            
            # 询问是否需要额外配置
            print("\n是否需要配置额外选项？(y/n，默认n): ", end="")
            need_config = input().strip().lower() == 'y'
            
            custom_scenario = {
                "name": "自定义消息",
                "request": {
                    "message": custom_message,
                    "user_id": TEST_CONFIG["user_id"],
                    "agent_id": TEST_CONFIG["agent_id"],
                    "stream": True
                },
                "description": f"自定义测试: {custom_message[:50]}..."
            }
            
            if need_config:
                print("\nAgent ID (直接回车使用默认): ", end="")
                agent_input = input().strip()
                if agent_input:
                    custom_scenario["request"]["agent_id"] = agent_input
                
                print("添加上下文变量？(y/n): ", end="")
                if input().strip().lower() == 'y':
                    print("位置 (如: 北京市朝阳区): ", end="")
                    location = input().strip()
                    if location:
                        custom_scenario["request"]["variables"] = {
                            "location": location,
                            "timezone": "Asia/Shanghai",
                            "locale": "zh-CN",
                            "currentTime": datetime.now().isoformat()
                        }
            
            print(f"\n🎯 运行自定义测试\n")
            await runner.test_scenario(custom_scenario, print_raw=True)
        
        elif choice == "9":
            # 运行所有场景
            print("\n🎯 运行所有测试场景\n")
            for num, name, scenario_fn in scenarios[:-2]:  # 排除"自定义消息"和"全部场景"
                if scenario_fn:
                    scenario = scenario_fn()
                    await runner.test_scenario(scenario, print_raw=True)
                    await asyncio.sleep(1)  # 场景间隔
        else:
            # 运行单个场景
            try:
                scenario_idx = int(choice)
                if scenario_idx == 0:
                    print("❌ 请使用选项 0 输入自定义消息")
                elif 1 <= scenario_idx <= 8:
                    _, name, scenario_fn = scenarios[scenario_idx - 1]
                    print(f"\n🎯 运行测试场景：{name}\n")
                    scenario = scenario_fn()
                    await runner.test_scenario(scenario, print_raw=True)
                else:
                    print("❌ 无效的选择")
            except ValueError:
                print("❌ 请输入数字")
        
        # 打印总结
        runner.print_summary()
    
    finally:
        await runner.close()


if __name__ == "__main__":
    print("\n⚠️  请确保后端服务已启动: python main.py\n")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ 测试被用户中断")
    except Exception as e:
        print(f"\n\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

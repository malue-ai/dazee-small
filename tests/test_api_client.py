"""
API 测试客户端
测试同步聊天和流式聊天功能
"""
import requests
import json
import time

BASE_URL = "http://localhost:8000"


def test_health():
    """测试健康检查"""
    print("=" * 60)
    print("🔍 测试 1: 健康检查")
    print("=" * 60)
    
    response = requests.get(f"{BASE_URL}/health")
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    print()


def test_simple_chat():
    """测试简单聊天"""
    print("=" * 60)
    print("🔍 测试 2: 简单聊天 - 同步模式")
    print("=" * 60)
    
    request_data = {
        "message": "你好，请用一句话介绍一下你自己",
        "stream": False
    }
    
    print(f"发送请求: {request_data['message']}")
    print("等待响应...")
    
    start_time = time.time()
    response = requests.post(
        f"{BASE_URL}/api/v1/chat",
        json=request_data,
        timeout=120
    )
    elapsed = time.time() - start_time
    
    print(f"\n状态码: {response.status_code}")
    print(f"耗时: {elapsed:.2f}秒")
    
    if response.status_code == 200:
        data = response.json()
        print(f"\n✅ 成功!")
        print(f"会话ID: {data['data']['session_id']}")
        print(f"状态: {data['data']['status']}")
        print(f"轮次: {data['data']['turns']}")
        print(f"\n回复内容:")
        print("-" * 60)
        print(data['data']['content'])
        print("-" * 60)
        return data['data']['session_id']
    else:
        print(f"❌ 失败: {response.text}")
        return None


def test_ppt_generation():
    """测试 PPT 生成（复杂任务）"""
    print("\n" + "=" * 60)
    print("🔍 测试 3: PPT 生成 - 同步模式（复杂任务）")
    print("=" * 60)
    
    request_data = {
        "message": "帮我生成一个关于人工智能发展的PPT大纲，包含3个主要部分",
        "stream": False
    }
    
    print(f"发送请求: {request_data['message']}")
    print("等待响应（复杂任务可能需要较长时间）...")
    
    start_time = time.time()
    response = requests.post(
        f"{BASE_URL}/api/v1/chat",
        json=request_data,
        timeout=180
    )
    elapsed = time.time() - start_time
    
    print(f"\n状态码: {response.status_code}")
    print(f"耗时: {elapsed:.2f}秒")
    
    if response.status_code == 200:
        data = response.json()
        print(f"\n✅ 成功!")
        print(f"会话ID: {data['data']['session_id']}")
        print(f"状态: {data['data']['status']}")
        print(f"轮次: {data['data']['turns']}")
        
        # 显示进度信息
        if data['data'].get('progress'):
            progress = data['data']['progress']
            print(f"\n进度信息:")
            print(f"  总步骤: {progress['total']}")
            print(f"  已完成: {progress['completed']}")
            print(f"  进度: {progress['progress']*100:.0f}%")
        
        # 显示工具调用统计
        if data['data'].get('invocation_stats'):
            stats = data['data']['invocation_stats']
            print(f"\n工具调用统计:")
            for method, count in stats.items():
                if count > 0:
                    print(f"  {method}: {count}次")
        
        print(f"\n回复内容:")
        print("-" * 60)
        print(data['data']['content'][:500] + "..." if len(data['data']['content']) > 500 else data['data']['content'])
        print("-" * 60)
        return data['data']['session_id']
    else:
        print(f"❌ 失败: {response.text}")
        return None


def test_stream_chat():
    """测试流式聊天"""
    print("\n" + "=" * 60)
    print("🔍 测试 4: 简单问答 - 流式模式")
    print("=" * 60)
    
    request_data = {
        "message": "什么是机器学习？用3句话解释",
        "session_id": "test-stream-session",
        "stream": True
    }
    
    print(f"发送请求: {request_data['message']}")
    print("实时接收事件流:")
    print("-" * 60)
    
    response = requests.post(
        f"{BASE_URL}/api/v1/chat/stream",
        json=request_data,
        stream=True,
        timeout=120
    )
    
    if response.status_code == 200:
        event_count = 0
        content_parts = []
        
        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    event_data = json.loads(line[6:])
                    event_type = event_data['type']
                    event_count += 1
                    
                    if event_type == 'session_start':
                        print("🚀 会话开始")
                    elif event_type == 'status':
                        msg = event_data['data'].get('message', '')
                        print(f"📌 {msg}")
                    elif event_type == 'thinking':
                        print("💭 ", end='', flush=True)
                    elif event_type == 'content':
                        text = event_data['data'].get('text', '')
                        content_parts.append(text)
                        print(text, end='', flush=True)
                    elif event_type == 'tool_call_start':
                        tool_name = event_data['data'].get('tool_name', '')
                        print(f"\n🔧 工具调用: {tool_name}")
                    elif event_type == 'tool_call_complete':
                        success = event_data['data'].get('success', False)
                        status = "✅" if success else "❌"
                        print(f"   {status} 完成")
                    elif event_type == 'plan_update':
                        print("\n📋 进度更新")
                    elif event_type == 'complete':
                        print("\n✅ 任务完成")
                    elif event_type == 'done':
                        print("\n🏁 流结束")
                        break
                    elif event_type == 'error':
                        msg = event_data['data'].get('message', '')
                        print(f"\n❌ 错误: {msg}")
        
        print("-" * 60)
        print(f"\n总事件数: {event_count}")
        print(f"内容长度: {len(''.join(content_parts))} 字符")
    else:
        print(f"❌ 失败: {response.text}")


def test_session_info(session_id):
    """测试获取会话信息"""
    if not session_id:
        return
    
    print("\n" + "=" * 60)
    print("🔍 测试 5: 获取会话信息")
    print("=" * 60)
    
    response = requests.get(f"{BASE_URL}/api/v1/session/{session_id}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ 会话信息:")
        print(json.dumps(data['data'], indent=2, ensure_ascii=False))
    else:
        print(f"❌ 失败: {response.text}")


def test_slidespeak_render():
    """测试 SlideSpeak 工具渲染 PPT"""
    print("\n" + "=" * 60)
    print("🔍 测试 6: SlideSpeak PPT 渲染")
    print("=" * 60)
    
    request_data = {
        "message": """帮我生成一个关于"Python编程入门"的PPT，包含以下内容：

1. 封面页：标题"Python编程入门"
2. 什么是Python
3. Python的主要特点
4. 第一个Python程序
5. 总结

请使用DEFAULT模板，语言为CHINESE。""",
        "stream": False
    }
    
    print(f"发送请求: SlideSpeak PPT 渲染测试")
    print("等待响应（PPT渲染可能需要1-2分钟）...")
    
    start_time = time.time()
    response = requests.post(
        f"{BASE_URL}/api/v1/chat",
        json=request_data,
        timeout=300  # 5分钟超时
    )
    elapsed = time.time() - start_time
    
    print(f"\n状态码: {response.status_code}")
    print(f"耗时: {elapsed:.2f}秒")
    
    if response.status_code == 200:
        data = response.json()
        print(f"\n✅ 成功!")
        print(f"会话ID: {data['data']['session_id']}")
        print(f"状态: {data['data']['status']}")
        print(f"轮次: {data['data']['turns']}")
        
        # 显示工具调用统计
        if data['data'].get('invocation_stats'):
            stats = data['data']['invocation_stats']
            print(f"\n工具调用统计:")
            for method, count in stats.items():
                if count > 0:
                    print(f"  {method}: {count}次")
        
        # 检查回复中是否包含PPT相关信息
        content = data['data']['content']
        print(f"\n回复内容:")
        print("-" * 60)
        print(content)
        print("-" * 60)
        
        # 验证是否成功调用了 slidespeak_render
        if "slidespeak" in content.lower() or "ppt" in content.lower() or ".pptx" in content.lower():
            print("\n✅ 检测到 PPT 相关输出")
            
            # 提取文件路径（如果有）
            if "outputs/ppt/" in content or "local_path" in content:
                print("✅ 检测到本地文件路径")
            
            # 提取下载链接（如果有）
            if "download_url" in content or "https://" in content:
                print("✅ 检测到下载链接")
        else:
            print("\n⚠️  未检测到 PPT 相关输出，可能工具调用失败")
        
        return data['data']['session_id']
    else:
        print(f"❌ 失败: {response.text}")
        return None


def test_list_sessions():
    """测试列出所有会话"""
    print("\n" + "=" * 60)
    print("🔍 测试 7: 列出所有会话")
    print("=" * 60)
    
    response = requests.get(f"{BASE_URL}/api/v1/sessions")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ 活跃会话数: {data['data']['total']}")
        if data['data']['sessions']:
            print("\n会话列表:")
            for session in data['data']['sessions']:
                print(f"  - {session['session_id']}: "
                      f"{'活跃' if session['active'] else '已结束'}, "
                      f"{session['turns']} 轮, "
                      f"{session['message_count']} 消息")
    else:
        print(f"❌ 失败: {response.text}")


def main():
    """运行所有测试"""
    print("\n" + "🚀" * 30)
    print("开始 API 测试")
    print("🚀" * 30 + "\n")
    
    try:
        # 1. 健康检查
        test_health()
        time.sleep(1)
        
        # 2. 简单聊天
        simple_session_id = test_simple_chat()
        time.sleep(2)
        
        # 3. PPT 生成（复杂任务）
        ppt_session_id = test_ppt_generation()
        time.sleep(2)
        
        # 4. 流式聊天
        test_stream_chat()
        time.sleep(2)
        
        # 5. 获取会话信息
        if simple_session_id:
            test_session_info(simple_session_id)
        time.sleep(1)
        
        # 6. SlideSpeak PPT 渲染测试
        slidespeak_session_id = test_slidespeak_render()
        time.sleep(2)
        
        # 7. 列出所有会话
        test_list_sessions()
        
        print("\n" + "=" * 60)
        print("✅ 所有测试完成！")
        print("=" * 60)
        
    except requests.exceptions.ConnectionError:
        print("\n❌ 错误: 无法连接到服务器")
        print("   请确保服务器正在运行: uvicorn main:app --host 0.0.0.0 --port 8000")
    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()


"""
SlideSpeak 工具专项测试
测试 slidespeak_render 工具的调用能力
"""
import requests
import json
import time

BASE_URL = "http://localhost:8000"


def test_slidespeak_simple():
    """测试简单的 SlideSpeak PPT 生成"""
    print("=" * 60)
    print("🔍 测试 1: 简单 PPT 生成（3页）")
    print("=" * 60)
    
    request_data = {
        "message": """请帮我生成一个关于"机器学习基础"的PPT""",
        "stream": False
    }
    
    print(f"📝 任务: {request_data['message'][:50]}...")
    print("⏳ 等待响应（预计1-2分钟）...\n")
    
    start_time = time.time()
    response = requests.post(
        f"{BASE_URL}/api/v1/chat",
        json=request_data,
        timeout=300
    )
    elapsed = time.time() - start_time
    
    print(f"\n⏱️  耗时: {elapsed:.2f}秒")
    print(f"📊 状态码: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        content = data['data']['content']
        
        print("\n" + "=" * 60)
        print("✅ 请求成功！")
        print("=" * 60)
        print(f"会话ID: {data['data']['session_id']}")
        print(f"轮次: {data['data']['turns']}")
        
        # 显示工具调用统计
        if data['data'].get('invocation_stats'):
            print("\n📊 工具调用统计:")
            for method, count in data['data']['invocation_stats'].items():
                if count > 0:
                    print(f"  • {method}: {count}次")
        
        print("\n📄 回复内容:")
        print("-" * 60)
        print(content)
        print("-" * 60)
        
        # 验证结果
        print("\n🔍 结果验证:")
        checks = {
            "slidespeak_render 被调用": "slidespeak" in content.lower(),
            "包含下载链接": "download_url" in content or "https://" in content,
            "包含本地路径": "local_path" in content or "outputs/ppt/" in content,
            "生成成功": "success" in content.lower() and "true" in content.lower(),
        }
        
        for check, result in checks.items():
            status = "✅" if result else "❌"
            print(f"  {status} {check}")
        
        all_passed = all(checks.values())
        if all_passed:
            print("\n🎉 所有验证通过！PPT 生成成功！")
        else:
            print("\n⚠️  部分验证未通过，请检查输出内容")
        
        return data['data']['session_id'], all_passed
    else:
        print(f"\n❌ 请求失败: {response.text}")
        return None, False


def test_slidespeak_complex():
    """测试复杂的 SlideSpeak PPT 生成（多布局）"""
    print("\n" + "=" * 60)
    print("🔍 测试 2: 复杂 PPT 生成（多种布局）")
    print("=" * 60)
    
    request_data = {
        "message": """请使用 slidespeak_render 工具生成一个"Python vs JavaScript对比"的PPT，要求：

1. 标题页：Python vs JavaScript
2. 使用 COMPARISON 布局对比两者特点
3. 使用 ITEMS 布局展示 Python 的优势（3个要点）
4. 使用 ITEMS 布局展示 JavaScript 的优势（3个要点）
5. 总结页

使用 DEFAULT 模板，CHINESE 语言。""",
        "stream": False
    }
    
    print(f"📝 任务: 生成复杂布局的对比PPT")
    print("⏳ 等待响应（预计2-3分钟）...\n")
    
    start_time = time.time()
    response = requests.post(
        f"{BASE_URL}/api/v1/chat",
        json=request_data,
        timeout=300
    )
    elapsed = time.time() - start_time
    
    print(f"\n⏱️  耗时: {elapsed:.2f}秒")
    print(f"📊 状态码: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        content = data['data']['content']
        
        print("\n" + "=" * 60)
        print("✅ 请求成功！")
        print("=" * 60)
        
        print(f"\n📄 回复内容（前500字符）:")
        print("-" * 60)
        print(content[:500] + "..." if len(content) > 500 else content)
        print("-" * 60)
        
        # 验证布局
        print("\n🔍 布局验证:")
        layouts = ["COMPARISON", "ITEMS"]
        for layout in layouts:
            found = layout.lower() in content.lower()
            status = "✅" if found else "⚠️ "
            print(f"  {status} {layout} 布局")
        
        return data['data']['session_id']
    else:
        print(f"\n❌ 请求失败: {response.text}")
        return None


def test_slidespeak_with_charts():
    """测试带图表的 PPT 生成"""
    print("\n" + "=" * 60)
    print("🔍 测试 3: 带图表的 PPT 生成")
    print("=" * 60)
    
    request_data = {
        "message": """请使用 slidespeak_render 工具生成一个"2024年销售数据分析"的PPT，要求：

1. 标题页：2024年销售数据分析
2. 使用 CHART 布局展示季度销售趋势（柱状图）
   数据：Q1: 100万, Q2: 150万, Q3: 180万, Q4: 200万
3. 使用 BIG_NUMBER 布局展示总销售额：630万
4. 总结与展望

使用 DEFAULT 模板，CHINESE 语言。""",
        "stream": False
    }
    
    print(f"📝 任务: 生成带图表的PPT")
    print("⏳ 等待响应（预计2-3分钟）...\n")
    
    start_time = time.time()
    response = requests.post(
        f"{BASE_URL}/api/v1/chat",
        json=request_data,
        timeout=300
    )
    elapsed = time.time() - start_time
    
    print(f"\n⏱️  耗时: {elapsed:.2f}秒")
    print(f"📊 状态码: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print("\n✅ 请求成功！")
        print(f"会话ID: {data['data']['session_id']}")
        
        # 验证图表相关内容
        content = data['data']['content']
        print("\n🔍 图表验证:")
        chart_features = {
            "CHART 布局": "chart" in content.lower(),
            "BIG_NUMBER 布局": "big_number" in content.lower() or "bignumber" in content.lower(),
            "包含数据": any(str(num) in content for num in ["100", "150", "180", "200", "630"]),
        }
        
        for feature, found in chart_features.items():
            status = "✅" if found else "⚠️ "
            print(f"  {status} {feature}")
        
        return data['data']['session_id']
    else:
        print(f"\n❌ 请求失败: {response.text}")
        return None


def main():
    """运行所有 SlideSpeak 测试"""
    print("\n" + "🎨" * 30)
    print("SlideSpeak 工具专项测试")
    print("🎨" * 30 + "\n")
    
    print("📋 测试说明:")
    print("  • 测试 slidespeak_render 工具的调用能力")
    print("  • 验证不同布局（ITEMS, COMPARISON, CHART, BIG_NUMBER）")
    print("  • 检查 PPT 生成结果和下载链接")
    print()
    
    try:
        # 检查服务器
        print("🔍 检查服务器状态...")
        health = requests.get(f"{BASE_URL}/health", timeout=5)
        if health.status_code != 200:
            print("❌ 服务器未响应")
            return
        print("✅ 服务器正常\n")
        
        results = []
        
        # 测试 1: 简单 PPT
        session_id, passed = test_slidespeak_simple()
        results.append(("简单PPT生成", passed))
        time.sleep(3)
        
        # 测试 2: 复杂布局
        session_id = test_slidespeak_complex()
        results.append(("复杂布局PPT", session_id is not None))
        time.sleep(3)
        
        # 测试 3: 带图表
        session_id = test_slidespeak_with_charts()
        results.append(("图表PPT生成", session_id is not None))
        
        # 总结
        print("\n" + "=" * 60)
        print("📊 测试总结")
        print("=" * 60)
        
        for test_name, result in results:
            status = "✅ 通过" if result else "❌ 失败"
            print(f"{status}  {test_name}")
        
        total = len(results)
        passed = sum(1 for _, r in results if r)
        print(f"\n总计: {passed}/{total} 测试通过")
        
        if passed == total:
            print("\n🎉 所有测试通过！SlideSpeak 工具运行正常！")
        else:
            print("\n⚠️  部分测试失败，请检查日志")
        
    except requests.exceptions.ConnectionError:
        print("\n❌ 错误: 无法连接到服务器")
        print("   请确保服务器正在运行: ./start_server.sh")
    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()


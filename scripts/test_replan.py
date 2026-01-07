"""
Re-Plan 功能测试脚本

测试 plan_todo_tool 的 replan 操作
"""

import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from tools.plan_todo_tool import PlanTodoTool

async def test_replan():
    """测试 Re-Plan 功能"""
    print("=" * 60)
    print("🧪 Re-Plan 功能测试")
    print("=" * 60)
    
    # 1. 创建工具实例
    print("\n📦 初始化 PlanTodoTool...")
    tool = PlanTodoTool()
    
    # 2. 创建初始计划
    print("\n📋 创建初始计划...")
    create_result = await tool.execute(
        operation="create_plan",
        data={"user_query": "做一个简单的待办事项 Web 应用，包含添加、删除、标记完成功能"}
    )
    
    if create_result["status"] != "success":
        print(f"❌ 创建计划失败: {create_result.get('message')}")
        return
    
    plan = create_result["plan"]
    print(f"✅ 计划创建成功: {plan['goal']}")
    print(f"   步骤数: {len(plan['steps'])}")
    for i, step in enumerate(plan['steps']):
        print(f"   {i+1}. [{step['status']}] {step['action'][:50]}...")
    
    # 3. 模拟执行前两个步骤
    print("\n⏳ 模拟执行步骤...")
    
    # 步骤 1 完成
    update_result = await tool.execute(
        operation="update_step",
        data={"step_index": 0, "status": "completed", "result": "HTML 结构创建完成"},
        current_plan=plan
    )
    plan = update_result["plan"]
    print(f"   ✅ 步骤 1 完成")
    
    # 步骤 2 失败
    if len(plan['steps']) > 1:
        update_result = await tool.execute(
            operation="update_step",
            data={"step_index": 1, "status": "failed", "result": "CSS 框架加载失败，网络超时"},
            current_plan=plan
        )
        plan = update_result["plan"]
        print(f"   ❌ 步骤 2 失败: CSS 框架加载失败")
    
    # 4. 测试 Re-Plan（增量策略）
    print("\n🔄 测试 Re-Plan（incremental 策略）...")
    replan_result = await tool.execute(
        operation="replan",
        data={
            "reason": "步骤 2 失败，CSS 框架无法加载，需要改用内联样式方案",
            "strategy": "incremental"
        },
        current_plan=plan
    )
    
    if replan_result["status"] != "success":
        print(f"❌ Re-Plan 失败: {replan_result.get('message')}")
    else:
        new_plan = replan_result["plan"]
        print(f"✅ Re-Plan 成功!")
        print(f"   重规划次数: {replan_result.get('replan_count', 1)}")
        print(f"   新步骤数: {len(new_plan['steps'])}")
        print(f"   保留已完成: {new_plan.get('completed_steps', 0)} 个")
        print("\n   新计划步骤:")
        for i, step in enumerate(new_plan['steps']):
            status_icon = "✅" if step['status'] == 'completed' else "⏳" if step['status'] == 'pending' else "🔄"
            print(f"   {i+1}. [{status_icon}] {step['action'][:60]}...")
    
    # 5. 测试 Re-Plan 次数限制
    print("\n🔄 测试 Re-Plan 次数限制...")
    test_plan = replan_result.get("plan", plan)
    test_plan["replan_count"] = 3  # 模拟已重规划 3 次
    
    limit_result = await tool.execute(
        operation="replan",
        data={"reason": "再次尝试重规划", "strategy": "full"},
        current_plan=test_plan
    )
    
    if limit_result["status"] == "error" and "最大重规划次数" in limit_result.get("message", ""):
        print(f"✅ 次数限制生效: {limit_result['message']}")
    else:
        print(f"⚠️ 次数限制可能未生效: {limit_result}")
    
    print("\n" + "=" * 60)
    print("✅ Re-Plan 功能测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_replan())



"""
简单测试：验证Router是否正确筛选E2B工具
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 设置环境变量
os.environ['E2B_API_KEY'] = 'e2b_83eb67de2fb85d4a8a87ddfe6fca5a89e9f7cc95'

from core.capability_registry import create_capability_registry
from core.capability_router import create_capability_router, select_tools_for_capabilities

def test_router_e2b():
    print("="*70)
    print("测试：Router 筛选 E2B 工具")
    print("="*70)
    
    registry = create_capability_registry()
    router = create_capability_router(registry)
    
    # 场景1：Vibe Coding
    print("\n场景1：Vibe Coding (app_generation)")
    print("-"*70)
    required_capabilities = ['app_generation', 'code_sandbox']
    selected = select_tools_for_capabilities(router, required_capabilities)
    
    print(f"需要能力: {required_capabilities}")
    print(f"选择工具: {[t.name for t in selected]}")
    
    # 验证
    tool_names = [t.name for t in selected]
    if 'e2b_vibe_coding' in tool_names:
        print("✅ e2b_vibe_coding 已选中")
    else:
        print("❌ e2b_vibe_coding 未选中")
    
    if 'e2b_python_sandbox' in tool_names:
        print("✅ e2b_python_sandbox 已选中")
    else:
        print("❌ e2b_python_sandbox 未选中")
    
    # 场景2：纯代码执行
    print("\n场景2：纯代码执行 (code_sandbox)")
    print("-"*70)
    required_capabilities = ['code_sandbox']
    selected = select_tools_for_capabilities(router, required_capabilities)
    
    print(f"需要能力: {required_capabilities}")
    print(f"选择工具: {[t.name for t in selected]}")
    
    tool_names = [t.name for t in selected]
    if 'e2b_python_sandbox' in tool_names:
        print("✅ e2b_python_sandbox 已选中")
    else:
        print("❌ e2b_python_sandbox 未选中")
    
    print("\n" + "="*70)
    print("测试完成")
    print("="*70)

if __name__ == "__main__":
    test_router_e2b()


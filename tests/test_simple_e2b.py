"""
简化的端到端测试 - 直接测试E2B工具执行
跳过完整Agent流程，验证核心功能
"""
import asyncio
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env", override=True)

async def test_e2b_direct():
    """直接测试E2B工具（跳过LLM）"""
    print("="*70)
    print("简化测试：直接执行E2B Vibe Coding工具")
    print("="*70)
    
    # 验证环境
    e2b_key = os.getenv("E2B_API_KEY")
    if not e2b_key:
        print("❌ E2B_API_KEY 未设置")
        return False
    
    print(f"✅ E2B_API_KEY: {e2b_key[:15]}...")
    
    # 创建E2B工具实例
    from core.memory import WorkingMemory
    from tools.e2b_vibe_coding import E2BVibeCoding
    
    memory = WorkingMemory()
    vibe = E2BVibeCoding(memory=memory, api_key=e2b_key)
    
    # 简单的Streamlit应用代码
    streamlit_code = '''
import streamlit as st
import random

st.title("📊 简单数据展示")
st.write("这是一个E2B Vibe Coding测试应用")

# 生成数据
data = [random.randint(1, 100) for _ in range(5)]
st.bar_chart(data)

st.success("✅ 应用运行成功！")
'''
    
    print("\n创建Streamlit应用...")
    result = await vibe.execute(
        action="create",
        stack="streamlit",
        description="简单数据展示测试",
        code=streamlit_code
    )
    
    print(f"\n结果: {result}")
    
    if result.get("success"):
        preview_url = result.get("preview_url")
        if preview_url:
            print(f"\n🎉 成功！预览URL: {preview_url}")
            print("\n⏳ 应用将在30秒后自动终止...")
            await asyncio.sleep(30)
            
            # 终止应用
            app_id = result.get("app_id")
            if app_id:
                await vibe.execute(action="terminate", app_id=app_id)
                print("✅ 应用已终止")
            
            return True
    
    print(f"❌ 失败: {result.get('error')}")
    return False


if __name__ == "__main__":
    success = asyncio.run(test_e2b_direct())
    print(f"\n{'='*70}")
    print(f"测试结果: {'✅ 通过' if success else '❌ 失败'}")
    print(f"{'='*70}")
    sys.exit(0 if success else 1)


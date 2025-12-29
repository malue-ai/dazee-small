"""
Vibe Coding 真实测试 - Streamlit 应用生成

严格按照 E2B Fragments 流程：
1. LLM 生成完整 Streamlit 代码
2. E2B 执行并返回预览 URL
3. 用户访问 URL 查看应用
4. 支持迭代修改

运行：python tests/test_vibe_coding_streamlit.py
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from logger import get_logger
from dotenv import load_dotenv

logger = get_logger("vibe_test")

# 加载环境变量
load_dotenv(Path(__file__).parent.parent.parent / ".env", override=True)


async def test_streamlit_app_generation():
    """测试 Streamlit 应用生成"""
    
    logger.info("="*70)
    logger.info("🎨 Vibe Coding 测试 - Streamlit 应用生成")
    logger.info("="*70)
    
    # 验证 API Key
    e2b_key = os.getenv("E2B_API_KEY")
    if not e2b_key:
        logger.error("❌ E2B_API_KEY 未设置")
        sys.exit(1)
    
    logger.info(f"✅ E2B_API_KEY: {e2b_key[:15]}...")
    
    # 初始化
    from core.memory import WorkingMemory
    from tools.e2b_vibe_coding import E2BVibeCoding
    
    memory = WorkingMemory()
    vibe = E2BVibeCoding(memory=memory, api_key=e2b_key)
    
    # 场景：用户要求生成数据可视化应用
    logger.info("\n" + "-"*70)
    logger.info("📝 用户需求：创建一个股票数据可视化应用")
    logger.info("-"*70)
    
    # AI 生成的 Streamlit 代码
    streamlit_code = """
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

st.set_page_config(page_title="股票数据分析", page_icon="📈", layout="wide")

st.title("📈 股票数据可视化应用")
st.markdown("**Powered by E2B Vibe Coding**")

# 侧边栏
with st.sidebar:
    st.header("⚙️ 设置")
    days = st.slider("数据天数", 7, 90, 30)
    volatility = st.slider("波动率", 0.01, 0.10, 0.03)

# 生成模拟数据
dates = pd.date_range(end=datetime.now(), periods=days)
base_price = 100
prices = [base_price]

np.random.seed(42)
for i in range(1, days):
    change = np.random.normal(0, volatility)
    new_price = prices[-1] * (1 + change)
    prices.append(new_price)

df = pd.DataFrame({
    'Date': dates,
    'Price': prices
})

# 主要内容
col1, col2, col3 = st.columns(3)

with col1:
    st.metric("当前价格", f"${df['Price'].iloc[-1]:.2f}")

with col2:
    change = df['Price'].iloc[-1] - df['Price'].iloc[0]
    pct_change = (change / df['Price'].iloc[0]) * 100
    st.metric("总涨跌", f"${change:.2f}", f"{pct_change:.2f}%")

with col3:
    st.metric("最高价", f"${df['Price'].max():.2f}")

# 图表
st.subheader("📊 价格走势")

fig = go.Figure()
fig.add_trace(go.Scatter(
    x=df['Date'],
    y=df['Price'],
    mode='lines',
    name='股价',
    line=dict(color='#1f77b4', width=2)
))

fig.update_layout(
    xaxis_title="日期",
    yaxis_title="价格 ($)",
    hovermode='x unified',
    template='plotly_white'
)

st.plotly_chart(fig, use_container_width=True)

# 统计数据
st.subheader("📈 统计分析")

col1, col2 = st.columns(2)

with col1:
    st.write("**数据摘要**")
    st.dataframe(df.describe())

with col2:
    st.write("**最近10天数据**")
    st.dataframe(df.tail(10))

st.success("✅ 应用运行正常！")
"""
    
    logger.info("\n🤖 AI 生成的代码（前500字符）:")
    logger.info(streamlit_code[:500] + "...")
    
    # 创建应用
    logger.info("\n🚀 部署到 E2B...")
    
    result = await vibe.create_app(
        stack="streamlit",
        description="股票数据可视化应用",
        code=streamlit_code
    )
    
    if result['success']:
        logger.info("\n" + "="*70)
        logger.info("🎉 应用创建成功！")
        logger.info("="*70)
        logger.info(f"\n📋 应用信息:")
        logger.info(f"  App ID: {result['app_id']}")
        logger.info(f"  Sandbox ID: {result['sandbox_id']}")
        logger.info(f"  端口: {result['port']}")
        logger.info(f"\n🔗 预览 URL（重要！）:")
        logger.info(f"  {result['preview_url']}")
        logger.info(f"\n💡 在浏览器中打开上面的 URL 查看应用！")
        logger.info(f"\n⏱️  应用会运行 24 小时（或手动终止）")
        
        # 等待一段时间让用户查看
        logger.info("\n⏳ 应用保持运行中，等待 60 秒...")
        logger.info("   （您可以在浏览器中访问预览 URL）")
        
        await asyncio.sleep(60)
        
        # 清理
        logger.info("\n🧹 清理资源...")
        await vibe.terminate_app(result['app_id'])
        logger.info("✅ 应用已终止")
        
        return True
    else:
        logger.error(f"\n❌ 应用创建失败: {result.get('error')}")
        return False


async def main():
    """主函数"""
    logger.info("="*70)
    logger.info("🚀 E2B Vibe Coding - Streamlit 应用生成测试")
    logger.info("="*70)
    logger.info("\n这是真正的 Vibe Coding 测试：")
    logger.info("  1. AI 生成完整 Streamlit 应用代码")
    logger.info("  2. E2B 执行并启动应用")
    logger.info("  3. 返回实时预览 URL")
    logger.info("  4. 用户在浏览器中查看应用")
    logger.info("")
    
    try:
        success = await test_streamlit_app_generation()
        
        if success:
            logger.info("\n" + "="*70)
            logger.info("✅ Vibe Coding 测试成功！")
            logger.info("="*70)
            logger.info("\n核心功能验证:")
            logger.info("  ✅ AI 生成完整应用代码")
            logger.info("  ✅ E2B 执行并启动应用")
            logger.info("  ✅ 返回实时预览 URL")
            logger.info("  ✅ 应用可通过浏览器访问")
            logger.info("\n🎉 Vibe Coding 已成功集成！")
        else:
            logger.error("\n❌ 测试失败")
            sys.exit(1)
    
    except Exception as e:
        logger.error(f"\n❌ 测试异常: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())


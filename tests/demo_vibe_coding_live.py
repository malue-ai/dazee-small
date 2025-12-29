"""
Vibe Coding 实时演示 - 应用保持运行

创建 Streamlit 应用并保持运行，让用户在浏览器中访问

使用方式：
  python tests/demo_vibe_coding_live.py
  
按 Ctrl+C 终止应用
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from logger import get_logger
from dotenv import load_dotenv

logger = get_logger("vibe_demo")

# 加载环境变量
load_dotenv(Path(__file__).parent.parent.parent / ".env", override=True)


async def create_and_run_streamlit_app():
    """创建并保持运行 Streamlit 应用"""
    
    logger.info("="*70)
    logger.info("🎨 Vibe Coding 实时演示 - Streamlit 应用")
    logger.info("="*70)
    
    # 验证
    e2b_key = os.getenv("E2B_API_KEY")
    if not e2b_key:
        logger.error("❌ E2B_API_KEY 未设置")
        sys.exit(1)
    
    logger.info(f"✅ E2B_API_KEY: {e2b_key[:15]}...")
    
    # 初始化
    from core.memory import WorkingMemory
    from tools.e2b_vibe_coding import E2BVibeCoding
    
    memory = WorkingMemory()
    # 设置沙箱生命周期为 1 小时（免费版最大值）
    vibe = E2BVibeCoding(memory=memory, api_key=e2b_key, sandbox_timeout_hours=1.0)
    
    # Streamlit 应用代码
    streamlit_code = """
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="数据分析应用", page_icon="📊", layout="wide")

# 标题
st.title("📊 E2B Vibe Coding 演示")
st.markdown("**实时数据可视化应用 - Powered by E2B**")

# 侧边栏
with st.sidebar:
    st.header("⚙️ 参数设置")
    data_points = st.slider("数据点数", 10, 200, 50)
    chart_type = st.selectbox("图表类型", ["折线图", "柱状图", "散点图"])

# 生成数据
np.random.seed(42)
df = pd.DataFrame({
    'x': range(data_points),
    'y': np.random.randn(data_points).cumsum(),
    'category': np.random.choice(['A', 'B', 'C'], data_points)
})

# 主要内容
col1, col2, col3 = st.columns(3)

with col1:
    st.metric("数据点", len(df))
with col2:
    st.metric("平均值", f"{df['y'].mean():.2f}")
with col3:
    st.metric("标准差", f"{df['y'].std():.2f}")

# 图表
st.subheader(f"📈 {chart_type}")

if chart_type == "折线图":
    fig = px.line(df, x='x', y='y', color='category', title='数据趋势')
elif chart_type == "柱状图":
    fig = px.bar(df, x='x', y='y', color='category', title='数据分布')
else:
    fig = px.scatter(df, x='x', y='y', color='category', size=abs(df['y']), title='数据散点')

st.plotly_chart(fig, use_container_width=True)

# 数据表
st.subheader("📋 数据详情")
st.dataframe(df, use_container_width=True)

# 统计信息
st.subheader("📊 统计摘要")
st.write(df.describe())

# 页脚
st.divider()
st.caption(f"⏰ 更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
st.caption("🚀 这是一个完全由 AI 生成的应用，运行在 E2B 沙箱中")
"""
    
    logger.info("\n📝 创建 Streamlit 应用...")
    logger.info("   应用类型: 数据可视化")
    logger.info("   技术栈: Streamlit + Plotly")
    
    # 创建应用
    result = await vibe.create_app(
        stack="streamlit",
        description="数据可视化演示应用",
        code=streamlit_code
    )
    
    if not result['success']:
        logger.error(f"❌ 应用创建失败: {result.get('error')}")
        sys.exit(1)
    
    # 显示预览信息
    logger.info("\n" + "="*70)
    logger.info("🎉 Streamlit 应用已创建并运行！")
    logger.info("="*70)
    
    preview_url = result['preview_url']
    app_id = result['app_id']
    sandbox_id = result['sandbox_id']
    
    logger.info(f"\n📋 应用信息:")
    logger.info(f"  • App ID: {app_id}")
    logger.info(f"  • Sandbox ID: {sandbox_id}")
    logger.info(f"  • 端口: {result['port']}")
    
    logger.info(f"\n🔗 预览 URL（在浏览器中打开）:")
    logger.info(f"\n  {preview_url}")
    logger.info(f"\n")
    
    logger.info("="*70)
    logger.info("💡 使用说明")
    logger.info("="*70)
    logger.info("1. 复制上面的 URL 到浏览器")
    logger.info("2. 应用会在几秒内加载完成")
    logger.info("3. 您可以：")
    logger.info("   - 调整侧边栏的参数")
    logger.info("   - 切换图表类型")
    logger.info("   - 查看数据详情")
    logger.info("")
    logger.info("⏱️  应用将保持运行直到您按 Ctrl+C")
    logger.info("="*70)
    
    try:
        # 保持运行
        logger.info("\n✅ 应用运行中... 按 Ctrl+C 终止")
        logger.info(f"💡 提示: 沙箱将在 {result.get('expires_in', '未知')} 后自动过期\n")
        
        # 每30秒显示一次状态和健康检查
        check_count = 0
        while True:
            await asyncio.sleep(30)
            check_count += 1
            
            # 每 3 次检查（90秒）做一次健康检查
            if check_count % 3 == 0:
                health = await vibe.check_sandbox_health(app_id)
                if health.get("alive"):
                    remaining_min = health.get("remaining_seconds", 0) // 60
                    logger.info(f"⏰ 应用运行中... URL: {preview_url}")
                    logger.info(f"   💓 沙箱健康 | 剩余时间: {remaining_min} 分钟")
                else:
                    logger.error(f"❌ 沙箱已失效: {health.get('error', '未知原因')}")
                    logger.error(f"   请重新运行脚本创建新的沙箱")
                    break
            else:
                logger.info(f"⏰ 应用运行中... URL: {preview_url}")
    
    except KeyboardInterrupt:
        logger.info("\n\n收到终止信号...")
    
    finally:
        # 清理
        logger.info("\n🧹 正在终止应用...")
        await vibe.terminate_app(app_id)
        logger.info("✅ 应用已终止")
        logger.info("\n再见！👋")


if __name__ == "__main__":
    try:
        asyncio.run(create_and_run_streamlit_app())
    except KeyboardInterrupt:
        logger.info("\n\n程序已退出")
        sys.exit(0)


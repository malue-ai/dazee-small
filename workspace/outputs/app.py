import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

# 页面配置
st.set_page_config(
    page_title="销售数据可视化分析",
    page_icon="📊",
    layout="wide"
)

# 标题和描述
st.title("📊 销售数据可视化分析系统")
st.markdown("---")

# 侧边栏 - 数据参数配置
st.sidebar.header("🎛️ 数据参数设置")

# 数据生成参数
data_points = st.sidebar.slider("数据点数量", 50, 500, 200, 10)
start_date = st.sidebar.date_input("开始日期", datetime.now() - timedelta(days=365))
seed = st.sidebar.number_input("随机种子（可选）", 0, 9999, 42)

# 产品类别
categories = st.sidebar.multiselect(
    "选择产品类别",
    ["电子产品", "服装", "食品", "家居", "图书"],
    default=["电子产品", "服装", "食品"]
)

# 生成数据按钮
if st.sidebar.button("🔄 生成新数据", type="primary"):
    st.session_state.refresh = True

# 数据生成函数
@st.cache_data
def generate_sales_data(n_points, start_dt, categories_list, random_seed):
    np.random.seed(random_seed)

    dates = pd.date_range(start=start_dt, periods=n_points, freq='D')

    data = {
        '日期': dates,
        '销售额': np.random.normal(50000, 15000, n_points).clip(10000, 120000),
        '订单数': np.random.poisson(100, n_points),
        '产品类别': np.random.choice(categories_list, n_points),
        '地区': np.random.choice(['华东', '华南', '华北', '西南', '华中'], n_points),
        '客户满意度': np.random.uniform(3.5, 5.0, n_points)
    }

    df = pd.DataFrame(data)
    df['平均订单价值'] = df['销售额'] / df['订单数']

    # 添加季节性趋势
    df['销售额'] = df['销售额'] * (1 + 0.3 * np.sin(np.arange(n_points) * 2 * np.pi / 365))

    return df

# 生成数据
if categories:
    df = generate_sales_data(data_points, start_date, categories, seed)

    # 主要内容区域
    col1, col2, col3, col4 = st.columns(4)

    # 统计指标卡片
    with col1:
        st.metric("总销售额", f"¥{df['销售额'].sum()/10000:.2f}万", 
                 delta=f"{df['销售额'].pct_change().mean()*100:.2f}%")

    with col2:
        st.metric("平均订单数", f"{df['订单数'].mean():.0f}", 
                 delta=f"{df['订单数'].std():.0f} 标准差")

    with col3:
        st.metric("平均客户满意度", f"{df['客户满意度'].mean():.2f}⭐", 
                 delta=f"{df['客户满意度'].max() - df['客户满意度'].min():.2f} 波动")

    with col4:
        st.metric("平均订单价值", f"¥{df['平均订单价值'].mean():.0f}", 
                 delta=f"¥{df['平均订单价值'].std():.0f} 标准差")

    st.markdown("---")

    # 图表类型选择
    chart_type = st.selectbox(
        "📈 选择图表类型",
        ["时间序列折线图", "类别对比柱状图", "地区分布饼图", "散点相关性分析", "箱线图分布", "热力地图"]
    )

    # 交互参数
    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.subheader(f"📊 {chart_type}")

        # 根据图表类型渲染不同的可视化
        if chart_type == "时间序列折线图":
            metric = st.radio("选择指标", ["销售额", "订单数", "客户满意度"], horizontal=True)

            fig = px.line(df, x='日期', y=metric, 
                         title=f'{metric}随时间变化趋势',
                         labels={metric: f'{metric}'},
                         color='产品类别' if len(categories) > 1 else None)
            fig.update_traces(mode='lines+markers')
            fig.update_layout(height=500, hovermode='x unified')
            st.plotly_chart(fig, use_container_width=True)

        elif chart_type == "类别对比柱状图":
            agg_method = st.radio("聚合方式", ["总和", "平均值", "中位数"], horizontal=True)

            agg_func = {'总和': 'sum', '平均值': 'mean', '中位数': 'median'}[agg_method]
            grouped = df.groupby('产品类别')['销售额'].agg(agg_func).reset_index()

            fig = px.bar(grouped, x='产品类别', y='销售额',
                        title=f'各产品类别销售额{agg_method}对比',
                        text_auto='.2s',
                        color='销售额',
                        color_continuous_scale='Blues')
            fig.update_layout(height=500)
            st.plotly_chart(fig, use_container_width=True)

        elif chart_type == "地区分布饼图":
            metric_pie = st.radio("选择指标", ["销售额", "订单数"], horizontal=True)

            grouped = df.groupby('地区')[metric_pie].sum().reset_index()

            fig = px.pie(grouped, values=metric_pie, names='地区',
                        title=f'{metric_pie}地区分布',
                        hole=0.4,
                        color_discrete_sequence=px.colors.qualitative.Set3)
            fig.update_traces(textposition='inside', textinfo='percent+label')
            fig.update_layout(height=500)
            st.plotly_chart(fig, use_container_width=True)

        elif chart_type == "散点相关性分析":
            x_axis = st.selectbox("X轴", ["订单数", "销售额", "客户满意度"])
            y_axis = st.selectbox("Y轴", ["平均订单价值", "销售额", "客户满意度"])

            fig = px.scatter(df, x=x_axis, y=y_axis, 
                           color='产品类别',
                           size='销售额',
                           hover_data=['日期', '地区'],
                           title=f'{x_axis} vs {y_axis} 相关性分析',
                           trendline="ols")
            fig.update_layout(height=500)
            st.plotly_chart(fig, use_container_width=True)

            # 计算相关系数
            corr = df[x_axis].corr(df[y_axis])
            st.info(f"相关系数: {corr:.3f}")

        elif chart_type == "箱线图分布":
            metric_box = st.radio("选择指标", ["销售额", "订单数", "客户满意度", "平均订单价值"], horizontal=True)
            group_by = st.radio("分组依据", ["产品类别", "地区"], horizontal=True)

            fig = px.box(df, x=group_by, y=metric_box,
                        color=group_by,
                        title=f'{metric_box}按{group_by}的分布情况',
                        points="outliers")
            fig.update_layout(height=500)
            st.plotly_chart(fig, use_container_width=True)

        elif chart_type == "热力地图":
            # 创建透视表
            pivot_data = df.pivot_table(
                values='销售额',
                index='产品类别',
                columns='地区',
                aggfunc='mean'
            )

            fig = px.imshow(pivot_data,
                           labels=dict(x="地区", y="产品类别", color="平均销售额"),
                           title="产品类别-地区销售额热力图",
                           aspect="auto",
                           color_continuous_scale='RdYlGn')
            fig.update_layout(height=500)
            st.plotly_chart(fig, use_container_width=True)

    with col_right:
        st.subheader("📊 详细统计")

        # 数据筛选
        selected_category = st.multiselect(
            "筛选产品类别",
            options=df['产品类别'].unique(),
            default=df['产品类别'].unique()
        )

        selected_region = st.multiselect(
            "筛选地区",
            options=df['地区'].unique(),
            default=df['地区'].unique()
        )

        # 筛选数据
        filtered_df = df[
            (df['产品类别'].isin(selected_category)) &
            (df['地区'].isin(selected_region))
        ]

        st.markdown(f"**筛选后数据量:** {len(filtered_df)} 条")

        # 统计摘要
        st.markdown("#### 销售额统计")
        stats_df = pd.DataFrame({
            '指标': ['总和', '平均值', '中位数', '最大值', '最小值', '标准差'],
            '数值': [
                f"¥{filtered_df['销售额'].sum()/10000:.2f}万",
                f"¥{filtered_df['销售额'].mean():.2f}",
                f"¥{filtered_df['销售额'].median():.2f}",
                f"¥{filtered_df['销售额'].max():.2f}",
                f"¥{filtered_df['销售额'].min():.2f}",
                f"¥{filtered_df['销售额'].std():.2f}"
            ]
        })
        st.dataframe(stats_df, hide_index=True, use_container_width=True)

        st.markdown("#### 订单数统计")
        order_stats = pd.DataFrame({
            '指标': ['总订单', '日均订单', '最高日订单'],
            '数值': [
                f"{filtered_df['订单数'].sum():.0f}",
                f"{filtered_df['订单数'].mean():.0f}",
                f"{filtered_df['订单数'].max():.0f}"
            ]
        })
        st.dataframe(order_stats, hide_index=True, use_container_width=True)

        # 分类占比
        st.markdown("#### 类别销售占比")
        category_pct = filtered_df.groupby('产品类别')['销售额'].sum().sort_values(ascending=False)
        category_pct_df = pd.DataFrame({
            '类别': category_pct.index,
            '占比': [f"{v/category_pct.sum()*100:.1f}%" for v in category_pct.values]
        })
        st.dataframe(category_pct_df, hide_index=True, use_container_width=True)

    # 数据表格展示
    st.markdown("---")
    st.subheader("📋 原始数据预览")

    col1, col2 = st.columns([3, 1])
    with col1:
        show_rows = st.slider("显示行数", 5, 50, 10)
    with col2:
        sort_by = st.selectbox("排序依据", df.columns)

    st.dataframe(
        filtered_df.sort_values(sort_by, ascending=False).head(show_rows),
        use_container_width=True,
        hide_index=True
    )

    # 下载数据
    csv = filtered_df.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        label="📥 下载筛选后的数据 (CSV)",
        data=csv,
        file_name=f'sales_data_{datetime.now().strftime("%Y%m%d")}.csv',
        mime='text/csv',
    )

else:
    st.warning("⚠️ 请在左侧至少选择一个产品类别！")

# 页脚
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #666;'>
        <p>💡 提示：调整左侧参数可以生成不同的数据 | 使用图表选择器切换可视化类型</p>
    </div>
    """,
    unsafe_allow_html=True
)

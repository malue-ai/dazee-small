"""
招聘管理系统
功能：登录、招聘计划管理、候选人管理、数据分析
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date, timedelta
import json
from pathlib import Path
import hashlib

# 页面配置
st.set_page_config(
    page_title="招聘管理系统",
    page_icon="👔",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 数据存储路径
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

PLANS_FILE = DATA_DIR / "recruitment_plans.json"
CANDIDATES_FILE = DATA_DIR / "candidates.json"
INTERVIEWS_FILE = DATA_DIR / "interviews.json"

# 招聘流程阶段
RECRUITMENT_STAGES = [
    "简历筛选",
    "在线沟通", 
    "业务负责人筛选",
    "邀请面试",
    "一面",
    "二面",
    "三面",
    "沟通offer",
    "发offer",
    "入职"
]

# 流失原因选项
DROPOUT_REASONS = [
    "简历不匹配",
    "薪资期望不符",
    "候选人拒绝",
    "面试表现不佳",
    "背景调查问题",
    "候选人接受其他offer",
    "其他"
]

# ==================== 数据管理函数 ====================

def load_json_data(file_path, default=[]):
    """加载JSON数据"""
    if file_path.exists():
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default

def save_json_data(file_path, data):
    """保存JSON数据"""
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_recruitment_plans():
    """获取招聘计划"""
    return load_json_data(PLANS_FILE, [])

def save_recruitment_plans(plans):
    """保存招聘计划"""
    save_json_data(PLANS_FILE, plans)

def get_candidates():
    """获取候选人列表"""
    return load_json_data(CANDIDATES_FILE, [])

def save_candidates(candidates):
    """保存候选人列表"""
    save_json_data(CANDIDATES_FILE, candidates)

def get_interviews():
    """获取面试记录"""
    return load_json_data(INTERVIEWS_FILE, [])

def save_interviews(interviews):
    """保存面试记录"""
    save_json_data(INTERVIEWS_FILE, interviews)

# ==================== 登录系统 ====================

def check_login():
    """检查登录状态"""
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    return st.session_state.logged_in

def login_page():
    """登录页面"""
    st.title("🔐 招聘管理系统")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("### 登录")
        st.info("💡 提示：用户名 zenflux，密码 hrhr123456")
        
        with st.form("login_form"):
            username = st.text_input("用户名", placeholder="zenflux")
            password = st.text_input("密码", type="password", placeholder="hrhr123456")
            submit = st.form_submit_button("登录", use_container_width=True)
            
            if submit:
                if username == "zenflux" and password == "hrhr123456":
                    st.session_state.logged_in = True
                    st.success("✅ 登录成功！正在跳转...")
                    st.experimental_rerun()
                else:
                    st.error("❌ 用户名或密码错误，请重试")

def logout():
    """登出"""
    st.session_state.logged_in = False
    st.experimental_rerun()

# ==================== 主页Dashboard ====================

def show_dashboard():
    """显示主页Dashboard"""
    st.title("📊 招聘管理系统 - 主页")
    
    # 获取数据
    plans = get_recruitment_plans()
    candidates = get_candidates()
    
    # 当前月份
    current_month = datetime.now().strftime("%Y-%m")
    
    # 月份选择器
    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader(f"📅 {current_month} 月度目标完成情况")
    with col2:
        if st.button("🔄 刷新数据"):
            st.experimental_rerun()
    
    # 筛选当月计划
    current_plans = [p for p in plans if p.get('month') == current_month]
    
    if not current_plans:
        st.info("本月暂无招聘计划，请先在「招聘计划管理」中创建计划。")
        return
    
    # 计算完成情况
    metrics_data = []
    for plan in current_plans:
        position = plan['position']
        target = plan['target_count']
        priority = plan['priority']
        owner = plan['business_owner']
        
        # 统计该岗位的入职人数
        onboarded = len([c for c in candidates 
                        if c.get('position') == position 
                        and c.get('current_stage') == '入职'
                        and c.get('month') == current_month])
        
        completion_rate = (onboarded / target * 100) if target > 0 else 0
        
        metrics_data.append({
            'position': position,
            'priority': priority,
            'target': target,
            'onboarded': onboarded,
            'completion_rate': completion_rate,
            'owner': owner
        })
    
    # 显示概览卡片
    col1, col2, col3, col4 = st.columns(4)
    
    total_target = sum([m['target'] for m in metrics_data])
    total_onboarded = sum([m['onboarded'] for m in metrics_data])
    total_completion = (total_onboarded / total_target * 100) if total_target > 0 else 0
    p0_positions = len([m for m in metrics_data if m['priority'] == 'P0'])
    
    with col1:
        st.metric("总目标人数", f"{total_target} 人")
    with col2:
        st.metric("已入职人数", f"{total_onboarded} 人")
    with col3:
        st.metric("整体完成率", f"{total_completion:.1f}%")
    with col4:
        st.metric("P0岗位数", f"{p0_positions} 个")
    
    st.divider()
    
    # 详细表格
    st.subheader("各岗位完成情况")
    
    if metrics_data:
        df = pd.DataFrame(metrics_data)
        df = df.rename(columns={
            'position': '岗位',
            'priority': '优先级',
            'target': '目标人数',
            'onboarded': '已入职',
            'completion_rate': '完成率(%)',
            'owner': '业务负责人'
        })
        
        # 添加颜色标记
        def highlight_priority(row):
            if row['优先级'] == 'P0':
                return ['background-color: #ffe6e6'] * len(row)
            elif row['优先级'] == 'P1':
                return ['background-color: #fff4e6'] * len(row)
            else:
                return [''] * len(row)
        
        styled_df = df.style.apply(highlight_priority, axis=1).format({
            '完成率(%)': '{:.1f}%'
        })
        
        st.dataframe(styled_df, use_container_width=True, hide_index=True)
        
        # 可视化图表
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("完成率对比")
            fig = px.bar(df, x='岗位', y='完成率(%)', 
                        color='优先级',
                        color_discrete_map={'P0': '#ff4444', 'P1': '#ff9944', 'P2': '#44aaff'},
                        text='完成率(%)')
            fig.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
            fig.update_layout(yaxis_range=[0, max(110, df['完成率(%)'].max() + 10)])
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.subheader("目标 vs 实际")
            df_melted = df.melt(id_vars=['岗位'], value_vars=['目标人数', '已入职'], 
                               var_name='类型', value_name='人数')
            fig = px.bar(df_melted, x='岗位', y='人数', color='类型',
                        barmode='group',
                        color_discrete_map={'目标人数': '#aaaaaa', '已入职': '#44ff44'})
            st.plotly_chart(fig, use_container_width=True)

# ==================== 招聘计划管理 ====================

def show_recruitment_plans():
    """招聘计划管理页面"""
    st.title("📋 招聘计划管理")
    
    tab1, tab2 = st.tabs(["查看计划", "创建/编辑计划"])
    
    with tab1:
        plans = get_recruitment_plans()
        
        if not plans:
            st.info("暂无招聘计划，请在「创建/编辑计划」标签页中添加。")
        else:
            # 按月份分组显示
            months = sorted(set([p['month'] for p in plans]), reverse=True)
            
            for month in months:
                with st.expander(f"📅 {month} 月招聘计划", expanded=(month == datetime.now().strftime("%Y-%m"))):
                    month_plans = [p for p in plans if p['month'] == month]
                    
                    df = pd.DataFrame(month_plans)
                    df = df[['position', 'priority', 'target_count', 'business_owner', 'created_at']]
                    df = df.rename(columns={
                        'position': '岗位',
                        'priority': '优先级',
                        'target_count': '目标人数',
                        'business_owner': '业务负责人',
                        'created_at': '创建时间'
                    })
                    
                    st.dataframe(df, use_container_width=True, hide_index=True)
                    
                    # 删除功能
                    st.write("删除计划：")
                    cols = st.columns(len(month_plans) + 1)
                    for idx, plan in enumerate(month_plans):
                        with cols[idx]:
                            if st.button(f"删除 {plan['position']}", key=f"del_{month}_{idx}"):
                                plans.remove(plan)
                                save_recruitment_plans(plans)
                                st.success(f"已删除 {plan['position']} 的计划")
                                st.experimental_rerun()
    
    with tab2:
        st.subheader("创建新的招聘计划")
        
        with st.form("new_plan_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                month = st.text_input("招聘月份", value=datetime.now().strftime("%Y-%m"),
                                     help="格式：YYYY-MM")
                position = st.text_input("岗位名称", placeholder="例如：高级Java工程师")
                priority = st.selectbox("优先级", options=["P0", "P1", "P2"])
            
            with col2:
                target_count = st.number_input("目标入职人数", min_value=1, value=1, step=1)
                business_owner = st.text_input("业务负责人", placeholder="例如：张三")
                notes = st.text_area("备注", placeholder="可选")
            
            submit = st.form_submit_button("创建计划", use_container_width=True)
            
            if submit:
                if not position or not business_owner:
                    st.error("岗位名称和业务负责人不能为空")
                else:
                    plans = get_recruitment_plans()
                    
                    new_plan = {
                        'id': f"{month}_{position}_{datetime.now().timestamp()}",
                        'month': month,
                        'position': position,
                        'priority': priority,
                        'target_count': target_count,
                        'business_owner': business_owner,
                        'notes': notes,
                        'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    
                    plans.append(new_plan)
                    save_recruitment_plans(plans)
                    
                    st.success(f"✅ 已创建 {position} 的招聘计划！")
                    st.experimental_rerun()

# ==================== 候选人管理 ====================

def show_candidate_management():
    """候选人管理页面"""
    st.title("👥 候选人管理")
    
    tab1, tab2, tab3 = st.tabs(["候选人列表", "添加候选人", "面试记录"])
    
    with tab1:
        candidates = get_candidates()
        
        if not candidates:
            st.info("暂无候选人，请在「添加候选人」标签页中添加。")
        else:
            # 筛选器
            col1, col2, col3 = st.columns(3)
            
            with col1:
                filter_stage = st.selectbox("筛选阶段", options=["全部"] + RECRUITMENT_STAGES)
            with col2:
                positions = list(set([c['position'] for c in candidates]))
                filter_position = st.selectbox("筛选岗位", options=["全部"] + positions)
            with col3:
                filter_month = st.selectbox("筛选月份", options=["全部"] + sorted(list(set([c.get('month', '') for c in candidates])), reverse=True))
            
            # 应用筛选
            filtered = candidates.copy()
            if filter_stage != "全部":
                filtered = [c for c in filtered if c.get('current_stage') == filter_stage]
            if filter_position != "全部":
                filtered = [c for c in filtered if c.get('position') == filter_position]
            if filter_month != "全部":
                filtered = [c for c in filtered if c.get('month') == filter_month]
            
            st.write(f"共 {len(filtered)} 条记录")
            
            # 显示候选人列表
            for idx, candidate in enumerate(filtered):
                with st.expander(f"👤 {candidate['name']} - {candidate['position']} ({candidate['current_stage']})"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write(f"**姓名：** {candidate['name']}")
                        st.write(f"**岗位：** {candidate['position']}")
                        st.write(f"**来源：** {candidate['source']}")
                        st.write(f"**当前阶段：** {candidate['current_stage']}")
                        st.write(f"**月份：** {candidate.get('month', 'N/A')}")
                    
                    with col2:
                        st.write(f"**联系方式：** {candidate.get('contact', 'N/A')}")
                        st.write(f"**创建时间：** {candidate.get('created_at', 'N/A')}")
                        st.write(f"**更新时间：** {candidate.get('updated_at', 'N/A')}")
                        
                        if candidate.get('dropout_reason'):
                            st.error(f"**流失原因：** {candidate['dropout_reason']}")
                    
                    st.divider()
                    
                    # 更新候选人状态
                    st.write("**更新候选人信息**")
                    
                    col_a, col_b, col_c = st.columns(3)
                    
                    with col_a:
                        new_stage = st.selectbox("更新阶段", options=RECRUITMENT_STAGES, 
                                                index=RECRUITMENT_STAGES.index(candidate['current_stage']),
                                                key=f"stage_{idx}")
                    
                    with col_b:
                        # 面试时间编辑 - 日期和时间
                        interview_date = st.date_input("面试日期", 
                                                      value=datetime.strptime(candidate.get('interview_date', datetime.now().strftime("%Y-%m-%d")), "%Y-%m-%d").date() if candidate.get('interview_date') else date.today(),
                                                      key=f"date_{idx}")
                        
                    with col_c:
                        interview_time = st.time_input("面试时间",
                                                      value=datetime.strptime(candidate.get('interview_time', '09:00'), "%H:%M").time() if candidate.get('interview_time') else datetime.now().time(),
                                                      key=f"time_{idx}")
                    
                    # 流失原因
                    if new_stage in ["简历筛选", "在线沟通", "业务负责人筛选"] or "面试" in new_stage:
                        dropout = st.selectbox("流失原因（如适用）", options=["无（继续流程）"] + DROPOUT_REASONS,
                                             key=f"dropout_{idx}")
                    else:
                        dropout = "无（继续流程）"
                    
                    col_update, col_delete = st.columns([3, 1])
                    
                    with col_update:
                        if st.button("💾 更新信息", key=f"update_{idx}", use_container_width=True):
                            candidate['current_stage'] = new_stage
                            candidate['interview_date'] = interview_date.strftime("%Y-%m-%d")
                            candidate['interview_time'] = interview_time.strftime("%H:%M")
                            candidate['updated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            
                            if dropout != "无（继续流程）":
                                candidate['dropout_reason'] = dropout
                                candidate['is_active'] = False
                            
                            save_candidates(candidates)
                            st.success("✅ 更新成功！")
                            st.experimental_rerun()
                    
                    with col_delete:
                        if st.button("🗑️ 删除", key=f"delete_{idx}", use_container_width=True):
                            candidates.remove(candidate)
                            save_candidates(candidates)
                            st.success("已删除候选人")
                            st.experimental_rerun()
    
    with tab2:
        st.subheader("添加新候选人")
        
        # 获取可用岗位
        plans = get_recruitment_plans()
        available_positions = list(set([p['position'] for p in plans]))
        
        if not available_positions:
            st.warning("请先在「招聘计划管理」中创建招聘计划")
        else:
            with st.form("new_candidate_form"):
                col1, col2 = st.columns(2)
                
                with col1:
                    name = st.text_input("姓名*", placeholder="候选人姓名")
                    position = st.selectbox("应聘岗位*", options=available_positions)
                    source = st.selectbox("来源*", options=["主动沟通", "候选人池"])
                    contact = st.text_input("联系方式", placeholder="电话或邮箱")
                
                with col2:
                    month = st.text_input("所属月份", value=datetime.now().strftime("%Y-%m"))
                    current_stage = st.selectbox("当前阶段", options=RECRUITMENT_STAGES, index=0)
                    interview_date = st.date_input("面试日期", value=date.today())
                    interview_time = st.time_input("面试时间", value=datetime.now().time())
                
                notes = st.text_area("备注", placeholder="可选")
                
                submit = st.form_submit_button("添加候选人", use_container_width=True)
                
                if submit:
                    if not name:
                        st.error("姓名不能为空")
                    else:
                        candidates = get_candidates()
                        
                        new_candidate = {
                            'id': f"{name}_{position}_{datetime.now().timestamp()}",
                            'name': name,
                            'position': position,
                            'source': source,
                            'contact': contact,
                            'month': month,
                            'current_stage': current_stage,
                            'interview_date': interview_date.strftime("%Y-%m-%d"),
                            'interview_time': interview_time.strftime("%H:%M"),
                            'notes': notes,
                            'is_active': True,
                            'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            'updated_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        
                        candidates.append(new_candidate)
                        save_candidates(candidates)
                        
                        st.success(f"✅ 已添加候选人：{name}")
                        st.experimental_rerun()
    
    with tab3:
        st.subheader("面试记录管理")
        
        candidates = get_candidates()
        interviews = get_interviews()
        
        # 候选人选择
        candidate_names = [f"{c['name']} - {c['position']}" for c in candidates]
        
        if not candidate_names:
            st.info("暂无候选人")
        else:
            selected = st.selectbox("选择候选人", options=candidate_names)
            
            if selected:
                candidate_name = selected.split(" - ")[0]
                candidate = [c for c in candidates if c['name'] == candidate_name][0]
                
                st.write(f"**候选人：** {candidate['name']}")
                st.write(f"**岗位：** {candidate['position']}")
                st.write(f"**当前阶段：** {candidate['current_stage']}")
                
                st.divider()
                
                # 显示该候选人的面试记录
                candidate_interviews = [i for i in interviews if i['candidate_id'] == candidate['id']]
                
                if candidate_interviews:
                    st.write("**历史面试记录：**")
                    for interview in candidate_interviews:
                        with st.expander(f"{interview['round']} - {interview['interview_date']} {interview.get('interview_time', '')}"):
                            st.write(f"**面试官：** {interview['interviewer']}")
                            st.write(f"**面试结果：** {interview['result']}")
                            st.write(f"**评价：** {interview['feedback']}")
                
                st.divider()
                
                # 添加新面试记录
                st.write("**添加新面试记录**")
                
                with st.form("new_interview_form"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        interview_round = st.selectbox("面试轮次", options=["一面", "二面", "三面"])
                        interviewer = st.text_input("面试官", placeholder="面试官姓名")
                        result = st.selectbox("面试结果", options=["通过", "未通过", "待定"])
                    
                    with col2:
                        interview_date = st.date_input("面试日期", value=date.today())
                        interview_time = st.time_input("面试时间", value=datetime.now().time())
                    
                    feedback = st.text_area("面试评价", placeholder="请输入面试评价和建议")
                    
                    submit_interview = st.form_submit_button("保存面试记录", use_container_width=True)
                    
                    if submit_interview:
                        if not interviewer:
                            st.error("面试官不能为空")
                        else:
                            new_interview = {
                                'id': f"{candidate['id']}_{interview_round}_{datetime.now().timestamp()}",
                                'candidate_id': candidate['id'],
                                'candidate_name': candidate['name'],
                                'position': candidate['position'],
                                'round': interview_round,
                                'interviewer': interviewer,
                                'interview_date': interview_date.strftime("%Y-%m-%d"),
                                'interview_time': interview_time.strftime("%H:%M"),
                                'result': result,
                                'feedback': feedback,
                                'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            }
                            
                            interviews.append(new_interview)
                            save_interviews(interviews)
                            
                            st.success("✅ 面试记录已保存！")
                            st.experimental_rerun()

# ==================== 数据分析 ====================

def show_analytics():
    """数据分析页面"""
    st.title("📈 数据分析")
    
    candidates = get_candidates()
    
    if not candidates:
        st.info("暂无候选人数据，无法生成分析报告")
        return
    
    tab1, tab2, tab3 = st.tabs(["招聘漏斗", "流失原因分析", "整体统计"])
    
    with tab1:
        st.subheader("🔽 招聘漏斗分析")
        
        # 统计各阶段人数
        stage_counts = {}
        for stage in RECRUITMENT_STAGES:
            count = len([c for c in candidates if c['current_stage'] == stage])
            stage_counts[stage] = count
        
        # 创建漏斗图
        fig = go.Figure(go.Funnel(
            y=list(stage_counts.keys()),
            x=list(stage_counts.values()),
            textinfo="value+percent initial",
            marker=dict(color=["#FF6B6B", "#FFA500", "#FFD700", "#90EE90", 
                              "#87CEEB", "#9370DB", "#FF69B4", "#20B2AA", 
                              "#32CD32", "#00CED1"])
        ))
        
        fig.update_layout(
            title="招聘流程各阶段候选人数量",
            height=600
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # 详细数据表
        st.write("**各阶段详情：**")
        df = pd.DataFrame(list(stage_counts.items()), columns=['阶段', '人数'])
        df['占初始比例'] = (df['人数'] / df['人数'].iloc[0] * 100).round(1).astype(str) + '%'
        st.dataframe(df, use_container_width=True, hide_index=True)
    
    with tab2:
        st.subheader("❌ 流失原因分析")
        
        # 统计流失原因
        dropout_candidates = [c for c in candidates if c.get('dropout_reason') and c.get('dropout_reason') != "无（继续流程）"]
        
        if not dropout_candidates:
            st.info("暂无流失数据")
        else:
            dropout_stats = {}
            for reason in DROPOUT_REASONS:
                count = len([c for c in dropout_candidates if c.get('dropout_reason') == reason])
                if count > 0:
                    dropout_stats[reason] = count
            
            # 饼图
            fig = px.pie(
                names=list(dropout_stats.keys()),
                values=list(dropout_stats.values()),
                title=f"流失原因占比（总流失：{len(dropout_candidates)} 人）"
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # 详细列表
            st.write("**流失候选人列表：**")
            dropout_df = pd.DataFrame([{
                '姓名': c['name'],
                '岗位': c['position'],
                '流失阶段': c['current_stage'],
                '流失原因': c['dropout_reason'],
                '时间': c.get('updated_at', 'N/A')
            } for c in dropout_candidates])
            
            st.dataframe(dropout_df, use_container_width=True, hide_index=True)
    
    with tab3:
        st.subheader("📊 整体统计")
        
        col1, col2, col3, col4 = st.columns(4)
        
        total_candidates = len(candidates)
        active_candidates = len([c for c in candidates if c.get('is_active', True)])
        onboarded = len([c for c in candidates if c['current_stage'] == '入职'])
        dropout = len([c for c in candidates if not c.get('is_active', True)])
        
        with col1:
            st.metric("总候选人数", total_candidates)
        with col2:
            st.metric("进行中", active_candidates)
        with col3:
            st.metric("已入职", onboarded)
        with col4:
            st.metric("已流失", dropout)
        
        st.divider()
        
        # 按岗位统计
        st.write("**各岗位统计：**")
        positions = list(set([c['position'] for c in candidates]))
        position_stats = []
        
        for pos in positions:
            pos_candidates = [c for c in candidates if c['position'] == pos]
            pos_onboarded = len([c for c in pos_candidates if c['current_stage'] == '入职'])
            pos_dropout = len([c for c in pos_candidates if not c.get('is_active', True)])
            
            position_stats.append({
                '岗位': pos,
                '候选人总数': len(pos_candidates),
                '已入职': pos_onboarded,
                '已流失': pos_dropout,
                '进行中': len(pos_candidates) - pos_onboarded - pos_dropout
            })
        
        df_pos = pd.DataFrame(position_stats)
        st.dataframe(df_pos, use_container_width=True, hide_index=True)
        
        # 按月份统计
        st.write("**按月份统计：**")
        months = sorted(list(set([c.get('month', 'N/A') for c in candidates])), reverse=True)
        
        month_stats = []
        for month in months:
            if month != 'N/A':
                month_candidates = [c for c in candidates if c.get('month') == month]
                month_onboarded = len([c for c in month_candidates if c['current_stage'] == '入职'])
                
                month_stats.append({
                    '月份': month,
                    '候选人数': len(month_candidates),
                    '已入职': month_onboarded
                })
        
        df_month = pd.DataFrame(month_stats)
        
        if not df_month.empty:
            fig = px.bar(df_month, x='月份', y=['候选人数', '已入职'], 
                        barmode='group',
                        title="月度候选人趋势")
            st.plotly_chart(fig, use_container_width=True)

# ==================== 主程序 ====================

def main():
    """主程序"""
    
    # 检查登录状态
    if not check_login():
        login_page()
        return
    
    # 侧边栏
    with st.sidebar:
        st.title("🎯 导航菜单")
        
        menu = st.radio(
            "选择功能",
            options=["主页", "招聘计划管理", "候选人管理", "数据分析"],
            index=0
        )
        
        st.divider()
        
        st.info(f"👤 当前用户：zenflux")
        
        if st.button("🚪 退出登录", use_container_width=True):
            logout()
    
    # 根据菜单显示对应页面
    if menu == "主页":
        show_dashboard()
    elif menu == "招聘计划管理":
        show_recruitment_plans()
    elif menu == "候选人管理":
        show_candidate_management()
    elif menu == "数据分析":
        show_analytics()

if __name__ == "__main__":
    main()

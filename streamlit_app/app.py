import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import datetime
import sys
import os
import isodate
import requests
from datetime import datetime

# Configure path for module imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database_operations.data_insertion import store_channel_data, get_recent_channels
from data_processing.channel_extractor import extract_channel_data
from data_processing.video_extractor import extract_video_data
from database_operations.Metrics_caluclator import (
    Caluclate_engagement_rate, 
    Calculate_avg_views, 
    Calculate_sub_to_view_ratio, 
    Calculate_content_score, 
    benchmark_videos,
    Identify_top_categories,
    Optimal_posting_time,
    Trend_analysis
)
from database_operations.db_connection import engine
from sqlalchemy import text

# --- PAGE CONFIG ---
st.set_page_config(page_title="YouTube Analytics Pro", page_icon="📊", layout="wide")

# --- HELPER FUNCTIONS ---
def fmt_k_m(num):
    if pd.isna(num):
        return "0"
    if num >= 1_000_000:
        return f"{num / 1_000_000:.1f}M"
    elif num >= 1_000:
        return f"{num / 1_000:.1f}K"
    return f"{int(num):,}"

def parse_duration(duration_str):
    try:
        if not duration_str: return 0
        return isodate.parse_duration(duration_str).total_seconds()
    except:
        return 0

def safe_image(url, width=None, use_container_width=False, use_column_width=False):
    """
    Safe image loader. Compatible with Streamlit 1.31.0 which uses use_column_width.
    Accepts both use_container_width and use_column_width for backward compatibility.
    """
    fallback = "https://via.placeholder.com/480x360.png?text=Image+Not+Available"
    # Merge both parameter names — if either is True, set use_column_width=True
    col_width = use_container_width or use_column_width
    # When col_width is set, don't pass explicit width (they conflict)
    img_kwargs = {}
    if col_width:
        img_kwargs['use_column_width'] = True
    elif width:
        img_kwargs['width'] = width
    try:
        if url and url.startswith("http"):
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                st.image(resp.content, **img_kwargs)
                return
        st.image(fallback, **img_kwargs)
    except:
        st.image(fallback, **img_kwargs)

def get_channel_data_from_db(channel_id):
    query = f"""
    SELECT 
        c.channel_id, c.channel_name, c.subscribers, c.views as total_views, 
        c.total_videos, c.thumbnail_url as c_thumb, c.description, c.published_at as c_published,
        v.video_id, v.title, v.published_at as published_at, 
        v.thumbnail_url as v_thumb, v.duration,
        s.view_count, s.like_count, s.comment_count
    FROM channels c
    JOIN videos v ON c.channel_id = v.channel_id
    JOIN video_statistics s ON v.video_id = s.video_id
    WHERE c.channel_id = '{channel_id}'
    AND s.captured_at = (SELECT MAX(captured_at) FROM video_statistics WHERE video_id = v.video_id)
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)
    return df

# --- PREMIUM UI CSS & FONTS ---
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">

<style>
    /* GLOBAL RESET & ULTRA-CLARITY */
    * { font-family: 'Inter', sans-serif; font-size: 1.05rem; }
    h1 { font-size: 3rem !important; }
    h2 { font-size: 2.2rem !important; }
    h3 { font-size: 1.8rem !important; }
    .main-title {
        font-family: 'Outfit', sans-serif !important;
        font-weight: 700 !important;
        color: #1E293B !important;
    }
    
    /* BACKGROUND */
    .stApp { background-color: #F8FAFC; }

    /* CARD STYLING */
    .metric-card {
        background-color: #FFFFFF;
        border-radius: 12px;
        padding: 30px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        border: 1px solid #E2E8F0;
        text-align: center;
        transition: transform 0.2s ease;
    }
    .metric-card:hover { transform: translateY(-2px); box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1); }
    .metric-value {
        font-size: 2.5rem; font-weight: 700; color: #FF0000;
        font-family: 'Outfit', sans-serif; margin-bottom: 8px;
    }
    .metric-label {
        font-size: 1rem; color: #64748B; font-weight: 600;
        text-transform: uppercase; letter-spacing: 0.1em;
    }

    /* SIDEBAR */
    section[data-testid="stSidebar"] {
        background-color: #FFFFFF;
        border-right: 1px solid #E2E8F0;
    }
    
    /* Premium Sidebar Buttons */
    .stSidebar [data-testid="stBaseButton-secondary"] {
        border-radius: 8px !important;
        border: 1px solid #E2E8F0 !important;
        background-color: #F8FAFC !important;
        color: #475569 !important;
        transition: all 0.3s ease !important;
        font-weight: 600 !important;
        text-align: left !important;
        padding: 0.5rem 1rem !important;
    }
    
    .stSidebar [data-testid="stBaseButton-secondary"]:hover {
        border-color: #FF0000 !important;
        color: #FF0000 !important;
        background-color: #FFF5F5 !important;
        transform: translateX(5px);
    }

    /* HIGHLIGHT BOX */
    .highlight-box {
        background-color: #E0F2FE;
        padding: 15px;
        border-radius: 8px;
        border-left: 5px solid #0369A1;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# --- NAVIGATION STATE ---
if 'page' not in st.session_state: st.session_state['page'] = 'dash'
if 'active_channel_id' not in st.session_state: st.session_state['active_channel_id'] = None

# --- SIDEBAR ---
with st.sidebar:
    st.markdown("<h2 style='margin-top:0;'>⚙️ Controls</h2>", unsafe_allow_html=True)
    channel_id_input = st.text_input("Channel ID", placeholder="UC_x5XG1OV2P6uZZ5FSM9Ttw")
    fetch_button = st.button("🚀 Run Analysis", type="primary", use_container_width=True)
    
    st.divider()
    
    st.markdown("### 🗺️ Navigation")
    # Using a slightly different layout to prevent text wrapping and look better
    nav_dash = st.button("📊 **Dash**", use_container_width=True)
    nav_prof = st.button("🏆 **Profile**", use_container_width=True)
    nav_batt = st.button("⚖️ **Battle**", use_container_width=True)
    nav_vis  = st.button("📈 **Visuals**", use_container_width=True)

    if nav_dash: st.session_state['page'] = 'dash'
    if nav_prof: st.session_state['page'] = 'profile'
    if nav_batt: st.session_state['page'] = 'battle'
    if nav_vis:  st.session_state['page'] = 'vis'
    
    st.divider()
    
    st.markdown("<h3 style='font-size: 1.1rem;'>🕒 Recently Viewed</h3>", unsafe_allow_html=True)
    recent_channels = get_recent_channels(limit=10)
    if recent_channels:
        for ch in recent_channels:
            if st.button(f"📺 {ch['name']}", key=f"sidebar_{ch['id']}", use_container_width=True):
                st.session_state['active_channel_id'] = ch['id']
                st.session_state['page'] = 'dash'
                st.rerun()
    else:
        st.caption("No history found.")

# --- MAIN PAGE HEADER ---
st.markdown(f"""
    <div style='text-align: center; padding: 10px 0 20px 0;'>
        <h1 class='main-title' style='font-size: 2.5rem; margin-bottom: 0;'>
            <span style='color: #FF0000;'>YouTube</span> Pro Dash
        </h1>
    </div>
""", unsafe_allow_html=True)

# --- HANDLE SYNC ---
if fetch_button and channel_id_input:
    with st.status("💎 Architecting Data Stream...", expanded=True) as status:
        st.write("📡 Accessing YouTube API...")
        res = store_channel_data(channel_id_input)
        if res['status'] == "Success":
            status.update(label="✨ Analysis Ready", state="complete")
            st.session_state['active_channel_id'] = channel_id_input
            st.session_state['page'] = 'dash'
            st.balloons()
            st.rerun()
        else:
            status.update(label="❌ Failed", state="error")
            st.error(res['message'])

# --- PAGE: DASHBOARD ---
if st.session_state['page'] == 'dash':
    if not st.session_state['active_channel_id']:
        st.info("👋 Enter a Channel ID or select a recent channel from the sidebar to begin.")
    else:
        chid = st.session_state['active_channel_id']
        df = get_channel_data_from_db(chid)
        if not df.empty:
            c_data = df.iloc[0]
            
            # Scorecards
            m1, m2, m3 = st.columns(3)
            with m1: st.markdown(f"<div class='metric-card'><div class='metric-value'>{int(c_data['subscribers'] or 0):,}</div><div class='metric-label'>Subscribers</div></div>", unsafe_allow_html=True)
            with m2: st.markdown(f"<div class='metric-card'><div class='metric-value'>{int(c_data['total_views']):,}</div><div class='metric-label'>Total Views</div></div>", unsafe_allow_html=True)
            with m3: st.markdown(f"<div class='metric-card'><div class='metric-value'>{int(c_data['total_videos']):,}</div><div class='metric-label'>Total Videos</div></div>", unsafe_allow_html=True)
            
            st.divider()
            
            # Identity
            p1, p2 = st.columns([1, 4])
            with p1: safe_image(c_data['c_thumb'], width=180)
            with p2:
                st.markdown(f"## {c_data['channel_name']} 🔗")
                st.caption(f"Joined: {pd.to_datetime(c_data['c_published']).strftime('%d %b, %Y')}")
                with st.expander("📝 Description"): st.write(c_data['description'])
            
            st.divider()
            
            # Tabs
            tab1, tab2, tab3 = st.tabs(["🏡 Overview & Strategy", "📈 Deep Dive Analytics", "💾 Raw Data"])
            
            # Pre-calculate video URLs for consistency
            df['video_url'] = "https://www.youtube.com/watch?v=" + df['video_id']
            
            with tab1:
                # Star Performer
                st.markdown("### 🌟 Star Performer")
                top_v = df.loc[df['view_count'].idxmax()]
                sp1, sp2 = st.columns([1, 2])
                with sp1: safe_image(top_v['v_thumb'], use_container_width=True)
                with sp2:
                    st.markdown(f"#### [{top_v['title']}]({top_v['video_url']})")
                    st.caption(f"Published: {top_v['published_at']}")
                    st.markdown(f"**{top_v['view_count']:,}** Views • **{top_v['like_count']:,}** Likes • **{top_v['comment_count']:,}** Comments")
                    st.info("This is your highest performing video. Click the title to watch it!")

            with tab2:
                # Content Reach
                st.markdown("### 📊 Content Performance Reach")
                c_col1, c_col2 = st.columns(2)
                with c_col1:
                    st.markdown("#### Most Viewed Videos")
                    top10_v = df.nlargest(10, 'view_count').sort_values('view_count', ascending=True)
                    fig_v = go.Figure()
                    fig_v.add_trace(go.Bar(
                        x=top10_v['view_count'],
                        y=top10_v['title'],
                        orientation='h',
                        marker=dict(
                            color=top10_v['view_count'].tolist(),
                            colorscale='Viridis',
                            showscale=True,
                            colorbar=dict(title="view_count", thickness=15, len=0.7)
                        ),
                        hovertemplate="<b>%{y}</b><br>Views: %{x:,}<extra></extra>"
                    ))
                    fig_v.update_layout(
                        height=400, template='plotly_white',
                        margin=dict(l=0, r=20, t=30, b=30),
                        yaxis=dict(visible=False, showticklabels=False),
                        xaxis=dict(gridcolor='#F1F5F9', title='view_count')
                    )
                    st.plotly_chart(fig_v, use_container_width=True)
                    with st.expander("🔗 View Links for Top 10 Viewed"):
                        st.dataframe(
                            top10_v.sort_values('view_count', ascending=False)[['title', 'video_url']], 
                            column_config={"video_url": st.column_config.LinkColumn("YouTube Link", display_text="Watch Video")}, 
                            hide_index=True,
                            use_container_width=True
                        )
                
                with c_col2:
                    st.markdown("#### Most Liked Videos")
                    top10_l = df.nlargest(10, 'like_count').sort_values('like_count', ascending=True)
                    fig_l = go.Figure()
                    fig_l.add_trace(go.Bar(
                        x=top10_l['like_count'],
                        y=top10_l['title'],
                        orientation='h',
                        marker=dict(
                            color=top10_l['like_count'].tolist(),
                            colorscale='Magma',
                            showscale=True,
                            colorbar=dict(title="like_count", thickness=15, len=0.7)
                        ),
                        hovertemplate="<b>%{y}</b><br>Likes: %{x:,}<extra></extra>"
                    ))
                    fig_l.update_layout(
                        height=400, template='plotly_white',
                        margin=dict(l=0, r=20, t=30, b=30),
                        yaxis=dict(visible=False, showticklabels=False),
                        xaxis=dict(gridcolor='#F1F5F9', title='like_count')
                    )
                    st.plotly_chart(fig_l, use_container_width=True)
                    with st.expander("🔗 View Links for Top 10 Liked"):
                        st.dataframe(
                            top10_l.sort_values('like_count', ascending=False)[['title', 'video_url']], 
                            column_config={"video_url": st.column_config.LinkColumn("YouTube Link", display_text="Watch Video")}, 
                            hide_index=True,
                            use_container_width=True
                        )

                st.divider()

                # Upload Schedule Analysis
                st.markdown("### 📅 Upload Schedule Analysis")
                # CRITICAL: Deduplicate by video_id to prevent duplicate rows from SQL JOIN
                df_sch = df.drop_duplicates(subset=['video_id']).copy()
                df_sch['published_at_dt'] = pd.to_datetime(df_sch['published_at'])
                df_sch['month'] = df_sch['published_at_dt'].dt.to_period('M').astype(str)
                df_sch['day_name'] = df_sch['published_at_dt'].dt.day_name()
                
                s1, s2 = st.columns(2)
                with s1:
                    st.markdown("#### Uploads by Month")
                    m_data = df_sch.groupby('month').size().reset_index(name='count')
                    m_data = m_data.sort_values('count', ascending=False)
                    
                    # Build Pie chart with EXPLICIT lists from the same m_data
                    month_labels = m_data['month'].tolist()
                    month_values = m_data['count'].tolist()
                    
                    fig_p = go.Figure(data=[go.Pie(
                        labels=month_labels,
                        values=month_values,
                        hole=0.5,
                        textinfo='percent',
                        textposition='inside',
                        textfont=dict(size=14, family='Outfit', color='white'),
                        pull=[0.03]*len(month_labels),
                        marker=dict(colors=px.colors.qualitative.Bold[:len(month_labels)])
                    )])
                    fig_p.update_layout(showlegend=True, height=350, template='plotly_white')
                    st.plotly_chart(fig_p, use_container_width=True)
                    
                    # Clarity Point — uses the SAME m_data (already sorted desc)
                    best_month = month_labels[0]  # first after sort_values descending
                    best_month_count = month_values[0]
                    st.markdown(f"""
                        <div class='highlight-box'>
                            🎯 <b>Monthly Highlight:</b> Most uploads (<b>{best_month_count}</b>) occurred in <b>{best_month}</b>. 
                            Consistency during peak periods often correlates with sustained viewership growth.
                        </div>
                    """, unsafe_allow_html=True)

                with s2:
                    st.markdown("#### Uploads by Day of Week")
                    d_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                    
                    # Count uploads per day from the SAME deduped df_sch
                    day_counts_series = df_sch['day_name'].value_counts()
                    day_values = [int(day_counts_series.get(d, 0)) for d in d_order]
                    
                    # Build Bar chart with EXPLICIT lists
                    fig_d = go.Figure(data=[go.Bar(
                        x=d_order,
                        y=day_values,
                        text=day_values,
                        textposition='outside',
                        textfont=dict(size=13, family='Outfit', color='#1E293B'),
                        marker=dict(
                            color=day_values,
                            colorscale='RdBu_r',
                            showscale=True,
                            colorbar=dict(title='Uploads', thickness=15, len=0.7)
                        ),
                        hovertemplate="<b>%{x}</b><br>Uploads: %{y}<extra></extra>"
                    )])
                    fig_d.update_layout(
                        showlegend=False, height=350, template='plotly_white',
                        margin=dict(l=20, r=20, t=40, b=40),
                        yaxis=dict(title='Uploads', gridcolor='#F1F5F9', zeroline=False),
                        xaxis=dict(title='Day of Week', categoryorder='array', categoryarray=d_order)
                    )
                    st.plotly_chart(fig_d, use_container_width=True)
                    
                    # Highlight — find the day with the MAX from the SAME day_values list
                    max_idx = day_values.index(max(day_values))
                    best_day = d_order[max_idx]
                    best_day_count = day_values[max_idx]
                    st.markdown(f"""
                        <div class='highlight-box'>
                            ✨ <b>Strategic Day:</b> <b>{best_day}</b> is your most frequent upload day (<b>{best_day_count}</b> uploads). 
                            If this day performs well, consider it your primary 'Anchor Day' for new content.
                        </div>
                    """, unsafe_allow_html=True)

            with tab3:
                st.markdown("### 📂 Video Data Catalog")
                raw_df = df.copy()
                raw_df['Mins'] = raw_df['duration'].apply(lambda x: round(parse_duration(x)/60, 1))
                st.dataframe(
                    raw_df[['title', 'published_at', 'view_count', 'like_count', 'comment_count', 'Mins', 'video_url']], 
                    column_config={"video_url": st.column_config.LinkColumn("Watch Video", display_text="Open Link")},
                    use_container_width=True, 
                    hide_index=True
                )

# --- PAGE: PROFILE (Cleaned up Intelligence Analytics) ---
elif st.session_state['page'] == 'profile':
    if not st.session_state['active_channel_id']:
        st.warning("Please select a channel from the sidebar.")
    else:
        chid = st.session_state['active_channel_id']
        df = get_channel_data_from_db(chid)
        if not df.empty:
            df = Caluclate_engagement_rate(df)
            df = Calculate_sub_to_view_ratio(df)
            df = Calculate_content_score(df)
            df = benchmark_videos(df)
            c = df.iloc[0]
            
            st.markdown(f"<h2 style='text-align:center;'>📈 {c['channel_name']} Performance Intelligence</h2>", unsafe_allow_html=True)
            
            # Gauge Section
            st.markdown("### 💎 Key Performance Indicators")
            k1, k2, k3, k4 = st.columns(4)
            
            def create_gauge(value, title, color="#FF0000", max_val=100, suffix="", format_str=""):
                # Hide the default number by removing 'number' from mode parameter
                fig = go.Figure(go.Indicator(
                    mode = "gauge", 
                    value = value,
                    title = {'text': title, 'font': {'size': 16, 'color': '#64748B'}},
                    gauge = {
                        'axis': {'range': [None, max_val], 'tickwidth': 1, 'tickcolor': "#CBD5E1"},
                        'bar': {'color': color},
                        'bgcolor': "#F1F5F9",  # Creates the pale track
                        'borderwidth': 0,
                    }
                ))
                
                # Format the text nicely
                if format_str:
                    val_text = format_str.format(value)
                elif suffix == "%":
                    val_text = f"{int(value)}{suffix}"
                else:
                    val_text = f"{value:.1f}{suffix}"

                # Place it perfectly in the center inside the gauge arc
                fig.add_annotation(
                    x=0.5, y=0.15,
                    text=f"<b>{val_text}</b>",
                    font=dict(size=30, color=color, family="Outfit"),
                    showarrow=False
                )
                
                # Increased top margin to t=70 so the title doesn't get cut off
                fig.update_layout(height=180, margin=dict(l=10, r=10, t=70, b=10))
                return fig
            
            # Determine a safe max scale for the subs/view ratio gauge so the meter actually fills
            sv_max = max(1.0, df['sub_to_view_ratio'].mean() * 1.5)

            with k1: st.plotly_chart(create_gauge(df['engagement_rate'].mean(), "Engage Rate", "#3B82F6", max_val=20, suffix="%"), use_container_width=True, config={'displayModeBar': True})
            with k2: st.plotly_chart(create_gauge(df['content_performance_score'].mean(), "Content Score", "#F59E0B", max_val=100, format_str="{:.1f}/100"), use_container_width=True, config={'displayModeBar': True})
            with k3: st.plotly_chart(create_gauge(df['sub_to_view_ratio'].mean(), "Subs / View", "#10B981", max_val=sv_max, format_str="{:.3f}"), use_container_width=True, config={'displayModeBar': True})
            with k4: st.plotly_chart(create_gauge(df['view_count'].mean()/1000, "Avg Views", "#EF4444", max_val=max(10, df['view_count'].max()/500), suffix="k", format_str="{:.0f}k"), use_container_width=True, config={'displayModeBar': True})

            st.divider()

            # Timing & Mix
            c1, c2 = st.columns([2, 1])
            with c1:
                st.markdown("### 🕒 Optimal Timing Analysis")
                
                # Inline calculation to bypass Streamlit's aggressive module caching of Metrics_caluclator.py
                df_timed = df.copy()
                df_timed['published_at'] = pd.to_datetime(df_timed['published_at'])
                df_timed['publish_hour'] = df_timed['published_at'].dt.hour
                
                avg_v = df_timed.groupby('publish_hour')['view_count'].mean().rename('avg_views')
                count_v = df_timed.groupby('publish_hour')['view_count'].count().rename('video_count')
                opt = pd.concat([avg_v, count_v], axis=1).fillna(0)
                opt = opt.reindex(range(24), fill_value=0)
                
                fig_time = go.Figure()

                # Solid Red Mountain
                fig_time.add_trace(go.Scatter(
                    x=list(range(24)),
                    y=[float(v) for v in opt['avg_views']], # Explicit cast to float to prevent Streamlit JSON dropout
                    mode='lines',
                    line=dict(color='#EF4444', width=2, shape='linear'), 
                    fill='tozeroy',
                    fillcolor='rgba(239, 68, 68, 0.5)', 
                    name='Avg Views',
                    hovertemplate='<b>%{x}:00</b><br>Avg Views: %{y:,.0f}<extra></extra>'
                ))
                
                # Annotate peak
                view_peak_hour = opt['avg_views'].idxmax()
                view_peak_val = opt['avg_views'].max()
                
                # Add star marker for highest views
                fig_time.add_trace(go.Scatter(
                    x=[view_peak_hour], y=[float(view_peak_val)],
                    mode='markers+text',
                    marker=dict(size=14, color='#B91C1C', symbol='star'),
                    text=[f"Top Views<br>({view_peak_val:,.0f} @ {view_peak_hour}:00)"],
                    textposition="top center",
                    textfont=dict(color='#B91C1C', size=12, family='Outfit', weight='bold'),
                    showlegend=False,
                    hoverinfo='skip'
                ))

                fig_time.update_layout(
                    margin=dict(l=20, r=20, t=60, b=20),
                    height=400,
                    xaxis=dict(title="Hour of Day (24h)", tickmode='linear', dtick=2, range=[0, 23]),
                    yaxis=dict(title="Average Views", rangemode='tozero', range=[0, view_peak_val * 1.25], showgrid=True),
                    showlegend=False,
                    template='plotly_white',
                    font=dict(family="Outfit")
                )
                
                st.plotly_chart(fig_time, use_container_width=True, config={'displayModeBar': True})
                
                upload_peak_hour = opt['video_count'].idxmax()
                st.info(f"💡 **Strategic Window:** You upload most often at **{upload_peak_hour}:00**, but your views actually peak when you post at **{view_peak_hour}:00**.")
            
            with c2:
                st.markdown("### 📊 Performance Distribution")
                ranks = df['performance_rank'].value_counts()
                fig_res = px.pie(values=ranks.values, names=ranks.index, hole=0.6, color_discrete_sequence=['#10B981', '#F59E0B', '#EF4444'])
                
                # Relocated legend to bottom to prevent modebar overlap in top right corner
                fig_res.update_layout(
                    margin=dict(l=0, r=0, t=10, b=30), 
                    height=320, 
                    showlegend=True,
                    legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5)
                )
                st.plotly_chart(fig_res, use_container_width=True, config={'displayModeBar': True})
                st.caption(f"You have **{ranks.get('High Performer', 0)}** High Performing videos.")

            st.divider()
            st.markdown("### 📈 Video Ranking Detail")
            st.dataframe(df[['title', 'view_count', 'engagement_rate', 'performance_rank']].sort_values(by='view_count', ascending=False), hide_index=True, use_container_width=True)

# ═══════════════════════════════════════════════════════════════
# PAGE: BATTLE ARENA — Complete Implementation
# ═══════════════════════════════════════════════════════════════
elif st.session_state['page'] == 'battle':
    st.markdown("""
        <div style='text-align:center; padding:10px 0 20px 0;'>
            <h2 style='font-family:Outfit; font-weight:700; color:#1E293B;'>⚖️ Creator Battle Arena</h2>
            <p style='color:#64748B; font-size:1.1rem;'>Compare channels across subscribers, views, engagement, and audience quality.</p>
        </div>
    """, unsafe_allow_html=True)

    # Load all synced channels for selection
    recent = get_recent_channels(limit=50)
    if not recent:
        st.info("No channels found. Please sync at least 2 channels first using the sidebar.")
    else:
        all_names = [r['name'] for r in recent]
        selected = st.multiselect(
            "👥 Select channels to compare (pick 2 or more):",
            all_names,
            placeholder="Start typing a channel name..."
        )

        if len(selected) < 1:
            st.info("👆 Select channels from the dropdown above to start the battle.")
        else:
            # ─── FETCH CHANNEL SUMMARY DATA ───────────────────────────
            ids = [r['id'] for r in recent if r['name'] in selected]
            id_str = "','".join(ids)

            q_ch = f"""
                SELECT channel_name, subscribers, views, total_videos
                FROM channels
                WHERE channel_id IN ('{id_str}')
            """
            with engine.connect() as conn:
                cdf = pd.read_sql(text(q_ch), conn)

            if cdf.empty:
                st.error("No data found for selected channels. Please re-sync them.")
            else:
                # ─────────────────────────────────────────────────────
                # SECTION 1: BAR CHARTS — Audience & Reach Battle
                # ─────────────────────────────────────────────────────
                st.markdown("---")
                st.markdown("### 📊 Head-to-Head Comparison")

                col_bar1, col_bar2 = st.columns(2)

                # ▶ CHART 1: Audience Battle (Subscribers)
                with col_bar1:
                    colors_sub = ['#1D4ED8', '#2563EB', '#3B82F6', '#60A5FA', '#93C5FD', '#BFDBFE']
                    fig_subs = go.Figure()
                    fig_subs.add_trace(go.Bar(
                        name="Subscribers",
                        x=cdf['channel_name'].tolist(),
                        y=cdf['subscribers'].tolist(),
                        marker=dict(
                            color=[colors_sub[i % len(colors_sub)] for i in range(len(cdf))],
                            line=dict(color='white', width=2),
                            cornerradius=6
                        ),
                        text=[fmt_k_m(v) for v in cdf['subscribers']],
                        textposition='outside',
                        cliponaxis=False,
                        textfont=dict(size=14, family='Outfit', color='#1E293B', weight='bold'),
                        textangle=-90,
                        hovertemplate="<b>%{x}</b><br>Subscribers: <b>%{y:,}</b><extra></extra>"
                    ))
                    fig_subs.update_layout(
                        title=dict(text="👥 Audience Battle — Subscribers", font=dict(size=16, family='Outfit')),
                        template='plotly_white',
                        height=440,
                        xaxis=dict(title="Channel", gridcolor='#F1F5F9', tickfont=dict(size=12)),
                        yaxis=dict(title="Total Subscribers (Log Scale)", type='log', gridcolor='#F1F5F9', zeroline=False),
                        font=dict(family="Outfit", size=13),
                        margin=dict(l=20, r=20, t=100, b=60),
                        showlegend=False,
                        plot_bgcolor='white'
                    )
                    st.plotly_chart(fig_subs, use_container_width=True)

                # ▶ CHART 2: Reach Battle (Total Views)
                with col_bar2:
                    colors_view = ['#991B1B', '#B91C1C', '#DC2626', '#EF4444', '#F87171', '#FCA5A5']
                    fig_views = go.Figure()
                    fig_views.add_trace(go.Bar(
                        name="Total Views",
                        x=cdf['channel_name'].tolist(),
                        y=cdf['views'].tolist(),
                        marker=dict(
                            color=[colors_view[i % len(colors_view)] for i in range(len(cdf))],
                            line=dict(color='white', width=2),
                            cornerradius=6
                        ),
                        text=[fmt_k_m(v) for v in cdf['views']],
                        textposition='outside',
                        cliponaxis=False,
                        textfont=dict(size=14, family='Outfit', color='#1E293B', weight='bold'),
                        textangle=-90,
                        hovertemplate="<b>%{x}</b><br>Total Views: <b>%{y:,}</b><extra></extra>"
                    ))
                    fig_views.update_layout(
                        title=dict(text="🚀 Reach Battle — Total Views", font=dict(size=16, family='Outfit')),
                        template='plotly_white',
                        height=440,
                        xaxis=dict(title="Channel", gridcolor='#F1F5F9', tickfont=dict(size=12)),
                        yaxis=dict(title="Total Views (Log Scale)", type='log', gridcolor='#F1F5F9', zeroline=False),
                        font=dict(family="Outfit", size=13),
                        margin=dict(l=20, r=20, t=100, b=60),
                        showlegend=False,
                        plot_bgcolor='white'
                    )
                    st.plotly_chart(fig_views, use_container_width=True)

                st.divider()

                # ─────────────────────────────────────────────────────
                # FETCH VIDEO-LEVEL DATA for Bubble + Funnel
                # ─────────────────────────────────────────────────────
                q_vids = f"""
                    SELECT
                        c.channel_name,
                        v.title,
                        s.view_count,
                        s.like_count,
                        s.comment_count
                    FROM videos v
                    JOIN channels c ON v.channel_id = c.channel_id
                    JOIN video_statistics s ON v.video_id = s.video_id
                    WHERE v.channel_id IN ('{id_str}')
                      AND s.captured_at = (
                          SELECT MAX(s2.captured_at)
                          FROM video_statistics s2
                          WHERE s2.video_id = v.video_id
                      )
                """
                with engine.connect() as conn:
                    v_df = pd.read_sql(text(q_vids), conn)

                # ─────────────────────────────────────────────────────
                # SECTION 2: BUBBLE CHART — Engagement Matrix (Channel Level)
                # ─────────────────────────────────────────────────────
                st.markdown("### 🫧 Engagement Strength Matrix")
                st.caption("Each bubble = **One Channel**. Size = total engagement. Color = channel. Ideal positioning is top-right.")

                if v_df.empty:
                    st.warning("No video statistics found. Please sync the selected channels first.")
                else:
                    # Aggregate video stats to the Channel level for 1 bubble per channel
                    ch_agg = v_df.groupby('channel_name')[['view_count', 'like_count', 'comment_count']].sum().reset_index()
                    ch_agg['engagement_strength'] = (ch_agg['like_count'] + ch_agg['comment_count']).clip(lower=1)
                    ch_agg['quality_score'] = (
                        ch_agg['engagement_strength'] / ch_agg['view_count'].replace(0, np.nan) * 100
                    ).fillna(0).clip(0, 100).round(3)

                    viridis_palette = [
                        '#440154', '#414487', '#2a788e', '#22a884',
                        '#7ad151', '#fde725', '#5ec962', '#31688e'
                    ]

                    max_eng = float(ch_agg['engagement_strength'].max())
                    sizeref_val = 2.0 * max_eng / (80 ** 2)

                    fig_bubble = go.Figure()
                    for i, row in ch_agg.iterrows():
                        fig_bubble.add_trace(go.Scatter(
                            x=[row['view_count']],
                            y=[row['quality_score']],
                            mode='markers+text',
                            name=row['channel_name'],
                            text=[row['channel_name']],
                            textposition="middle right",
                            cliponaxis=False,
                            textfont=dict(size=13, weight='bold', family="Outfit", color='#1E293B'),
                            marker=dict(
                                size=[row['engagement_strength']],
                                sizemode='area',
                                sizeref=sizeref_val,
                                sizemin=15,
                                color=viridis_palette[i % len(viridis_palette)],
                                opacity=0.85,
                                line=dict(color='white', width=2)
                            ),
                            hovertemplate=(
                                "<b>%{text}</b><br>"
                                "Total Views: <b>%{x:,}</b><br>"
                                "Overall Quality Score: <b>%{y:.2f}%</b><br>"
                                "Total Engagement: <b>" + f"{row['engagement_strength']:,}" + "</b><br>"
                                "<extra></extra>"
                            )
                        ))

                    # Expand margins so the text doesn't clip on the right side or top icons
                    # We also add an artificial x-axis padding multiplier to the range implicitly by letting Plotly autorange wide
                    fig_bubble.update_layout(
                        template='plotly_white',
                        height=560,
                        xaxis=dict(
                            title="Total Network Views",
                            gridcolor='#F1F5F9',
                            zeroline=False
                        ),
                        yaxis=dict(
                            title="Overall Quality Score % (engagement/views × 100)",
                            gridcolor='#F1F5F9',
                            zeroline=False
                        ),
                        legend=dict(
                            orientation="h",
                            yanchor="top", y=-0.15,
                            xanchor="center", x=0.5,
                            font=dict(size=12)
                        ),
                        font=dict(family="Inter", size=13),
                        margin=dict(l=50, r=180, t=80, b=50),
                        plot_bgcolor='white'
                    )
                    st.plotly_chart(fig_bubble, use_container_width=True)

                st.divider()

                # ─────────────────────────────────────────────────────
                # SECTION 3: RADAR CHART — Multichannel Capabilities
                # ─────────────────────────────────────────────────────
                st.markdown("### 🕸️ Multichannel Capabilities Radar")
                st.caption("A multi-dimensional comparison of reach, production output, and engagement depth.")

                # Normalize metrics for the radar chart (0 to 1 scales)
                cdf['views_norm'] = cdf['views'] / cdf['views'].max()
                cdf['subs_norm'] = cdf['subscribers'] / cdf['subscribers'].max()
                cdf['videos_norm'] = cdf['total_videos'] / cdf['total_videos'].max()

                # Calculate avg engagement rate from v_df
                if not v_df.empty:
                    er_map = ch_agg.set_index('channel_name')['quality_score']
                    cdf['eng_rate'] = cdf['channel_name'].map(er_map).fillna(0)
                    if cdf['eng_rate'].max() > 0:
                        cdf['eng_norm'] = cdf['eng_rate'] / cdf['eng_rate'].max()
                    else:
                        cdf['eng_norm'] = 0
                else:
                    cdf['eng_rate'] = 0
                    cdf['eng_norm'] = 0

                cat = ['Views Reach', 'Subscribers', 'Video Volume', 'Engagement Depth']

                fig_radar = go.Figure()
                palette = ['#EF4444', '#3B82F6', '#10B981', '#F59E0B', '#8B5CF6']
                
                for i, row in cdf.iterrows():
                    raw_vals = [fmt_k_m(row['views']), fmt_k_m(row['subscribers']), f"{row['total_videos']:,}", f"{row['eng_rate']:.2f}%"]
                    
                    fig_radar.add_trace(go.Bar(
                        x=cat,
                        y=[row['views_norm'], row['subs_norm'], row['videos_norm'], row['eng_norm']],
                        name=row['channel_name'],
                        marker_color=palette[i % len(palette)],
                        marker_line=dict(color='white', width=1.5),
                        customdata=raw_vals,
                        text=raw_vals,
                        textposition='outside',
                        cliponaxis=False,
                        textfont=dict(size=11, family='Outfit', color='#475569'),
                        hovertemplate="<b>%{x}</b><br>Relative Score: %{y:.2f}<br>Actual Value: <b>%{customdata}</b><extra></extra>"
                    ))

                fig_radar.update_layout(
                        barmode='group',
                        showlegend=True,
                        template='plotly_white',
                        height=460,
                        margin=dict(l=20, r=20, t=40, b=40),
                        font=dict(family="Outfit", size=13),
                        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="center", x=0.5),
                        yaxis=dict(title="Normalized Score (0 to 1.0)", range=[0, 1.05], gridcolor='#F1F5F9', zeroline=False),
                        xaxis=dict(gridcolor='#F1F5F9'),
                        plot_bgcolor='white',
                        shapes=[
                            dict(type="line", x0=0.5, x1=0.5, y0=0, y1=1, yref="paper", line=dict(color="#CBD5E1", width=1, dash="dot")),
                            dict(type="line", x0=1.5, x1=1.5, y0=0, y1=1, yref="paper", line=dict(color="#CBD5E1", width=1, dash="dot")),
                            dict(type="line", x0=2.5, x1=2.5, y0=0, y1=1, yref="paper", line=dict(color="#CBD5E1", width=1, dash="dot")),
                        ]
                    )
                st.plotly_chart(fig_radar, use_container_width=True)

                st.divider()

                # ─────────────────────────────────────────────────────
                # SECTION 4: SUMMARY TABLE
                # ─────────────────────────────────────────────────────
                st.markdown("### 📋 Channel Summary Stats")
                
                # Combine cdf with engagement rates from earlier analysis if available
                display_cdf = cdf[['channel_name', 'subscribers', 'views', 'total_videos']].copy()
                if 'eng_rate' in cdf.columns:
                    display_cdf['Avg Quality %'] = cdf['eng_rate'].round(2)
                
                display_cdf = display_cdf.rename(columns={
                    'channel_name': 'Channel',
                    'subscribers': 'Subscribers',
                    'views': 'Total Views',
                    'total_videos': 'Videos'
                })
                
                # Use Pandas Styler to make the table look much better and highly visible
                styler = display_cdf.set_index('Channel').style.format({
                    'Subscribers': "{:,.0f}",
                    'Total Views': "{:,.0f}",
                    'Videos': "{:,.0f}",
                    'Avg Quality %': "{:.2f}%"
                }).background_gradient(
                    cmap="Blues", subset=['Total Views']
                ).background_gradient(
                    cmap="Greens", subset=['Avg Quality %']
                ).set_properties(**{
                    'background-color': '#F8FAFC',
                    'color': '#0F172A',
                    'font-family': 'Outfit, sans-serif',
                    'font-size': '15px',
                    'padding': '12px'
                }).set_table_styles([{
                    'selector': 'th',
                    'props': [
                        ('background-color', '#1E293B'), 
                        ('color', 'white'), 
                        ('font-size', '16px'), 
                        ('font-weight', 'bold'),
                        ('font-family', 'Outfit'),
                        ('padding', '12px')
                    ]
                }])
                
                st.dataframe(styler, use_container_width=True)


# --- PAGE: VISUALS (Task 12 & 13: Pro Intelligence) ---
# --- PAGE: VISUALS (Task 12 & 13: Ultimate Strategic Suite) ---
elif st.session_state['page'] == 'vis':
    if not st.session_state['active_channel_id']:
        st.warning("Please select a channel from the sidebar to view analysis.")
    else:
        chid = st.session_state['active_channel_id']
        df = get_channel_data_from_db(chid)
        if not df.empty:
            # 1. ENHANCED DATA PREP
            df['published_at_dt'] = pd.to_datetime(df['published_at'])
            df['year'] = df['published_at_dt'].dt.year
            df['month_name'] = df['published_at_dt'].dt.month_name()
            df['day_name'] = df['published_at_dt'].dt.day_name()
            df['hour'] = df['published_at_dt'].dt.hour
            # Improved Shorts detection: check for #Shorts tag OR duration <= 100s (for 'Long Shorts')
            def detect_type(row):
                dur = parse_duration(row['duration'])
                has_tag = '#shorts' in row['title'].lower()
                if has_tag or dur <= 100:
                    return 'Shorts'
                return 'Long-form'
            
            df['is_short'] = df.apply(detect_type, axis=1)
            df['engagement_rate'] = ((df['like_count'] + df['comment_count']) / df['view_count'] * 100).fillna(0)
            df['video_url'] = "https://www.youtube.com/watch?v=" + df['video_id']
            
            st.markdown(f"<h2 style='text-align:center;'>💎 Ultimate Pro-Plus Dashboard</h2>", unsafe_allow_html=True)
            
            # 2. HYPER-REACTIVE FILTERS
            with st.container():
                st.markdown("<div style='background-color: #F8FAFC; padding: 25px; border-radius: 12px; border: 1px solid #E2E8F0; margin-bottom: 2rem;'>", unsafe_allow_html=True)
                r1_c1, r1_c2, r1_c3 = st.columns(3)
                with r1_c1:
                    metric_opt = {"Views": "view_count", "Likes": "like_count", "Comments": "comment_count", "Quality %": "engagement_rate"}
                    sel_metric_label = st.selectbox("🧪 Primary Metric Strategy", list(metric_opt.keys()))
                    sel_metric = metric_opt[sel_metric_label]
                with r1_c2:
                    years = sorted(df['year'].unique(), reverse=True)
                    sel_year = st.multiselect("📅 Select Years", years, default=years)
                with r1_c3:
                    sel_duration = st.multiselect("⏱️ Video Type", ["Long-form", "Shorts"], default=["Long-form", "Shorts"])
                days_list = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                sel_days = st.multiselect("🗓️ Days of the Week", days_list, default=days_list)
                
                # New Time Period Filter
                st.markdown("---")
                time_periods = ["All Time", "Last 30 Days", "Last 6 Months", "Last 1 Year"]
                sel_period = st.selectbox("📅 Time Scope Analysis", time_periods)
                
                st.markdown("</div>", unsafe_allow_html=True)

            # APPLY FILTERS
            # 1. Basic Filters
            f_df = df[
                (df['year'].isin(sel_year)) & 
                (df['is_short'].isin(sel_duration)) & 
                (df['day_name'].isin(sel_days))
            ].copy()
            
            # 2. Time Period Filter
            if not f_df.empty:
                max_date = f_df['published_at_dt'].max()
                if sel_period == "Last 30 Days":
                    f_df = f_df[f_df['published_at_dt'] >= (max_date - pd.Timedelta(days=30))]
                elif sel_period == "Last 6 Months":
                    f_df = f_df[f_df['published_at_dt'] >= (max_date - pd.Timedelta(days=180))]
                elif sel_period == "Last 1 Year":
                    f_df = f_df[f_df['published_at_dt'] >= (max_date - pd.Timedelta(days=365))]
            
            if f_df.empty:
                st.error("No data matches your criteria. Try loosening the filters.")
            else:
                # --- PRO-PLUS BRAIN: CALCULATION SPACE ---
                # 1. Stability Score (Expert Metric)
                # Formula: 100 * (1 - (StdDev / Mean)). Higher = More consistent.
                v_avg = f_df[sel_metric].mean()
                v_std = f_df[sel_metric].std()
                cv = (v_std / v_avg) if v_avg > 0 else 0
                stability_score = max(0, min(100, (1 - cv) * 100)) if len(f_df) > 1 else 100
                
                # 2. Topic Analysis (Keyword Extractor)
                common_stops = {'the', 'a', 'to', 'in', 'for', 'of', 'and', 'with', 'on', 'how', 'is', 'it', 'at', 'this', 'that'}
                all_words = " ".join(f_df['title'].str.lower()).split()
                keywords = [w for w in all_words if len(w) > 3 and w not in common_stops]
                top_keywords = pd.Series(keywords).value_counts().head(10).index.tolist()
                
                kw_impact = []
                for kw in top_keywords:
                    avg_m = f_df[f_df['title'].str.contains(kw, case=False, regex=False)][sel_metric].mean()
                    kw_impact.append({'Keyword': kw.capitalize(), 'Avg Impact': avg_m})
                kw_df = pd.DataFrame(kw_impact).sort_values('Avg Impact', ascending=False)

                # 3. 4-TAB PRO-PLUS SYSTEM
                v_tab1, v_tab2, v_tab3, v_tab4 = st.tabs([
                    "📈 Growth Trends", 
                    "🧠 Topic & Stability", 
                    "💎 Content Fingerprint",
                    "📚 Master Search Library"
                ])
                
                # --- TAB 1: GROWTH & VELOCITY ---
                with v_tab1:
                    st.markdown("### 📈 Monthly Engagement Trends")
                    st.caption("📘 Monthly totals — each metric on its own scale for clear trend visibility.")

                    # ── Monthly aggregation from RAW dataset (ignores global filters) ─────
                    trend_df = df.copy()
                    trend_df['pub_dt']    = pd.to_datetime(trend_df['published_at_dt'], errors='coerce')
                    trend_df = trend_df.dropna(subset=['pub_dt']).sort_values('pub_dt')
                    trend_df['year']      = trend_df['pub_dt'].dt.year
                    trend_df['month_num'] = trend_df['pub_dt'].dt.month
                    # True datetime object for continuous spline smoothing
                    trend_df['period_start_dt'] = pd.to_datetime(trend_df['year'].astype(str) + '-' + trend_df['month_num'].astype(str) + '-01')
                    trend_df['ym_label']  = trend_df['pub_dt'].dt.strftime('%b %Y')

                    monthly = (
                        trend_df.groupby(['period_start_dt', 'ym_label'], as_index=False)
                        .agg(views=('view_count','sum'),
                             likes=('like_count','sum'),
                             comments=('comment_count','sum'),
                             uploads=('view_count','count'))
                        .sort_values('period_start_dt')
                    )

                    if monthly.empty or len(monthly) < 2:
                        st.info("Not enough monthly data for long-term trends.")
                    else:
                        from plotly.subplots import make_subplots as _make_subplots

                        ROWS = [
                            ("👁️ Monthly Views",    "views",    '#3B82F6', 'rgba(59,130,246,0.15)'),
                            ("❤️ Monthly Likes",    "likes",    '#10B981', 'rgba(16,185,129,0.15)'),
                            ("� Monthly Comments", "comments", '#F97316', 'rgba(249,115,22,0.15)'),
                        ]

                        fig_line = _make_subplots(
                            rows=3, cols=1,
                            shared_xaxes=True,
                            subplot_titles=[r[0] for r in ROWS],
                            vertical_spacing=0.09
                        )

                        for row_i, (title, col, line_c, fill_c) in enumerate(ROWS, start=1):
                            y_vals = monthly[col].tolist()
                            x_vals = monthly['period_start_dt'].tolist()
                            peak_i = int(monthly[col].idxmax())

                            # Filled area + line
                            fig_line.add_trace(go.Scatter(
                                x=x_vals, y=y_vals,
                                mode='lines+markers',
                                name=title,
                                line=dict(color=line_c, width=2.5, shape='spline'),
                                fill='tozeroy', fillcolor=fill_c,
                                marker=dict(size=7, color=line_c,
                                            line=dict(color='white', width=1.5)),
                                hovertemplate=f"<b>%{{x|%b %Y}}</b><br>{title}: <b>%{{y:,}}</b><extra></extra>",
                                showlegend=False
                            ), row=row_i, col=1)

                            # Peak annotation — explicit xref/yref
                            _yref_map = {1: 'y', 2: 'y2', 3: 'y3'}
                            fig_line.add_annotation(
                                x=x_vals[peak_i], y=y_vals[peak_i],
                                xref='x', yref=_yref_map[row_i],
                                text=f"⚡ {monthly['ym_label'].iloc[peak_i]}",
                                showarrow=True, arrowhead=2, arrowcolor=line_c,
                                ax=0, ay=-38,
                                bgcolor=line_c, bordercolor='white', borderwidth=1, borderpad=4,
                                font=dict(size=10, color='white', family='Inter')
                            )

                            # Y-axis formatting per row
                            fig_line.update_yaxes(
                                title_text=col.capitalize(),
                                tickformat='.2s',
                                gridcolor='#F1F5F9',
                                row=row_i, col=1
                            )

                        fig_line.update_xaxes(
                            tickformat="%b %Y",
                            gridcolor='#F1F5F9',
                            tickfont=dict(size=11),
                            row=3, col=1  # only bottom row needs x-label
                        )
                        fig_line.update_layout(
                            height=680,
                            template='plotly_white',
                            hovermode='x unified',
                            font=dict(family='Inter', size=12),
                            margin=dict(l=60, r=40, t=60, b=40),
                            plot_bgcolor='white',
                            paper_bgcolor='white'
                        )
                        st.plotly_chart(fig_line, use_container_width=True)

                        # ── Trend Verdict ─────────────────────────────────────
                        def _trend(col):
                            first, last = monthly[col].iloc[0], monthly[col].iloc[-1]
                            pct = (last - first) / max(first, 1) * 100
                            arrow = "📈" if pct >= 0 else "📉"
                            return f"{arrow} {abs(pct):.0f}% {'growth' if pct>=0 else 'decline'}"

                        peak_m = monthly.loc[monthly['views'].idxmax(), 'ym_label']
                        st.markdown(f"""
                        <div style='background:#F8FAFC; padding:16px 20px; border-radius:10px;
                                    border-left:6px solid #3B82F6; margin-top:4px;'>
                            <h4 style='margin:0 0 8px 0; color:#1E293B;'>⚡ Trend Intelligence Verdict</h4>
                            <div style='display:flex; gap:32px; font-size:0.92rem; color:#334155;'>
                                <span>👁️ <b>Views:</b> {_trend('views')}</span>
                                <span>❤️ <b>Likes:</b> {_trend('likes')}</span>
                                <span>💬 <b>Comments:</b> {_trend('comments')}</span>
                                <span>⚡ <b>Peak Month:</b> {peak_m}</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

                    st.divider()

                    # ── UPLOAD FREQUENCY HEATMAP ────────────────────────────────
                    st.markdown("### 🗓️ Upload Frequency Heatmap (Month × Day of Week)")
                    st.caption("Each cell = number of videos uploaded on that day/month combination. Darker green = more uploads.")

                    # Build matrix manually using integer month numbers + day names
                    # This avoids the groupby pivot returning numeric indices
                    MONTHS_ABBR = ['Jan','Feb','Mar','Apr','May','Jun',
                                   'Jul','Aug','Sep','Oct','Nov','Dec']
                    DAYS_ORDER  = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
                    DAY_MAP = {
                        'Monday':'Mon','Tuesday':'Tue','Wednesday':'Wed',
                        'Thursday':'Thu','Friday':'Fri','Saturday':'Sat','Sunday':'Sun'
                    }

                    # Extract month (1-12) and short day name from filtered data
                    hm_df = f_df.copy()
                    hm_df['month_num']  = hm_df['published_at_dt'].dt.month          # 1-12
                    hm_df['day_short']  = hm_df['day_name'].map(DAY_MAP)             # 'Mon'...'Sun'

                    # Build 7×12 matrix (rows=days, cols=months)
                    import numpy as np
                    z_matrix = np.zeros((7, 12), dtype=int)
                    for _, row in hm_df.iterrows():
                        m_idx = int(row['month_num']) - 1          # 0-11
                        d_idx = DAYS_ORDER.index(row['day_short']) if row['day_short'] in DAYS_ORDER else -1
                        if 0 <= m_idx < 12 and d_idx >= 0:
                            z_matrix[d_idx][m_idx] += 1

                    # Green density colorscale
                    green_scale = [
                        [0.00, '#EBEDF0'],   # empty/grey (0 uploads)
                        [0.01, '#9BE9A8'],   # very light green
                        [0.25, '#40C463'],   # light green
                        [0.60, '#30A14E'],   # medium green
                        [1.00, '#216E39'],   # dark green (most uploads)
                    ]

                    # Hover text matrix
                    hover_matrix = []
                    for d_i, day in enumerate(DAYS_ORDER):
                        row_text = []
                        for m_i, mon in enumerate(MONTHS_ABBR):
                            cnt = z_matrix[d_i][m_i]
                            row_text.append(f"<b>{day}, {mon}</b><br>Uploads: <b>{cnt}</b>")
                        hover_matrix.append(row_text)

                    fig_heat = go.Figure(go.Heatmap(
                        z=z_matrix.tolist(),
                        x=MONTHS_ABBR,
                        y=DAYS_ORDER,
                        colorscale=green_scale,
                        xgap=4,
                        ygap=4,
                        showscale=True,
                        colorbar=dict(
                            title=dict(text="Uploads", font=dict(size=11)),
                            thickness=13,
                            len=0.75,
                            tickfont=dict(size=10)
                        ),
                        text=hover_matrix,
                        hovertemplate="%{text}<extra></extra>",
                        zmin=0
                    ))
                    fig_heat.update_layout(
                        height=420,  # Taller so it looks naturally proportional when expanded
                        template='plotly_white',
                        xaxis=dict(
                            title="Month",
                            side='bottom',
                            tickfont=dict(size=12, family='Outfit'),
                            tickangle=0,
                            gridcolor='rgba(0,0,0,0)',
                            fixedrange=True
                        ),
                        yaxis=dict(
                            title="",
                            autorange='reversed',
                            tickfont=dict(size=12, family='Outfit'),
                            gridcolor='rgba(0,0,0,0)',
                            fixedrange=True
                            # Removed scaleanchor to prevent 'shrinking to middle' on wide screens
                        ),
                        margin=dict(l=50, r=20, t=20, b=50),
                        plot_bgcolor='white',
                        paper_bgcolor='white',
                        font=dict(family="Outfit", size=12)
                    )
                    st.plotly_chart(fig_heat, use_container_width=True)
                    st.caption("🟩 Dark green = most uploads on that day/month | ⬜ Grey = no uploads")

                    # ── Heatmap Conclusion Card ───────────────────────────────────
                    max_u = int(np.max(z_matrix))
                    if max_u > 0:
                        max_d_i, max_m_i = np.unravel_index(np.argmax(z_matrix), z_matrix.shape)
                        peak_d = DAYS_ORDER[max_d_i]
                        peak_m = MONTHS_ABBR[max_m_i]
                        total_u = int(np.sum(z_matrix))
                        
                        st.markdown(f"""
                        <div style='background:#F8FAFC; padding:16px 20px; border-radius:10px; border-left:6px solid #10B981; margin-top:4px;'>
                            <h4 style='margin:0; color:#1E293B;'>⚡ Upload Pattern Insights</h4>
                            <p style='margin:8px 0 0 0; font-size:0.95rem; color:#334155;'>
                                Across this period, you uploaded <b>{total_u} videos</b>. Your absolute peak posting time was on 
                                <b>{peak_d}s in {peak_m}</b> (with {max_u} uploads).
                            </p>
                        </div>
                        """, unsafe_allow_html=True)

                # ── TAB 2: TOPICS & STABILITY ──────────────────────────────
                with v_tab2:
                    n_videos = len(f_df)
                    st.markdown(f"### 📈 Expert Channel Health Analytics")
                    st.info(f"🎯 Analysing **{n_videos} videos** from your selected filters. Adjust the year/type/days filters above to change the scope.")

                    # ── Better Stability Score Formula ──
                    # Use a log-normalised CV so even very variable channels don't hit absolute 0
                    v_vals = f_df[sel_metric].dropna()
                    if len(v_vals) <= 1:
                        stability_score = 100.0
                    elif v_vals.mean() <= 0:
                        stability_score = 0.0
                    else:
                        cv = v_vals.std() / v_vals.mean()
                        # cv=0 → 100, cv=0.5 → ~70, cv=1 → ~50, cv=2 → ~30
                        stability_score = round(max(5, 100 / (1 + cv)), 1)

                    if stability_score >= 70:
                        score_color = '#10B981'
                        score_label = 'HIGHLY CONSISTENT'
                        score_msg = 'Your content delivers predictable, repeatable results. Strong foundation for algorithmic growth.'
                    elif stability_score >= 40:
                        score_color = '#F59E0B'
                        score_label = 'MODERATELY VARIABLE'
                        score_msg = 'Mixed performance — some viral hits alongside steady videos. Consider identifying what makes your top videos spike.'
                    else:
                        score_color = '#EF4444'
                        score_label = 'HIGHLY VOLATILE'
                        score_msg = 'Your growth is driven by viral outliers. The channel has a wide spread of low and high performers.'

                    c_h1, c_h2 = st.columns([1, 1])
                    with c_h1:
                        # ── go.Indicator gauge: no Pie chart = no null-label JS crash ──
                        fig_ring = go.Figure(go.Indicator(
                            mode="gauge+number",
                            value=stability_score,
                            domain={'x': [0, 1], 'y': [0.1, 1]},
                            number=dict(
                                font=dict(size=72, color=score_color, family='Inter, sans-serif'),
                                suffix=""
                            ),
                            gauge=dict(
                                axis=dict(
                                    range=[0, 100],
                                    showticklabels=True,
                                    tickvals=[0, 40, 70, 100],
                                    ticktext=["0", "40", "70", "100"],
                                    tickfont=dict(size=11, color='#94A3B8')
                                ),
                                bar=dict(color=score_color, thickness=0.30),
                                bgcolor='#F1F5F9',
                                borderwidth=0,
                                steps=[
                                    dict(range=[0, 40],  color='#FEE2E2'),
                                    dict(range=[40, 70], color='#FEF9C3'),
                                    dict(range=[70, 100],color='#D1FAE5'),
                                ],
                                threshold=dict(
                                    line=dict(color=score_color, width=4),
                                    thickness=0.85,
                                    value=stability_score
                                )
                            )
                        ))
                        # Tier label annotation below the gauge number
                        fig_ring.add_annotation(
                            text=f"<b>{score_label}</b> &nbsp;|&nbsp; / 100",
                            x=0.5, y=0.08,
                            font=dict(size=13, color=score_color, family='Inter, sans-serif'),
                            showarrow=False, xref='paper', yref='paper',
                            align='center'
                        )
                        fig_ring.update_layout(
                            height=460,
                            margin=dict(l=30, r=30, t=60, b=20),
                            paper_bgcolor='white',
                            title=dict(
                                text="◆ Consistency Score",
                                x=0.5, y=0.97,
                                font=dict(size=13, color='#64748B', family='Inter')
                            )
                        )
                        st.plotly_chart(fig_ring, use_container_width=True)
                        st.info(f"**Analysis:** {score_msg}")

                    with c_h2:
                        st.markdown("### 📦 Performance Box Plot")
                        st.caption(f"Spread of **{sel_metric_label}** from {n_videos} videos")

                        # Format large numbers as K/M for readability
                        def fmt_num(n):
                            if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
                            if n >= 1_000: return f"{n/1_000:.0f}K"
                            return f"{n:.0f}"

                        fig_box = go.Figure()
                        fig_box.add_trace(go.Box(
                            y=f_df[sel_metric].tolist(),
                            name=sel_metric_label,
                            boxpoints='all',
                            jitter=0.45,
                            pointpos=-1.8,
                            marker=dict(color='#10B981', size=5, opacity=0.7),
                            line=dict(color='#059669', width=2),
                            fillcolor='rgba(16,185,129,0.15)',
                            hovertemplate=f"{sel_metric_label}: %{{y:,.0f}}<extra></extra>"
                        ))
                        # Format y-axis ticks to K/M
                        max_val = float(f_df[sel_metric].max())
                        if max_val >= 1_000_000:
                            tickformat = ".2s"
                        elif max_val >= 1_000:
                            tickformat = ".3s"
                        else:
                            tickformat = ".0f"
                        fig_box.update_layout(
                            template='plotly_white', height=420,
                            yaxis=dict(title=sel_metric_label, gridcolor='#F1F5F9', tickformat=tickformat),
                            font=dict(family="Inter", size=13),
                            showlegend=False,
                            margin=dict(l=30, r=15, t=20, b=30)
                        )
                        st.plotly_chart(fig_box, use_container_width=True)

                        # ── Box plot conclusion card ───────────────────────────
                        bp_vals = f_df[sel_metric].dropna()
                        bp_q1   = float(bp_vals.quantile(0.25))
                        bp_med  = float(bp_vals.median())
                        bp_q3   = float(bp_vals.quantile(0.75))
                        bp_iqr  = bp_q3 - bp_q1
                        bp_max  = float(bp_vals.max())
                        bp_min  = float(bp_vals.min())
                        outlier_thresh = bp_q3 + 1.5 * bp_iqr
                        n_outliers = int((bp_vals > outlier_thresh).sum())

                        spread_label = "tight (very consistent)" if bp_iqr < bp_med * 0.5 else \
                                       "moderate" if bp_iqr < bp_med else "wide (highly variable)"

                        st.markdown(f"""
                        <div style='background:linear-gradient(135deg,#F0FDF4,#ECFDF5);
                                    border:1px solid #6EE7B7; border-radius:12px;
                                    padding:15px 20px; margin-top:6px;'>
                            <p style='margin:0 0 8px 0; font-size:0.95rem; font-weight:600; color:#065F46;'>
                                📋 Box Plot Reading — {sel_metric_label}
                            </p>
                            <ul style='margin:0; padding-left:18px; font-size:0.88rem; color:#1E293B; line-height:1.8;'>
                                <li>📏 <b>Middle 50% of videos</b> (IQR) range from
                                    <b>{fmt_num(bp_q1)}</b> to <b>{fmt_num(bp_q3)}</b>
                                    — spread is <b>{spread_label}</b>.</li>
                                <li>📍 <b>Median {sel_metric_label}:</b> <b>{fmt_num(bp_med)}</b>
                                    — half your videos perform above this, half below.</li>
                                <li>{'⚠️' if n_outliers else '✅'} <b>Outliers:</b>
                                    {'<b>' + str(n_outliers) + ' video(s)</b> exceeded <b>' + fmt_num(outlier_thresh) + '</b> (1.5×IQR above Q3) — these are your viral spikes worth studying.'
                                     if n_outliers else
                                     'No statistical outliers detected — performance is evenly distributed.'}</li>
                            </ul>
                        </div>
                        """, unsafe_allow_html=True)

                    st.divider()

                    # ── HISTOGRAM ──────────────────────────────────────────────
                    st.markdown("### 📊 View Count Distribution (Histogram)")
                    st.caption(f"How are your {n_videos} videos distributed across view count ranges?")

                    hist_vals = f_df['view_count'].dropna()
                    max_views = float(hist_vals.max())
                    # Determine axis tick format
                    if max_views >= 1_000_000:
                        tick_sfx, divisor = "M", 1_000_000
                    elif max_views >= 1_000:
                        tick_sfx, divisor = "K", 1_000
                    else:
                        tick_sfx, divisor = "", 1

                    # Scale the values for display
                    hist_display = (hist_vals / divisor).round(2) if divisor > 1 else hist_vals

                    fig_hist = go.Figure(go.Histogram(
                        x=hist_display.tolist(),
                        nbinsx=min(25, max(5, n_videos // 3)),
                        marker=dict(
                            color='#6366F1',
                            line=dict(color='white', width=1.5)
                        ),
                        hovertemplate=f"Views: %{{x}}{tick_sfx}<br>Videos: %{{y}}<extra></extra>"
                    ))
                    fig_hist.update_layout(
                        template='plotly_white', height=420, bargap=0.08,
                        xaxis=dict(title=f"View Count ({tick_sfx if tick_sfx else 'absolute'})", gridcolor='#F1F5F9'),
                        yaxis=dict(title="Number of Videos", gridcolor='#F1F5F9'),
                        font=dict(family="Inter", size=13),
                        margin=dict(l=30, r=30, t=20, b=40)
                    )
                    st.plotly_chart(fig_hist, use_container_width=True)
                    st.caption(f"X-axis units: **{tick_sfx if tick_sfx else 'absolute count'}**. Each bar = a range of view counts. Taller bars = more videos in that bracket.")

                    st.divider()

                    # ── KEYWORDS ──────────────────────────────────────────────
                    st.markdown("### 🧠 Topic Intelligence: Winning Keywords")
                    st.write("Which words in your titles actually drive the most performance?")
                    if not kw_df.empty:
                        kw_df_clean = kw_df.dropna(subset=['Avg Impact']).copy()
                        if not kw_df_clean.empty:
                            kw_df_clean = kw_df_clean.sort_values('Avg Impact', ascending=True)
                            n_kw = len(kw_df_clean)

                            # ── Soothing teal→purple gradient per bar ──────────
                            KW_PALETTE = [
                                '#06B6D4','#0EA5E9','#3B82F6','#6366F1',
                                '#8B5CF6','#A855F7','#C026D3','#DB2777',
                            ]
                            def kw_color(rank_0, total):
                                idx = int(rank_0 * (len(KW_PALETTE)-1) / max(total-1, 1))
                                return KW_PALETTE[min(idx, len(KW_PALETTE)-1)]
                            bar_colors = [kw_color(i, n_kw) for i in range(n_kw)]

                            # ── Color indicator legend ─────────────────────────
                            st.markdown("""
                            <div style='display:flex; align-items:center; gap:10px; margin:4px 0 10px 0;'>
                                <span style='font-size:0.8rem; color:#64748B; white-space:nowrap;'>Low impact</span>
                                <div style='flex:1; height:10px; border-radius:6px;
                                    background:linear-gradient(to right,#06B6D4,#3B82F6,#6366F1,#8B5CF6,#C026D3,#DB2777);
                                    border:1px solid #E2E8F0;'></div>
                                <span style='font-size:0.8rem; color:#64748B; white-space:nowrap;'>High impact</span>
                            </div>""", unsafe_allow_html=True)

                            # ── Build bar chart ────────────────────────────────
                            fig_kw = go.Figure(go.Bar(
                                x=kw_df_clean['Avg Impact'].tolist(),
                                y=kw_df_clean['Keyword'].tolist(),
                                orientation='h',
                                marker=dict(
                                    color=bar_colors,
                                    line=dict(color='white', width=1.5)
                                ),
                                text=[f"  {v:.1f}" for v in kw_df_clean['Avg Impact']],
                                textposition='outside',
                                textfont=dict(size=12, color='#334155'),
                                hovertemplate="<b>%{y}</b><br>Avg Impact: <b>%{x:.2f}</b><extra></extra>"
                            ))
                            fig_kw.update_layout(
                                template='plotly_white',
                                height=max(320, n_kw * 38),
                                font=dict(family='Inter', size=13),
                                xaxis=dict(title='Avg Impact Score', gridcolor='#F1F5F9'),
                                yaxis=dict(title='', gridcolor='rgba(0,0,0,0)'),
                                margin=dict(l=10, r=60, t=10, b=40),
                                plot_bgcolor='white', paper_bgcolor='white'
                            )
                            st.plotly_chart(fig_kw, use_container_width=True)

                            # ── Top 3 conclusion card ──────────────────────────
                            top3 = kw_df_clean.sort_values('Avg Impact', ascending=False).head(3)
                            avg_val = max(f_df[sel_metric].mean(), 0.001)
                            badge_colors = ['#8B5CF6', '#3B82F6', '#06B6D4']
                            medal = ['🥇', '🥈', '🥉']
                            badges_html = "".join([
                                f"<span style='background:{badge_colors[i]}; color:white; padding:4px 14px; "
                                f"border-radius:20px; font-size:0.88rem; margin-right:8px;'>"
                                f"{medal[i]} <b>{row['Keyword']}</b> — {row['Avg Impact']/avg_val:.1f}x avg</span>"
                                for i, (_, row) in enumerate(top3.iterrows())
                            ])
                            st.markdown(f"""
                            <div style='background:linear-gradient(135deg,#F0F9FF,#EDE9FE);
                                        border:1px solid #C7D2FE; border-radius:12px;
                                        padding:16px 20px; margin-top:8px;'>
                                <p style='margin:0 0 10px 0; font-size:0.95rem; font-weight:600; color:#1E293B;'>
                                    📌 Top 3 Keywords Driving Your {sel_metric_label}
                                </p>
                                <div style='display:flex; flex-wrap:wrap; gap:6px;'>{badges_html}</div>
                                <p style='margin:12px 0 0 0; font-size:0.82rem; color:#64748B;'>
                                    💡 Include these words in future titles to maximise {sel_metric_label}.
                                </p>
                            </div>
                            """, unsafe_allow_html=True)
                        else:
                            st.info("Not enough keyword data to analyze for this filter selection.")
                    else:
                        st.info("Not enough keyword data to analyze for this filter selection.")


                 # ─── TAB 3: CONTENT FINGERPRINT ─────────────────────────────
                with v_tab3:
                    st.markdown("### 🗺️ Content Impact Architecture — Top 15 Videos")

                    # ── Select top 15 by the chosen metric ──
                    val_col = 'view_count' if sel_metric == 'engagement_rate' else sel_metric
                    treemap_df = f_df.nlargest(15, val_col).copy()
                    # Remove any videos with 0 value to prevent empty blocks
                    treemap_df = treemap_df[treemap_df[val_col] > 0].copy()
                    treemap_df = treemap_df.sort_values('engagement_rate').reset_index(drop=True)
                    n_blocks   = len(treemap_df)

                    if n_blocks == 0:
                        st.info("No videos with data for this metric/filter combination.")
                    else:
                        e_min_real = float(treemap_df['engagement_rate'].min())
                        e_max_real = float(treemap_df['engagement_rate'].max())

                        st.caption(
                            f"Block **size** = {sel_metric_label}  |  "
                            f"Hover a block for full details  |  "
                            f"Engagement range: **{e_min_real:.3f}% → {e_max_real:.3f}%**"
                        )

                        # ── 15-stop gradient palette ──────────────────────────────
                        PALETTE = [
                            '#0F172A', '#0C1A3E', '#133066', '#1D4ED8', '#2563EB',
                            '#3B82F6', '#0EA5E9', '#06B6D4', '#10B981', '#34D399',
                            '#84CC16', '#EAB308', '#F59E0B', '#F97316', '#EF4444',
                        ]
                        def rank_to_color(rank_0_based, total):
                            idx = int(rank_0_based * (len(PALETTE) - 1) / max(total - 1, 1))
                            return PALETTE[min(idx, len(PALETTE) - 1)]

                        treemap_df['block_color'] = [rank_to_color(i, n_blocks) for i in range(n_blocks)]

                        # Format numbers
                        def fmt(n):
                            n = int(n)
                            if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
                            if n >= 1_000:     return f"{n/1_000:.1f}K"
                            return str(n)

                        # ── Block label: ONLY short title + rank (clean, large font) ──
                        treemap_df['short_title'] = treemap_df['title'].apply(
                            lambda t: t[:30] + '…' if len(t) > 30 else t
                        )
                        treemap_df['block_label'] = treemap_df.apply(
                            lambda r: f"{r['short_title']}  •  #{int(r.name)+1}",
                            axis=1
                        )

                        # ── Hover tooltip: FULL details on mouse-over ─────────────
                        treemap_df['hover_text'] = treemap_df.apply(
                            lambda r: (
                                f"<b>{r['title']}</b><br>"
                                f"───────────────────────<br>"
                                f"👁 Views: <b>{fmt(r['view_count'])}</b><br>"
                                f"❤️ Likes: <b>{fmt(r['like_count'])}</b><br>"
                                f"💬 Comments: <b>{fmt(r['comment_count'])}</b><br>"
                                f"📊 Engagement: <b>{r['engagement_rate']:.3f}%</b><br>"
                                f"🏅 Rank: <b>#{int(r.name)+1} / {n_blocks}</b>"
                            ), axis=1
                        )

                        # ── Build go.Treemap ──────────────────────────────────────
                        fig_tree = go.Figure(go.Treemap(
                            ids            = treemap_df['short_title'].tolist(),
                            labels         = treemap_df['block_label'].tolist(),
                            parents        = [''] * n_blocks,
                            values         = treemap_df[val_col].tolist(),
                            text           = treemap_df['hover_text'].tolist(),
                            textinfo       = 'label',
                            hovertemplate  = "%{text}<extra></extra>",
                            textposition   = "middle center",
                            marker=dict(
                                colors   = treemap_df['block_color'].tolist(),
                                line     = dict(width=3, color='white'),
                                pad      = dict(t=8, l=8, r=8, b=8)
                            ),
                            insidetextfont = dict(
                                size   = 18,
                                family = 'Outfit, Inter, sans-serif',
                                color  = 'white'
                            ),
                            tiling = dict(packing='squarify'),
                            root   = dict(color='#F8FAFC')
                        ))
                        fig_tree.update_layout(
                            height=540,
                            margin=dict(l=8, r=8, t=8, b=8),
                            font=dict(family="Outfit", size=14),
                            paper_bgcolor='white'
                        )
                        st.plotly_chart(fig_tree, use_container_width=True)

                        # ── Color Legend (below chart, clean layout) ──────────────
                        st.markdown(f"""
                        <div style='display:flex; align-items:center; gap:10px; margin:10px 0 4px 0;'>
                            <span style='font-size:0.85rem; color:#475569; font-weight:600; white-space:nowrap;'>🔵 Low Engagement</span>
                            <div style='
                                flex:1; height:16px; border-radius:10px;
                                background: linear-gradient(to right,
                                    #0F172A, #133066, #1D4ED8, #3B82F6,
                                    #0EA5E9, #06B6D4, #10B981, #34D399,
                                    #84CC16, #EAB308, #F59E0B, #F97316, #EF4444);
                                border: 1px solid #E2E8F0;
                            '></div>
                            <span style='font-size:0.85rem; color:#475569; font-weight:600; white-space:nowrap;'>🔴 High Engagement</span>
                        </div>
                        <p style='font-size:0.8rem; color:#94A3B8; margin:2px 0 10px 0; text-align:center;'>
                            Color = relative engagement rank within these {n_blocks} videos  |  Block size = {sel_metric_label}
                        </p>
                        """, unsafe_allow_html=True)



                    st.divider()

                    # ── RADAR + FUNNEL side by side ────────────────────────────
                    c5, c6 = st.columns([1, 1])

                    with c5:
                        st.markdown("### 🎯 Best Video Signature Radar")
                        if not f_df.empty:
                            top_v = f_df.nlargest(1, sel_metric).iloc[0]
                            radar_metrics = ['view_count', 'like_count', 'comment_count', 'engagement_rate']
                            radar_labels  = ['Views', 'Likes', 'Comments', 'Quality %']
                            norm_vals = [
                                top_v[m] / (f_df[m].max() if f_df[m].max() > 0 else 1)
                                for m in radar_metrics
                            ]
                            fig_radar = go.Figure(go.Scatterpolar(
                                r=norm_vals + [norm_vals[0]],
                                theta=radar_labels + [radar_labels[0]],
                                fill='toself',
                                fillcolor='rgba(99,102,241,0.18)',
                                line=dict(color='#6366F1', width=3),
                                marker=dict(size=9, color='#6366F1',
                                            line=dict(color='white', width=2))
                            ))
                            fig_radar.update_layout(
                                polar=dict(
                                    bgcolor='#F8FAFC',
                                    radialaxis=dict(
                                        visible=True, range=[0, 1],
                                        tickfont=dict(size=9),
                                        gridcolor='#E2E8F0'
                                    ),
                                    angularaxis=dict(gridcolor='#E2E8F0')
                                ),
                                showlegend=False, height=400,
                                margin=dict(l=50, r=50, t=30, b=30),
                                paper_bgcolor='white',
                                font=dict(family="Outfit", size=13)
                            )
                            st.plotly_chart(fig_radar, use_container_width=True)

                            # Top video info card
                            st.markdown(f"""
                                <div style='background:linear-gradient(135deg,#6366F1,#8B5CF6); color:white;
                                            padding:14px 18px; border-radius:12px; margin-top:-10px;'>
                                    <p style='margin:0; font-size:0.82rem; opacity:0.85;'>🏆 Best Performing Video</p>
                                    <p style='margin:4px 0 0 0; font-size:0.95rem; font-weight:600;'>{top_v['title'][:60]}{'…' if len(top_v['title'])>60 else ''}</p>
                                    <p style='margin:6px 0 0 0; font-size:0.85rem; opacity:0.9;'>
                                        👁 {int(top_v['view_count']):,} views &nbsp;|&nbsp;
                                        ❤️ {int(top_v['like_count']):,} likes &nbsp;|&nbsp;
                                        💬 {int(top_v['comment_count']):,} comments
                                    </p>
                                </div>
                            """, unsafe_allow_html=True)

                    with c6:
                        st.markdown("### 🌪️ Audience Conversion Funnel")
                        st.caption("What % of views turn into genuine engagement?")

                        total_views    = int(f_df['view_count'].sum())
                        total_likes    = int(f_df['like_count'].sum())
                        total_comments = int(f_df['comment_count'].sum())

                        # Guard: ensure views > 0 to prevent infinity%
                        if total_views <= 0:
                            st.warning("⚠️ No view data available for this filter. Try expanding your year/type selection.")
                        else:
                            def humanize(n):
                                if n >= 1_000_000: return f"{n/1_000_000:.2f}M"
                                if n >= 1_000:     return f"{n/1_000:.1f}K"
                                return str(n)

                            like_pct    = round(total_likes    / total_views * 100, 2)
                            comment_pct = round(total_comments / total_views * 100, 2)

                            fig_funnel = go.Figure(go.Funnel(
                                y=["👁️ Total Views", "❤️ Total Likes", "💬 Total Comments"],
                                x=[total_views, total_likes, total_comments],
                                # Views bar is wide → label inside; Likes & Comments are thin → label outside/beside
                                textposition=["inside", "outside", "outside"],
                                textinfo="none",   # we use custom text below
                                text=[
                                    f"<b>{humanize(total_views)}</b><br>100% reach",
                                    f"<b>{humanize(total_likes)}</b>  {like_pct:.2f}% of views",
                                    f"<b>{humanize(total_comments)}</b>  {comment_pct:.2f}% of views"
                                ],
                                texttemplate="%{text}",
                                textfont=dict(size=13, family="Inter"),
                                marker=dict(
                                    color=["#3B82F6", "#10B981", "#F59E0B"],
                                    line=dict(width=2, color="white")
                                ),
                                connector=dict(line=dict(color="#CBD5E1", dash="dot", width=2)),
                                opacity=0.93
                            ))
                            fig_funnel.update_layout(
                                template='plotly_white',
                                height=420,
                                font=dict(family="Inter", size=14),
                                margin=dict(l=80, r=40, t=20, b=20),
                                paper_bgcolor='white',
                                plot_bgcolor='white'
                            )
                            st.plotly_chart(fig_funnel, use_container_width=True)

                            # Summary metrics below funnel
                            fm1, fm2, fm3 = st.columns(3)
                            fm1.metric("👁️ Views", humanize(total_views))
                            fm2.metric("❤️ Like Rate", f"{like_pct:.2f}%")
                            fm3.metric("💬 Comment Rate", f"{comment_pct:.2f}%")

                # --- TAB 4: MASTER SEARCH LIBRARY ---
                with v_tab4:
                    st.markdown("### 📚 Master Video Search Library")
                    st.write("Search for any video, filter by metric, and watch instantly.")
                    
                    search_query = st.text_input("🔍 Search by Title or Keyword:", placeholder="e.g. Python tutorial...")
                    s_df = f_df[f_df['title'].str.contains(search_query, case=False, regex=False)] if search_query else f_df
                    
                    sort_metric = st.selectbox("Sort Library by:", list(metric_opt.keys()))
                    s_df = s_df.sort_values(metric_opt[sort_metric], ascending=False)
                    
                    st.markdown(f"**Showing {len(s_df)} Videos**")
                    
                    for idx, row in s_df.head(20).iterrows():
                        with st.container():
                            col1, col2, col3 = st.columns([1, 4, 1])
                            with col1:
                                thumb_url = row.get('v_thumb', "")
                                if thumb_url:
                                    # use_column_width is correct for Streamlit 1.31.0
                                    st.image(thumb_url, use_column_width=True)
                                else:
                                    st.info("No Preview")
                            with col2:
                                st.markdown(f"**{row['title']}**")
                                type_color = "#10B981" if row['is_short'] == 'Long-form' else "#3B82F6"
                                st.markdown(f"<span style='background-color: {type_color}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem;'>{row['is_short']}</span>", unsafe_allow_html=True)
                                st.caption(f"Published: {row['published_at_dt'].strftime('%b %d, %Y')} | Duration: {row['duration']} ({int(parse_duration(row['duration']))}s)")
                                st.write(f"📈 {row['view_count']:,} Views | ❤️ {row['like_count']:,} Likes | 💎 {row['engagement_rate']:.2f}% Quality")
                            with col3:
                                st.markdown("<br>", unsafe_allow_html=True)
                                # use_container_width not supported in st.link_button in Streamlit 1.31.0
                                st.link_button("📺 Watch", row['video_url'])
                            st.divider()

                st.markdown("<p style='text-align:right; font-size:0.9rem; color:#64748B;'>👑 Pro-Plus Visual Intelligence Suite | All charts are interactive.</p>", unsafe_allow_html=True)

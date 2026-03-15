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
import matplotlib
matplotlib.use('Agg') # Non-interactive backend
import matplotlib.pyplot as plt
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

@st.cache_data(ttl=3600)
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

    /* TEXT COLORS — two-tone: dark headings, slate content */
    h1, h2, h3, h4, h5, h6 { color: #0F172A !important; font-family: 'Outfit', sans-serif !important; }
    .stMarkdown p, .stMarkdown span, .stMarkdown li { color: #334155 !important; }
    label, .stSelectbox label, .stMultiSelect label,
    .stSlider label, .stDateInput label, .stTextInput label { color: #1E293B !important; font-weight: 600 !important; }
    [data-testid="stMetricValue"] { color: #0F172A !important; font-weight: 700 !important; }
    [data-testid="stMetricLabel"] { color: #475569 !important; }
    [data-testid="stMetricDelta"] { font-weight: 600 !important; }
    .stCaption p { color: #64748B !important; }
    .stDataFrame th { color: #1E293B !important; }

    /* SUPER HEADINGS */
    .super-heading {
        border-left: 4px solid #6366F1;
        padding-left: 15px;
        margin: 20px 0 10px 0;
        background: linear-gradient(90deg, #F1F5F9 0%, rgba(241, 245, 249, 0) 100%);
        border-radius: 4px;
    }

    /* DYNAMIC METRIC CARDS */
    .perf-card {
        padding: 20px;
        border-radius: 14px;
        border: 1px solid #E2E8F0;
        text-align: center;
        transition: all 0.3s ease;
    }
    .perf-card-pos { background-color: #F0FDF4; border-color: #BBF7D0; }
    .perf-card-neg { background-color: #FEF2F2; border-color: #FECACA; }
    
    .perf-value { font-size: 1.8rem; font-weight: 700; font-family: 'Outfit'; margin: 5px 0; }
    .perf-label { font-size: 0.85rem; color: #64748B; font-weight: 600; text-transform: uppercase; }
    
    .perf-pill {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 700;
    }
    .perf-pill-pos { background-color: #DCFCE7; color: #166534; }
    .perf-pill-neg { background-color: #FEE2E2; color: #991B1B; }

    /* VIBRANT & HIGH-CONTRAST COMPONENTS */
    .vibrant-card {
        background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
        color: #F8FAFC !important;
        padding: 25px;
        border-radius: 20px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.2);
        transition: all 0.3s ease;
    }
    .vibrant-card:hover { transform: translateY(-5px); border-color: #3B82F6; }
    .vibrant-card h4 { color: #3B82F6 !important; margin-bottom: 10px; }
    .vibrant-card p { color: #CBD5E1 !important; }

    .feature-pill {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 700;
        text-transform: uppercase;
        margin-bottom: 10px;
    }
    .pill-input { background-color: #DBEAFE; color: #1E40AF; border: 1px solid #3B82F6; }
    .pill-output { background-color: #DCFCE7; color: #166534; border: 1px solid #10B981; }
    .pill-filter { background-color: #FEF3C7; color: #92400E; border: 1px solid #F59E0B; }

    .target-user-card {
        background: linear-gradient(135deg, #FF0000 0%, #991B1B 100%);
        color: white !important;
        padding: 30px;
        border-radius: 24px;
        text-align: center;
        box-shadow: 0 10px 15px -3px rgba(255, 0, 0, 0.3);
    }
    .target-user-card h3 { color: white !important; }
    .target-user-card p { color: rgba(255, 255, 255, 0.9) !important; }

    .glow-text {
        text-shadow: 0 0 10px rgba(59, 130, 246, 0.5);
        color: #3B82F6 !important;
        font-weight: 700;
    }
    
    .faq-card {
        background: white;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #E2E8F0;
        margin-bottom: 15px;
        transition: border-color 0.3s ease;
    }
    .faq-card:hover { border-color: #EF4444; }

    .module-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 16px;
        padding: 20px;
        height: 100%;
        transition: all 0.3s ease;
    }
    .module-card:hover { border-color: #6366F1; background: #F8FAFC; transform: scale(1.02); }

    /* RED AESTHETIC EVOLUTION */
    .red-hero-card {
        background: linear-gradient(135deg, #FF0000 0%, #8B0000 100%);
        color: white !important;
        padding: 40px;
        border-radius: 28px;
        text-align: center;
        box-shadow: 0 20px 40px -10px rgba(255, 0, 0, 0.4);
        border: 2px solid rgba(255, 255, 255, 0.2);
        margin-bottom: 40px;
    }
    .red-hero-card h1 { color: white !important; font-weight: 800; letter-spacing: -1px; }
    .red-hero-card p { color: rgba(255, 255, 255, 0.9) !important; font-size: 1.2rem; }

    .creative-red-card {
        background: #FFFFFF;
        border: 1px solid #FECACA;
        border-top: 5px solid #EF4444;
        border-radius: 20px;
        padding: 25px;
        height: 100%;
        transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    }
    .creative-red-card:hover {
        transform: translateY(-10px);
        box-shadow: 0 20px 25px -5px rgba(239, 68, 68, 0.1), 0 10px 10px -5px rgba(239, 68, 68, 0.04);
        border-color: #EF4444;
    }
    .creative-red-card h4 { color: #991B1B !important; }
    
    .pill-red { background-color: #FEE2E2; color: #991B1B; border: 1px solid #FCA5A5; }
</style>
""", unsafe_allow_html=True)

# --- NAVIGATION STATE ---
if 'page' not in st.session_state: st.session_state['page'] = 'dash'
if 'active_channel_id' not in st.session_state: st.session_state['active_channel_id'] = None

# --- SEARCH & FILTER PERSISTENCE (Task 14) ---
if 'sf_query'    not in st.session_state: st.session_state['sf_query']    = ''
if 'sf_view_min' not in st.session_state: st.session_state['sf_view_min'] = 0
if 'sf_view_max' not in st.session_state: st.session_state['sf_view_max'] = 10_000_000
if 'sf_date_from' not in st.session_state: st.session_state['sf_date_from'] = None
if 'sf_date_to'   not in st.session_state: st.session_state['sf_date_to']   = None
if 'sf_eng'       not in st.session_state: st.session_state['sf_eng']       = ['High','Medium','Low']
if 'sf_dur'       not in st.session_state: st.session_state['sf_dur']       = ['Short (<5m)','Medium (5-15m)','Long (>15m)']
if 'sf_sort'      not in st.session_state: st.session_state['sf_sort']      = 'Views (High → Low)'
if 'sf_page'      not in st.session_state: st.session_state['sf_page']      = 0

# --- GLOBAL FILTER PERSISTENCE (Milestone 7) ---
# Visuals Page
if 'v_metric'   not in st.session_state: st.session_state['v_metric']    = 'Views'
if 'v_years'    not in st.session_state: st.session_state['v_years']     = []
if 'v_types'    not in st.session_state: st.session_state['v_types']     = ["Long-form", "Shorts"]
if 'v_days'     not in st.session_state: st.session_state['v_days']      = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
if 'v_period'   not in st.session_state: st.session_state['v_period']    = "All Time"

# Battle Page
if 'b_selected' not in st.session_state: st.session_state['b_selected']  = []

# Compare Page
if 'c_bench_ch' not in st.session_state: st.session_state['c_bench_ch']  = None
if 'c_trend_ch' not in st.session_state: st.session_state['c_trend_ch']  = []
if 'c_trend_m'  not in st.session_state: st.session_state['c_trend_m']   = 'Views'
if 'c_trend_t'  not in st.session_state: st.session_state['c_trend_t']   = 'Grouped Bar'
if 'c_rank_by'  not in st.session_state: st.session_state['c_rank_by']   = 'Subscribers'

# --- SIDEBAR ---
with st.sidebar:
    st.markdown("<h2 style='margin-top:0;'>⚙️ Controls</h2>", unsafe_allow_html=True)
    channel_id_input = st.text_input("Channel ID", placeholder="UC_x5XG1OV2P6uZZ5FSM9Ttw")
    fetch_button = st.button("🚀 Run Analysis", type="primary", use_container_width=True)
    
    # NEW PRIMARY BUTTON: Recently Analyzed Channels
    recent_hub_btn = st.button("🏘️ Recently Analyzed Channels", use_container_width=True, help="Explore all synced channels in a gallery view")
    
    if recent_hub_btn:
        st.session_state['page'] = 'recent'
        st.rerun()

    st.divider()
    
    st.markdown("### 🗺️ Navigation")
    # Group navigation for a cleaner look
    nav_about = st.button("ℹ️ **About Hub**", use_container_width=True, help="Learn about the technical architecture and features")
    st.markdown("<div style='margin-bottom: -10px;'></div>", unsafe_allow_html=True)
    
    nav_dash = st.button("📊 **Dash**", use_container_width=True)
    nav_prof = st.button("🏆 **Profile**", use_container_width=True)
    nav_batt = st.button("⚖️ **Battle Arena**", use_container_width=True)
    nav_vis  = st.button("📈 **Visuals**", use_container_width=True)
    nav_srch = st.button("🔍 **Search**", use_container_width=True)
    nav_comp = st.button("📊 **Compare**", use_container_width=True)
    
    st.markdown("<div style='margin-top: -10px;'></div>", unsafe_allow_html=True)
    nav_help = st.button("❓ **Help & FAQ**", use_container_width=True, help="Support center and documentation")

    if nav_about: 
        st.session_state['page'] = 'about'
        st.rerun()
    if nav_dash: st.session_state['page'] = 'dash'
    if nav_prof: st.session_state['page'] = 'profile'
    if nav_batt: st.session_state['page'] = 'battle'
    if nav_vis:  st.session_state['page'] = 'vis'
    if nav_srch: st.session_state['page'] = 'search'
    if nav_comp: st.session_state['page'] = 'compare'
    if nav_help:
        st.session_state['page'] = 'help'
        st.rerun()
    
    # ══════════════════════════════════════════════════════
    # DYNAMIC PAGE FILTERS (Milestone 7)
    # ══════════════════════════════════════════════════════
    cur_page = st.session_state['page']
    if cur_page in ['vis', 'search', 'battle', 'compare']:
        st.divider()
        st.markdown(f"""
            <div style='background-color: #F1F5F9; padding: 12px; border-radius: 8px; border-left: 4px solid #FF0000; margin-bottom: 20px;'>
                <p style='margin:0; font-family:Outfit; font-weight:700; color:#1E293B; font-size:1.1rem;'>🎯 Please Filter Here:</p>
            </div>
        """, unsafe_allow_html=True)
        
        # ─── VISUALS PAGE FILTERS ───
        if cur_page == 'vis':
            # Data needed for dynamic years
            chid = st.session_state['active_channel_id']
            if chid:
                df_sb = get_channel_data_from_db(chid)
                if not df_sb.empty:
                    df_sb['published_at_dt'] = pd.to_datetime(df_sb['published_at'])
                    df_sb['year'] = df_sb['published_at_dt'].dt.year
                    
                    years_opt = sorted(df_sb['year'].unique(), reverse=True)
                    if not st.session_state['v_years']: st.session_state['v_years'] = years_opt

                    metric_opt = {"Views": "view_count", "Likes": "like_count", "Comments": "comment_count", "Quality %": "engagement_rate"}
                    st.selectbox("🧪 Primary Metric", list(metric_opt.keys()), key='v_metric')
                    
                    st.multiselect("📅 Select Years", years_opt, key='v_years')
                    st.multiselect("⏱️ Video Type", ["Long-form", "Shorts"], key='v_types')
                    
                    days_list = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                    st.multiselect("🗓️ Days of the Week", days_list, key='v_days')
                    
                    time_periods = ["All Time", "Last 30 Days", "Last 6 Months", "Last 1 Year"]
                    st.selectbox("📅 Time Scope", time_periods, key='v_period')
                    
                    st.divider()
                    if st.button("📊 Download Full Visuals Report", use_container_width=True, type="primary"):
                        try:
                            df_pdf = get_channel_data_from_db(chid)
                            if not df_pdf.empty:
                                df_pdf['published_at_dt'] = pd.to_datetime(df_pdf['published_at'])
                                df_pdf['year'] = df_pdf['published_at_dt'].dt.year
                                df_pdf['is_short'] = df_pdf.apply(lambda r: 'Shorts' if parse_duration(r['duration']) <= 100 or '#shorts' in str(r['title']).lower() else 'Long-form', axis=1)
                                df_pdf['day_name'] = df_pdf['published_at_dt'].dt.day_name()
                                f_pdf = df_pdf[
                                    (df_pdf['year'].isin(st.session_state['v_years'])) & 
                                    (df_pdf['is_short'].isin(st.session_state['v_types'])) & 
                                    (df_pdf['day_name'].isin(st.session_state['v_days']))
                                ].copy()
                                
                                metric_opt = {"Views": "view_count", "Likes": "like_count", "Comments": "comment_count", "Quality %": "engagement_rate"}
                                sel_metric_label = st.session_state['v_metric']
                                sel_metric = metric_opt[sel_metric_label]

                                if not f_pdf.empty:
                                    if sel_metric == 'engagement_rate':
                                        f_pdf['engagement_rate'] = ((f_pdf['like_count'] + f_pdf['comment_count']) / f_pdf['view_count'].replace(0,1)) * 100
                                        
                                    from fpdf import FPDF
                                    pdf = FPDF(); pdf.add_page(); pdf.set_auto_page_break(auto=True, margin=15)
                                    
                                    # Pro Header
                                    pdf.set_fill_color(30, 41, 59); pdf.rect(0, 0, 210, 24, 'F')
                                    pdf.set_font('Helvetica', 'B', 15); pdf.set_text_color(255, 255, 255)
                                    pdf.set_y(6); pdf.cell(0, 10, 'VISUAL INTELLIGENCE: PERFORMANCE REPORT', align='C', ln=True); pdf.ln(12)
                                    
                                    pdf.set_font('Helvetica', 'B', 12); pdf.set_text_color(71, 85, 105)
                                    pdf.cell(0, 10, f"Channel: {df_pdf.iloc[0]['channel_name']} | Metric: {sel_metric_label} | Videos: {len(f_pdf)}", ln=True); pdf.ln(5)

                                    # 1. Growth Trends
                                    pdf.set_font('Helvetica', 'B', 11); pdf.set_text_color(30, 41, 59)
                                    pdf.cell(0, 8, f"1. Monthly {sel_metric_label} Velocity", ln=True)
                                    f_pdf['ym'] = f_pdf['published_at_dt'].dt.to_period('M')
                                    trend_pdf = f_pdf.groupby('ym')[sel_metric].sum().reset_index()
                                    trend_pdf['ym_str'] = trend_pdf['ym'].astype(str)
                                    
                                    plt.figure(figsize=(10, 3.5))
                                    plt.plot(trend_pdf['ym_str'], trend_pdf[sel_metric], marker='o', color='#3B82F6', linewidth=2)
                                    plt.fill_between(trend_pdf['ym_str'], trend_pdf[sel_metric], color='#3B82F6', alpha=0.1)
                                    plt.title(f"Macro Growth Trend ({sel_metric_label})"); plt.xticks(rotation=45)
                                    plt.grid(alpha=0.3); plt.tight_layout(); plt.savefig("pdf_v_trend.png"); plt.close()
                                    pdf.image("pdf_v_trend.png", x=10, w=190); os.remove("pdf_v_trend.png"); pdf.ln(2)

                                    # 2. Topic & Stability (Side by Side)
                                    pdf.set_font('Helvetica', 'B', 11); pdf.cell(0, 8, "2. Content Strategy & Topic Impact", ln=True)
                                    
                                    # Keyword extraction
                                    stops = {'the','to','in','for','of','and','with','on','how','is','it','at','this','that','you','my','from'}
                                    words = " ".join(f_pdf['title'].str.lower()).split()
                                    kws = [w for w in words if len(w) > 3 and w not in stops]
                                    top_kw = pd.Series(kws).value_counts().head(5).index.tolist()
                                    
                                    kw_data = []
                                    for kw in top_kw:
                                        avg_m = f_pdf[f_pdf['title'].str.contains(kw, case=False, regex=False)][sel_metric].mean()
                                        kw_data.append({'kw': kw.capitalize(), 'val': avg_m})
                                    kw_df = pd.DataFrame(kw_data).sort_values('val', ascending=True)

                                    # Day of week impact
                                    d_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                                    day_df = f_pdf.groupby('day_name')[sel_metric].mean().reindex(d_order).fillna(0).reset_index()

                                    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
                                    # Topic Bar
                                    if not kw_df.empty:
                                        ax1.barh(kw_df['kw'], kw_df['val'], color='#10B981')
                                    ax1.set_title(f"Top Keywords (Avg {sel_metric_label})"); ax1.grid(axis='x', alpha=0.3)
                                    # Day Bar
                                    ax2.bar(day_df['day_name'].str[:3], day_df[sel_metric], color='#F59E0B')
                                    ax2.set_title(f"Best Days (Avg {sel_metric_label})"); ax2.grid(axis='y', alpha=0.3)
                                    
                                    plt.tight_layout(); plt.savefig("pdf_v_strat.png"); plt.close()
                                    pdf.image("pdf_v_strat.png", x=10, w=190); os.remove("pdf_v_strat.png"); pdf.ln(5)

                                    # 3. AI Insights & Stability
                                    v_avg = f_pdf[sel_metric].mean(); v_std = f_pdf[sel_metric].std()
                                    cv = (v_std / v_avg) if v_avg > 0 else 0
                                    stab_score = round(max(5, 100 / (1 + cv)), 1) if len(f_pdf)>1 else 100.0
                                    
                                    pdf.set_font('Helvetica', 'B', 11); pdf.cell(0, 10, "3. System Insights & Stability", ln=True)
                                    pdf.set_font('Helvetica', '', 10); pdf.set_text_color(51, 65, 85)
                                    
                                    best_day = day_df.loc[day_df[sel_metric].idxmax(), 'day_name'] if not day_df.empty else 'N/A'
                                    best_top = kw_df.iloc[-1]['kw'] if not kw_df.empty else 'N/A'
                                    
                                    insights = (
                                        f"- PERFORMANCE VOLATILITY: Your channel stability score is {stab_score}/100. "
                                        f"{'This indicates highly consistent performance.' if stab_score > 60 else 'This indicates high variance (hit-driven performance).'}\n"
                                        f"- TIMING ADVANTAGE: {best_day} yields the highest average {sel_metric_label.lower()} for this segment.\n"
                                        f"- TOPIC HOOK: Videos containing the word '{best_top}' dramatically overperform the channel average."
                                    )
                                    pdf.multi_cell(0, 7, insights)

                                    st.download_button("📩 Download Premium Visual Intelligence Report", bytes(pdf.output()), "visual_intelligence_report.pdf", "application/pdf", use_container_width=True)
                        except Exception as e: st.error(f"PDF Error: {e}")


        # ─── SEARCH PAGE FILTERS ───
        elif cur_page == 'search':
            st.text_input("🔎 Search Keyword", value=st.session_state['sf_query'], key='_sf_q_input')
            
            max_views_in_data = 10_000_000 # Default/Fallback
            st.slider(
                "👁️ View Count Range", 0, max_views_in_data,
                (st.session_state['sf_view_min'], st.session_state['sf_view_max']),
                key='_sf_view_slider'
            )
            
            from datetime import date as dt_date
            st.date_input(
                "📅 Date Range",
                value=(st.session_state['sf_date_from'] or dt_date(2005, 1, 1), 
                       st.session_state['sf_date_to'] or dt_date.today()),
                key='_sf_date_input'
            )
            
            st.multiselect("💎 Engagement", ['High', 'Medium', 'Low'], default=st.session_state['sf_eng'], key='_sf_eng_sel')
            st.multiselect("⏱️ Duration", ['Short (<5m)', 'Medium (5-15m)', 'Long (>15m)'], default=st.session_state['sf_dur'], key='_sf_dur_sel')
            
            sort_options = ['Views (High → Low)', 'Views (Low → High)', 'Likes (High → Low)',
                            'Date (Newest)', 'Date (Oldest)', 'Engagement (High → Low)',
                            'Duration (Longest)', 'Comments (High → Low)']
            st.selectbox("🔀 Sort By", sort_options, 
                         index=sort_options.index(st.session_state['sf_sort']) if st.session_state['sf_sort'] in sort_options else 0,
                         key='_sf_sort_sel')
            
            sc1, sc2 = st.columns(2)
            apply_btn = sc1.button("✅ Apply", type="primary", use_container_width=True)
            clear_btn = sc2.button("🧹 Clear", use_container_width=True)
            
            if clear_btn:
                st.session_state['sf_query'] = ''
                st.session_state['sf_view_min'] = 0
                st.session_state['sf_view_max'] = 10_000_000
                st.session_state['sf_date_from'] = None
                st.session_state['sf_date_to'] = None
                st.session_state['sf_eng'] = ['High', 'Medium', 'Low']
                st.session_state['sf_dur'] = ['Short (<5m)', 'Medium (5-15m)', 'Long (>15m)']
                st.session_state['sf_sort'] = 'Views (High → Low)'
                st.session_state['sf_page'] = 0
                st.rerun()
            
            if apply_btn:
                st.session_state['sf_query'] = st.session_state['_sf_q_input']
                st.session_state['sf_view_min'] = st.session_state['_sf_view_slider'][0]
                st.session_state['sf_view_max'] = st.session_state['_sf_view_slider'][1]
                dr = st.session_state['_sf_date_input']
                if isinstance(dr, (list, tuple)) and len(dr) == 2:
                    st.session_state['sf_date_from'], st.session_state['sf_date_to'] = dr
                st.session_state['sf_eng'] = st.session_state['_sf_eng_sel']
                st.session_state['sf_dur'] = st.session_state['_sf_dur_sel']
                st.session_state['sf_sort'] = st.session_state['_sf_sort_sel']
                st.session_state['sf_page'] = 0
                st.rerun()
            
            st.divider()
            if st.button("📊 Download Full Search Report", use_container_width=True, type="primary"):
                try:
                    chid = st.session_state['active_channel_id']
                    df_pdf = get_channel_data_from_db(chid)
                    if not df_pdf.empty:
                        # Apply exact same filtering as main page for consistency
                        pdf_f = df_pdf.copy()
                        pdf_f['published_at_dt'] = pd.to_datetime(pdf_f['published_at'])
                        if st.session_state['sf_query'].strip():
                            pdf_f = pdf_f[pdf_f['title'].str.lower().str.contains(st.session_state['sf_query'].lower())]
                        
                        pdf_f = pdf_f[(pdf_f['view_count'] >= st.session_state['sf_view_min']) &
                                      (pdf_f['view_count'] <= st.session_state['sf_view_max'])]

                        if st.session_state['sf_date_from'] and st.session_state['sf_date_to']:
                            pdf_f = pdf_f[(pdf_f['published_at_dt'].dt.date >= st.session_state['sf_date_from']) &
                                          (pdf_f['published_at_dt'].dt.date <= st.session_state['sf_date_to'])]
                        
                        def safe_text(val):
                            if pd.isna(val): return ""
                            s = str(val).replace('—', '-').replace('–', '-').replace('…', '...')
                            return s.encode('latin-1', 'replace').decode('latin-1')

                        from fpdf import FPDF
                        pdf = FPDF(); pdf.add_page(); pdf.set_auto_page_break(auto=True, margin=15)
                        
                        # Header
                        pdf.set_fill_color(30, 41, 59); pdf.rect(0, 0, 210, 24, 'F')
                        pdf.set_font('Helvetica', 'B', 15); pdf.set_text_color(255, 255, 255)
                        pdf.set_y(6); pdf.cell(0, 10, 'VIDEO SEARCH & ANALYSIS REPORT', align='C', ln=True); pdf.ln(12)
                        
                        pdf.set_font('Helvetica', 'B', 12); pdf.set_text_color(71, 85, 105)
                        pdf.cell(0, 8, f"Channel: {safe_text(df_pdf.iloc[0]['channel_name'])}", ln=True)
                        pdf.cell(0, 8, f"Search Query: '{safe_text(st.session_state.get('sf_query', ''))}' | Matches: {len(pdf_f)}", ln=True)
                        pdf.ln(5)
                        
                        if not pdf_f.empty:
                            # 1. Performance Scatter Chart (Views vs Likes)
                            pdf.set_font('Helvetica', 'B', 11); pdf.set_text_color(30, 41, 59)
                            pdf.cell(0, 8, "1. Engagement vs Reach Scatter", ln=True)
                            
                            plt.figure(figsize=(10, 4))
                            plt.scatter(pdf_f['view_count'], pdf_f['like_count'], color='#6366F1', alpha=0.6, edgecolors='white', s=80)
                            plt.title("Likes vs Views for Matching Videos")
                            plt.xlabel("Total Views"); plt.ylabel("Total Likes")
                            plt.grid(alpha=0.3); plt.tight_layout()
                            plt.savefig("temp_s_scatter.png"); plt.close()
                            pdf.image("temp_s_scatter.png", x=10, w=190); os.remove("temp_s_scatter.png"); pdf.ln(5)
                            
                            # 2. Result Table (Top 10)
                            pdf.set_font('Helvetica', 'B', 11); pdf.cell(0, 8, "2. Top Matching Videos (by Views)", ln=True)
                            pdf.set_font('Helvetica', 'B', 8); pdf.set_fill_color(241, 245, 249)
                            pdf.cell(110, 8, "Video Title", 1, 0, 'C', True)
                            pdf.cell(30, 8, "Views", 1, 0, 'C', True)
                            pdf.cell(25, 8, "Likes", 1, 0, 'C', True)
                            pdf.cell(25, 8, "Comments", 1, 1, 'C', True)
                            
                            pdf.set_font('Helvetica', '', 8)
                            top_v = pdf_f.sort_values('view_count', ascending=False).head(10)
                            for _, r in top_v.iterrows():
                                safe_title = safe_text(r['title'])[:60]
                                pdf.cell(110, 7, safe_title, 1)
                                pdf.cell(30, 7, f"{int(r['view_count']):,}", 1, 0, 'R')
                                pdf.cell(25, 7, f"{int(r['like_count']):,}", 1, 0, 'R')
                                pdf.cell(25, 7, f"{int(r['comment_count']):,}", 1, 1, 'R')
                            pdf.ln(5)
                            
                            # 3. Insights
                            pdf.set_font('Helvetica', 'B', 11); pdf.cell(0, 8, "3. Search Insights", ln=True)
                            pdf.set_font('Helvetica', '', 10); pdf.set_text_color(51, 65, 85)
                            avg_v = pdf_f['view_count'].mean()
                            tot_v = pdf_f['view_count'].sum()
                            top_hit_title = safe_text(top_v.iloc[0]['title'])
                            insight_str = (
                                f"- TOTAL REACH: These {len(pdf_f)} matching videos have accumulated {int(tot_v):,} total views.\n"
                                f"- AVERAGE PERFORMANCE: The average video in this subset has {int(avg_v):,} views.\n"
                                f"- TOP HIT: The highest performing matched video is '{top_hit_title}' with {int(top_v.iloc[0]['view_count']):,} views."
                            )
                            pdf.multi_cell(0, 7, insight_str)
                            
                        st.download_button("📩 Download Premium Search Report", bytes(pdf.output()), "search_analysis_report.pdf", "application/pdf", use_container_width=True)
                except Exception as e: st.error(f"PDF Error: {e}")
            
            # CSV Export also in sidebar
            if st.button("📊 Download Results CSV", use_container_width=True):
                try:
                    df_csv = get_channel_data_from_db(st.session_state['active_channel_id'])
                    if not df_csv.empty:
                        csv_data = df_csv.to_csv(index=False).encode('utf-8')
                        st.download_button("📥 Save CSV File", csv_data, "video_results.csv", "text/csv", use_container_width=True)
                except: st.error("CSV Export failed")

        # ─── BATTLE PAGE FILTERS ───
        elif cur_page == 'battle':
            recent_ch = get_recent_channels(limit=50)
            if recent_ch:
                ch_names = [r['name'] for r in recent_ch]
                st.multiselect("🤜 Select Rivals", ch_names, 
                               key='b_selected',
                               max_selections=6)
                
                st.divider()
                if st.button("⚔️ Download Full Battle Report", use_container_width=True, type="primary"):
                    try:
                        if st.session_state['b_selected']:
                            from fpdf import FPDF
                            id_str = "', '".join([r.replace("'", "''") for r in st.session_state['b_selected']])
                            q_ch = f"SELECT channel_name, subscribers, views, total_videos FROM channels WHERE channel_name IN ('{id_str}')"
                            q_vids = f"SELECT c.channel_name, s.view_count, s.like_count, s.comment_count FROM videos v JOIN channels c ON v.channel_id = c.channel_id JOIN video_statistics s ON v.video_id = s.video_id WHERE v.channel_id IN (SELECT channel_id FROM channels WHERE channel_name IN ('{id_str}')) AND s.captured_at = (SELECT MAX(s2.captured_at) FROM video_statistics s2 WHERE s2.video_id = v.video_id)"
                            with engine.connect() as conn:
                                cdf_p = pd.read_sql(text(q_ch), conn)
                                v_df_p = pd.read_sql(text(q_vids), conn)

                            if not cdf_p.empty:
                                pdf = FPDF(); pdf.add_page(); pdf.set_auto_page_break(auto=True, margin=15)
                                # Professional Header
                                pdf.set_fill_color(30, 41, 59); pdf.rect(0, 0, 210, 24, 'F')
                                pdf.set_font('Helvetica', 'B', 15); pdf.set_text_color(255, 255, 255)
                                pdf.set_y(6); pdf.cell(0, 10, 'BATTTLE ARENA: COMPREHENSIVE PERFORMANCE REPORT', align='C', ln=True); pdf.ln(12)
                                pdf.set_font('Helvetica', 'B', 12); pdf.set_text_color(71, 85, 105)
                                pdf.cell(0, 10, f"Benchmark set: {', '.join(cdf_p['channel_name'])}", ln=True); pdf.ln(5)

                                # 1. Audience & Reach
                                pdf.set_font('Helvetica', 'B', 11); pdf.set_text_color(30, 41, 59)
                                pdf.cell(0, 8, "1. Audience & Global Reach Battle", ln=True); pdf.ln(2)
                                fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
                                ax1.bar(cdf_p['channel_name'], cdf_p['subscribers'], color='#3B82F6'); ax1.set_title("Subscribers (Log)"); ax1.set_yscale('log')
                                ax2.bar(cdf_p['channel_name'], cdf_p['views'], color='#EF4444'); ax2.set_title("Total Views (Log)"); ax2.set_yscale('log')
                                plt.tight_layout(); plt.savefig("pdf_b_ar.png"); plt.close()
                                pdf.image("pdf_b_ar.png", x=10, w=190); os.remove("pdf_b_ar.png"); pdf.ln(5)

                                # 2. Engagement Matrix
                                if not v_df_p.empty:
                                    pdf.set_font('Helvetica', 'B', 11); pdf.cell(0, 8, "2. Engagement Quality Matrix", ln=True)
                                    ch_agg_p = v_df_p.groupby('channel_name')[['view_count', 'like_count', 'comment_count']].sum().reset_index()
                                    ch_agg_p['quality'] = (ch_agg_p['like_count'] + ch_agg_p['comment_count']) / ch_agg_p['view_count'].replace(0,1) * 100
                                    plt.figure(figsize=(10, 5))
                                    plt.scatter(ch_agg_p['view_count'], ch_agg_p['quality'], s=300, color='#10B981', alpha=0.6)
                                    for i, r in ch_agg_p.iterrows(): plt.annotate(r['channel_name'], (r['view_count'], r['quality']), xytext=(5,5), textcoords='offset points')
                                    plt.title("Reach vs Quality Benchmark"); plt.xlabel("Total Views"); plt.ylabel("Quality Score %"); plt.grid(alpha=0.3)
                                    plt.tight_layout(); plt.savefig("pdf_b_eng_full.png"); plt.close()
                                    pdf.image("pdf_b_eng_full.png", x=10, w=190); os.remove("pdf_b_eng_full.png"); pdf.ln(5)

                                # 3. Capabilities Comparison
                                pdf.add_page(); pdf.set_font('Helvetica', 'B', 11); pdf.cell(0, 8, "3. Multichannel Capabilities Analysis", ln=True)
                                cdf_p['views_n'] = cdf_p['views'] / cdf_p['views'].max()
                                cdf_p['subs_n'] = cdf_p['subscribers'] / cdf_p['subscribers'].max()
                                cdf_p['vids_n'] = cdf_p['total_videos'] / cdf_p['total_videos'].max()
                                pdf_cap = cdf_p.set_index('channel_name')[['views_n','subs_n','vids_n']]
                                pdf_cap.plot(kind='bar', figsize=(10, 5), width=0.8, color=['#6366F1', '#EC4899', '#8B5CF6'])
                                plt.title("Normalized Strategy Profiles (Reach vs Output)"); plt.legend(["Views", "Subs", "Videos"]); plt.grid(axis='y', alpha=0.3)
                                plt.tight_layout(); plt.savefig("pdf_b_cap.png"); plt.close()
                                pdf.image("pdf_b_cap.png", x=10, w=190); os.remove("pdf_b_cap.png"); pdf.ln(5)

                                # 4. Metrics Table
                                pdf.set_font('Helvetica', 'B', 11); pdf.cell(0, 10, "4. Competitive Metrics Summary", ln=True)
                                pdf.set_font('Helvetica', 'B', 8); pdf.set_fill_color(241, 245, 249)
                                pdf.cell(70, 8, "Channel", 1, 0, 'C', True); pdf.cell(40, 8, "Subscribers", 1, 0, 'C', True)
                                pdf.cell(40, 8, "Total Views", 1, 0, 'C', True); pdf.cell(40, 8, "Quality %", 1, 1, 'C', True)
                                pdf.set_font('Helvetica', '', 8)
                                for _, r in cdf_p.iterrows():
                                    q_val = ch_agg_p[ch_agg_p['channel_name']==r['channel_name']]['quality'].values[0] if not v_df_p.empty else 0
                                    pdf.cell(70, 7, str(r['channel_name']), 1)
                                    pdf.cell(40, 7, f"{int(r['subscribers']):,}", 1, 0, 'R')
                                    pdf.cell(40, 7, f"{int(r['views']):,}", 1, 0, 'R')
                                    pdf.cell(40, 7, f"{q_val:.2f}%", 1, 1, 'R')

                                # 5. AI STRATEGY INSIGHTS
                                pdf.ln(5); pdf.set_font('Helvetica', 'B', 11); pdf.cell(0, 10, "5. Data-Driven Strategic Insights", ln=True)
                                pdf.set_font('Helvetica', '', 10); pdf.set_text_color(51, 65, 85)
                                leader = cdf_p.loc[cdf_p['views'].idxmax()]['channel_name']
                                q_leader = ch_agg_p.loc[ch_agg_p['quality'].idxmax()]['channel_name'] if not v_df_p.empty else "N/A"
                                pdf.multi_cell(0, 7, f"- SCALE LEADER: {leader} shows overwhelming reach dominance in the current set.\n- QUALITY CHAMPION: {q_leader} maintains the highest engagement-to-view ratio, indicating superior audience retention.\n- STRATEGIC GAP: High output (video volume) does not always correlate with high quality scores. Channels should focus on content depth over frequency.")

                                st.download_button("📩 Download Premium Battle Report", bytes(pdf.output()), "battle_arena_full_report.pdf", "application/pdf", use_container_width=True)
                    except Exception as e: st.error(f"PDF Error: {e}")

        # ─── COMPARE PAGE FILTERS ───
        elif cur_page == 'compare':
            recent_ch = get_recent_channels(limit=50)
            if recent_ch:
                ch_names = [r['name'] for r in recent_ch]
                st.selectbox("🎯 Benchmark Channel", ch_names, key='c_bench_ch')
                
                st.multiselect("📺 Compare Trends", ch_names, key='c_trend_ch')
                
                trend_metric_opts = {'Views': 'view_count', 'Likes': 'like_count', 'Comments': 'comment_count'}
                st.selectbox("📊 Trend Metric", list(trend_metric_opts.keys()), key='c_trend_m')
                
                chart_types = ['Grouped Bar', 'Line + Markers', 'Area']
                st.selectbox("📉 Chart Style", chart_types, key='c_trend_t')
                
                st.divider()
                st.markdown("<p style='font-family:Outfit; font-weight:700; color:#1E293B;'>🏆 Leaderboard Sort</p>", unsafe_allow_html=True)
                lb_sort_opts = ['Subscribers', 'Total Views', 'Engagement %', 'Total Videos']
                st.selectbox("🔀 Rank By", lb_sort_opts, key='c_rank_by')

                st.divider()
                if st.button("📈 Download Full Compare Report", use_container_width=True, type="primary"):
                    try:
                        bench_ch = st.session_state.get('c_bench_ch')
                        rivals = st.session_state.get('c_trend_ch', [])
                        if not bench_ch:
                            st.error("Please select a Benchmark Channel first.")
                        else:
                            all_channels = [bench_ch] + rivals
                            id_str = "','".join([c.replace("'", "''") for c in all_channels])
                            q_all = f"SELECT channel_name, subscribers, views, total_videos FROM channels WHERE channel_name IN ('{id_str}')"
                            
                            # Get Database Averages for Baseline
                            q_avg = "SELECT AVG(subscribers) as avg_sub, AVG(views) as avg_view, AVG(total_videos) as avg_vid FROM channels"
                            
                            with engine.connect() as conn:
                                cdf = pd.read_sql(text(q_all), conn)
                                db_avg = pd.read_sql(text(q_avg), conn).iloc[0]
                                
                            if not cdf.empty:
                                from fpdf import FPDF
                                pdf = FPDF(); pdf.add_page(); pdf.set_auto_page_break(auto=True, margin=15)
                                
                                # Header
                                pdf.set_fill_color(30, 41, 59); pdf.rect(0, 0, 210, 24, 'F')
                                pdf.set_font('Helvetica', 'B', 15); pdf.set_text_color(255, 255, 255)
                                pdf.set_y(6); pdf.cell(0, 10, 'COMPARATIVE BENCHMARKING REPORT', align='C', ln=True); pdf.ln(12)
                                
                                pdf.set_font('Helvetica', 'B', 12); pdf.set_text_color(71, 85, 105)
                                pdf.cell(0, 8, f"Benchmark Anchor: {bench_ch}", ln=True)
                                if rivals: pdf.cell(0, 8, f"Rivals Analyzed: {', '.join(rivals)}", ln=True)
                                pdf.ln(5)

                                # 1. Benchmark Chart vs Database Average
                                pdf.set_font('Helvetica', 'B', 11); pdf.set_text_color(30, 41, 59)
                                pdf.cell(0, 8, "1. Channel Performance vs Database Average (Ratio)", ln=True)
                                
                                b_row = cdf[cdf['channel_name'] == bench_ch].iloc[0]
                                metrics_l = ['Subscribers', 'Total Views', 'Total Videos']
                                b_vals = [b_row['subscribers'], b_row['views'], b_row['total_videos']]
                                a_vals = [db_avg['avg_sub'], db_avg['avg_view'], db_avg['avg_vid']]
                                
                                ratios = [v/max(a, 0.01) for v, a in zip(b_vals, a_vals)]
                                
                                plt.figure(figsize=(10, 4))
                                plt.bar(metrics_l, ratios, color='#6366F1', width=0.4, label=bench_ch)
                                plt.axhline(1.0, color='#EF4444', linestyle='--', label='Database Avg (1.0x)')
                                plt.title(f"{bench_ch} Benchmark Multipliers"); plt.ylabel("Ratio (1.0 = Average)")
                                plt.grid(axis='y', alpha=0.3); plt.legend()
                                plt.tight_layout(); plt.savefig("pdf_c_bench.png"); plt.close()
                                pdf.image("pdf_c_bench.png", x=10, w=190); os.remove("pdf_c_bench.png"); pdf.ln(5)

                                # 2. Rival Comparison Bar Charts (if rivals selected)
                                if rivals:
                                    pdf.set_font('Helvetica', 'B', 11); pdf.cell(0, 8, "2. Direct Rival Head-to-Head", ln=True)
                                    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
                                    ax1.bar(cdf['channel_name'], cdf['subscribers'], color='#10B981')
                                    ax1.set_title("Subscribers"); ax1.tick_params(axis='x', rotation=45)
                                    ax2.bar(cdf['channel_name'], cdf['views'], color='#3B82F6')
                                    ax2.set_title("Total Views"); ax2.tick_params(axis='x', rotation=45)
                                    plt.tight_layout(); plt.savefig("pdf_c_rivals.png"); plt.close()
                                    pdf.image("pdf_c_rivals.png", x=10, w=190); os.remove("pdf_c_rivals.png"); pdf.ln(5)
                                    
                                # 3. Data Table Summary
                                pdf.set_font('Helvetica', 'B', 11); pdf.cell(0, 8, "Competitive Summary Matrix", ln=True)
                                pdf.set_font('Helvetica', 'B', 9); pdf.set_fill_color(241, 245, 249)
                                pdf.cell(80, 8, "Channel", 1, 0, 'C', True); pdf.cell(40, 8, "Subscribers", 1, 0, 'C', True)
                                pdf.cell(40, 8, "Total Views", 1, 0, 'C', True); pdf.cell(30, 8, "Videos", 1, 1, 'C', True)
                                pdf.set_font('Helvetica', '', 9)
                                
                                table_df = cdf.sort_values('views', ascending=False)
                                for _, r in table_df.iterrows():
                                    pdf.cell(80, 8, r['channel_name'][:35], 1)
                                    pdf.cell(40, 8, f"{int(r['subscribers']):,}", 1, 0, 'R')
                                    pdf.cell(40, 8, f"{int(r['views']):,}", 1, 0, 'R')
                                    pdf.cell(30, 8, f"{int(r['total_videos']):,}", 1, 1, 'R')
                                pdf.ln(5)

                                # 4. Strategic Assessment
                                leader_views = table_df.iloc[0]['channel_name']
                                pdf.set_font('Helvetica', 'B', 11); pdf.cell(0, 8, "Strategic Assessment", ln=True)
                                pdf.set_font('Helvetica', '', 10); pdf.set_text_color(51, 65, 85)
                                
                                assesstext = f"- BENCHMARK STANDING: {bench_ch} is performing at {ratios[1]:.2f}x the database average for total views and {ratios[0]:.2f}x for subscribers.\n"
                                if rivals: assesstext += f"- DOMINANT FORCE: {leader_views} leads the cohort in absolute reach and audience accumulation."
                                
                                pdf.multi_cell(0, 7, assesstext)

                                st.download_button("📩 Download Premium Compare Report", bytes(pdf.output()), "comparative_analysis.pdf", "application/pdf", use_container_width=True)
                    except Exception as e: st.error(f"PDF Error: {e}")

        # End of filters
    
    # Removed local list in favor of the new Recent Hub page
    pass

# --- MAIN PAGE HEADER ---
if st.session_state['page'] not in ['search', 'compare', 'recent']:
    st.markdown(f"""
        <div style='text-align: center; padding: 10px 0 20px 0;'>
            <h1 class='main-title' style='font-size: 2.5rem; margin-bottom: 0;'>
                <span style='color: #FF0000;'>YouTube</span> Pro Dash
            </h1>
        </div>
    """, unsafe_allow_html=True)
else:
    # Small spacing for pages with no header
    st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)

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

# ═══════════════════════════════════════════════════════════════
# PAGE: RECENT HUB — Premium Gallery View
# ═══════════════════════════════════════════════════════════════
if st.session_state['page'] == 'recent':
    st.markdown("""
        <div style='text-align:center; padding:40px 0 20px 0;'>
            <h1 style='font-family:Outfit; font-weight:700; color:#1E293B; margin-bottom:10px;'>🏘️ Recently Analyzed Channels</h1>
            <p style='color:#64748B; font-size:1.15rem; font-weight:400;'>Choose a workspace from your library to explore real-time insights</p>
        </div>
    """, unsafe_allow_html=True)
    
    # Direct DB Query to ensure all metadata is fetched without caching issues
    q_recent = """
        SELECT channel_name as name, channel_id as id, subscribers, thumbnail_url
        FROM channels
        ORDER BY channel_name ASC
        LIMIT 40
    """
    try:
        with engine.connect() as conn:
            all_ch_df = pd.read_sql(text(q_recent), conn)
            all_ch = all_ch_df.to_dict('records')
    except Exception as e:
        st.error(f"Error loading library: {e}")
        all_ch = []

    if not all_ch:
        st.info("No channels synced yet. Use the 'Channel ID' input and 'Run Analysis' to add your first channel.")
    else:
        # High-density grid
        cols = st.columns(4)
        for i, ch in enumerate(all_ch):
            with cols[i % 4]:
                # Premium Card container with elevated shadow
                thumb = ch.get('thumbnail_url') or "https://via.placeholder.com/100"
                subs = ch.get('subscribers') or 0
                
                st.markdown(f"""
                    <div style='background:white; border-radius:18px; padding:28px 20px; border:2px solid #FF0000; 
                              box-shadow:0 10px 15px -3px rgba(255,0,0,0.1), 0 4px 6px -2px rgba(0,0,0,0.02); 
                              text-align:center; margin-bottom:24px;'>
                        <div style='display:flex; justify-content:center; margin-bottom:18px;'>
                            <div style='width:95px; height:95px; border-radius:50%; overflow:hidden; 
                                        border:4px solid #F8FAFC; box-shadow:0 0 0 1px #E2E8F0; background:#FAFAFA;'>
                                <img src='{thumb}' style='width:100%; height:100%; object-fit:cover;'>
                            </div>
                        </div>
                        <h4 style='margin:0; color:#1E3A8A; font-family:Outfit; font-weight:700; font-size:1.15rem; line-height:1.2; height:2.4em; display:flex; align-items:center; justify-content:center;'>{ch['name']}</h4>
                        <p style='color:#FF0000; font-size:1rem; margin:10px 0 0 0; font-weight:700; font-family:Outfit;'>{fmt_k_m(subs)} Subscribers</p>
                    </div>
                """, unsafe_allow_html=True)
                
                # Primary action for Recent Hub
                if st.button(f"🚀 Dive into Analytics", key=f"hub_load_{ch['id']}", use_container_width=True, type="primary"):
                    st.session_state['active_channel_id'] = ch['id']
                    st.session_state['page'] = 'dash'
                    st.rerun()

# --- PAGE: DASHBOARD ---
elif st.session_state['page'] == 'dash':
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
        # Battle Arena Selection (MIGRATED TO SIDEBAR)
        sel_battle = st.session_state['b_selected']
        
        if len(sel_battle) < 2:
            st.info("👆 Select at least **2 channels** from the sidebar to start the battle.")
        else:
            rivals_str = " vs ".join(sel_battle)
            st.success(f"⚔️ **Battle Matchup:** {rivals_str}")
            # ─── FETCH CHANNEL SUMMARY DATA ───────────────────────────
            ids = [r['id'] for r in recent if r['name'] in sel_battle]
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
            
            # 2. HYPER-REACTIVE FILTERS (MIGRATED TO SIDEBAR)
            metric_opt = {"Views": "view_count", "Likes": "like_count", "Comments": "comment_count", "Quality %": "engagement_rate"}
            sel_metric_label = st.session_state['v_metric']
            sel_metric = metric_opt[sel_metric_label]
            sel_year = st.session_state['v_years']
            sel_duration = st.session_state['v_types']
            sel_days = st.session_state['v_days']
            sel_period = st.session_state['v_period']

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

                # 3. 3-TAB PRO-PLUS SYSTEM
                v_tab1, v_tab2, v_tab3 = st.tabs([
                    "📈 Growth Trends", 
                    "🧠 Topic & Stability", 
                    "💎 Content Fingerprint"
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
                            ("💬 Monthly Comments", "comments", '#F97316', 'rgba(249,115,22,0.15)'),
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

                    st.divider()
                
                    st.divider()
                
                # --- PDF EXPORT MOVED TO SIDEBAR ---

                st.markdown("<p style='text-align:right; font-size:0.9rem; color:#64748B;'>👑 Pro-Plus Visual Intelligence Suite | All charts are interactive.</p>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# PAGE: SEARCH & FILTER — Task 14 (Milestone 3)
# ═══════════════════════════════════════════════════════════════
elif st.session_state['page'] == 'search':
    if not st.session_state['active_channel_id']:
        st.warning("👋 Please select a channel from the sidebar to use Search & Filter.")
    else:
        chid = st.session_state['active_channel_id']
        df_raw = get_channel_data_from_db(chid)

        if df_raw.empty:
            st.error("No data found. Please sync this channel first.")
        else:
            # ── Data prep ──
            df_s = df_raw.drop_duplicates(subset=['video_id']).copy()
            df_s['published_at_dt'] = pd.to_datetime(df_s['published_at'], format='ISO8601')
            df_s['duration_sec'] = df_s['duration'].apply(parse_duration)
            df_s['duration_min'] = (df_s['duration_sec'] / 60).round(1)
            df_s['engagement_rate'] = ((df_s['like_count'] + df_s['comment_count']) / df_s['view_count'].replace(0, np.nan) * 100).fillna(0)
            df_s['video_url'] = "https://www.youtube.com/watch?v=" + df_s['video_id']

            # Improved Shorts detection
            def detect_type(row):
                dur = parse_duration(row['duration'])
                has_tag = '#shorts' in str(row['title']).lower()
                if has_tag or dur <= 100: return 'Shorts'
                return 'Long-form'
            df_s['is_short'] = df_s.apply(detect_type, axis=1)

            # Engagement classification
            def eng_class(val):
                if val >= 5: return 'High'
                elif val >= 2: return 'Medium'
                return 'Low'
            df_s['eng_level'] = df_s['engagement_rate'].apply(eng_class)

            # Duration classification
            def dur_class(mins):
                if mins < 5: return 'Short (<5m)'
                elif mins <= 15: return 'Medium (5-15m)'
                return 'Long (>15m)'
            df_s['dur_level'] = df_s['duration_min'].apply(dur_class)

            total_videos = len(df_s)

            # ── Page Header ──
            c_name = df_s.iloc[0]['channel_name']
            st.markdown(f"""
                <div class='super-heading'>
                    <h2 style='margin:0;'>🔍 Smart Video Search & Filter</h2>
                    <p style='margin:0; color:#64748B;'>Deep-dive into <b>{c_name}</b>'s library of <b>{total_videos}</b> videos</p>
                </div>
            """, unsafe_allow_html=True)

            # ════════════════════════════════════════════════════════
            # 2. SEAMLESS FILTERS (MIGRATED TO SIDEBAR)
            max_views_in_data = int(df_s['view_count'].max()) if not df_s.empty else 10_000_000
            # ════════════════════════════════════════════════════════
            # DATA FILTERING LOGIC
            # ════════════════════════════════════════════════════════
            filt = df_s.copy()
            if st.session_state['sf_query'].strip():
                q = st.session_state['sf_query'].strip().lower()
                filt = filt[filt['title'].str.lower().str.contains(q, na=False)]

            filt = filt[(filt['view_count'] >= st.session_state['sf_view_min']) &
                        (filt['view_count'] <= st.session_state['sf_view_max'])]

            if st.session_state['sf_date_from'] and st.session_state['sf_date_to']:
                filt = filt[(filt['published_at_dt'].dt.date >= st.session_state['sf_date_from']) &
                            (filt['published_at_dt'].dt.date <= st.session_state['sf_date_to'])]

            filt = filt[filt['eng_level'].isin(st.session_state['sf_eng'])]
            filt = filt[filt['dur_level'].isin(st.session_state['sf_dur'])]

            sort_map = {
                'Views (High → Low)':      ('view_count', False),
                'Views (Low → High)':       ('view_count', True),
                'Likes (High → Low)':       ('like_count', False),
                'Date (Newest)':            ('published_at_dt', False),
                'Date (Oldest)':            ('published_at_dt', True),
                'Engagement (High → Low)':  ('engagement_rate', False),
                'Duration (Longest)':       ('duration_sec', False),
                'Comments (High → Low)':    ('comment_count', False),
            }
            s_col, s_asc = sort_map.get(st.session_state['sf_sort'], ('view_count', False))
            filt = filt.sort_values(s_col, ascending=s_asc).reset_index(drop=True)

            n_results = len(filt)

            # ── Summary Stats ──
            st.markdown("---")
            sm1, sm2, sm3, sm4, sm5 = st.columns(5)
            sm1.metric("📹 Results", f"{n_results} / {total_videos}")
            sm2.metric("👁️ Avg Views", fmt_k_m(filt['view_count'].mean()) if n_results else "—")
            sm3.metric("❤️ Avg Likes", fmt_k_m(filt['like_count'].mean()) if n_results else "—")
            sm4.metric("💎 Avg Engagement", f"{filt['engagement_rate'].mean():.2f}%" if n_results else "—")
            sm5.metric("⏱️ Avg Duration", f"{filt['duration_min'].mean():.1f}m" if n_results else "—")

            if n_results == 0:
                st.warning("No videos match your filters. Adjust and click **Apply Filters**.")
            else:
                st.markdown(f"**Showing {n_results} Matching Videos**")
                
                # ── PREMIUM VIEW: CARDS (RESTORED FROM LIBRARY) ──
                for idx, row in filt.head(20).iterrows():
                    with st.container():
                        col1, col2, col3 = st.columns([1, 4, 1])
                        with col1:
                            thumb_url = row.get('v_thumb', "")
                            if thumb_url: st.image(thumb_url, use_column_width=True)
                            else: st.info("No Preview")
                        with col2:
                            st.markdown(f"**{row['title']}**")
                            type_color = "#10B981" if row['is_short'] == 'Long-form' else "#3B82F6"
                            st.markdown(f"<span style='background-color: {type_color}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem;'>{row['is_short']}</span>", unsafe_allow_html=True)
                            st.caption(f"Published: {row['published_at_dt'].strftime('%b %d, %Y')} | Duration: {row['duration']} ({int(parse_duration(row['duration']))}s)")
                            st.write(f"📈 {row['view_count']:,} Views | ❤️ {row['like_count']:,} Likes | 💎 {row['engagement_rate']:.2f}% Quality")
                        with col3:
                            st.markdown("<br>", unsafe_allow_html=True)
                            st.link_button("📺 Watch", row['video_url'])
                        st.divider()

                st.markdown("<div style='height:30px;'></div>", unsafe_allow_html=True)

                st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)
                # --- ALL EXPORTS ARE NOW IN THE SIDEBAR ---

                # ════════════════════════════════════════════════════
                # PAGINATED TABLE
                # ════════════════════════════════════════════════════
                ROWS_PER_PAGE = 20
                total_pages = max(1, (n_results + ROWS_PER_PAGE - 1) // ROWS_PER_PAGE)

                # Clamp page
                if st.session_state['sf_page'] >= total_pages:
                    st.session_state['sf_page'] = total_pages - 1

                page_start = st.session_state['sf_page'] * ROWS_PER_PAGE
                page_end = min(page_start + ROWS_PER_PAGE, n_results)
                page_df = filt.iloc[page_start:page_end]

                st.markdown(f"""
                    <div style='display:flex; justify-content:space-between; align-items:center; margin:12px 0 6px 0;'>
                        <span style='font-size:1.05rem; font-weight:600; color:#1E293B;'>
                            📋 Results Table — Page {st.session_state['sf_page']+1} of {total_pages}
                        </span>
                        <span style='font-size:0.9rem; color:#64748B;'>
                            Showing rows {page_start+1}–{page_end} of {n_results}
                        </span>
                    </div>
                """, unsafe_allow_html=True)

                # Display table
                display_cols = {
                    'title': 'Title',
                    'view_count': 'Views',
                    'like_count': 'Likes',
                    'comment_count': 'Comments',
                    'engagement_rate': 'Engagement %',
                    'duration_min': 'Duration (min)',
                    'published_at_dt': 'Published',
                    'eng_level': 'Eng. Level',
                    'dur_level': 'Duration Type',
                    'video_url': 'Watch'
                }
                show_df = page_df[list(display_cols.keys())].rename(columns=display_cols)
                show_df['Engagement %'] = show_df['Engagement %'].round(2)
                show_df['Published'] = pd.to_datetime(show_df['Published'], format='ISO8601').dt.strftime('%b %d, %Y')

                st.dataframe(
                    show_df,
                    column_config={
                        "Watch": st.column_config.LinkColumn("Watch", display_text="▶ Play"),
                        "Engagement %": st.column_config.NumberColumn(format="%.2f"),
                    },
                    hide_index=True,
                    use_container_width=True,
                    height=min(n_results, ROWS_PER_PAGE) * 38 + 40
                )

                # ── Pagination Buttons ──
                pg_c1, pg_c2, pg_c3 = st.columns([1, 2, 1])
                with pg_c1:
                    if st.button("⬅️ Previous Page", disabled=(st.session_state['sf_page'] <= 0), use_container_width=True):
                        st.session_state['sf_page'] -= 1
                        st.rerun()
                with pg_c2:
                    page_nums = ""
                    for p in range(total_pages):
                        if p == st.session_state['sf_page']:
                            page_nums += f"<span style='background:#3B82F6; color:white; padding:4px 10px; border-radius:6px; margin:0 3px; font-weight:700;'>{p+1}</span>"
                        else:
                            page_nums += f"<span style='background:#F1F5F9; color:#475569; padding:4px 10px; border-radius:6px; margin:0 3px;'>{p+1}</span>"
                    st.markdown(f"<div style='text-align:center; padding:6px 0;'>{page_nums}</div>", unsafe_allow_html=True)
                with pg_c3:
                    if st.button("➡️ Next Page", disabled=(st.session_state['sf_page'] >= total_pages - 1), use_container_width=True):
                        st.session_state['sf_page'] += 1
                        st.rerun()

                # ── Active Filters Summary ──
                active_filters = []
                if st.session_state['sf_query'].strip():
                    active_filters.append(f"🔎 \"{st.session_state['sf_query']}\"")
                if st.session_state['sf_view_min'] > 0 or st.session_state['sf_view_max'] < max_views_in_data:
                    active_filters.append(f"👁️ {st.session_state['sf_view_min']:,}–{st.session_state['sf_view_max']:,} views")
                if len(st.session_state['sf_eng']) < 3:
                    active_filters.append(f"💎 {', '.join(st.session_state['sf_eng'])}")
                if len(st.session_state['sf_dur']) < 3:
                    active_filters.append(f"⏱️ {', '.join(st.session_state['sf_dur'])}")

                if active_filters:
                    pills = "  ".join([f"<span style='background:#EFF6FF; color:#1D4ED8; padding:4px 12px; border-radius:20px; font-size:0.85rem; border:1px solid #BFDBFE;'>{f}</span>" for f in active_filters])
                    st.markdown(f"""
                        <div style='background:#F8FAFC; padding:12px 16px; border-radius:10px; border:1px solid #E2E8F0; margin-top:10px;'>
                            <span style='font-weight:600; color:#1E293B; font-size:0.9rem;'>🏷️ Active Filters:</span>
                            <span style='margin-left:8px;'>{pills}</span>
                        </div>
                    """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# PAGE: COMPARATIVE ANALYTICS — Task 15 (Milestone 3)
# ═══════════════════════════════════════════════════════════════
elif st.session_state['page'] == 'compare':
    st.markdown("""
        <div style='text-align:center; padding:10px 0 25px 0;'>
            <h2 style='font-family:Outfit; font-weight:700; color:#1E293B; margin-bottom:4px;'>
                📊 Comparative Analytics Hub
            </h2>
            <p style='color:#64748B; font-size:1.05rem;'>
                Leaderboard rankings, benchmark analysis, trend comparison, and exportable reports
            </p>
        </div>
    """, unsafe_allow_html=True)

    recent = get_recent_channels(limit=50)
    if not recent or len(recent) < 1:
        st.info("No channels synced yet. Please sync at least 2 channels from the sidebar to use comparison features.")
    else:
        # ── Fetch all channel summary data ──
        all_ids = [r['id'] for r in recent]
        id_str = "','".join(all_ids)
        q_all = f"""
            SELECT c.channel_id, c.channel_name, c.subscribers, c.views, c.total_videos
            FROM channels c
            WHERE c.channel_id IN ('{id_str}')
        """
        with engine.connect() as conn:
            all_ch = pd.read_sql(text(q_all), conn)

        if all_ch.empty:
            st.error("Could not load channel data.")
        else:
            # --- GLOBAL FIGURE CAPTURE FOR PDF ---
            import os, numpy as np
            
            # Compute detail stats
            q_vid = f"""
                SELECT c.channel_name,
                       SUM(s.view_count) as total_vid_views,
                       SUM(s.like_count) as total_likes,
                       SUM(s.comment_count) as total_comments,
                       COUNT(DISTINCT v.video_id) as video_count
                FROM videos v
                JOIN channels c ON v.channel_id = c.channel_id
                JOIN video_statistics s ON v.video_id = s.video_id
                WHERE v.channel_id IN ('{id_str}')
                  AND s.captured_at = (SELECT MAX(s2.captured_at) FROM video_statistics s2 WHERE s2.video_id = v.video_id)
                GROUP BY c.channel_name
            """
            with engine.connect() as conn:
                vid_agg = pd.read_sql(text(q_vid), conn)

            if not vid_agg.empty:
                vid_agg['avg_engagement'] = (
                    (vid_agg['total_likes'] + vid_agg['total_comments']) /
                    vid_agg['total_vid_views'].replace(0, np.nan) * 100
                ).fillna(0).round(2)
                all_ch = all_ch.merge(vid_agg[['channel_name', 'avg_engagement', 'total_vid_views', 'video_count']], on='channel_name', how='left')
                all_ch['avg_engagement'] = all_ch['avg_engagement'].fillna(0)
            else:
                all_ch['avg_engagement'] = 0
                all_ch['total_vid_views'] = all_ch['views']
                all_ch['video_count'] = all_ch['total_videos']

            db_avg = all_ch[['subscribers', 'views', 'avg_engagement', 'total_videos']].mean()
            metrics_bench = ['Subscribers', 'Total Views', 'Engagement %', 'Total Videos']
            
            # 1. Benchmark Figure
            bench_channel = st.session_state.get('c_bench_ch')
            if bench_channel and bench_channel in all_ch['channel_name'].values:
                ch_row = all_ch[all_ch['channel_name'] == bench_channel].iloc[0]
                ch_vals  = [ch_row['subscribers'], ch_row['views'], ch_row['avg_engagement'], ch_row['total_videos']]
                avg_vals = [db_avg['subscribers'], db_avg['views'], db_avg['avg_engagement'], db_avg['total_videos']]
                fig_bench = go.Figure()
                fig_bench.add_trace(go.Bar(x=metrics_bench, y=[v/max(a,0.01) for v,a in zip(ch_vals, avg_vals)], name=bench_channel, marker_color='#6366F1'))
                fig_bench.add_trace(go.Bar(x=metrics_bench, y=[1,1,1,1], name='Avg', marker_color='#CBD5E1'))
                fig_bench.update_layout(template='plotly_white', height=400, barmode='group', margin=dict(l=30,r=20,t=40,b=40))
                st.session_state['fig_bench_ptr'] = fig_bench
            
            # 2. Trend Figure
            t_sels = st.session_state['c_trend_ch']
            if len(t_sels) >= 2:
                t_ids = [r['id'] for r in recent if r['name'] in t_sels]
                t_metric = trend_metric_opts[st.session_state['c_trend_m']]
                t_id_s = "','".join(t_ids)
                q_t = f"SELECT c.channel_name, v.published_at, s.view_count, s.like_count, s.comment_count FROM videos v JOIN channels c ON v.channel_id = c.channel_id JOIN video_statistics s ON v.video_id = s.video_id WHERE v.channel_id IN ('{t_id_s}') AND s.captured_at = (SELECT MAX(s2.captured_at) FROM video_statistics s2 WHERE s2.video_id = v.video_id)"
                with engine.connect() as conn: t_raw = pd.read_sql(text(q_t), conn)
                if not t_raw.empty:
                    t_raw['month'] = pd.to_datetime(t_raw['published_at'], format='ISO8601').dt.to_period('M').astype(str)
                    t_grp = t_raw.groupby(['channel_name', 'month'])[t_metric].sum().reset_index()
                    fig_trend = px.line(t_grp, x='month', y=t_metric, color='channel_name', template='plotly_white', height=500)
                    st.session_state['fig_trend_ptr'] = fig_trend
            
            # --- END GLOBAL CAPTURE ---
            
            # ═══════════════════════════════════════════════════
            # SECTION 1: LEADERBOARD
            # ═══════════════════════════════════════════════════
            st.markdown("""
                <div class='super-heading'>
                    <h3 style='margin:0;'>🏆 Channel Leaderboard</h3>
                    <p style='margin:0; color:#64748B; font-size:0.9rem;'>All synced channels ranked by performance</p>
                </div>
            """, unsafe_allow_html=True)

            # 🔀 Rank By (MIGRATED TO SIDEBAR)
            lb_sort_opts = {'Subscribers': 'subscribers', 'Total Views': 'views',
                            'Engagement %': 'avg_engagement', 'Total Videos': 'total_videos'}
            lb_sort = st.session_state['c_rank_by']
            lb_col = lb_sort_opts.get(lb_sort, 'subscribers')

            lb = all_ch.sort_values(lb_col, ascending=False).reset_index(drop=True)
            lb.index = lb.index + 1

            def get_medal(rank):
                if rank == 1: return '🥇'
                elif rank == 2: return '🥈'
                elif rank == 3: return '🥉'
                return f'#{rank}'
            lb['Rank'] = [get_medal(i) for i in lb.index]

            show_lb = lb[['Rank', 'channel_name', 'subscribers', 'views', 'avg_engagement', 'total_videos']].rename(columns={
                'channel_name': 'Channel',
                'subscribers': 'Subscribers',
                'views': 'Total Views',
                'avg_engagement': 'Engagement %',
                'total_videos': 'Videos'
            })

            # Styled Results Table
            st.dataframe(
                show_lb,
                column_config={
                    "Rank": st.column_config.TextColumn("🏆"),
                    "Subscribers": st.column_config.NumberColumn(format="%d", help="Total Subscribers"),
                    "Total Views": st.column_config.ProgressColumn(
                        "Popularity Index", 
                        help="Total Views represented as a progress bar", 
                        format="%d",
                        min_value=0,
                        max_value=int(all_ch['views'].max())
                    ),
                    "Engagement %": st.column_config.NumberColumn(format="%.2f%%", help="Interaction Rate"),
                    "Videos": st.column_config.NumberColumn(format="%d"),
                },
                hide_index=True,
                use_container_width=True
            )

            st.divider()

            # ═══════════════════════════════════════════════════
            # SECTION 2: BENCHMARK ANALYSIS
            # ═══════════════════════════════════════════════════
            st.markdown("""
                <div class='super-heading'>
                    <h3 style='margin:0;'>📏 Channel vs Database Benchmark</h3>
                    <p style='margin:0; color:#64748B; font-size:0.9rem;'>See how one channel stacks up against the average of all channels</p>
                </div>
            """, unsafe_allow_html=True)

            # 🎯 Select Channel to Benchmark (MIGRATED TO SIDEBAR)
            bench_channel = st.session_state.get('c_bench_ch')
            
            # SAFE CHECK: Ensure channel exists in the dataframe
            if not bench_channel or bench_channel not in all_ch['channel_name'].values:
                st.info("🎯 Please select a **Benchmark Channel** from the sidebar to see comparison stats.")
                ch_row = None
            else:
                ch_row = all_ch[all_ch['channel_name'] == bench_channel].iloc[0]

            if ch_row is not None:
                db_avg = all_ch[['subscribers', 'views', 'avg_engagement', 'total_videos']].mean()

                metrics_bench = ['Subscribers', 'Total Views', 'Engagement %', 'Total Videos']
                ch_vals  = [ch_row['subscribers'], ch_row['views'], ch_row['avg_engagement'], ch_row['total_videos']]
                avg_vals = [db_avg['subscribers'], db_avg['views'], db_avg['avg_engagement'], db_avg['total_videos']]

                # Delta indicators
                bm1, bm2, bm3, bm4 = st.columns(4)
                for col_w, label, ch_v, av_v in zip([bm1, bm2, bm3, bm4], metrics_bench, ch_vals, avg_vals):
                    diff_pct = ((ch_v - av_v) / av_v * 100) if av_v > 0 else 0
                    is_pos = diff_pct >= 0
                    arrow = "↑" if is_pos else "↓"
                    card_cls = "perf-card-pos" if is_pos else "perf-card-neg"
                    pill_cls = "perf-pill-pos" if is_pos else "perf-pill-neg"
                    
                    if label in ['Subscribers', 'Total Views']:
                        val_str = fmt_k_m(ch_v)
                    elif label == 'Engagement %':
                        val_str = f"{ch_v:.2f}%"
                    else:
                        val_str = f"{int(ch_v):,}"
                        
                    col_w.markdown(f"""
                        <div class='perf-card {card_cls}'>
                            <p class='perf-label'>{label}</p>
                            <p class='perf-value'>{val_str}</p>
                            <div class='perf-pill {pill_cls}'>
                                {arrow} {abs(diff_pct):.1f}% vs avg
                            </div>
                        </div>
                    """, unsafe_allow_html=True)

                fig_bench = go.Figure()
                fig_bench.add_trace(go.Bar(
                    x=metrics_bench, y=[ch_v / max(av_v, 0.01) for ch_v, av_v in zip(ch_vals, avg_vals)],
                    name=bench_channel,
                    marker=dict(color='#6366F1', cornerradius=4, line=dict(color='white', width=1.5)),
                    hovertemplate="<b>%{x}</b><br>Ratio: %{y:.2f}x<extra></extra>"
                ))
                fig_bench.add_trace(go.Bar(
                    x=metrics_bench, y=[1, 1, 1, 1],
                    name='Database Average',
                    marker=dict(color='#CBD5E1', cornerradius=4, line=dict(color='white', width=1.5)),
                    hovertemplate="<b>%{x}</b><br>Baseline: 1.0x<extra></extra>"
                ))
                fig_bench.update_layout(
                    barmode='group', template='plotly_white', height=400,
                    yaxis=dict(title='Ratio (1.0 = Average)', gridcolor='#F1F5F9',
                               zeroline=True, zerolinecolor='#CBD5E1'),
                    xaxis=dict(gridcolor='#F1F5F9'),
                    font=dict(family='Outfit', size=13),
                    legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='center', x=0.5),
                    margin=dict(l=30, r=20, t=60, b=40),
                    shapes=[dict(type='line', x0=-0.5, x1=3.5, y0=1, y1=1,
                                 line=dict(color='#EF4444', width=2, dash='dash'))]
                )
                st.plotly_chart(fig_bench, use_container_width=True)
                st.caption("🔴 Dashed red line = database average (1.0x). Bars above the line = above average.")

            st.divider()


            # ═══════════════════════════════════════════════════
            # SECTION 3: TREND COMPARISON
            # ═══════════════════════════════════════════════════
            st.markdown("""
                <div class='super-heading'>
                    <h3 style='margin:0;'>📈 Trend Comparison</h3>
                    <p style='margin:0; color:#64748B; font-size:0.9rem;'>Compare monthly performance trends across multiple channels</p>
                </div>
            """, unsafe_allow_html=True)

            # 📈 Trend Controls (MIGRATED TO SIDEBAR)
            trend_channels = st.session_state['c_trend_ch']
            trend_metric_label = st.session_state['c_trend_m']
            trend_metric_opts = {'Views': 'view_count', 'Likes': 'like_count', 'Comments': 'comment_count'}
            trend_metric = trend_metric_opts[trend_metric_label]
            chart_type = st.session_state['c_trend_t']

            if len(trend_channels) >= 2:
                trend_ids = [r['id'] for r in recent if r['name'] in trend_channels]
                t_id_str = "','".join(trend_ids)

                q_trend = f"""
                    SELECT c.channel_name, v.published_at, s.view_count, s.like_count, s.comment_count
                    FROM videos v
                    JOIN channels c ON v.channel_id = c.channel_id
                    JOIN video_statistics s ON v.video_id = s.video_id
                    WHERE v.channel_id IN ('{t_id_str}')
                      AND s.captured_at = (SELECT MAX(s2.captured_at) FROM video_statistics s2 WHERE s2.video_id = v.video_id)
                """
                with engine.connect() as conn:
                    t_df = pd.read_sql(text(q_trend), conn)

                if not t_df.empty:
                    t_df['published_at_dt'] = pd.to_datetime(t_df['published_at'], format='ISO8601')
                    t_df['month'] = t_df['published_at_dt'].dt.to_period('M').astype(str)

                    trend_data = t_df.groupby(['channel_name', 'month'])[trend_metric].sum().reset_index()
                    # Fill missing months with 0 so all channels have same x-axis
                    all_months = sorted(trend_data['month'].unique())
                    full_index = pd.MultiIndex.from_product([trend_channels, all_months], names=['channel_name', 'month'])
                    trend_data = trend_data.set_index(['channel_name', 'month']).reindex(full_index, fill_value=0).reset_index()
                    trend_data = trend_data.sort_values('month')

                    trend_colors = ['#3B82F6', '#EF4444', '#10B981', '#F59E0B', '#8B5CF6', '#EC4899', '#06B6D4', '#F97316']
                    fig_trend = go.Figure()

                    for i, ch_name in enumerate(trend_channels):
                        ch_data = trend_data[trend_data['channel_name'] == ch_name]
                        color = trend_colors[i % len(trend_colors)]

                        if chart_type == 'Grouped Bar':
                            fig_trend.add_trace(go.Bar(
                                x=ch_data['month'].tolist(),
                                y=ch_data[trend_metric].tolist(),
                                name=ch_name,
                                marker=dict(color=color, cornerradius=3, line=dict(color='white', width=1)),
                                text=[f"{v:,.0f}" if v > 0 else "" for v in ch_data[trend_metric].tolist()],
                                textposition='outside', textfont=dict(size=8, color=color),
                                hovertemplate=f"<b>{ch_name}</b><br>%{{x}}<br>{trend_metric_label}: %{{y:,.0f}}<extra></extra>"
                            ))
                        elif chart_type == 'Area':
                            hex_c = color.lstrip('#')
                            fill_c = f"rgba({int(hex_c[0:2],16)},{int(hex_c[2:4],16)},{int(hex_c[4:6],16)},0.15)"
                            fig_trend.add_trace(go.Scatter(
                                x=ch_data['month'].tolist(), y=ch_data[trend_metric].tolist(),
                                mode='lines', name=ch_name, fill='tozeroy',
                                line=dict(color=color, width=2), fillcolor=fill_c,
                                hovertemplate=f"<b>{ch_name}</b><br>%{{x}}<br>{trend_metric_label}: %{{y:,.0f}}<extra></extra>"
                            ))
                        else:
                            fig_trend.add_trace(go.Scatter(
                                x=ch_data['month'].tolist(), y=ch_data[trend_metric].tolist(),
                                mode='lines+markers', name=ch_name,
                                line=dict(color=color, width=3),
                                marker=dict(size=10, color=color, line=dict(color='white', width=2), symbol='diamond'),
                                hovertemplate=f"<b>{ch_name}</b><br>%{{x}}<br>{trend_metric_label}: %{{y:,.0f}}<extra></extra>"
                            ))

                    barmode = 'group' if chart_type == 'Grouped Bar' else None
                    fig_trend.update_layout(
                        template='plotly_white', height=500, barmode=barmode,
                        xaxis=dict(title='Month', gridcolor='#F1F5F9', tickangle=-45, categoryorder='category ascending'),
                        yaxis=dict(title=f'Total {trend_metric_label}', gridcolor='#F1F5F9', tickformat='.2s'),
                        font=dict(family='Outfit', size=13, color='#334155'),
                        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='center', x=0.5, font=dict(size=11, color='#1E293B')),
                        margin=dict(l=40, r=20, t=60, b=80), hovermode='x unified', plot_bgcolor='white'
                    )
                    st.plotly_chart(fig_trend, use_container_width=True)

                    # Summary table below chart
                    st.markdown("<h4 style='color:#0F172A;'>📋 Channel Summary Comparison</h4>", unsafe_allow_html=True)
                    summary_rows = []
                    for ch_name in trend_channels:
                        ch_d = trend_data[trend_data['channel_name'] == ch_name]
                        total = ch_d[trend_metric].sum()
                        avg = ch_d[trend_metric].mean()
                        peak_month = ch_d.loc[ch_d[trend_metric].idxmax(), 'month'] if total > 0 else 'N/A'
                        peak_val = ch_d[trend_metric].max()
                        summary_rows.append({'Channel': ch_name, f'Total {trend_metric_label}': f"{total:,.0f}",
                                             'Avg Monthly': f"{avg:,.0f}", 'Peak Month': peak_month,
                                             'Peak Value': f"{peak_val:,.0f}", 'Active Months': str(int((ch_d[trend_metric] > 0).sum()))})
                    st.dataframe(pd.DataFrame(summary_rows), hide_index=True, use_container_width=True)
                else:
                    st.warning("No video data available for the selected channels.")
            else:
                st.info("👆 Select at least **2 channels** above to compare their monthly trends.")

            st.divider()

            # ═══════════════════════════════════════════════════
            # SECTION 4: EXPORT & DATA HUB
            # ═══════════════════════════════════════════════════
            st.markdown("""
                <div class='super-heading'>
                    <h3 style='margin:0; color:#0F172A;'>💎 Analytics Data Hub</h3>
                    <p style='margin:0; color:#64748B; font-size:0.9rem;'>Premium CSV exports with deep architectural insights</p>
                </div>
            """, unsafe_allow_html=True)

            # Styled CSV Cards
            export_lb = all_ch[['channel_name','subscribers','views','avg_engagement','total_videos']].rename(columns={
                'channel_name':'Channel','subscribers':'Subscribers','views':'Total Views','avg_engagement':'Avg Engagement %','total_videos':'Total Videos'
            }).sort_values('Subscribers', ascending=False)
            
            exp_c1, exp_c2, exp_c3 = st.columns(3)
            
            with exp_c1:
                st.markdown("""
                    <div style='background:linear-gradient(135deg, #EFF6FF, #DBEAFE); border-radius:12px; padding:20px; border-left:5px solid #3B82F6; box-shadow:0 4px 6px rgba(0,0,0,0.05);'>
                        <p style='font-size:0.9rem; font-weight:800; color:#1E40AF; margin:0;'>📊 LEADERBOARD</p>
                        <p style='font-size:0.8rem; color:#1E40AF; margin:5px 0 15px 0; opacity:0.8;'>Strategic channel rankings</p>
                    </div>
                """, unsafe_allow_html=True)
                st.markdown("<style>div[data-testid='stHorizontalBlock'] div[key='csv_lb'] button {background:#3B82F6 !important; color:white !important; border:none !important;}</style>", unsafe_allow_html=True)
                st.download_button("📥 Download Leaderboard", export_lb.to_csv(index=False).encode('utf-8'), 'leaderboard.csv', 'text/csv', use_container_width=True, key='csv_lb')

            with exp_c2:
                if bench_channel:
                    st.markdown(f"""
                        <div style='background:linear-gradient(135deg, #F5F3FF, #EDE9FE); border-radius:12px; padding:20px; border-left:5px solid #8B5CF6; box-shadow:0 4px 6px rgba(0,0,0,0.05);'>
                            <p style='font-size:0.9rem; font-weight:800; color:#5B21B6; margin:0;'>📏 BENCHMARK: {bench_channel[:12]}</p>
                            <p style='font-size:0.8rem; color:#5B21B6; margin:5px 0 15px 0; opacity:0.8;'>Comparative variance analysis</p>
                        </div>
                    """, unsafe_allow_html=True)
                    st.markdown("<style>div[data-testid='stHorizontalBlock'] div[key='csv_bm'] button {background:#8B5CF6 !important; color:white !important; border:none !important;}</style>", unsafe_allow_html=True)
                    bench_export = pd.DataFrame({'Metric': metrics_bench, bench_channel: ch_vals, 'Database Average': [round(v,2) for v in avg_vals]})
                    st.download_button("📥 Download Benchmark", bench_export.to_csv(index=False).encode('utf-8'), f'bench_{bench_channel}.csv', 'text/csv', use_container_width=True, key='csv_bm')
                else: st.info("Select benchmark channel")

            with exp_c3:
                if 'c_trend_ch' in st.session_state and len(st.session_state.get('c_trend_ch', [])) >= 2:
                    st.markdown("""
                        <div style='background:linear-gradient(135deg, #FFFBEB, #FEF3C7); border-radius:12px; padding:20px; border-left:5px solid #F59E0B; box-shadow:0 4px 6px rgba(0,0,0,0.05);'>
                            <p style='font-size:0.9rem; font-weight:800; color:#92400E; margin:0;'>📈 TREND DATA</p>
                            <p style='font-size:0.8rem; color:#92400E; margin:5px 0 15px 0; opacity:0.8;'>Historical performance cycles</p>
                        </div>
                    """, unsafe_allow_html=True)
                    st.markdown("<style>div[data-testid='stHorizontalBlock'] div[key='csv_tr'] button {background:#F59E0B !important; color:white !important; border:none !important;}</style>", unsafe_allow_html=True)
                    try:
                        trend_export = trend_data.rename(columns={'channel_name':'Channel','month':'Month',trend_metric:trend_metric_label})
                        st.download_button("📥 Download Trends", trend_export.to_csv(index=False).encode('utf-8'), 'trends.csv', 'text/csv', use_container_width=True, key='csv_tr')
                    except: st.caption("Select trends")
                else: st.info("Configure trends first")

            st.markdown("<div style='height:40px;'></div>", unsafe_allow_html=True)

            # ═══════════════════════════════════════════════════
            # PDF REPORT GENERATOR — Redesigned with Templates
            # ═══════════════════════════════════════════════════
            # ═══════════════════════════════════════════════════
            # PDF REPORT WIZARD — Clean Step-by-Step Flow
            # ═══════════════════════════════════════════════════
            if '_rpt_step' not in st.session_state: st.session_state['_rpt_step'] = 1
            if '_rpt_secs' not in st.session_state: st.session_state['_rpt_secs'] = []
            if '_rpt_ttl' not in st.session_state: st.session_state['_rpt_ttl'] = "YouTube Analytics Report"

            st.markdown("<h4 style='color:#0F172A; margin-bottom:15px;'>📄 PDF Report Builder</h4>", unsafe_allow_html=True)
            
            # Wizard Tab Navigation (Modern Pill Style)
            step = st.session_state['_rpt_step']
            cols = st.columns([1, 1, 1])
            labels = ["1. Choose Template", "2. Customize Content", "3. Download Report"]
            for i, label in enumerate(labels):
                is_active = (step == i + 1)
                bg = "#EFF6FF" if is_active else "transparent"
                border = "2px solid #3B82F6" if is_active else "1px solid #E2E8F0"
                txt = "#1D4ED8" if is_active else "#64748B"
                shadow = "0 4px 6px -1px rgba(59, 130, 246, 0.1)" if is_active else "none"
                cols[i].markdown(f"""
                    <div style='text-align:center; padding:10px; background:{bg}; border:{border}; 
                                border-radius:12px; color:{txt}; font-weight:600; font-size:0.9rem;
                                box-shadow:{shadow}; transition: all 0.3s ease;'>
                        {label}
                    </div>
                """, unsafe_allow_html=True)
            st.markdown("<div style='height:30px;'></div>", unsafe_allow_html=True)
            # --- STEP 1: CHOOSE TEMPLATE ---
            if step == 1:
                st.markdown("<p style='color:#64748B; margin-bottom:25px; text-align:center; font-size:1rem;'>Select a professional architecture for your analytics report.</p>", unsafe_allow_html=True)
                t1, t2, t3 = st.columns(3)
                
                with t1:
                    st.markdown("""
                        <div style='background:linear-gradient(180deg, #EFF6FF, #DBEAFE); border:1px solid #BFDBFE; border-radius:16px; padding:25px; text-align:center; height:220px; box-shadow:0 4px 12px rgba(30,58,138,0.05);'>
                            <div style='font-size:2rem; margin-bottom:10px;'>📊</div>
                            <h3 style='font-size:1.3rem; color:#1E3A8A; margin:0;'>Executive</h3>
                            <p style='font-size:0.85rem; color:#1E40AF; margin-top:8px;'>High-level strategic insights and core metrics for leadership.</p>
                        </div>
                    """, unsafe_allow_html=True)
                    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
                    if st.button("Select Executive", key="btn_tpl_exec", use_container_width=True, type="primary"):
                        st.session_state['_rpt_secs'] = ['Channel Overview', 'Leaderboard Rankings', 'Strategic Insights', 'Key Insights', 'Trend Analysis']
                        st.session_state['_rpt_ttl'] = "Executive Analytics Brief"
                        st.session_state['_rpt_step'] = 2
                        st.session_state['_rpt_theme'] = 'Executive'
                        st.rerun()

                with t2:
                    st.markdown("""
                        <div style='background:linear-gradient(180deg, #ECFDF5, #D1FAE5); border:1px solid #A7F3D0; border-radius:16px; padding:25px; text-align:center; height:220px; box-shadow:0 4px 12px rgba(6,95,70,0.05);'>
                            <div style='font-size:2rem; margin-bottom:10px;'>📈</div>
                            <h3 style='font-size:1.3rem; color:#065F46; margin:0;'>Growth</h3>
                            <p style='font-size:0.85rem; color:#065F46; margin-top:8px;'>Deep analysis of expansion trends and growth velocity metrics.</p>
                        </div>
                    """, unsafe_allow_html=True)
                    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
                    if st.button("Select Growth", key="btn_tpl_growth", use_container_width=True, type="primary"):
                        st.session_state['_rpt_secs'] = ['Channel Overview', 'Leaderboard Rankings', 'Growth Velocity', 'Benchmark Analysis', 'Trend Analysis']
                        st.session_state['_rpt_ttl'] = "Growth & Expansion Report"
                        st.session_state['_rpt_step'] = 2
                        st.session_state['_rpt_theme'] = 'Growth'
                        st.rerun()

                with t3:
                    st.markdown("""
                        <div style='background:linear-gradient(180deg, #FFF1F2, #FFE4E6); border:1px solid #FECDD3; border-radius:16px; padding:25px; text-align:center; height:220px; box-shadow:0 4px 12px rgba(159,18,57,0.05);'>
                            <div style='font-size:2rem; margin-bottom:10px;'>💎</div>
                            <h3 style='font-size:1.3rem; color:#9F1239; margin:0;'>Engagement</h3>
                            <p style='font-size:0.85rem; color:#9F1239; margin-top:8px;'>Comprehensive interaction breakdown and audience quality.</p>
                        </div>
                    """, unsafe_allow_html=True)
                    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
                    if st.button("Select Engagement", key="btn_tpl_engage", use_container_width=True, type="primary"):
                        st.session_state['_rpt_secs'] = ['Audience Quality', 'Benchmark Analysis', 'Key Insights', 'Performance Summary', 'Trend Analysis']
                        st.session_state['_rpt_ttl'] = "Audience Engagement Suite"
                        st.session_state['_rpt_step'] = 2
                        st.session_state['_rpt_theme'] = 'Engagement'
                        st.rerun()

            elif step == 2:
                with st.container():
                    st.markdown(f"<p style='color:#1D4ED8; font-weight:700; font-size:1.1rem; margin-bottom:5px;'>Step 2: Customizing the {st.session_state.get('_rpt_theme','')} Template</p>", unsafe_allow_html=True)
                    st.markdown("<p style='color:#64748B; font-size:0.9rem; margin-bottom:20px;'>Refine your report structure and branding.</p>", unsafe_allow_html=True)
                    all_secs_opt = ['Channel Overview', 'Leaderboard Rankings', 'Benchmark Analysis', 'Growth Velocity', 'Audience Quality', 'Strategic Insights', 'Key Insights', 'Performance Summary']
                    
                    c1, c2 = st.columns([2, 1])
                    with c1:
                        sel_secs = st.multiselect("📝 Included Sections", all_secs_opt, default=[s for s in st.session_state['_rpt_secs'] if s in all_secs_opt])
                    with c2:
                        sel_ttl = st.text_input("📌 Report Title", value=st.session_state['_rpt_ttl'])
                    
                    st.divider()
                    b1, b2 = st.columns([1, 1])
                    if b1.button("⬅️ Back to Templates", use_container_width=True):
                        st.session_state['_rpt_step'] = 1
                        st.rerun()
                    if b2.button("🚀 Prepare Download", use_container_width=True, type="primary"):
                        st.session_state['_rpt_secs'] = sel_secs
                        st.session_state['_rpt_ttl'] = sel_ttl
                        st.session_state['_rpt_step'] = 3
                        st.rerun()

            # --- STEP 3: PREVIEW & DOWNLOAD ---
            elif step == 3:
                focus_context = f" for **{bench_channel}**" if bench_channel else ""
                st.info(f"✨ **Ready!** Your report '{st.session_state['_rpt_ttl']}'{focus_context} is prepared with {len(st.session_state['_rpt_secs'])} sections.")
                
                try:
                    from fpdf import FPDF
                    from datetime import datetime
                    
                    class AnalyticsPDF(FPDF):
                        def header(self):
                            if self.page_no() == 1:
                                self.set_fill_color(30, 41, 59)
                                self.rect(0, 0, 210, 30, 'F')
                                self.set_fill_color(59, 130, 246)
                                self.rect(0, 30, 210, 3, 'F')
                                self.set_font('Helvetica', 'B', 18)
                                self.set_text_color(255, 255, 255)
                                self.set_y(8)
                                self.cell(0, 10, self.title or 'YouTube Analytics Report', align='C')
                                self.ln(26)
                            else:
                                self.ln(10)
                        def footer(self):
                            self.set_y(-15)
                            self.set_fill_color(241, 245, 249)
                            self.rect(0, self.get_y()-2, 210, 20, 'F')
                            self.set_font('Helvetica', 'I', 8)
                            self.set_text_color(100, 116, 139)
                            self.cell(0, 10, f'Page {self.page_no()} | {datetime.now().strftime("%b %d, %Y")} | YouTube Pro Dashboard', align='C')
                        def ensure_page_fit(self, h):
                            if self.get_y() + h > self.page_break_trigger:
                                self.add_page()

                        def section_header(self, title, color=(59,130,246)):
                            self.ensure_page_fit(30)
                            self.ln(5)
                            self.set_fill_color(*color); self.set_text_color(255, 255, 255)
                            self.set_font('Helvetica', 'B', 12)
                            self.cell(0, 10, f'  {title}', fill=True, new_x='LMARGIN', new_y='NEXT')
                            self.ln(3); self.set_text_color(30, 41, 59)
                            
                        def smart_table(self, headers, data, col_widths=None, h_color=(59,130,246), highlight_val=None):
                            if not col_widths: col_widths = [190//len(headers)]*len(headers)
                            
                            def print_hdr():
                                self.set_font('Helvetica', 'B', 8); self.set_fill_color(*h_color); self.set_text_color(255, 255, 255)
                                for i,h in enumerate(headers): self.cell(col_widths[i], 8, str(h), border=0, fill=True, align='C')
                                self.ln(); self.set_text_color(30, 41, 59); self.set_font('Helvetica', '', 8)

                            self.ensure_page_fit(20)
                            print_hdr()
                            for ri, row in enumerate(data):
                                if self.get_y() + 10 > self.page_break_trigger:
                                    self.add_page(); print_hdr()
                                
                                # Highlight row if highlight_val matches any cell
                                row_highlight = highlight_val and any(str(highlight_val).lower() == str(cell).lower() for cell in row)
                                
                                if row_highlight: self.set_fill_color(254, 252, 232) # Light Yellow
                                elif ri%2==0: self.set_fill_color(248,250,252)
                                else: self.set_fill_color(255,255,255)
                                
                                for i,v in enumerate(row): 
                                    if row_highlight: self.set_font('Helvetica', 'B', 8)
                                    else: self.set_font('Helvetica', '', 8)
                                    self.cell(col_widths[i], 7, str(v), border=0, fill=True, align='C')
                                self.ln()
                            self.ln(2)

                    pdf = AnalyticsPDF()
                    pdf.title = st.session_state['_rpt_ttl']
                    pdf.add_page()
                    pdf.set_auto_page_break(auto=True, margin=20)
                    
                    # Focus Channel Identifer (Top of Report)
                    if bench_channel:
                        pdf.set_fill_color(248, 250, 252)
                        pdf.set_draw_color(59, 130, 246)
                        pdf.rect(10, 35, 190, 15, 'DF')
                        pdf.set_font('Helvetica', 'B', 12); pdf.set_text_color(30, 41, 59)
                        pdf.set_xy(15, 38)
                        pdf.cell(0, 10, f"PRIMARY REPORT TARGET: {bench_channel.upper()}")
                        pdf.ln(15)
                    else:
                        pdf.ln(5)
                    
                    # Summary Header
                    pdf.set_font('Helvetica', 'B', 11); pdf.set_text_color(30, 41, 59)
                    pdf.cell(0, 7, f'Multi-Channel Performance Intelligence', new_x='LMARGIN', new_y='NEXT')
                    pdf.set_font('Helvetica', '', 9); pdf.set_text_color(71, 85, 105)
                    pdf.cell(0, 6, f'Generated: {datetime.now().strftime("%B %d, %Y")} | Comparison Set: {len(all_ch)} Channels', new_x='LMARGIN', new_y='NEXT')
                    if bench_channel:
                        pdf.set_font('Helvetica', 'B', 9); pdf.set_text_color(59, 130, 246)
                        pdf.cell(0, 6, f'Focus Channel: {bench_channel} (Highlighted in Tables)', new_x='LMARGIN', new_y='NEXT')
                    pdf.ln(5)

                    r_secs = st.session_state['_rpt_secs']
                    if 'Channel Overview' in r_secs:
                        pdf.section_header('Network Performance Matrix', (16,185,129))
                        ov_data = [
                            ['Total Network Subscribers', f"{int(all_ch['subscribers'].sum()):,}"],
                            ['Total Network Views', f"{int(all_ch['views'].sum()):,}"],
                            ['Average Engagement %', f"{all_ch['avg_engagement'].mean():.2f}%"]
                        ]
                        pdf.smart_table(['Network Metric', 'System Value'], ov_data, [100, 90], (16,185,129), highlight_val=bench_channel)
                        pdf.ln(5)

                    if 'Leaderboard Rankings' in r_secs:
                        pdf.section_header('Global Channel Rankings (Top 20)', (245,158,11))
                        lb_s = all_ch.sort_values('subscribers', ascending=False).head(20).reset_index(drop=True)
                        data = [[str(i+1), str(r['channel_name']), f"{int(r['subscribers']):,}", f"{int(r['views']):,}", f"{r['avg_engagement']:.2f}%"] for i,r in lb_s.iterrows()]
                        pdf.smart_table(['#','Channel Name','Subscribers','Accumulated Views','Engagement %'], data, [10,60,40,40,40], (245,158,11), highlight_val=bench_channel)
                        pdf.ln(5)

                    if 'Growth Velocity' in r_secs:
                        pdf.section_header('Growth Velocity & Efficiency', (5, 150, 105))
                        all_ch['velocity'] = all_ch['views'] / all_ch['subscribers'].replace(0, 1)
                        gv_s = all_ch.sort_values('velocity', ascending=False).head(15).reset_index(drop=True)
                        data = [[str(i+1), str(r['channel_name']), f"{r['velocity']:.1f}x", f"{int(r['total_videos']):,}", f"{int(r['views']/max(r['total_videos'],1)):,}"] for i,r in gv_s.iterrows()]
                        pdf.smart_table(['#','Channel','Reach Multiplier','Videos','Views/Video'], data, [10,60,40,40,40], (5, 150, 105), highlight_val=bench_channel)
                        pdf.set_font('Helvetica', 'I', 8); pdf.set_text_color(100, 116, 139)
                        pdf.multi_cell(0, 5, "Reach Multiplier = Views / Subscribers. High multipliers indicate viral potential beyond the core base.")
                        pdf.ln(5)

                    if 'Audience Quality' in r_secs:
                        pdf.section_header('Audience Quality Scorecard', (190, 18, 60))
                        import numpy as np
                        all_ch['aq_score'] = (all_ch['avg_engagement'] * 10) / np.log10(all_ch['subscribers'].replace(0, 10))
                        aq_s = all_ch.sort_values('aq_score', ascending=False).head(15).reset_index(drop=True)
                        data = [[str(i+1), str(r['channel_name']), f"{r['aq_score']:.1f}", f"{r['avg_engagement']:.2f}%", f"{int(r['subscribers']):,}"] for i,r in aq_s.iterrows()]
                        pdf.smart_table(['#','Channel','Quality Score','Engagement','Subscribers'], data, [10,60,40,40,40], (190, 18, 60), highlight_val=bench_channel)
                        pdf.set_font('Helvetica', 'I', 8); pdf.set_text_color(100, 116, 139)
                        pdf.multi_cell(0, 5, "Quality Score = Weighted interaction rate relative to audience size. High scores indicate very loyal small-mid size communities.")
                        pdf.ln(5)

                    if 'Benchmark Analysis' in r_secs and bench_channel:
                        pdf.section_header(f'Full Benchmark Analysis: {bench_channel}', (139,92,246))
                        
                        fig_b = st.session_state.get('fig_bench_ptr')
                        if fig_b:
                            try:
                                b_img = "temp_bench.png"
                                # 📊 MATPLOT LIB REFACTORED (Replaces Kaleido)
                                plt.figure(figsize=(10, 5))
                                x_idx = np.arange(len(metrics_bench))
                                width = 0.35
                                
                                # Ratio calculation
                                ratios = [v / max(av, 0.01) for v, av in zip(ch_vals, avg_vals)]
                                
                                plt.bar(x_idx - width/2, ratios, width, label=bench_channel, color='#6366F1', alpha=0.9)
                                plt.bar(x_idx + width/2, [1.0]*len(metrics_bench), width, label='Database Avg', color='#CBD5E1', alpha=0.8)
                                
                                plt.axhline(1.0, color='#EF4444', linestyle='--', linewidth=1.2)
                                plt.xticks(x_idx, metrics_bench, fontfamily='sans-serif', fontsize=9)
                                plt.ylabel('Performance Ratio (1.0 = Average)', fontsize=9)
                                plt.title(f'Performance Benchmark: {bench_channel}', fontsize=12, pad=15)
                                plt.legend(fontsize=8)
                                plt.grid(axis='y', linestyle=':', alpha=0.3)
                                plt.tight_layout()
                                plt.savefig(b_img, dpi=120)
                                plt.close()

                                if os.path.exists(b_img):
                                    pdf.ensure_page_fit(60)
                                    pdf.image(b_img, x=10, w=190)
                                    pdf.ln(2)
                                    os.remove(b_img)
                            except Exception as e:
                                pdf.set_font('Helvetica', 'I', 8); pdf.set_text_color(153, 27, 27)
                                pdf.cell(0, 5, f"[Graph Export Error: Matplotlib fallback. Error: {str(e)[:40]}]")
                                pdf.ln(5)

                        data = []
                        for m, cv, av in zip(metrics_bench, ch_vals, avg_vals):
                            diff = ((cv-av)/av*100) if av>0 else 0
                            verdict = 'OUTPERFORMING' if diff>=0 else 'BELOW DATABASE AVG'
                            data.append([m, f"{cv:,.0f}" if 'Views' in m or 'Subs' in m else f"{cv:.2f}", f"{av:,.0f}" if 'Views' in m or 'Subs' in m else f"{av:.2f}", f"{diff:+.1f}%", verdict])
                        pdf.smart_table(['Metric','Value','DB Average','Variance','Verdict'], data, [40,40,40,30,40], (139,92,246))

                    if 'Strategic Insights' in r_secs:
                        pdf.section_header('Strategic Roadmap & AI Insights', (6,182,212))
                        pdf.set_font('Helvetica', 'B', 10)
                        pdf.cell(0, 8, "Primary Recommendation:", new_x='LMARGIN', new_y='NEXT')
                        pdf.set_font('Helvetica', '', 10)
                        top_v = all_ch.loc[all_ch['avg_engagement'].idxmax()]
                        pdf.multi_cell(0, 7, f"The data indicates that {top_v['channel_name']} is currently leading the interaction curve. To compete, focus on 'Interaction Stacking' - replying to first-hour comments. Your growth velocity suggests a strong retention potential if the upload frequency remains at >2 videos/week.")
                        pdf.ln(4)
                        pdf.set_font('Helvetica', 'B', 10)
                        pdf.cell(0, 8, "Channel Health Alert:", new_x='LMARGIN', new_y='NEXT')
                        pdf.set_font('Helvetica', '', 10)
                        pdf.multi_cell(0, 7, "Comparison against the top decile shows a view-to-sub ratio gap. Recommendation: Optimize 'End Screens' for higher session duration.")
                        pdf.ln(5)

                    if 'Key Insights' in r_secs:
                        pdf.section_header('Performance Summary', (6,182,212))
                        pdf.set_font('Helvetica', '', 10)
                        pdf.multi_cell(0, 8, "Key Takeaway: Engagement continues to be the primary driver of reach. Channels in the 90th percentile of interaction show accelerated subscriber growth cycles. Maintain engagement baseline at >3.5% for sustainable scalability.")
                        pdf.ln(5)

                    if 'Trend Analysis' in r_secs:
                        pdf.section_header('Historical Trend Analysis', (59, 130, 246))
                        fig_t = st.session_state.get('fig_trend_ptr')
                        if fig_t:
                            try:
                                img_p = "temp_trend.png"
                                # 📈 MATPLOT LIB REFACTORED TRENDS
                                plt.figure(figsize=(10, 5))
                                
                                months = sorted(trend_data['month'].unique())
                                trend_colors_mp = ['#3B82F6', '#EF4444', '#10B981', '#F59E0B', '#8B5CF6', '#EC4899', '#06B6D4', '#F97316']
                                
                                if chart_type == 'Grouped Bar':
                                    x_axis = np.arange(len(months))
                                    w = 0.8 / len(trend_channels)
                                    for i, ch in enumerate(trend_channels):
                                        ch_d = trend_data[trend_data['channel_name'] == ch]
                                        plt.bar(x_axis + (i * w) - 0.4 + w/2, ch_d[trend_metric], w, 
                                                label=ch, color=trend_colors_mp[i % len(trend_colors_mp)])
                                elif chart_type == 'Area':
                                    for i, ch in enumerate(trend_channels):
                                        ch_d = trend_data[trend_data['channel_name'] == ch]
                                        plt.fill_between(months, ch_d[trend_metric], label=ch, 
                                                       color=trend_colors_mp[i % len(trend_colors_mp)], alpha=0.3)
                                        plt.plot(months, ch_d[trend_metric], color=trend_colors_mp[i % len(trend_colors_mp)], linewidth=2)
                                else: # Line + Markers
                                    for i, ch in enumerate(trend_channels):
                                        ch_d = trend_data[trend_data['channel_name'] == ch]
                                        plt.plot(months, ch_d[trend_metric], label=ch, marker='d', 
                                                 color=trend_colors_mp[i % len(trend_colors_mp)], linewidth=2)

                                plt.title(f'Monthly Performance Trends: {trend_metric_label}', fontsize=12)
                                plt.ylabel(trend_metric_label, fontsize=9)
                                plt.xticks(rotation=45, fontsize=8)
                                plt.legend(fontsize=8, loc='upper left')
                                plt.grid(linestyle=':', alpha=0.2)
                                plt.tight_layout()
                                plt.savefig(img_p, dpi=120)
                                plt.close()

                                if os.path.exists(img_p):
                                    pdf.ensure_page_fit(70)
                                    pdf.image(img_p, x=10, w=190)
                                    pdf.ln(2)
                                    os.remove(img_p)
                            except Exception as e:
                                pdf.set_font('Helvetica', 'I', 8); pdf.set_text_color(153, 27, 27)
                                pdf.cell(0, 5, f"[Trend Export Error: {str(e)[:50]}]")
                                pdf.ln(5)
                        else:
                            pdf.set_font('Helvetica', 'I', 8); pdf.set_text_color(100, 116, 139)
                            pdf.cell(0, 5, "[Trend chart not found in session memory. Select channels to include.]")
                            pdf.ln(5)


                    pdf_bytes = pdf.output()
                    
                    theme_name = st.session_state.get('_rpt_theme','Professional')
                    st.markdown(f"""
                        <div style='background:#F0FDF4; border:1px solid #BBF7D0; border-radius:12px; padding:20px; margin-bottom:20px;'>
                            <h4 style='color:#166534; margin:0;'>✅ Report Ready</h4>
                            <p style='color:#166534; font-size:0.9rem; margin-top:5px;'>
                                Your <b>{theme_name}</b> report has been generated with strategic metrics and target channel highlighting.
                            </p>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # Theme-based button colors
                    theme_btn_color = "#1D4ED8" if st.session_state.get('_rpt_theme') == 'Executive' else \
                                      "#059669" if st.session_state.get('_rpt_theme') == 'Growth' else \
                                      "#E11D48" if st.session_state.get('_rpt_theme') == 'Engagement' else "#3B82F6"
                    
                    # Dynamic Style Injector for Buttons
                    st.markdown(f"""
                        <style>
                        div[st-vertical-block='true'] button[key='dl_pdf_final'] {{
                            background-color: {theme_btn_color} !important;
                            color: white !important;
                            border: none !important;
                        }}
                        </style>
                    """, unsafe_allow_html=True)
                    
                    st.divider()
                    # Short buttons as requested
                    c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
                    with c1:
                        st.download_button("📥 Download PDF", bytes(pdf_bytes), f'report_{datetime.now().strftime("%Y%m%d")}.pdf', 'application/pdf', use_container_width=True, key='dl_pdf_final')
                    with c2:
                        if st.button("🔙 Reset", use_container_width=True, key='reset_wizard'):
                            st.session_state['_rpt_step'] = 1
                            st.rerun()
                        
                except Exception as e:
                    st.error(f"Error building report: {e}")
                    if st.button("Retry Wizard"): st.session_state['_rpt_step'] = 1; st.rerun()

            st.markdown("<p style='text-align:right; font-size:0.85rem; color:#475569; margin-top:40px;'>📊 Professional Analytics Intelligence Hub</p>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# PAGE: ABOUT — Red Aesthetic Evolution
# ═══════════════════════════════════════════════════════════════
elif st.session_state['page'] == 'about':
    st.markdown("<div class='animate-step'>", unsafe_allow_html=True)
    
    # --- RED HERO HEADER ---
    st.markdown("""
        <div class='red-hero-card'>
            <h1 style='margin:0; color:#fbfbfc;'>The Strategic Blueprint</h1>
            <p style='margin-top:10px;'>Mapping the data ecosystem of YouTube Pro Dash</p>
            <div style='display:flex; justify-content:center; gap:20px; margin-top:20px;'>
                 <span style='background:rgba(255,255,255,0.2); padding:5px 15px; border-radius:15px; font-size:0.85rem;'>⚡ High Energy</span>
                 <span style='background:rgba(255,255,255,0.2); padding:5px 15px; border-radius:15px; font-size:0.85rem;'>📊 Expert Analytics</span>
                 <span style='background:rgba(255,255,255,0.2); padding:5px 15px; border-radius:15px; font-size:0.85rem;'>🎯 Creator First</span>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # --- MODULAR ENCYCLOPEDIA (RED THEMED) ---
    st.markdown("### 🗺️ Application Roadmap: Sections & Intelligence")
    
    # Row 1: Dashboard & Profile
    r1c1, r1c2 = st.columns(2)
    with r1c1:
        st.markdown(f"""
            <div class='creative-red-card'>
                <h4 style='margin:0;'>📊 Dashboard (The Pulse)</h4>
                <div style='margin:10px 0;'>
                    <span class='feature-pill pill-red'>Input: Channel ID</span>
                    <span class='feature-pill pill-red'>Output: Reality Meters</span>
                </div>
                <p style='font-size:0.9rem; color:#475569;'>A real-time performance audit. Explore <b>Views</b>, <b>Subs</b>, and <b>Engagement</b> averages compared to historical norms.</p>
                <div style='background:#FFF1F1; padding:10px; border-radius:8px; font-size:0.85rem; border-left:3px solid #EF4444;'>
                    <b style='color:#991B1B;'>🔍 Explore:</b> Growth Trends, Stability Score, Engagement Velocity.
                </div>
            </div>
        """, unsafe_allow_html=True)
    with r1c2:
        st.markdown(f"""
            <div class='creative-red-card'>
                <h4 style='margin:0;'>🏆 Profile (The Identity)</h4>
                <div style='margin:10px 0;'>
                    <span class='feature-pill pill-red'>Input: Metadata Sync</span>
                    <span class='feature-pill pill-red'>Output: Content DNA</span>
                </div>
                <p style='font-size:0.9rem; color:#475569;'>The digital fingerprint of a creator. We extract <b>Tags</b>, <b>Descriptions</b>, and <b>Top Videos</b> to understand the niche.</p>
                <div style='background:#FFF1F1; padding:10px; border-radius:8px; font-size:0.85rem; border-left:3px solid #EF4444;'>
                    <b style='color:#991B1B;'>🔍 Explore:</b> Viral Hit-List, Keyword Cloud, Subscriber ROI.
                </div>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin-top:25px;'></div>", unsafe_allow_html=True)

    # Row 2: Battle Arena & Visuals
    r2c1, r2c2 = st.columns(2)
    with r2c1:
        st.markdown(f"""
            <div class='creative-red-card'>
                <h4 style='margin:0;'>⚖️ Battle Arena (Rivalry)</h4>
                <div style='margin:10px 0;'>
                    <span class='feature-pill pill-red'>Input: Rival Select</span>
                    <span class='feature-pill pill-red'>Output: Share of Voice</span>
                </div>
                <p style='font-size:0.9rem; color:#475569;'>Head-to-head benchmarking. Select rivals from your library to see who is winning the <b>Reach Battle</b> and <b>Engagement Matrix</b>.</p>
                <div style='background:#FFF1F1; padding:10px; border-radius:8px; font-size:0.85rem; border-left:3px solid #EF4444;'>
                    <b style='color:#991B1B;'>🔍 Explore:</b> Quality Index, Multi-Channel Comparison charts.
                </div>
            </div>
        """, unsafe_allow_html=True)
    with r2c2:
        st.markdown(f"""
            <div class='creative-red-card'>
                <h4 style='margin:0;'>📈 Visuals (Patterns)</h4>
                <div style='margin:10px 0;'>
                    <span class='feature-pill pill-red'>Filters: Year, Metric, Format</span>
                    <span class='feature-pill pill-red'>Output: Trend Maps</span>
                </div>
                <p style='font-size:0.9rem; color:#475569;'>Deep-dive pattern recognition. Use filters to narrow down data by <b>Year</b> or <b>Content Type</b> (Shorts vs Long-form).</p>
                <div style='background:#FFF1F1; padding:10px; border-radius:8px; font-size:0.85rem; border-left:3px solid #EF4444;'>
                    <b style='color:#991B1B;'>🔍 Explore:</b> Heatmaps (Post Times), Treemaps (Topic Share).
                </div>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin-top:25px;'></div>", unsafe_allow_html=True)

    # Row 3: Search & Compare
    r3c1, r3c2 = st.columns(2)
    with r3c1:
        st.markdown(f"""
            <div class='creative-red-card'>
                <h4 style='margin:0;'>🔍 Search (The Toolkit)</h4>
                <div style='margin:10px 0;'>
                    <span class='feature-pill pill-red'>Filters: Views, Days, Query</span>
                    <span class='feature-pill pill-red'>Output: CSV/Excel Hub</span>
                </div>
                <p style='font-size:0.9rem; color:#475569;'>Advanced video discovery. Apply range filters for <b>Views</b> and <b>Duration</b> to find specific data points.</p>
                <div style='background:#FFF1F1; padding:10px; border-radius:8px; font-size:0.85rem; border-left:3px solid #EF4444;'>
                    <b style='color:#991B1B;'>🔍 Explore:</b> Bulk Export, Keyword Specific Performance.
                </div>
            </div>
        """, unsafe_allow_html=True)
    with r3c2:
        st.markdown(f"""
            <div class='creative-red-card'>
                <h4 style='margin:0;'>📊 Compare (Intelligence)</h4>
                <div style='margin:10px 0;'>
                    <span class='feature-pill pill-red'>Step: Select Rival</span>
                    <span class='feature-pill pill-red'>Output: PDF Intelligence</span>
                </div>
                <p style='font-size:0.9rem; color:#475569;'>Strategic reporting center. Run the <b>Report Wizard</b> to generate professional PDF dossiers for stakeholders.</p>
                <div style='background:#FFF1F1; padding:10px; border-radius:8px; font-size:0.85rem; border-left:3px solid #EF4444;'>
                    <b style='color:#991B1B;'>🔍 Explore:</b> Executive Reports, Growth Benchmarks.
                </div>
            </div>
        """, unsafe_allow_html=True)

    st.divider()

    # --- THE WHY & FOR WHOM (RED VERSION) ---
    bc1, bc2 = st.columns([1, 2])
    with bc1:
        st.markdown(f"""
            <div style='padding-top:20px; text-align:center;'>
                <div style='font-size:5rem;'>🎯</div>
                <h2 style='margin:0; color:#EF4444;'>The Mission</h2>
            </div>
        """, unsafe_allow_html=True)
    with bc2:
        st.markdown(f"""
            <div class='target-user-card'>
                <h3 style='margin:0;'>Elite Target Audience</h3>
                <p style='font-size:1.1rem; margin-top:15px;'>
                    <b>YouTube Pro Dash</b> is engineered for <b>Modern Creators</b>, <b>Digital Strategists</b>, and <b>Agency Managers</b> who demand high-energy, actionable video intelligence.
                </p>
                <div style='display:flex; justify-content:center; gap:10px; margin-top:20px; flex-wrap:wrap;'>
                    <span style='background:rgba(255,255,255,0.2); padding:5px 15px; border-radius:20px; font-size:0.8rem;'>Creators</span>
                    <span style='background:rgba(255,255,255,0.2); padding:5px 15px; border-radius:20px; font-size:0.8rem;'>Growth Hackers</span>
                    <span style='background:rgba(255,255,255,0.2); padding:5px 15px; border-radius:20px; font-size:0.8rem;'>Brand Managers</span>
                    <span style='background:rgba(255,255,255,0.2); padding:5px 15px; border-radius:20px; font-size:0.8rem;'>Data Analysts</span>
                </div>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# PAGE: HELP & FAQ — Elite Support Repository
# ═══════════════════════════════════════════════════════════════
elif st.session_state['page'] == 'help':
    st.markdown("<div class='animate-step'>", unsafe_allow_html=True)
    
    # --- RED HERO SUPPORT HEADER ---
    st.markdown("""
        <div class='red-hero-card'>
            <h1 style='margin:0;'>Elite Support Repository</h1>
            <p style='margin-top:10px;'>Mastering the toolkit: Definitions, FAQs, and System Diagnostics</p>
        </div>
    """, unsafe_allow_html=True)

    # --- FAQ STYLING CSS ---
    st.markdown("""
        <style>
        .streamlit-expanderHeader {
            font-weight: 800 !important;
            color: #0F172A !important;
            font-size: 1.1rem !important;
        }
        .streamlit-expanderContent {
            color: #1E293B !important;
            font-weight: 500 !important;
        }
        </style>
    """, unsafe_allow_html=True)

    # --- COLLAPSIBLE FAQ ENGINE ---
    st.markdown("### 📋 Interactive FAQ: Multi-category Support")
    faq_tabs = st.tabs(["🚀 Getting Started", "📈 Data & Metrics", "🔧 Troubleshooting"])
    
    with faq_tabs[0]: # Getting Started
        with st.expander("❓ Where do I find my Channel ID?", expanded=True):
            st.markdown("""
                The Channel ID is a unique code starting with **UC**. 
                - Go to any YouTube channel.
                - Look at the URL. If it says `youtube.com/channel/UC...`, the code after 'channel/' is your ID.
                - If it's a handle like `@creator`, go to their **'About'** page, click **'Share'**, and select **'Copy Channel ID'**.
            """)
        with st.expander("❓ How do I add my own channel to the library?"):
            st.markdown("""
                In the sidebar, enter your **Channel ID** and click **'Run Analysis'**. 
                The system will automatically fetch all metadata, calculate metrics, and save it to your local MySQL database.
            """)
        with st.expander("❓ Is this application free to use?"):
            st.markdown("""
                Yes! This is your personal **Elite Hub**. It uses the official YouTube Data API v3 and runs entirely on your local machine for maximum privacy.
            """)

    with faq_tabs[1]: # Data & Metrics
        with st.expander("❓ Why are my View counts different from the YouTube app?"):
            st.markdown("""
                YouTube updates public counts at different speeds globally. We cache data for **60 minutes** to keep your dashboard fast. 
                *Note: You can force a fresh sync by running the analysis again in the sidebar.*
            """)
        with st.expander("❓ What does 'Engagement Velocity' actually tell me?"):
            st.markdown("""
                It tells you **interaction quality per 1,000 views**. 
                - **High Velocity (>50):** Your fans are extremely active.
                - **Low Velocity (<10):** People are watching but not hitting like/comment. Switch up your call-to-action!
            """)
        with st.expander("❓ How is 'Stability Score' calculated?"):
            st.markdown("""
                We use a standard deviation formula against your views. 
                - **High Score:** Steady growth.
                - **Low Score:** Your channel depends on rare 'Viral Hits' while other videos struggle.
            """)

    with faq_tabs[2]: # Troubleshooting
        with st.expander("❓ The 'Run Analysis' button is stuck or loading forever.", expanded=True):
            st.markdown("""
                This usually happens if the YouTube API quota is exceeded or your internet is unstable. 
                - Check the **System Health** cards at the top.
                - If quota is okay, try refreshing the page.
            """)
        with st.expander("❓ I don't see my channel in the 'Recently Analyzed' list."):
            st.markdown("""
                Ensure the analysis completed without errors. If code 403 or 404 appeared, the ID might be wrong or the API key might be invalid.
            """)
        with st.expander("❓ Why can't I export the 'Battle Arena' results?"):
            st.markdown("""
                Battle Arena is for **Live Comparison**. To export, go to the **Search** page or use the **Report Wizard** in the 'Compare' tab to generate a PDF.
            """)

    st.divider()

    # --- SERVICE TILES (KNOWLEDGE BASE) ---
    st.markdown("### 📚 Strategic Knowledge Base")
    k1, k2 = st.columns(2)
    with k1:
        st.markdown(f"""
            <div class='creative-red-card'>
                <h5 style='margin:0; color:#EF4444;'>🎥 Video Tutorials</h5>
                <p style='font-size:0.85rem; color:#475569; margin-top:10px;'>Learn how to master the **Engagement Matrix** and **Reach Battle** charts effectively.</p>
                <div style='background:#F1F5F9; padding:8px; border-radius:6px; font-size:0.75rem;'>COMING SOON: v2.7 Update</div>
            </div>
        """, unsafe_allow_html=True)
    with k2:
        st.markdown(f"""
            <div class='creative-red-card'>
                <h5 style='margin:0; color:#EF4444;'>🔒 Data Privacy Policy</h5>
                <p style='font-size:0.85rem; color:#475569; margin-top:10px;'>Your analysis is saved **locally**. We never upload your rival lists or private metrics to external servers.</p>
                <div style='background:#F1F5F9; padding:8px; border-radius:6px; font-size:0.75rem;'>Security: Enterprise Standard</div>
            </div>
        """, unsafe_allow_html=True)

    st.divider()

    # --- PRO TIP BOX ---
    st.info("💡 **Expert Support:** If you encounter a bug or analysis error, please contact your local system administrator for terminal logs.")

    st.markdown("<p style='text-align:center; color:#94A3B8; font-size:0.85rem; margin-top:30px;'>YouTube Pro Dash v2.6 | Elite Support repository</p>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)




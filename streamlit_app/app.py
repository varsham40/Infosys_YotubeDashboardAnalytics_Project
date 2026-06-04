import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import datetime
import sys
import os
import html
import isodate
import requests
import matplotlib
matplotlib.use('Agg') # Non-interactive backend
import matplotlib.pyplot as plt
from datetime import datetime

# --- Fix for FPDF Unicode Errors ---
try:
    import fpdf
    def safe_normalize_text(self, text):
        return str(text).encode(getattr(self, 'core_fonts_encoding', 'windows-1252'), 'replace').decode('latin-1')
    fpdf.fpdf.FPDF.normalize_text = safe_normalize_text
except ImportError:
    pass

# Configure path for module imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database_operations.data_insertion import store_channel_data, get_recent_channels, store_channel_data_for_year, discard_channel_data_for_year
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
from help_widget import render_help_widget
from ai_assistant import render_ai_assistant

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
    Safe image loader. Compatible with Streamlit 1.57.0 which uses use_container_width.
    Accepts both use_container_width and use_column_width for backward compatibility.
    """
    fallback = "https://via.placeholder.com/480x360.png?text=Image+Not+Available"
    # Merge both parameter names — if either is True, set use_container_width=True
    col_width = use_container_width or use_column_width
    
    img_kwargs = {}
    if width:
        img_kwargs['width'] = width
    if col_width:
        img_kwargs['use_container_width'] = True
    try:
        if url and url.startswith("http"):
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                st.image(resp.content, **img_kwargs)
                return
        st.image(fallback, **img_kwargs)
    except:
        st.image(fallback, **img_kwargs)

def render_premium_table(df, table_id, link_cols=None, max_height=420, formatters=None):
    """Render a consistently styled HTML table (works when Streamlit dataframe styling is limited)."""
    link_cols = link_cols or {}
    formatters = formatters or {}
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]

    thead = ""
    for col in df.columns:
        th_class = "linkcol" if col in link_cols else ""
        thead += f"<th class='{th_class}'>{html.escape(str(col))}</th>"
    rows_html = []

    for _, row in df.iterrows():
        cells = []
        for col in df.columns:
            val = row[col]
            if pd.isna(val):
                disp = "-"
            elif col in formatters:
                try:
                    disp = formatters[col].format(val)
                except Exception:
                    disp = str(val)
            elif col in numeric_cols:
                if isinstance(val, (int, np.integer)):
                    disp = f"{int(val):,}"
                else:
                    disp = f"{float(val):,.1f}" if col.lower() == 'mins' else f"{float(val):,.0f}"
            else:
                disp = str(val)

            if col in link_cols and isinstance(val, str) and val.startswith("http"):
                text = html.escape(link_cols[col])
                safe_url = html.escape(val, quote=True)
                cell_html = f"<a class='pt-link' href='{safe_url}' target='_blank'>{text}</a>"
            else:
                safe_text = html.escape(disp)
                cell_html = safe_text

            align_class = "num" if col in numeric_cols else "text"
            if col in link_cols:
                align_class += " linkcol"
            cells.append(f"<td class='{align_class}'>{cell_html}</td>")
        rows_html.append(f"<tr>{''.join(cells)}</tr>")

    table_html = f"""
    <div class='pt-wrap' id='{html.escape(table_id)}' style='max-height:{int(max_height)}px;'>
        <table class='pt-table'>
            <thead><tr>{thead}</tr></thead>
            <tbody>{''.join(rows_html)}</tbody>
        </table>
    </div>
    """
    st.markdown(table_html, unsafe_allow_html=True)

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

def apply_global_filters(df):
    if df.empty:
        return df
    
    # Drop duplicates by video_id to ensure clean operations
    df = df.drop_duplicates(subset=['video_id']).copy()
    
    # Compute temporal/metric columns
    df['published_at_dt'] = pd.to_datetime(df['published_at'], errors='coerce')
    df = df.dropna(subset=['published_at_dt'])
    df['year'] = df['published_at_dt'].dt.year
    df['month_name'] = df['published_at_dt'].dt.month_name()
    df['day_name'] = df['published_at_dt'].dt.day_name()
    df['hour'] = df['published_at_dt'].dt.hour
    
    # Parse duration and determine type
    def detect_type(row):
        dur = parse_duration(row['duration'])
        has_tag = '#shorts' in str(row['title']).lower()
        if has_tag or dur <= 100: return 'Shorts'
        return 'Long-form'
    
    df['is_short'] = df.apply(detect_type, axis=1)
    df['engagement_rate'] = ((df['like_count'] + df['comment_count']) / df['view_count'].replace(0, np.nan) * 100).fillna(0)
    df['video_url'] = "https://www.youtube.com/watch?v=" + df['video_id']
    
    # Filter by global year selection
    if 'v_selected_year' in st.session_state and st.session_state['v_selected_year'] != "All Years":
        target_year = int(st.session_state['v_selected_year'])
        df = df[df['year'] == target_year]
        
    # Filter by global content type selection
    if 'v_types' in st.session_state and st.session_state['v_types']:
        df = df[df['is_short'].isin(st.session_state['v_types'])]
        
    return df

def get_channel_data(channel_id):
    df_raw = get_channel_data_from_db(channel_id)
    return apply_global_filters(df_raw)

# --- PREMIUM UI CSS & FONTS ---
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">

<style>
    /* GLOBAL RESET & ULTRA-CLARITY */
    * { font-family: 'Inter', sans-serif; font-size: 1.05rem; }
    iframe { border: none !important; overflow: hidden !important; }
    div[data-testid="stPlotlyChart"], .stPlotlyChart { border: none !important; overflow: hidden !important; }
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

    /* PAGE HEADING CARD — consistent light style across all pages */
    .page-heading-card {
        background: linear-gradient(135deg, #F8FAFC 0%, #F1F5F9 100%);
        border: 1px solid #E2E8F0;
        border-radius: 14px;
        padding: 20px 24px;
        margin-bottom: 24px;
        box-shadow: 0 6px 16px rgba(15, 23, 42, 0.06);
        display: flex;
        align-items: center;
        gap: 16px;
    }
    /* Color variants for different pages */
    .page-heading-card.dash {
        background: linear-gradient(135deg, #DBEAFE 0%, #BAE6FD 100%);
        border-color: #7DD3FC;
        box-shadow: 0 6px 16px rgba(3, 102, 214, 0.12);
    }
    .page-heading-card.dash h1 {
        color: #0C4A6E !important;
    }
    .page-heading-card.profile {
        background: linear-gradient(135deg, #DDD6FE 0%, #C7D2FE 100%);
        border-color: #A5B4FC;
        box-shadow: 0 6px 16px rgba(79, 70, 229, 0.12);
    }
    .page-heading-card.profile h1 {
        color: #3730A3 !important;
    }
    .page-heading-card.battle {
        background: linear-gradient(135deg, #FECACA 0%, #FCA5A5 100%);
        border-color: #F87171;
        box-shadow: 0 6px 16px rgba(239, 68, 68, 0.12);
    }
    .page-heading-card.battle h1 {
        color: #7F1D1D !important;
    }
    .page-heading-card.vis {
        background: linear-gradient(135deg, #C7F0D8 0%, #A7F3D0 100%);
        border-color: #6EE7B7;
        box-shadow: 0 6px 16px rgba(5, 150, 105, 0.12);
    }
    .page-heading-card.vis h1 {
        color: #065F46 !important;
    }
    .page-heading-card.compare {
        background: linear-gradient(135deg, #F3E8FF 0%, #E9D5FF 100%);
        border-color: #D8B4FE;
        box-shadow: 0 6px 16px rgba(147, 51, 234, 0.12);
    }
    .page-heading-card.compare h1 {
        color: #581C87 !important;
    }
    .page-heading-card .icon {
        font-size: 2.2rem;
        display: inline-flex;
        align-items: center;
    }
    .page-heading-card h1 {
        margin: 0;
        font-family: 'Outfit', sans-serif;
        font-size: 2rem;
        font-weight: 800;
        color: #0F172A;
        letter-spacing: -0.5px;
    }

    /* SIDEBAR — modern global navigation shell */
    section[data-testid="stSidebar"] {
        background:
            radial-gradient(circle at 12% 10%, rgba(59,130,246,0.22) 0%, rgba(59,130,246,0) 38%),
            radial-gradient(circle at 88% 92%, rgba(99,102,241,0.14) 0%, rgba(99,102,241,0) 40%),
            linear-gradient(180deg, #F8FAFF 0%, #EEF2FF 100%);
        border-right: 1px solid #CFD9F6;
    }
    section[data-testid="stSidebar"] > div {
        padding-top: 0.6rem;
    }

    /* Sidebar brand block */
    .sb-brand {
        display: flex;
        align-items: center;
        gap: 10px;
        margin: 0.1rem 0 0.45rem 0;
        padding: 0.35rem 0.2rem;
    }
    .sb-brand-link {
        display: block;
        text-decoration: none !important;
        border-radius: 12px;
        transition: background 0.2s ease;
    }
    .sb-brand-link:hover {
        background: rgba(255, 255, 255, 0.45);
    }
    .sb-brand .sb-menu {
        width: 34px;
        height: 34px;
        border-radius: 10px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 1.15rem;
        color: #FFFFFF;
        background: linear-gradient(135deg, #FF0000 0%, #D90429 100%);
        border: 1px solid rgba(255, 255, 255, 0.5);
        box-shadow: 0 8px 18px rgba(217, 4, 41, 0.28);
    }
    .sb-brand .sb-title {
        font-family: 'Outfit', sans-serif;
        font-size: 1.42rem;
        font-weight: 800;
        color: #0F172A;
        letter-spacing: 0.01em;
    }
    .sb-section-label {
        margin: 0.2rem 0 0.28rem 0;
        font-size: 0.74rem;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: #64748B;
        padding-left: 0.18rem;
    }

    /* Global sidebar button geometry */
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button {
        width: 100% !important;
        min-height: 2.95rem !important;
        height: 2.95rem !important;
        border-radius: 12px !important;
        font-size: 1.18rem !important;
        line-height: 1.15 !important;
        letter-spacing: 0.02em !important;
        font-weight: 700 !important;
        text-align: left !important;
        padding: 0.43rem 0.9rem !important;
        transition: all 0.2s ease !important;
        margin-bottom: 0.18rem !important;
    }

    /* Icon styling in buttons - larger, darker, elevated */
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button::before {
        letter-spacing: 0.08em;
        text-shadow: 0 2px 4px rgba(0, 0, 0, 0.15);
    }

    /* Secondary = idle nav style */
    .stSidebar [data-testid="stBaseButton-secondary"],
    .stSidebar [data-testid="baseButton-secondary"] {
        color: #1E293B !important;
        border: 1px solid #D4DCF4 !important;
        background: rgba(255, 255, 255, 0.88) !important;
        box-shadow: 0 4px 12px rgba(15, 23, 42, 0.06) !important;
    }

    .stSidebar [data-testid="stBaseButton-secondary"]::before,
    .stSidebar [data-testid="baseButton-secondary"]::before {
        text-shadow: 0 1px 3px rgba(0, 0, 0, 0.12);
    }
    .stSidebar [data-testid="stBaseButton-secondary"]:hover,
    .stSidebar [data-testid="baseButton-secondary"]:hover {
        color: #0F172A !important;
        background: #FFFFFF !important;
        border-color: #B9C7F0 !important;
        box-shadow: 0 8px 16px rgba(15, 23, 42, 0.1) !important;
        transform: translateY(-1px);
    }

    /* Primary = active nav button */
    .stSidebar [data-testid="stBaseButton-primary"] {
        color: #FFFFFF !important;
        border: 2px solid rgba(239, 68, 68, 0.6) !important;
        background: linear-gradient(135deg, #FF1744 0%, #D32F2F 100%) !important;
        box-shadow: 0 10px 22px rgba(239, 68, 68, 0.35),
                    0 0 20px rgba(239, 68, 68, 0.2) !important;
        transition: all 0.3s ease !important;
        position: relative;
        overflow: hidden;
    }
    .stSidebar [data-testid="stBaseButton-primary"]::before {
        content: '';
        position: absolute;
        top: 50%;
        left: 50%;
        width: 0;
        height: 0;
        border-radius: 50%;
        background: rgba(255, 255, 255, 0.3);
        transform: translate(-50%, -50%);
        transition: width 0.6s, height 0.6s;
    }
    .stSidebar [data-testid="stBaseButton-primary"]:hover {
        transform: translateY(-2px) scale(1.02);
        box-shadow: 0 14px 32px rgba(239, 68, 68, 0.5),
                    0 0 30px rgba(239, 68, 68, 0.3) !important;
        border-color: rgba(239, 68, 68, 0.8) !important;
        background: linear-gradient(135deg, #F50057 0%, #C51162 100%) !important;
        filter: brightness(1.1) saturate(1.1);
    }
    .stSidebar [data-testid="stBaseButton-primary"]:active {
        transform: translateY(0px) scale(0.98);
        box-shadow: 0 8px 16px rgba(59, 99, 224, 0.4) !important;
    }
    .stSidebar [data-testid="stBaseButton-primary"] p,
    .stSidebar [data-testid="stBaseButton-primary"] span {
        color: #FFFFFF !important;
    }

    /* Enhanced sidebar input styling */
    .stSidebar div[data-testid="stTextInput"] input {
        border: 2px solid rgba(99, 102, 241, 0.3) !important;
        border-radius: 12px !important;
        padding: 11px 14px !important;
        background: rgba(255, 255, 255, 0.95) !important;
        font-size: 0.95rem !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 4px 12px rgba(99, 102, 241, 0.08) !important;
    }

    .stSidebar div[data-testid="stTextInput"] input:focus {
        border-color: rgba(99, 102, 241, 0.7) !important;
        background: rgba(255, 255, 255, 1) !important;
        box-shadow: 0 6px 20px rgba(99, 102, 241, 0.2),
                    inset 0 0 0 1px rgba(99, 102, 241, 0.1) !important;
        outline: none !important;
    }

    .stSidebar div[data-testid="stTextInput"] input::placeholder {
        color: rgba(148, 163, 184, 0.6) !important;
        font-weight: 500;
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
        background: linear-gradient(145deg, rgba(255, 241, 241, 0.95), rgba(254, 226, 226, 0.9));
        backdrop-filter: blur(12px);
        color: #991B1B !important;
        padding: 25px;
        border-radius: 20px;
        border: 1px solid rgba(239, 68, 68, 0.2);
        box-shadow: 0 8px 32px 0 rgba(239, 68, 68, 0.08);
        transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
    }
    .vibrant-card:hover { transform: translateY(-8px); border-color: #EF4444; box-shadow: 0 15px 35px rgba(239, 68, 68, 0.15); }
    .vibrant-card h4 { color: #991B1B !important; margin-bottom: 10px; }
    .vibrant-card p { color: #7F1D1D !important; line-height: 1.6; }

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
        background: linear-gradient(135deg, rgba(254, 242, 242, 0.95) 0%, rgba(254, 226, 226, 0.95) 100%);
        backdrop-filter: blur(8px);
        color: #991B1B !important;
        padding: 30px;
        border-radius: 28px;
        text-align: center;
        border: 1px solid rgba(239, 68, 68, 0.25);
        box-shadow: 0 15px 35px -5px rgba(239, 68, 68, 0.12), 0 5px 15px rgba(0, 0, 0, 0.03);
    }
    .target-user-card h3 { color: #991B1B !important; font-weight: 800; }
    .target-user-card p { color: #7F1D1D !important; opacity: 0.9; }

    /* ════════════════════════════════ FLOATING HELP WIDGET ════════════════════════════════ */
    .help-icon-float {
        position: fixed;
        bottom: 24px;
        right: 24px;
        width: 54px;
        height: 54px;
        border-radius: 50%;
        background: linear-gradient(135deg, #FF1744 0%, #D32F2F 100%);
        color: white;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        font-size: 1.8rem;
        text-decoration: none;
        box-shadow: 0 10px 28px rgba(255, 23, 68, 0.35);
        z-index: 998;
        transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
        filter: drop-shadow(0 4px 12px rgba(255, 23, 68, 0.25));
        border: 2px solid rgba(255, 255, 255, 0.15);
    }
    .help-icon-float:hover {
        transform: scale(1.15) translateY(-4px);
        box-shadow: 0 14px 36px rgba(255, 23, 68, 0.42);
        filter: drop-shadow(0 6px 16px rgba(255, 23, 68, 0.32));
        border-color: rgba(255, 255, 255, 0.3);
    }

    /* ════════════════════════════════ HELP PAGE STYLES ════════════════════════════════ */
    .help-page-hero {
        text-align: center;
        padding: 32px 20px;
        background: linear-gradient(135deg, #FFE5E9 0%, #FFEBEE 100%);
        border-radius: 16px;
        margin-bottom: 32px;
        border: 1px solid rgba(255, 23, 68, 0.15);
    }
    .help-page-hero h1 {
        margin: 0 0 8px 0;
        color: #0F172A;
        font-size: 2.2rem;
        font-weight: 800;
        font-family: 'Outfit', sans-serif;
    }
    .help-page-hero p {
        margin: 0;
        color: #475569;
        font-size: 1.05rem;
    }
    .help-section-card {
        background: linear-gradient(135deg, #FFFFFF 0%, #F8FAFC 100%);
        border-radius: 12px;
        padding: 24px;
        margin-bottom: 20px;
        border: 1px solid #E2E8F0;
        box-shadow: 0 4px 12px rgba(15, 23, 42, 0.06);
        transition: all 0.3s ease;
    }
    .help-section-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 20px rgba(15, 23, 42, 0.1);
        border-color: #CBD5E1;
    }
    .help-section-card h3 {
        margin: 0 0 12px 0;
        color: #0F172A;
        font-size: 1.3rem;
        font-weight: 700;
        font-family: 'Outfit', sans-serif;
    }
    .help-section-card p {
        margin: 0 0 10px 0;
        color: #475569;
        font-size: 0.95rem;
        line-height: 1.6;
    }
    .help-feature-list {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
        gap: 10px;
        margin-top: 14px;
    }
    .help-feature-item {
        background: linear-gradient(135deg, #FFE5E9 0%, #FFCDD2 100%);
        padding: 10px 14px;
        border-radius: 8px;
        font-size: 0.85rem;
        font-weight: 600;
        color: #C62828;
        text-align: center;
        border: 1px solid rgba(198, 40, 40, 0.2);
    }

    .glow-text {
        text-shadow: 0 0 10px rgba(59, 130, 246, 0.5);
        color: #3B82F6 !important;
        font-weight: 700;
    }
    
    .faq-card {
        background: #FFFFFF;
        padding: 24px;
        border-radius: 20px;
        border: 1px solid rgba(0, 0, 0, 0.05);
        margin-bottom: 20px;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.04), 0 8px 10px -6px rgba(0, 0, 0, 0.04);
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .faq-card:hover { 
        transform: translateY(-4px); 
        box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
        border-color: #FEE2E2;
    }

    @keyframes pulse-red {
        0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.7); }
        70% { transform: scale(1); box-shadow: 0 0 0 10px rgba(239, 68, 68, 0); }
        100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
    }
    .pulse-dot {
        height: 12px; width: 12px;
        background-color: #EF4444;
        border-radius: 50%;
        display: inline-block;
        animation: pulse-red 2s infinite;
        margin-right: 10px;
    }
    @keyframes pulse-green {
        0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.7); }
        70% { transform: scale(1); box-shadow: 0 0 0 10px rgba(34, 197, 94, 0); }
        100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(34, 197, 94, 0); }
    }
    .pulse-dot-green {
        height: 12px; width: 12px;
        background-color: #22C55E;
        border-radius: 50%;
        display: inline-block;
        animation: pulse-green 2s infinite;
        margin-right: 10px;
    }

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
        background: linear-gradient(135deg, #FFF8F8 0%, #FEE2E2 100%);
        color: #991B1B !important;
        padding: 45px;
        border-radius: 32px;
        text-align: center;
        box-shadow: 0 20px 40px -15px rgba(239, 68, 68, 0.15), inset 0 0 0 1px rgba(255, 255, 255, 0.5);
        border: 1px solid rgba(239, 68, 68, 0.2);
        margin-bottom: 40px;
    }
    .red-hero-card h1 { 
        color: #991B1B !important; 
        font-weight: 950; 
        letter-spacing: 0px; 
        line-height: 1.2;
    }
    .red-hero-card p { color: #7F1D1D !important; font-size: 1.25rem; font-weight: 500; }

    .creative-red-card {
        background: rgba(255, 255, 255, 0.7);
        backdrop-filter: blur(10px);
        border: 1px solid #E2E8F0;
        border-top: 5px solid #EF4444;
        border-radius: 24px;
        padding: 25px;
        height: 100%;
        transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        box-shadow: 0 4px 15px -1px rgba(0, 0, 0, 0.03);
    }
    .creative-red-card:hover {
        transform: scale(1.03) translateY(-10px);
        box-shadow: 0 25px 45px -10px rgba(239, 68, 68, 0.12);
        border-color: #EF4444;
    }
    .creative-red-card h4 { color: #991B1B !important; }
    
    /* Glassy card variants */
    .glassy-card-indigo {
        background: linear-gradient(135deg, rgba(238, 242, 255, 0.8) 0%, rgba(224, 231, 255, 0.7) 100%);
        backdrop-filter: blur(10px);
        border: 2px solid rgba(99, 102, 241, 0.3);
        border-radius: 24px;
        padding: 32px;
        height: 100%;
        transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        box-shadow: 0 8px 24px rgba(99, 102, 241, 0.1);
    }
    .glassy-card-indigo:hover {
        transform: scale(1.03) translateY(-12px);
        box-shadow: 0 25px 50px rgba(99, 102, 241, 0.2);
        border-color: rgba(99, 102, 241, 0.6);
    }
    .glassy-card-indigo h3 { color: #3730A3 !important; font-weight: 800; }
    .glassy-card-indigo p { color: #4C51BF !important; }

    .glassy-card-purple {
        background: linear-gradient(135deg, rgba(245, 243, 255, 0.8) 0%, rgba(233, 213, 255, 0.7) 100%);
        backdrop-filter: blur(10px);
        border: 2px solid rgba(139, 92, 246, 0.3);
        border-radius: 24px;
        padding: 32px;
        height: 100%;
        text-align: center;
        transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        box-shadow: 0 8px 24px rgba(139, 92, 246, 0.1);
    }
    .glassy-card-purple:hover {
        transform: scale(1.03) translateY(-12px);
        box-shadow: 0 25px 50px rgba(139, 92, 246, 0.2);
        border-color: rgba(139, 92, 246, 0.6);
    }
    .glassy-card-purple h2, .glassy-card-purple h3 { color: #6D28D9 !important; font-weight: 800; }
    .glassy-card-purple p { color: #7C3AED !important; }

    .glassy-card-teal {
        background: linear-gradient(135deg, rgba(240, 253, 250, 0.8) 0%, rgba(204, 251, 241, 0.7) 100%);
        backdrop-filter: blur(10px);
        border: 2px solid rgba(16, 185, 129, 0.3);
        border-radius: 24px;
        padding: 32px;
        height: 100%;
        transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        box-shadow: 0 8px 24px rgba(16, 185, 129, 0.1);
    }
    .glassy-card-teal:hover {
        transform: scale(1.03) translateY(-12px);
        box-shadow: 0 25px 50px rgba(16, 185, 129, 0.2);
        border-color: rgba(16, 185, 129, 0.6);
    }
    .glassy-card-teal h3 { color: #0D9488 !important; font-weight: 800; }
    .glassy-card-teal p { color: #059669 !important; }
    
    .pill-red { background-color: #FEE2E2; color: #991B1B; border: 1px solid #FCA5A5; }

    .icon-zoom {
        font-size: 3rem;
        margin-bottom: 20px;
        display: inline-block;
        filter: drop-shadow(0 10px 15px rgba(239, 68, 68, 0.25));
        transition: all 0.5s ease;
    }
    .icon-zoom:hover { transform: scale(1.2) rotate(5deg); }

    .tech-badge {
        display: inline-block;
        padding: 6px 14px;
        background: #F1F5F9;
        color: #475569;
        border-radius: 99px;
        font-size: 0.85rem;
        font-weight: 600;
        border: 1px solid #E2E8F0;
        margin: 4px;
        transition: all 0.3s ease;
    }
    .tech-badge:hover { background: #EF4444; color: white; border-color: #EF4444; }

    /* Premium bright table palette (single theme) */
    .pt-wrap {
        overflow: auto;
        border: 1px solid #B6D8FF;
        border-radius: 14px;
        box-shadow: 0 10px 24px rgba(37, 99, 235, 0.12);
        background: #FFFFFF;
    }
    .pt-table {
        width: 100%;
        border-collapse: separate;
        border-spacing: 0;
        min-width: 760px;
        font-family: 'Inter', sans-serif;
        table-layout: auto;
    }
    .pt-table thead th {
        position: sticky;
        top: 0;
        z-index: 2;
        padding: 9px 10px;
        text-align: left;
        color: #FFFFFF;
        font-weight: 700;
        border-right: 1px solid rgba(255,255,255,0.18);
        background: linear-gradient(135deg, #2563EB 0%, #0EA5E9 100%);
        letter-spacing: 0.2px;
        font-size: 0.96rem;
    }
    .pt-table thead th:last-child { border-right: none; }
    .pt-table tbody td {
        padding: 8px 10px;
        border-bottom: 1px solid #E5F0FF;
        border-right: 1px solid #EEF5FF;
        color: #0F172A;
        font-size: 0.87rem;
        line-height: 1.3;
        white-space: normal;
    }
    .pt-table tbody td:last-child { border-right: none; }
    .pt-table tbody tr:nth-child(odd) td {
        background: #F8FBFF;
    }
    .pt-table tbody tr:nth-child(even) td {
        background: #EEF6FF;
    }
    .pt-table tbody tr:hover td {
        background: #DBEAFE !important;
    }
    .pt-table td.num {
        text-align: right;
        font-variant-numeric: tabular-nums;
        font-weight: 600;
        color: #1E3A8A;
    }
    .pt-table td.text {
        text-align: left;
        word-break: break-word;
    }
    .pt-table th.linkcol,
    .pt-table td.linkcol {
        width: 128px;
        min-width: 128px;
        max-width: 128px;
        text-align: center;
        white-space: nowrap;
    }
    .pt-link {
        display: inline-block;
        text-decoration: none;
        color: #FFFFFF !important;
        background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%);
        border: 1px solid #1E40AF;
        border-radius: 999px;
        padding: 3px 8px;
        font-size: 0.75rem;
        font-weight: 700;
        line-height: 1.2;
    }
    .pt-link:hover {
        background: linear-gradient(135deg, #1D4ED8 0%, #1E3A8A 100%);
        box-shadow: 0 4px 10px rgba(37, 99, 235, 0.35);
    }

    /* Two link tables: force full-content readability at 100% zoom */
    #top_viewed_links .pt-table,
    #top_liked_links .pt-table {
        min-width: 100%;
        table-layout: fixed;
    }
    #top_viewed_links .pt-table th:first-child,
    #top_liked_links .pt-table th:first-child {
        width: calc(100% - 128px);
    }
    #top_viewed_links .pt-table td.text,
    #top_liked_links .pt-table td.text {
        white-space: normal;
        overflow: visible;
        text-overflow: clip;
        word-break: break-word;
        line-height: 1.28;
    }
    #top_viewed_links .pt-table th.linkcol,
    #top_viewed_links .pt-table td.linkcol,
    #top_liked_links .pt-table th.linkcol,
    #top_liked_links .pt-table td.linkcol {
        position: sticky;
        right: 0;
        z-index: 4;
    }
    #top_viewed_links .pt-table thead th.linkcol,
    #top_liked_links .pt-table thead th.linkcol {
        z-index: 6;
        border-left: 1px solid rgba(255,255,255,0.25);
    }
    #top_viewed_links .pt-table tbody tr:nth-child(odd) td.linkcol,
    #top_liked_links .pt-table tbody tr:nth-child(odd) td.linkcol {
        background: #F8FBFF !important;
        border-left: 1px solid #CFE4FF;
    }
    #top_viewed_links .pt-table tbody tr:nth-child(even) td.linkcol,
    #top_liked_links .pt-table tbody tr:nth-child(even) td.linkcol {
        background: #EEF6FF !important;
        border-left: 1px solid #CFE4FF;
    }
    #top_viewed_links .pt-table tbody tr:hover td.linkcol,
    #top_liked_links .pt-table tbody tr:hover td.linkcol {
        background: #DBEAFE !important;
    }

    /* Raw data table: fit all columns in viewport at 100% zoom */
    #raw_data_table .pt-table {
        min-width: 100%;
        width: 100%;
        table-layout: fixed;
    }
    #raw_data_table .pt-table thead th {
        font-size: 0.93rem;
    }
    #raw_data_table .pt-table tbody td {
        font-size: 0.86rem;
    }
    #raw_data_table .pt-table th:nth-child(1),
    #raw_data_table .pt-table td:nth-child(1) { width: 52%; }
    #raw_data_table .pt-table th:nth-child(2),
    #raw_data_table .pt-table td:nth-child(2) { width: 11%; }
    #raw_data_table .pt-table th:nth-child(3),
    #raw_data_table .pt-table td:nth-child(3) { width: 8%; }
    #raw_data_table .pt-table th:nth-child(4),
    #raw_data_table .pt-table td:nth-child(4) { width: 7%; }
    #raw_data_table .pt-table th:nth-child(5),
    #raw_data_table .pt-table td:nth-child(5) { width: 9%; }
    #raw_data_table .pt-table th:nth-child(6),
    #raw_data_table .pt-table td:nth-child(6) { width: 5%; }
    #raw_data_table .pt-table th:nth-child(7),
    #raw_data_table .pt-table td:nth-child(7) {
        width: 8%;
        min-width: 118px;
    }
    #raw_data_table .pt-table td.text {
        max-width: 100%;
        white-space: normal;
        word-break: break-word;
        line-height: 1.3;
    }
    #raw_data_table .pt-table th.linkcol,
    #raw_data_table .pt-table td.linkcol {
        position: sticky;
        right: 0;
        z-index: 4;
        text-align: center;
        border-left: 1px solid #CFE4FF;
    }
    #raw_data_table .pt-table thead th.linkcol {
        z-index: 6;
        border-left: 1px solid rgba(255,255,255,0.25);
    }
    #raw_data_table .pt-table tbody tr:nth-child(odd) td.linkcol {
        background: #F8FBFF !important;
    }
    #raw_data_table .pt-table tbody tr:nth-child(even) td.linkcol {
        background: #EEF6FF !important;
    }
    #raw_data_table .pt-table tbody tr:hover td.linkcol {
        background: #DBEAFE !important;
    }
    #raw_data_table .pt-link {
        font-size: 0.72rem;
        padding: 3px 7px;
    }

    /* Compare page tables: mirror raw data readability */
    #compare_leaderboard_table .pt-table,
    #compare_trend_summary_table .pt-table {
        min-width: 100%;
        width: 100%;
        table-layout: fixed;
    }
    #compare_leaderboard_table .pt-table thead th,
    #compare_trend_summary_table .pt-table thead th {
        font-size: 0.93rem;
    }
    #compare_leaderboard_table .pt-table tbody td,
    #compare_trend_summary_table .pt-table tbody td {
        font-size: 0.86rem;
    }
    #compare_leaderboard_table .pt-table th:nth-child(1),
    #compare_leaderboard_table .pt-table td:nth-child(1) { width: 8%; }
    #compare_leaderboard_table .pt-table th:nth-child(2),
    #compare_leaderboard_table .pt-table td:nth-child(2) { width: 34%; }
    #compare_leaderboard_table .pt-table th:nth-child(3),
    #compare_leaderboard_table .pt-table td:nth-child(3) { width: 16%; }
    #compare_leaderboard_table .pt-table th:nth-child(4),
    #compare_leaderboard_table .pt-table td:nth-child(4) { width: 20%; }
    #compare_leaderboard_table .pt-table th:nth-child(5),
    #compare_leaderboard_table .pt-table td:nth-child(5) { width: 12%; }
    #compare_leaderboard_table .pt-table th:nth-child(6),
    #compare_leaderboard_table .pt-table td:nth-child(6) { width: 10%; }
    #compare_leaderboard_table .pt-table td.text,
    #compare_trend_summary_table .pt-table td.text {
        white-space: normal;
        word-break: break-word;
        line-height: 1.3;
    }

    /* Compare visuals: bright palette + smooth motion */
    @keyframes compare-fade-up {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }
    .compare-hero {
        text-align: center;
        padding: 14px 14px 24px 14px;
        animation: compare-fade-up 0.55s ease-out;
    }
    .compare-hero h2 {
        margin: 0 0 4px 0;
        color: #0F172A;
        font-family: 'Outfit', sans-serif;
        font-weight: 800;
        letter-spacing: 0.01em;
    }
    .compare-hero p {
        margin: 0;
        color: #475569;
        font-size: 1rem;
    }
    .compare-super-heading {
        border-left: 4px solid #0284C7;
        padding: 10px 14px;
        margin: 20px 0 10px 0;
        background: linear-gradient(90deg, #E0F2FE 0%, rgba(224,242,254,0) 100%);
        border-radius: 8px;
        animation: compare-fade-up 0.45s ease-out;
    }
    .compare-perf-card {
        padding: 20px;
        border-radius: 14px;
        border: 1px solid #C7D2FE;
        text-align: center;
        background: linear-gradient(160deg, #EFF6FF 0%, #FFFFFF 100%);
        box-shadow: 0 10px 22px rgba(37, 99, 235, 0.12);
        transition: transform 0.25s ease, box-shadow 0.25s ease;
        animation: compare-fade-up 0.5s ease-out;
    }
    .compare-perf-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 14px 28px rgba(37, 99, 235, 0.18);
    }
    .compare-pill {
        display: inline-block;
        margin-top: 4px;
        padding: 3px 11px;
        border-radius: 999px;
        font-size: 0.8rem;
        font-weight: 700;
    }
    .compare-pill-pos { background: #DCFCE7; color: #166534; border: 1px solid #86EFAC; }
    .compare-pill-neg { background: #FEE2E2; color: #991B1B; border: 1px solid #FCA5A5; }

    .compare-export-card {
        border-radius: 14px;
        padding: 18px 16px;
        min-height: 124px;
        border: 1px solid;
        box-shadow: 0 10px 18px rgba(15, 23, 42, 0.08);
        transition: transform 0.25s ease, box-shadow 0.25s ease;
        animation: compare-fade-up 0.6s ease-out;
    }
    .compare-export-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 14px 26px rgba(15, 23, 42, 0.12);
    }
    .compare-export-card h4 {
        margin: 0;
        font-size: 0.96rem;
        font-weight: 800;
        font-family: 'Outfit', sans-serif;
    }
    .compare-export-card p {
        margin: 6px 0 0 0;
        font-size: 0.82rem;
        opacity: 0.9;
    }
    .compare-export-blue { background: linear-gradient(135deg, #EFF6FF 0%, #DBEAFE 100%); border-color: #93C5FD; }
    .compare-export-blue h4, .compare-export-blue p { color: #1E3A8A !important; }
    .compare-export-violet { background: linear-gradient(135deg, #F5F3FF 0%, #EDE9FE 100%); border-color: #C4B5FD; }
    .compare-export-violet h4, .compare-export-violet p { color: #5B21B6 !important; }
    .compare-export-amber { background: linear-gradient(135deg, #FFFBEB 0%, #FEF3C7 100%); border-color: #FCD34D; }
    .compare-export-amber h4, .compare-export-amber p { color: #92400E !important; }

    .intel-box {
        background: rgba(239, 68, 68, 0.05);
        border-left: 4px solid #EF4444;
        padding: 15px;
        border-radius: 8px;
        margin-top: 10px;
    }
    .intel-box b { color: #991B1B; display: block; margin-bottom: 5px; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 1px; }

    /* ════════════════════════════════
       PROFESSIONAL TAB NAVIGATION BAR
       ════════════════════════════════ */

    /* Tab strip container invisible */
    div[data-testid="stTabs"] > div[data-baseweb="tab-list"],
    div[data-testid="stTabs"] > div:first-child {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        gap: 12px !important; /* Space between pills */
        padding: 0 !important;
    }

    /* Standalone Pill tab buttons */
    button[role="tab"] {
        font-family: 'Outfit', sans-serif !important;
        font-size: 0.9rem !important;
        font-weight: 600 !important;
        color: #475569 !important;
        background: #F1F5F9 !important;
        border: 1px solid #E2E8F0 !important;
        border-radius: 99px !important; /* Full rounded pill */
        padding: 10px 24px !important;
        box-shadow: none !important;
        transition: all 0.3s ease !important;
        margin: 0 !important;
    }

    /* Hover pill */
    button[role="tab"]:hover {
        background: #E2E8F0 !important;
        color: #1E293B !important;
        border-color: #CBD5E1 !important;
        transform: translateY(-2px);
    }

    /* Active pill */
    button[role="tab"][aria-selected="true"] {
        background: linear-gradient(135deg, #6366F1 0%, #8B5CF6 100%) !important;
        color: #FFFFFF !important;
        font-weight: 700 !important;
        border: 1px solid rgba(139,92,246,0.5) !important;
        box-shadow: 0 6px 20px rgba(99,102,241,0.4) !important;
    }

    /* Hide the default red underline / ink bar completely */
    div[data-testid="stTabs"] button[role="tab"]::after,
    div[data-testid="stTabs"] [data-baseweb="tab-highlight"],
    div[data-baseweb="tab-highlight"] {
        display: none !important;
        background: transparent !important;
    }

    button[role="tab"]::after {
        display: none !important;
        background: transparent !important;
    }

</style>

""", unsafe_allow_html=True)

# --- NAVIGATION STATE ---
if 'page' not in st.session_state: st.session_state['page'] = 'dash'
if 'active_channel_id' not in st.session_state: st.session_state['active_channel_id'] = None
if 'gp_explore' not in st.session_state: st.session_state['gp_explore'] = False

if st.query_params.get("home") == "1":
    st.session_state['page'] = 'dash'
    st.session_state['active_channel_id'] = None
    st.session_state['gp_explore'] = False
    st.query_params.clear()
    st.rerun()

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
if 'b_bench_ch' not in st.session_state: st.session_state['b_bench_ch'] = None
if 'b_trend_ch' not in st.session_state: st.session_state['b_trend_ch'] = []
if 'b_trend_m'  not in st.session_state: st.session_state['b_trend_m']  = 'Views'
if 'b_trend_t'  not in st.session_state: st.session_state['b_trend_t']  = 'Grouped Bar'

# Compare Page
if 'c_bench_ch' not in st.session_state: st.session_state['c_bench_ch']  = None
if 'c_trend_ch' not in st.session_state: st.session_state['c_trend_ch']  = []
if 'c_trend_m'  not in st.session_state: st.session_state['c_trend_m']   = 'Views'
if 'c_trend_t'  not in st.session_state: st.session_state['c_trend_t']   = 'Grouped Bar'
if 'c_rank_by'  not in st.session_state: st.session_state['c_rank_by']   = 'Subscribers'

# --- SIDEBAR ---
with st.sidebar:
    cur_page = st.session_state['page']
    st.markdown("""
        <a class='sb-brand-link' href='?home=1' target='_self'>
            <div class='sb-brand'>
                <span class='sb-menu'>▶</span>
                <span class='sb-title'>YT Analytics</span>
            </div>
        </a>
    """, unsafe_allow_html=True)
    st.markdown("<div class='sb-section-label'>Channel Setup</div>", unsafe_allow_html=True)
    channel_id_input = st.text_input("Channel ID", placeholder="UC_x5XG1OV2P6uZZ5FSM9Ttw")
    fetch_button = st.button("🚀 Run Analysis", type="primary", use_container_width=True)
    
    recent_hub_btn = st.button("☷  Channel Library", use_container_width=True, help="Explore all synced channels in a gallery view")
    
    if recent_hub_btn:
        st.session_state['page'] = 'recent'
        st.rerun()

    st.divider()
    
    st.markdown("<div class='sb-section-label'>Navigation</div>", unsafe_allow_html=True)
    nav_about = st.button("ℹ️  About Hub", use_container_width=True, type="primary" if cur_page == 'about' else "secondary")
    
    nav_dash = st.button("📈  Dashboard", use_container_width=True, type="primary" if cur_page == 'dash' else "secondary")
    nav_prof = st.button("👤  Profile", use_container_width=True, type="primary" if cur_page == 'profile' else "secondary")
    nav_batt = st.button("⚔️  Battle Arena", use_container_width=True, type="primary" if cur_page == 'battle' else "secondary")
    nav_vis  = st.button("📊  Visuals", use_container_width=True, type="primary" if cur_page == 'vis' else "secondary")
    nav_srch = st.button("🔍  Search", use_container_width=True, type="primary" if cur_page == 'search' else "secondary")
    nav_comp = st.button("📦  Exports", use_container_width=True, type="primary" if cur_page == 'compare' else "secondary")
    nav_help = st.button("❓  Help Center", use_container_width=True, type="primary" if cur_page == 'help' else "secondary")

    if nav_about: 
        st.session_state['page'] = 'about'
        st.rerun()
    if nav_dash: 
        st.session_state['page'] = 'dash'
        st.session_state['gp_explore'] = False
        st.query_params.clear()
        st.rerun()
    if nav_prof: 
        st.session_state['page'] = 'profile'
        st.rerun()
    if nav_batt: 
        st.session_state['page'] = 'battle'
        st.rerun()
    if nav_vis:  
        st.session_state['page'] = 'vis'
        st.rerun()
    if nav_srch: 
        st.session_state['page'] = 'search'
        st.rerun()
    if nav_comp: 
        st.session_state['page'] = 'compare'
        st.rerun()
    if nav_help:
        st.session_state['page'] = 'help'
        st.rerun()
    
    # ══════════════════════════════════════════════════════
    # GLOBAL ANALYTICS FILTERS
    # ══════════════════════════════════════════════════════
    chid = st.session_state.get('active_channel_id')
    if chid:
        df_sb = get_channel_data_from_db(chid)
        if not df_sb.empty:
            df_sb['published_at_dt'] = pd.to_datetime(df_sb['published_at'])
            df_sb['year'] = df_sb['published_at_dt'].dt.year
            
            # Determine year range from channel start year to current year
            start_year = 2005
            if 'c_published' in df_sb.columns and not df_sb['c_published'].empty:
                try:
                    pub_date = str(df_sb['c_published'].iloc[0])
                    if len(pub_date) >= 4:
                        start_year = int(pub_date[:4])
                except Exception:
                    pass
            
            current_year = datetime.now().year
            years_range = list(range(current_year, start_year - 1, -1))
            dropdown_options = ["All Years"] + [str(y) for y in years_range]

            st.divider()
            st.markdown("<div class='sb-section-label'>🎯 Global Analytics Filters</div>", unsafe_allow_html=True)
            
            if 'v_selected_year' not in st.session_state:
                st.session_state['v_selected_year'] = "All Years"

            st.selectbox("📅 Select Year", dropdown_options, key='v_selected_year')

            # Set v_years list based on selectbox
            if st.session_state['v_selected_year'] == "All Years":
                st.session_state['v_years'] = years_range
            else:
                st.session_state['v_years'] = [int(st.session_state['v_selected_year'])]

            st.multiselect("⏱️ Video Type", ["Long-form", "Shorts"], key='v_types')

            # Check if active channel has cached videos for the selected year
            selected_year_val = st.session_state['v_selected_year']
            has_data_for_selected_year = True
            if selected_year_val != "All Years":
                target_year = int(selected_year_val)
                has_data_for_selected_year = any(df_sb['year'] == target_year)

            if not has_data_for_selected_year:
                st.warning(f"⚠️ No cached videos found for {selected_year_val}.")
                if st.button(f"📥 Sync {selected_year_val} Videos", use_container_width=True, type="primary"):
                    with st.status(f"Fetching videos from {selected_year_val}...", expanded=True) as sync_status:
                        sync_status.write("📡 Connecting to YouTube API...")
                        res = store_channel_data_for_year(chid, int(selected_year_val), limit=50)
                        if res['status'] == "Success":
                            st.cache_data.clear()
                            sync_status.update(label="✨ Sync Complete!", state="complete")
                            st.toast(f"Successfully synced videos for {selected_year_val}!")
                            st.rerun()
                        else:
                            sync_status.update(label="❌ Sync Failed", state="error")
                            st.error(res['message'])
            else:
                if selected_year_val != "All Years":
                    st.info(f"💡 {selected_year_val} data is cached in database.")
                    if st.button(f"🗑️ Discard {selected_year_val} Cache", use_container_width=True, type="secondary"):
                        with st.status(f"Discarding cached data for {selected_year_val}...", expanded=True) as discard_status:
                            res = discard_channel_data_for_year(chid, int(selected_year_val))
                            if res['status'] == "Success":
                                st.cache_data.clear()
                                discard_status.update(label="🧹 Cache Purged!", state="complete")
                                st.toast(f"Successfully discarded {selected_year_val} cache!")
                                st.rerun()
                            else:
                                discard_status.update(label="❌ Purge Failed", state="error")
                                st.error(res['message'])

            # Sync check for rivals if Battle Arena is active
            if cur_page == 'battle' and selected_year_val != "All Years":
                selected_rivals = st.session_state.get('b_selected', [])
                if selected_rivals:
                    recent_ch = get_recent_channels(limit=50)
                    id_map = {r['name']: r['id'] for r in recent_ch}
                    sel_ids = [id_map[ch] for ch in selected_rivals if ch in id_map]
                    if sel_ids:
                        target_year = int(selected_year_val)
                        id_str_list = "','".join([cid.replace("'", "''") for cid in sel_ids])
                        q_check = f"""
                            SELECT channel_id, COUNT(*) as cnt 
                            FROM videos 
                            WHERE channel_id IN ('{id_str_list}') 
                              AND published_at LIKE '{target_year}%'
                            GROUP BY channel_id
                        """
                        try:
                            with engine.connect() as conn:
                                db_res = pd.read_sql(text(q_check), conn)
                            synced_ids = set(db_res['channel_id'].tolist())
                        except Exception:
                            synced_ids = set()
                            
                        missing_rivals = []
                        for name in selected_rivals:
                            cid = id_map.get(name)
                            if cid and cid not in synced_ids:
                                missing_rivals.append((name, cid))
                                
                        if missing_rivals:
                            st.warning(f"⚠️ Benchmark channels missing data for {target_year}: {', '.join([r[0] for r in missing_rivals])}")
                            for r_name, r_id in missing_rivals:
                                if st.button(f"📥 Sync {target_year} for {r_name}", key=f"sync_rival_{r_id}_{target_year}", use_container_width=True, type="primary"):
                                    with st.status(f"Syncing {r_name} for {target_year}...", expanded=True) as r_sync_status:
                                        r_sync_status.write(f"📡 Syncing {r_name} from YouTube API...")
                                        res = store_channel_data_for_year(r_id, target_year, limit=50)
                                        if res['status'] == "Success":
                                            st.cache_data.clear()
                                            r_sync_status.update(label="✨ Sync Complete!", state="complete")
                                            st.toast(f"Synced {r_name} for {target_year}!")
                                            st.rerun()
                                        else:
                                            r_sync_status.update(label="❌ Sync Failed", state="error")
                                            st.error(res['message'])

    # ══════════════════════════════════════════════════════
    # DYNAMIC PAGE FILTERS (Milestone 7)
    # ══════════════════════════════════════════════════════
    if cur_page in ['vis', 'search', 'battle', 'compare']:
        st.divider()
        st.markdown(f"""
            <div style='background-color: #F1F5F9; padding: 12px; border-radius: 8px; border-left: 4px solid #FF0000; margin-bottom: 20px;'>
                <p style='margin:0; font-family:Outfit; font-weight:700; color:#1E293B; font-size:1.1rem;'>🎯 Please Filter Here:</p>
            </div>
        """, unsafe_allow_html=True)
        
        # ─── VISUALS PAGE FILTERS ───
        if cur_page == 'vis':
            chid = st.session_state.get('active_channel_id')
            if chid:
                df_sb = get_channel_data_from_db(chid)
                if not df_sb.empty:
                    metric_opt = {"Views": "view_count", "Likes": "like_count", "Comments": "comment_count", "Quality %": "engagement_rate"}
                    st.selectbox("🧪 Primary Metric", list(metric_opt.keys()), key='v_metric')
                    
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
            st.markdown("""
            <style>
            .search-filter-title {
                margin: 0.1rem 0 0.6rem 0;
                padding: 0.72rem 0.9rem;
                border-radius: 12px;
                background: linear-gradient(135deg, #0f766e 0%, #0ea5a4 100%);
                color: #f8fafc;
                text-align: center;
                font-size: 0.98rem;
                font-weight: 800;
                letter-spacing: 0.02em;
                box-shadow: 0 8px 20px rgba(13, 148, 136, 0.24);
                border: 1px solid rgba(255, 255, 255, 0.28);
            }
            .search-filter-section {
                margin: 0.6rem 0 0.38rem 0;
                padding: 0.38rem 0.62rem;
                border-radius: 9px;
                background: linear-gradient(135deg, #f0fdfa 0%, #ccfbf1 100%);
                color: #0f172a;
                font-size: 0.79rem;
                font-weight: 800;
                letter-spacing: 0.04em;
                text-transform: uppercase;
                border-left: 4px solid #0f766e;
            }
            .search-filter-note {
                margin: 0.16rem 0 0.5rem 0;
                font-size: 0.72rem;
                color: #475569;
                text-align: center;
            }
            .search-filter-divider {
                border: 0;
                height: 1px;
                margin: 0.55rem 0 0.45rem 0;
                background: linear-gradient(90deg, rgba(15,118,110,0.0), rgba(15,118,110,0.45), rgba(15,118,110,0.0));
            }
            </style>
            """, unsafe_allow_html=True)

            st.markdown("<div class='search-filter-title'>Search Controls</div>", unsafe_allow_html=True)
            st.markdown("<div class='search-filter-note'>Refine your video results with keyword, range, and quality filters</div>", unsafe_allow_html=True)

            st.markdown("<div class='search-filter-section'>Keyword</div>", unsafe_allow_html=True)
            st.text_input("🔎 Search Keyword", value=st.session_state['sf_query'], key='_sf_q_input')

            st.markdown("<hr class='search-filter-divider' />", unsafe_allow_html=True)
            st.markdown("<div class='search-filter-section'>Views & Time Window</div>", unsafe_allow_html=True)
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

            st.markdown("<hr class='search-filter-divider' />", unsafe_allow_html=True)
            st.markdown("<div class='search-filter-section'>Quality & Duration</div>", unsafe_allow_html=True)
            st.multiselect("💎 Engagement", ['High', 'Medium', 'Low'], default=st.session_state['sf_eng'], key='_sf_eng_sel')
            st.multiselect("⏱️ Duration", ['Short (<5m)', 'Medium (5-15m)', 'Long (>15m)'], default=st.session_state['sf_dur'], key='_sf_dur_sel')

            st.markdown("<hr class='search-filter-divider' />", unsafe_allow_html=True)
            st.markdown("<div class='search-filter-section'>Sort Results</div>", unsafe_allow_html=True)
            sort_options = ['Views (High → Low)', 'Views (Low → High)', 'Likes (High → Low)',
                            'Date (Newest)', 'Date (Oldest)', 'Engagement (High → Low)',
                            'Duration (Longest)', 'Comments (High → Low)']
            st.selectbox("🔀 Sort By", sort_options, 
                         index=sort_options.index(st.session_state['sf_sort']) if st.session_state['sf_sort'] in sort_options else 0,
                         key='_sf_sort_sel')

            st.markdown("<hr class='search-filter-divider' />", unsafe_allow_html=True)
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
            render_help_widget('battle')
            recent_ch = get_recent_channels(limit=50)
            if recent_ch:
                st.markdown("""
                <style>
                .compare-filter-section {
                    margin: 0.6rem 0 0.38rem 0;
                    padding: 0.38rem 0.62rem;
                    border-radius: 9px;
                    background: linear-gradient(135deg, #E0F2FE 0%, #BAE6FD 100%);
                    color: #0f172a;
                    font-size: 0.79rem;
                    font-weight: 800;
                    letter-spacing: 0.04em;
                    text-transform: uppercase;
                    border-left: 4px solid #0284c7;
                }
                .compare-filter-divider {
                    border: 0;
                    height: 1px;
                    margin: 0.55rem 0 0.45rem 0;
                    background: linear-gradient(90deg, rgba(2,132,199,0.0), rgba(2,132,199,0.45), rgba(2,132,199,0.0));
                }
                </style>
                """, unsafe_allow_html=True)

                ch_names = [r['name'] for r in recent_ch]
                selected_rivals = st.multiselect("🤜 Select Rivals", ch_names, 
                               key='b_selected',
                               max_selections=6)
                
                # Show selection status with persistent indicator
                if selected_rivals and len(selected_rivals) >= 2:
                    st.success(f"✅ {len(selected_rivals)} rivals selected and saved to session. These will be included in your PDF report.")
                elif selected_rivals:
                    st.info(f"⏳ {len(selected_rivals)} rival selected. Select at least 2 to enable Battle charts in PDF report.")
                else:
                    st.info("👉 Select 2-6 rivals to create Battle Arena comparison charts (automatically saved to session).")

                st.markdown("<hr class='compare-filter-divider' />", unsafe_allow_html=True)
                st.markdown("<div class='compare-filter-section'>Benchmark Setup</div>", unsafe_allow_html=True)
                # Default benchmark to the currently analyzed channel when channel context changes.
                active_id = st.session_state.get('active_channel_id')
                active_name = next((r['name'] for r in recent_ch if r['id'] == active_id), None)
                if active_name and st.session_state.get('b_bench_source_id') != active_id:
                    st.session_state['b_bench_ch'] = active_name
                    st.session_state['b_bench_source_id'] = active_id
                elif st.session_state.get('b_bench_ch') not in ch_names:
                    st.session_state['b_bench_ch'] = active_name if active_name else ch_names[0]
                st.selectbox("🎯 Benchmark Channel", ch_names, key='b_bench_ch')

                st.markdown("<hr class='compare-filter-divider' />", unsafe_allow_html=True)
                st.markdown("<div class='compare-filter-section'>Trend Chart Settings</div>", unsafe_allow_html=True)
                st.caption("Trend Comparison automatically uses channels from Select Rivals.")
                trend_metric_opts_b = ['Views', 'Likes', 'Comments']
                st.selectbox("📊 Trend Metric", trend_metric_opts_b, key='b_trend_m')

                chart_types_b = ['Grouped Bar', 'Line + Markers', 'Area']
                st.selectbox("📉 Chart Style", chart_types_b, key='b_trend_t')
                
                st.divider()
                if st.button("⚔️ Download Full Battle Report", use_container_width=True, type="primary"):
                    try:
                        selected = st.session_state.get('b_selected', [])
                        if len(selected) < 2:
                            st.error("Select at least 2 rivals to generate the Battle report.")
                        else:
                            from fpdf import FPDF

                            bench_channel = st.session_state.get('b_bench_ch')
                            trend_metric_label = st.session_state.get('b_trend_m', 'Views')
                            chart_type = st.session_state.get('b_trend_t', 'Grouped Bar')
                            trend_metric_opts = {'Views': 'view_count', 'Likes': 'like_count', 'Comments': 'comment_count'}
                            trend_metric = trend_metric_opts.get(trend_metric_label, 'view_count')

                            id_map = {r['name']: r['id'] for r in recent_ch}
                            sel_ids = [id_map[ch] for ch in selected if ch in id_map]
                            id_str = "','".join([cid.replace("'", "''") for cid in sel_ids])

                            q_ch = f"SELECT channel_name, subscribers, views, total_videos FROM channels WHERE channel_id IN ('{id_str}')"
                            q_vids = f"""
                                SELECT c.channel_name, v.published_at, s.view_count, s.like_count, s.comment_count
                                FROM videos v
                                JOIN channels c ON v.channel_id = c.channel_id
                                JOIN video_statistics s ON v.video_id = s.video_id
                                WHERE v.channel_id IN ('{id_str}')
                                  AND s.captured_at = (SELECT MAX(s2.captured_at) FROM video_statistics s2 WHERE s2.video_id = v.video_id)
                            """
                            q_db_avg = "SELECT AVG(subscribers) avg_sub, AVG(views) avg_view, AVG(total_videos) avg_vid FROM channels"

                            with engine.connect() as conn:
                                cdf_p = pd.read_sql(text(q_ch), conn)
                                v_df_p = pd.read_sql(text(q_vids), conn)
                                db_avg_row = pd.read_sql(text(q_db_avg), conn).iloc[0]

                            if cdf_p.empty:
                                st.error("No data found for selected rivals.")
                            else:
                                # Channel quality map for report metrics
                                if not v_df_p.empty:
                                    ch_agg_p = v_df_p.groupby('channel_name')[['view_count', 'like_count', 'comment_count']].sum().reset_index()
                                    ch_agg_p['quality'] = (ch_agg_p['like_count'] + ch_agg_p['comment_count']) / ch_agg_p['view_count'].replace(0, 1) * 100
                                else:
                                    ch_agg_p = pd.DataFrame(columns=['channel_name', 'quality'])

                                pdf = FPDF()
                                pdf.add_page()
                                pdf.set_auto_page_break(auto=True, margin=15)

                                # Header
                                pdf.set_fill_color(30, 41, 59)
                                pdf.rect(0, 0, 210, 24, 'F')
                                pdf.set_font('Helvetica', 'B', 15)
                                pdf.set_text_color(255, 255, 255)
                                pdf.set_y(6)
                                pdf.cell(0, 10, 'BATTLE ARENA: COMPREHENSIVE PERFORMANCE REPORT', align='C', ln=True)
                                pdf.ln(12)
                                pdf.set_font('Helvetica', 'B', 11)
                                pdf.set_text_color(71, 85, 105)
                                pdf.cell(0, 8, f"Rivals: {', '.join(selected)}", ln=True)
                                pdf.cell(0, 8, f"Benchmark Channel: {bench_channel if bench_channel else 'Not selected'}", ln=True)
                                pdf.cell(0, 8, f"Trend Metric/Style: {trend_metric_label} / {chart_type}", ln=True)
                                pdf.ln(3)

                                # 1) Audience & Reach
                                pdf.set_font('Helvetica', 'B', 11)
                                pdf.set_text_color(30, 41, 59)
                                pdf.cell(0, 8, '1. Audience and Reach Battle', ln=True)
                                fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
                                sub_colors = ['#7C3AED' if ch == bench_channel else '#3B82F6' for ch in cdf_p['channel_name']]
                                view_colors = ['#A855F7' if ch == bench_channel else '#EF4444' for ch in cdf_p['channel_name']]
                                ax1.bar(cdf_p['channel_name'], cdf_p['subscribers'], color=sub_colors)
                                ax1.set_title('Subscribers (Log)')
                                ax1.set_yscale('log')
                                ax1.tick_params(axis='x', rotation=30)
                                ax2.bar(cdf_p['channel_name'], cdf_p['views'], color=view_colors)
                                ax2.set_title('Total Views (Log)')
                                ax2.set_yscale('log')
                                ax2.tick_params(axis='x', rotation=30)
                                plt.tight_layout()
                                plt.savefig('pdf_battle_reach.png', dpi=120)
                                plt.close()
                                pdf.image('pdf_battle_reach.png', x=10, w=190)
                                os.remove('pdf_battle_reach.png')
                                pdf.ln(4)

                                # 2) Benchmark analysis (vs DB average)
                                if bench_channel and bench_channel in cdf_p['channel_name'].values:
                                    pdf.set_font('Helvetica', 'B', 11)
                                    pdf.cell(0, 8, f"2. Benchmark Ratio Analysis ({bench_channel})", ln=True)
                                    b_row = cdf_p[cdf_p['channel_name'] == bench_channel].iloc[0]
                                    b_quality = 0.0
                                    if not ch_agg_p.empty and bench_channel in ch_agg_p['channel_name'].values:
                                        b_quality = float(ch_agg_p[ch_agg_p['channel_name'] == bench_channel]['quality'].iloc[0])
                                    db_quality = float(ch_agg_p['quality'].mean()) if not ch_agg_p.empty else 0.0

                                    metrics = ['Subscribers', 'Total Views', 'Engagement %', 'Total Videos']
                                    vals = [b_row['subscribers'], b_row['views'], b_quality, b_row['total_videos']]
                                    avgs = [db_avg_row['avg_sub'], db_avg_row['avg_view'], db_quality, db_avg_row['avg_vid']]
                                    ratios = [v / max(a, 0.01) for v, a in zip(vals, avgs)]

                                    plt.figure(figsize=(10, 4.2))
                                    x_idx = np.arange(len(metrics))
                                    w = 0.35
                                    plt.bar(x_idx - w/2, ratios, w, label=bench_channel, color='#7C3AED')
                                    plt.bar(x_idx + w/2, [1.0] * len(metrics), w, label='Database Avg', color='#CBD5E1')
                                    plt.axhline(1.0, color='#EF4444', linestyle='--', linewidth=1.2)
                                    plt.xticks(x_idx, metrics, fontsize=9)
                                    plt.ylabel('Ratio (1.0 = Average)', fontsize=9)
                                    plt.title('Benchmark Multipliers', fontsize=12)
                                    plt.grid(axis='y', linestyle=':', alpha=0.3)
                                    plt.legend(fontsize=8)
                                    plt.tight_layout()
                                    plt.savefig('pdf_battle_benchmark.png', dpi=120)
                                    plt.close()
                                    pdf.image('pdf_battle_benchmark.png', x=10, w=190)
                                    os.remove('pdf_battle_benchmark.png')
                                    pdf.ln(4)

                                # 3) Trend comparison (uses Select Rivals only)
                                pdf.set_font('Helvetica', 'B', 11)
                                pdf.cell(0, 8, f"3. Trend Comparison ({trend_metric_label} / {chart_type})", ln=True)
                                if not v_df_p.empty:
                                    t_df = v_df_p.copy()
                                    t_df['published_at_dt'] = pd.to_datetime(t_df['published_at'], errors='coerce')
                                    t_df = t_df.dropna(subset=['published_at_dt'])
                                    t_df['month'] = t_df['published_at_dt'].dt.to_period('M').astype(str)
                                    trend_data = t_df.groupby(['channel_name', 'month'])[trend_metric].sum().reset_index()
                                    months = sorted(trend_data['month'].unique())
                                    palette = ['#3B82F6', '#EF4444', '#10B981', '#F59E0B', '#8B5CF6', '#EC4899']

                                    plt.figure(figsize=(10, 4.6))
                                    if chart_type == 'Grouped Bar':
                                        x_axis = np.arange(len(months))
                                        w = 0.8 / max(len(selected), 1)
                                        for i, ch in enumerate(selected):
                                            ch_d = trend_data[trend_data['channel_name'] == ch]
                                            month_map = dict(zip(ch_d['month'], ch_d[trend_metric]))
                                            y_vals = [month_map.get(m, 0) for m in months]
                                            clr = '#7C3AED' if ch == bench_channel else palette[i % len(palette)]
                                            plt.bar(x_axis + (i * w) - 0.4 + w/2, y_vals, w, label=ch, color=clr)
                                        plt.xticks(x_axis, months, rotation=45, fontsize=8)
                                    elif chart_type == 'Area':
                                        for i, ch in enumerate(selected):
                                            ch_d = trend_data[trend_data['channel_name'] == ch]
                                            month_map = dict(zip(ch_d['month'], ch_d[trend_metric]))
                                            y_vals = [month_map.get(m, 0) for m in months]
                                            clr = '#7C3AED' if ch == bench_channel else palette[i % len(palette)]
                                            plt.fill_between(months, y_vals, color=clr, alpha=0.2)
                                            plt.plot(months, y_vals, color=clr, linewidth=2.2, label=ch)
                                        plt.xticks(rotation=45, fontsize=8)
                                    else:
                                        for i, ch in enumerate(selected):
                                            ch_d = trend_data[trend_data['channel_name'] == ch]
                                            month_map = dict(zip(ch_d['month'], ch_d[trend_metric]))
                                            y_vals = [month_map.get(m, 0) for m in months]
                                            clr = '#7C3AED' if ch == bench_channel else palette[i % len(palette)]
                                            plt.plot(months, y_vals, marker='d', linewidth=2.2, color=clr, label=ch)
                                        plt.xticks(rotation=45, fontsize=8)

                                    plt.title(f'Monthly {trend_metric_label} Trends', fontsize=12)
                                    plt.ylabel(trend_metric_label, fontsize=9)
                                    plt.grid(linestyle=':', alpha=0.2)
                                    plt.legend(fontsize=8)
                                    plt.tight_layout()
                                    plt.savefig('pdf_battle_trends.png', dpi=120)
                                    plt.close()
                                    pdf.image('pdf_battle_trends.png', x=10, w=190)
                                    os.remove('pdf_battle_trends.png')
                                    pdf.ln(4)

                                # 4) Summary table + highlighted benchmark
                                pdf.set_font('Helvetica', 'B', 11)
                                pdf.cell(0, 8, '4. Competitive Summary ([BENCH] = benchmark)', ln=True)
                                pdf.set_font('Helvetica', 'B', 8)
                                pdf.set_fill_color(241, 245, 249)
                                pdf.cell(70, 8, 'Channel', 1, 0, 'C', True)
                                pdf.cell(36, 8, 'Subscribers', 1, 0, 'C', True)
                                pdf.cell(36, 8, 'Total Views', 1, 0, 'C', True)
                                pdf.cell(24, 8, 'Videos', 1, 0, 'C', True)
                                pdf.cell(24, 8, 'Quality%', 1, 1, 'C', True)
                                pdf.set_font('Helvetica', '', 8)
                                q_map = {}
                                if not ch_agg_p.empty:
                                    q_map = dict(zip(ch_agg_p['channel_name'], ch_agg_p['quality']))
                                for _, row in cdf_p.sort_values('views', ascending=False).iterrows():
                                    ch_name = str(row['channel_name'])
                                    mark_name = f"[BENCH] {ch_name}" if ch_name == bench_channel else ch_name
                                    qv = float(q_map.get(ch_name, 0.0))
                                    pdf.cell(70, 7, mark_name[:34], 1)
                                    pdf.cell(36, 7, f"{int(row['subscribers']):,}", 1, 0, 'R')
                                    pdf.cell(36, 7, f"{int(row['views']):,}", 1, 0, 'R')
                                    pdf.cell(24, 7, f"{int(row['total_videos']):,}", 1, 0, 'R')
                                    pdf.cell(24, 7, f"{qv:.2f}", 1, 1, 'R')

                                # 5) Strategic insights
                                leader = cdf_p.loc[cdf_p['views'].idxmax()]['channel_name']
                                q_leader = ch_agg_p.loc[ch_agg_p['quality'].idxmax()]['channel_name'] if not ch_agg_p.empty else 'N/A'
                                pdf.ln(4)
                                pdf.set_font('Helvetica', 'B', 11)
                                pdf.cell(0, 8, '5. Strategic Insights', ln=True)
                                pdf.set_font('Helvetica', '', 10)
                                pdf.set_text_color(51, 65, 85)
                                insight = (
                                    f"- SCALE LEADER: {leader} currently leads total reach.\n"
                                    f"- QUALITY CHAMPION: {q_leader} has the highest quality score.\n"
                                    f"- BENCHMARK FOCUS: {'[BENCH] ' + bench_channel if bench_channel else 'No benchmark selected'} should be tracked against ratio 1.0 baseline and monthly trend continuity."
                                )
                                pdf.multi_cell(0, 7, insight)

                                st.download_button(
                                    "📩 Download Premium Battle Report",
                                    bytes(pdf.output()),
                                    "battle_arena_full_report.pdf",
                                    "application/pdf",
                                    use_container_width=True
                                )
                    except Exception as e: st.error(f"PDF Error: {e}")

        # ─── COMPARE PAGE FILTERS ───
        elif cur_page == 'compare':
            render_help_widget('compare')
            recent_ch = get_recent_channels(limit=50)
            if recent_ch:
                st.markdown("""
                <style>
                .compare-filter-title {
                    margin: 0.1rem 0 0.6rem 0;
                    padding: 0.72rem 0.9rem;
                    border-radius: 12px;
                    background: linear-gradient(135deg, #0284c7 0%, #0ea5e9 100%);
                    color: #f8fafc;
                    text-align: center;
                    font-size: 0.98rem;
                    font-weight: 800;
                    letter-spacing: 0.02em;
                    box-shadow: 0 8px 20px rgba(2, 132, 199, 0.24);
                    border: 1px solid rgba(255, 255, 255, 0.28);
                }
                .compare-filter-section {
                    margin: 0.6rem 0 0.38rem 0;
                    padding: 0.38rem 0.62rem;
                    border-radius: 9px;
                    background: linear-gradient(135deg, #E0F2FE 0%, #BAE6FD 100%);
                    color: #0f172a;
                    font-size: 0.79rem;
                    font-weight: 800;
                    letter-spacing: 0.04em;
                    text-transform: uppercase;
                    border-left: 4px solid #0284c7;
                }
                .compare-filter-note {
                    margin: 0.16rem 0 0.5rem 0;
                    font-size: 0.72rem;
                    color: #475569;
                    text-align: center;
                }
                .compare-filter-divider {
                    border: 0;
                    height: 1px;
                    margin: 0.55rem 0 0.45rem 0;
                    background: linear-gradient(90deg, rgba(2,132,199,0.0), rgba(2,132,199,0.45), rgba(2,132,199,0.0));
                }
                </style>
                """, unsafe_allow_html=True)

                st.markdown("<div class='compare-filter-title'>Exports Controls</div>", unsafe_allow_html=True)
                st.markdown("<div class='compare-filter-note'>Configure leaderboard ranking and export options for the Exports page</div>", unsafe_allow_html=True)

                ch_names = [r['name'] for r in recent_ch]
                st.markdown("<div class='compare-filter-section'>Leaderboard Ranking</div>", unsafe_allow_html=True)
                lb_sort_opts = ['Subscribers', 'Total Views', 'Engagement %', 'Total Videos']
                st.selectbox("🔀 Rank By", lb_sort_opts, key='c_rank_by')

        # End of filters
    
    # Removed local list in favor of the new Recent Hub page
    pass

# --- MAIN PAGE HEADER WITH COLOR-CODED CARDS ---
# Removed - pages now have centered cards instead
pass

# --- HANDLE SYNC ---
if fetch_button and channel_id_input:
    with st.status("💎 Architecting Data Stream...", expanded=True) as status:
        st.write("📡 Accessing YouTube API...")
        res = store_channel_data(channel_id_input)
        if res['status'] == "Success":
            st.cache_data.clear()
            status.update(label="✨ Analysis Ready", state="complete")
            st.session_state['active_channel_id'] = channel_id_input
            st.session_state['page'] = 'dash'
            st.session_state['gp_explore'] = False
            st.query_params.clear()
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
                thumb = ch.get('thumbnail_url') or "https://upload.wikimedia.org/wikipedia/commons/7/7c/Profile_avatar_placeholder_large.png"
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
                    st.session_state['gp_explore'] = False
                    st.query_params.clear()
                    st.rerun()

# --- PAGE: DASHBOARD ---
elif st.session_state['page'] == 'dash':
    qp_channel = st.query_params.get("channel_id")
    qp_explore = st.query_params.get("gp_explore")
    if qp_channel:
        st.session_state['active_channel_id'] = qp_channel
        st.session_state['page'] = 'dash'
    if qp_explore == "1":
        if 'gp_explore' not in st.session_state:
            st.session_state['gp_explore'] = True
        else:
            st.session_state['gp_explore'] = True
    if qp_channel or qp_explore:
        st.query_params.clear()
        st.rerun()

    if not st.session_state['active_channel_id']:
        # --- GENESIS 2.3: VISUAL GALLERY OVERHAUL ---
        import base64, os

        def _img_b64(path):
            if os.path.exists(path):
                with open(path, "rb") as f:
                    return base64.b64encode(f.read()).decode()
            return ""

        _img1 = _img_b64(r"C:\Users\VARSHA\.gemini\antigravity\brain\73d149b4-7287-4cca-97bc-08d956086152\genesis_profile_card_1773854954407.png")
        _img2 = _img_b64(r"C:\Users\VARSHA\.gemini\antigravity\brain\73d149b4-7287-4cca-97bc-08d956086152\genesis_main_dashboard_1773854983437.png")
        _img3 = _img_b64(r"C:\Users\VARSHA\.gemini\antigravity\brain\73d149b4-7287-4cca-97bc-08d956086152\genesis_reports_view_1773855034677.png")
        _img4 = _img_b64(r"C:\Users\VARSHA\.gemini\antigravity\brain\73d149b4-7287-4cca-97bc-08d956086152\genesis_visualizations_view_1773855092148.png")

        st.markdown(f"""
            <style>
                @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;700;900&display=swap');

                @keyframes img-scroll {{
                    0%   {{ transform: translateX(0); }}
                    100% {{ transform: translateX(-50%); }}
                }}

                .genesis23-bg {{
                    background: radial-gradient(ellipse at 80% 0%, #1E1B4B 0%, #0F172A 50%, #fff 100%);
                    border-radius: 40px;
                    padding: 80px 40px 60px 40px;
                    text-align: center;
                    margin-top: 20px;
                    border: 1px solid rgba(255,255,255,0.08);
                    box-shadow: 0 40px 120px -20px rgba(0,0,0,0.35);
                    position: relative;
                    overflow: hidden;
                }}

                /* floating orbs */
                .genesis23-bg::before {{
                    content: '';
                    position: absolute; top: -80px; left: -80px;
                    width: 400px; height: 400px;
                    background: radial-gradient(circle, rgba(139,92,246,0.18) 0%, transparent 70%);
                    filter: blur(60px); pointer-events: none;
                }}
                .genesis23-bg::after {{
                    content: '';
                    position: absolute; bottom: -80px; right: -80px;
                    width: 400px; height: 400px;
                    background: radial-gradient(circle, rgba(239,68,68,0.15) 0%, transparent 70%);
                    filter: blur(60px); pointer-events: none;
                }}

                /* icon row */
                .genesis23-icons {{
                    display: flex;
                    justify-content: center;
                    gap: 32px;
                    margin-bottom: 40px;
                    position: relative; z-index: 2;
                }}
                .genesis23-icon-pill {{
                    display: flex; align-items: center; gap: 10px;
                    background: rgba(255,255,255,0.07);
                    border: 1px solid rgba(255,255,255,0.12);
                    border-radius: 99px;
                    padding: 12px 24px;
                    backdrop-filter: blur(12px);
                    color: #fff; font-family: 'Outfit', sans-serif; font-weight: 700; font-size: 0.9rem;
                    letter-spacing: 0.5px;
                }}
                .genesis23-icon-pill .pill-icon {{ font-size: 1.3rem; }}

                /* headline */
                .genesis23-headline {{
                    font-family: 'Outfit', sans-serif;
                    font-size: 3.6rem; font-weight: 900; letter-spacing: -2px; line-height: 1.1;
                    color: #fff; margin-bottom: 20px;
                    text-shadow: 0 8px 24px rgba(0,0,0,0.5);
                    position: relative; z-index: 2;
                }}
                .genesis23-sub {{
                    font-family: 'Outfit', sans-serif;
                    font-size: 1.15rem; color: #94A3B8; max-width: 680px;
                    margin: 0 auto 48px auto; line-height: 1.7;
                    position: relative; z-index: 2;
                }}

                /* command hub */
                /* Glow animation keyframes for input */
                @keyframes input-glow {{
                    0%, 100% {{
                        border-color: #FF0000;
                        box-shadow: 0 0 15px rgba(255, 0, 0, 0.5),
                                    0 0 30px rgba(255, 68, 68, 0.3),
                                    inset 0 0 0 1px rgba(255, 0, 0, 0.2);
                    }}
                    50% {{
                        border-color: #FF4444;
                        box-shadow: 0 0 25px rgba(255, 68, 68, 0.6),
                                    0 0 50px rgba(255, 100, 100, 0.4),
                                    inset 0 0 0 2px rgba(255, 68, 68, 0.15);
                    }}
                }}

                @keyframes input-pulse {{
                    0%, 100% {{ transform: scale(1); }}
                    50% {{ transform: scale(1.01); }}
                }}

                .command-engine-glass {{
                    background: transparent;
                    backdrop-filter: none;
                    -webkit-backdrop-filter: none;
                    border: none;
                    border-radius: 0; 
                    padding: 12px 0;
                    max-width: 620px; 
                    margin: 0 auto;
                    box-shadow: none;
                    position: relative; 
                    z-index: 10;
                    transition: all 0.3s ease;
                }}

                .command-engine-glass input {{
                    border: 3px solid #FF0000 !important;
                    border-radius: 16px !important;
                    padding: 14px 18px !important;
                    background: rgba(255, 255, 255, 0.98) !important;
                    font-size: 1.05rem !important;
                    font-weight: 500 !important;
                    color: #1E293B !important;
                    transition: all 0.3s ease !important;
                    animation: input-glow 2.5s ease-in-out infinite, input-pulse 2.5s ease-in-out infinite !important;
                    box-shadow: 0 0 15px rgba(255, 0, 0, 0.5),
                                0 0 30px rgba(255, 68, 68, 0.3) !important;
                    letter-spacing: 0.3px;
                }}

                .command-engine-glass input::placeholder {{
                    color: rgba(148, 163, 184, 0.8) !important;
                    font-weight: 500;
                }}

                .command-engine-glass input:focus {{
                    border-color: #FF0000 !important;
                    background: rgba(255, 255, 255, 1) !important;
                    box-shadow: 0 0 30px rgba(255, 68, 68, 0.7),
                                0 0 50px rgba(255, 100, 100, 0.5),
                                inset 0 0 0 2px rgba(255, 68, 68, 0.2) !important;
                    outline: none !important;
                }}

                .command-engine-glass:hover input {{
                    border-color: #FF4444 !important;
                    box-shadow: 0 0 25px rgba(255, 68, 68, 0.8),
                                0 0 50px rgba(255, 100, 100, 0.6) !important;
                }}

                .command-engine-glass:hover {{
                    border-color: transparent;
                    box-shadow: none;
                }}

                /* image gallery marquee */
                .img-marquee-wrap {{
                    overflow: hidden;
                    white-space: nowrap;
                    margin-top: 70px;
                    position: relative;
                    mask-image: linear-gradient(to right, transparent 0%, black 12%, black 88%, transparent 100%);
                    -webkit-mask-image: linear-gradient(to right, transparent 0%, black 12%, black 88%, transparent 100%);
                }}
                .img-marquee-track {{
                    display: inline-flex;
                    gap: 28px;
                    animation: img-scroll 36s linear infinite;
                    will-change: transform;
                    padding: 20px 0;
                }}
                .img-marquee-track:hover {{ animation-play-state: paused; }}
                .img-marquee-track img {{
                    height: 260px;
                    width: auto;
                    border-radius: 22px;
                    border: 1px solid rgba(255,255,255,0.1);
                    box-shadow: 0 20px 50px -10px rgba(0,0,0,0.5);
                    object-fit: cover;
                    flex-shrink: 0;
                    transition: transform 0.4s ease, box-shadow 0.4s ease;
                }}
                .img-marquee-track img:hover {{
                    transform: scale(1.06) translateY(-8px);
                    box-shadow: 0 30px 70px -10px rgba(139,92,246,0.5);
                    cursor: pointer;
                }}

                /* capability cards */
                .cap-card {{
                    background: rgba(255,255,255,0.97);
                    border: 1px solid #E2E8F0;
                    border-radius: 28px;
                    padding: 36px 32px;
                    transition: all 0.45s cubic-bezier(0.19,1,0.22,1);
                    text-align: left; height: 100%;
                }}
                .cap-card:hover {{
                    transform: translateY(-12px) scale(1.02);
                    box-shadow: 0 28px 60px -12px rgba(239,68,68,0.14);
                    border-color: #EF4444;
                }}
                .cap-card .cap-icon {{ font-size: 2.8rem; margin-bottom: 18px; }}
                .cap-card h3 {{ margin: 0; color: #1E293B; font-family: 'Outfit', sans-serif; font-size: 1.2rem; font-weight: 800; }}
                .cap-card p {{ color: #64748B; font-size: 0.95rem; margin-top: 12px; line-height: 1.65; }}
            </style>

            <!-- HERO -->
            <div class='genesis23-bg'>
                <div class='genesis23-icons'>
                    <div class='genesis23-icon-pill' style='border-color:rgba(139,92,246,0.35); background:rgba(139,92,246,0.12);'>
                        <span class='pill-icon'>🌍</span> Battle Arena
                    </div>
                    <div class='genesis23-icon-pill' style='border-color:rgba(239,68,68,0.35); background:rgba(239,68,68,0.12);'>
                        <span class='pill-icon'>📈</span> Velocity Intel
                    </div>
                    <div class='genesis23-icon-pill' style='border-color:rgba(16,185,129,0.35); background:rgba(16,185,129,0.12);'>
                        <span class='pill-icon'>🛡️</span> Stability Guard
                    </div>
                    <div class='genesis23-icon-pill' style='border-color:rgba(245,158,11,0.35); background:rgba(245,158,11,0.12);'>
                        <span class='pill-icon'>📊</span> Deep Analytics
                    </div>
                </div>
                <div class='genesis23-headline'>Your YouTube Intelligence<br>Command Center</div>
                <div class='genesis23-sub'>From sub-millisecond data syncs to deep-rival mapping — build, grow, and dominate faster than ever.</div>
            </div>
        """, unsafe_allow_html=True)

        # COMMAND ENGINE (glassmorphic search hub)
        st.markdown("<div style='margin-top:-60px;'></div>", unsafe_allow_html=True)
        _, center_col, _ = st.columns([1, 2, 1])
        with center_col:
            st.markdown("<div class='command-engine-glass'>", unsafe_allow_html=True)
            with st.form("genesis_2_form"):
                g2_chid = st.text_input("YouTube Channel ID Search", placeholder="Paste your Channel ID here... ✍️", label_visibility="collapsed")
                g2_btn = st.form_submit_button("🚀 Initiate Intelligence Analysis", use_container_width=True, type="primary")
                if g2_btn and g2_chid:
                    with st.status("💎 Architecting Data Stream...", expanded=True) as status:
                        res = store_channel_data(g2_chid)
                        if res['status'] == "Success":
                            status.update(label="✨ Analysis Ready", state="complete")
                            st.session_state['active_channel_id'] = g2_chid
                            st.balloons()
                            st.rerun()
                        else:
                            status.update(label="❌ Stream Interrupted", state="error")
                            st.error(res['message'])
            st.markdown("</div>", unsafe_allow_html=True)

        # AUTO-SCROLLING IMAGE GALLERY
        imgs = [_img1, _img2, _img3, _img4]
        img_tags = "".join(
            f'<img src="data:image/png;base64,{b}" alt="Genesis Panel {i+1}"/>'
            for i, b in enumerate(imgs) if b
        )
        # duplicate for seamless loop
        img_tags_double = img_tags + img_tags
        st.markdown(f"""
            <div class='img-marquee-wrap'>
                <div class='img-marquee-track'>
                    {img_tags_double}
                </div>
            </div>
        """, unsafe_allow_html=True)

        # SECTION HEADING
        st.markdown("""
            <div style='margin-top:80px; text-align:center;'>
                <p style='font-family:Outfit; font-size:0.85rem; font-weight:700; color:#94A3B8; text-transform:uppercase; letter-spacing:4px; margin-bottom:10px;'>INTELLIGENCE MODULES</p>
                <h2 style='font-family:Outfit; font-weight:900; color:#1E293B; letter-spacing:-1.5px; font-size:2.4rem; margin:0;'>Everything you need to dominate</h2>
            </div>
        """, unsafe_allow_html=True)

        # CAPABILITY CARDS
        f1, f2, f3 = st.columns(3)
        with f1:
            st.markdown("""
                <div class='cap-card' style='border-top:6px solid #8B5CF6;'>
                    <div class='cap-icon'>🌍</div>
                    <h3>Battle Arena</h3>
                    <p>Map your entire rival ecosystem. Reveal normalized strategy profiles and niche dominance with automated gap analysis.</p>
                </div>
            """, unsafe_allow_html=True)
        with f2:
            st.markdown("""
                <div class='cap-card' style='border-top:6px solid #EF4444;'>
                    <div class='cap-icon'>📈</div>
                    <h3>Velocity Intelligence</h3>
                    <p>Track engagement hooks in real-time. Uncover the precise moments and topics that trigger massive viral reactive spikes.</p>
                </div>
            """, unsafe_allow_html=True)
        with f3:
            st.markdown("""
                <div class='cap-card' style='border-top:6px solid #10B981;'>
                    <div class='cap-icon'>🛡️</div>
                    <h3>Stability Guard</h3>
                    <p>Monitor deep health scores. Use sub-to-view ratios to ensure your audience is loyal, consistent, and growing sustainably.</p>
                </div>
            """, unsafe_allow_html=True)

        st.markdown("<div style='margin-bottom:120px;'></div>", unsafe_allow_html=True)

    else:
        render_help_widget('dashboard')
        chid = st.session_state['active_channel_id']
        df = get_channel_data(chid)
        if not df.empty:
            c_data = df.iloc[0]

            # ──────────────────────────────────────────
            # GENESIS PROFILE CARD  (Dark Glassmorphic)
            # ──────────────────────────────────────────
            subs       = int(c_data['subscribers'] or 0)
            tot_views  = int(c_data['total_views'] or 0)
            tot_vids   = int(c_data['total_videos'] or 0)
            ch_name    = c_data['channel_name']
            ch_id      = chid
            joined     = pd.to_datetime(c_data['c_published']).strftime('%d %b, %Y')
            thumb_url  = c_data.get('c_thumb', '')

            def _fmt(n):
                if n >= 1_000_000_000: return f"{n/1_000_000_000:.2f}B"
                if n >= 1_000_000:     return f"{n/1_000_000:.2f}M"
                if n >= 1_000:         return f"{n/1_000:.1f}K"
                return str(n)

            # Pre-compute avatar HTML (avoids complex expressions inside f-string)
            if thumb_url:
                _avatar_html = f'<img src="{thumb_url}" alt="Channel Avatar"/>'
            else:
                _avatar_html = '<span style="font-size:2.5rem;">🎬</span>'
            _handle = ch_name.lower().replace(' ', '')
            _ch_id_short = ch_id[:18]
            _subs_fmt = _fmt(subs)
            _views_fmt = _fmt(tot_views)
            _vids_fmt = _fmt(tot_vids)

            if 'gp_explore' not in st.session_state:
                st.session_state['gp_explore'] = False

            def _close_gp_explore():
                st.session_state['gp_explore'] = False
                st.query_params.clear()

            if not st.session_state['gp_explore']:
                st.markdown(f"""
                    <style>
                        @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700;900&display=swap');
                        .genesis-profile-bg {{
                            background: linear-gradient(135deg, #0F172A 0%, #1E1B4B 40%, #12172C 100%);
                            border-radius: 32px; padding: 48px 48px 36px 48px;
                            margin-bottom: 32px;
                            border: 1px solid rgba(139,92,246,0.18);
                            box-shadow: 0 40px 80px -20px rgba(0,0,0,0.7), inset 0 1px 0 rgba(255,255,255,0.06);
                            position: relative; overflow: hidden;
                        }}
                    .genesis-profile-bg::before {{
                        content:''; position:absolute; top:-120px; right:-120px;
                        width:400px; height:400px;
                        background:radial-gradient(circle, rgba(139,92,246,0.22) 0%, transparent 70%);
                        filter:blur(60px); pointer-events:none;
                    }}
                    .genesis-profile-bg::after {{
                        content:''; position:absolute; bottom:-100px; left:10%;
                        width:350px; height:350px;
                        background:radial-gradient(circle, rgba(239,68,68,0.15) 0%, transparent 70%);
                        filter:blur(60px); pointer-events:none;
                    }}
                    .gp-header {{ display:flex; align-items:center; gap:36px; position:relative; z-index:2; }}
                    .gp-avatar-wrap {{ position:relative; flex-shrink:0; }}
                    .gp-avatar-ring {{
                        width:110px; height:110px; border-radius:50%;
                        background:conic-gradient(#8B5CF6, #EF4444, #F59E0B, #10B981, #8B5CF6);
                        padding:3px;
                        display:flex; align-items:center; justify-content:center;
                    }}
                    @keyframes spin-ring {{
                        from {{ transform:rotate(0deg); }}
                        to   {{ transform:rotate(360deg); }}
                    }}
                    .gp-avatar-inner {{
                        width:104px; height:104px; border-radius:50%;
                        background:#0F172A; display:flex; align-items:center; justify-content:center; overflow:hidden;
                    }}
                    .gp-avatar-inner img {{ width:100%; height:100%; object-fit:cover; border-radius:50%; }}
                    .gp-avatar-badge {{
                        position:absolute; bottom:2px; right:2px;
                        background:#10B981; border:2px solid #0F172A;
                        border-radius:50%; width:18px; height:18px;
                    }}
                    .gp-info {{ flex:1; }}
                    .gp-handle {{ font-family:'Outfit',sans-serif; font-size:0.82rem; font-weight:700; color:#8B5CF6; text-transform:uppercase; letter-spacing:3px; margin-bottom:6px; }}
                    .gp-name {{ font-family:'Outfit',sans-serif; font-size:2.1rem; font-weight:900; color:#fff; letter-spacing:-0.5px; line-height:1.1; margin-bottom:6px; }}
                    .gp-meta {{ font-family:'Outfit',sans-serif; font-size:0.88rem; color:#CBD5E1; margin-bottom:16px; font-weight:500; }}
                    .gp-tags {{ display:flex; gap:10px; flex-wrap:wrap; }}
                    .gp-tag {{ background:#FFFFFF; border-radius:99px; padding:6px 18px; font-family:'Outfit',sans-serif; font-size:0.82rem; font-weight:700; letter-spacing:0.3px; color:#1E293B; display:inline-flex; align-items:center; gap:6px; }}
                    .gp-tag-yt  {{ border-left:3px solid #EF4444; }}
                    .gp-tag-an  {{ border-left:3px solid #10B981; }}
                    .gp-tag-gi  {{ border-left:3px solid #8B5CF6; }}
                    .gp-stats {{ display:grid; grid-template-columns:repeat(3,1fr); gap:16px; margin-top:36px; position:relative; z-index:2; }}
                    .gp-stat-card {{ background:rgba(15, 23, 42, 0.7); border:1px solid rgba(255, 255, 255, 0.1); border-radius:18px; padding:24px 20px; backdrop-filter:blur(12px); -webkit-backdrop-filter:blur(12px); transition:all 0.3s ease; box-shadow: 0 8px 32px rgba(0,0,0,0.3); }}
                    .gp-stat-card:hover {{ background:rgba(30, 41, 59, 0.9); border-color:rgba(139,92,246,0.6); transform:translateY(-4px); box-shadow:0 12px 40px rgba(139,92,246,0.25); }}
                    .gp-stat-icon {{ font-size:1.5rem; margin-bottom:10px; }}
                    .gp-stat-value {{ font-family:'Outfit',sans-serif; font-size:1.9rem; font-weight:900; color:#FFFFFF; letter-spacing:-1px; line-height:1; }}
                    .gp-stat-label {{ font-family:'Outfit',sans-serif; font-size:0.8rem; font-weight:700; color:#94A3B8; text-transform:uppercase; letter-spacing:2px; margin-top:6px; }}
                    .gp-stat-sub {{ font-size:0.78rem; font-weight:600; margin-top:4px; color:#CBD5E1; }}
                    .gp-footer {{ margin-top:28px; display:flex; align-items:center; gap:12px; position:relative; z-index:2; }}
                    .gp-see-overview {{ display:inline-flex; align-items:center; justify-content:center; gap:10px; width:100%; background:#FFFFFF; border:none; border-radius:12px; padding:12px 22px; font-family:'Outfit',sans-serif; font-size:0.92rem; font-weight:700; color:#1E293B; cursor:pointer; text-decoration:none; transition:all 0.2s; box-shadow:0 4px 20px rgba(0,0,0,0.2); }}
                    .gp-see-overview:hover {{ background:#F1F5F9; color:#1E293B; transform:translateY(-2px); box-shadow:0 8px 30px rgba(0,0,0,0.25); }}
                    .gp-explore-overview {{ display:inline-flex; align-items:center; justify-content:center; gap:10px; width:100%; background:linear-gradient(135deg, #1E3A8A 0%, #1D4ED8 100%); border:1px solid rgba(147,197,253,0.55); border-radius:12px; padding:12px 22px; font-family:'Outfit',sans-serif; font-size:0.92rem; font-weight:700; color:#DBEAFE; cursor:pointer; text-decoration:none; transition:all 0.2s; box-shadow:0 8px 24px rgba(30,58,138,0.35); }}
                    .gp-explore-overview:hover {{ color:#FFFFFF; border-color:#BFDBFE; transform:translateY(-2px); box-shadow:0 12px 30px rgba(30,58,138,0.55); }}
                    .gp-divider {{ height:1px; background:linear-gradient(to right, rgba(139,92,246,0.3), transparent); margin:36px 0 0 0; position:relative; z-index:2; }}
                </style>
                <div class="genesis-profile-bg">
                    <div class="gp-header">
                        <div class="gp-avatar-wrap">
                            <div class="gp-avatar-ring">
                                <div class="gp-avatar-inner">{_avatar_html}</div>
                            </div>
                            <div class="gp-avatar-badge"></div>
                        </div>
                        <div class="gp-info">
                            <div class="gp-handle">@{_handle}</div>
                            <div class="gp-name">{ch_name}</div>
                            <div class="gp-meta">Joined {joined} &nbsp;&bull;&nbsp; ID: {_ch_id_short}...</div>
                            <div class="gp-tags">
                                <span class="gp-tag gp-tag-yt">🎥 YouTube Creator</span>
                                <span class="gp-tag gp-tag-an">📊 {_subs_fmt} Subscribers</span>
                                <span class="gp-tag gp-tag-gi">🎬 {_vids_fmt} Videos</span>
                            </div>
                        </div>
                    </div>
                    <div class="gp-stats">
                        <div class="gp-stat-card" style="border-left:3px solid #8B5CF6;">
                            <div class="gp-stat-icon">👥</div>
                            <div class="gp-stat-value">{_subs_fmt}</div>
                            <div class="gp-stat-label">Subscribers</div>
                            <div class="gp-stat-sub" style="color:#8B5CF6;">📡 Total Channel Subscribers</div>
                        </div>
                        <div class="gp-stat-card" style="border-left:3px solid #EF4444;">
                            <div class="gp-stat-icon">👁️</div>
                            <div class="gp-stat-value">{_views_fmt}</div>
                            <div class="gp-stat-label">Total Views</div>
                            <div class="gp-stat-sub" style="color:#10B981;">📈 Cumulative All-Time Views</div>
                        </div>
                        <div class="gp-stat-card" style="border-left:3px solid #10B981;">
                            <div class="gp-stat-icon">🎬</div>
                            <div class="gp-stat-value">{_vids_fmt}</div>
                            <div class="gp-stat-label">Videos</div>
                            <div class="gp-stat-sub" style="color:#F59E0B;">🎬 Published on Channel</div>
                        </div>
                    </div>
                    <div class="gp-divider"></div>
                    <div class="gp-footer">
                        <a href="https://www.youtube.com/channel/{ch_id}" target="_blank" style="text-decoration:none; flex:1;">
                            <div class="gp-see-overview">
                                ▶ See Channel on YouTube
                            </div>
                        </a>
                        <a href="?page=dash&channel_id={ch_id}&gp_explore=1" target="_self" style="text-decoration:none; flex:1;">
                            <div class="gp-explore-overview">
                                🔭 Explore Analytics
                            </div>
                        </a>
                    </div>
                </div>
            """, unsafe_allow_html=True)

            # ── PROFESSIONAL NAV BAR for tabs ──────────────────────────────
            st.markdown("""
                <style>
                    /* Tab container strip - light clean style */
                    div[data-testid="stTabs"] > div:first-child {
                        background: #F8FAFC;
                        border-radius: 16px;
                        padding: 6px 8px;
                        border: 1px solid #E2E8F0;
                        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
                        gap: 4px;
                        margin-bottom: 24px;
                    }

                    /* Individual tab buttons */
                    div[data-testid="stTabs"] button[role="tab"] {
                        font-family: 'Outfit', sans-serif !important;
                        font-size: 0.9rem !important;
                        font-weight: 600 !important;
                        color: #475569 !important;
                        border-radius: 12px !important;
                        padding: 10px 24px !important;
                        border: 1px solid transparent !important;
                        background: transparent !important;
                        transition: all 0.25s ease !important;
                        letter-spacing: 0.3px;
                        white-space: nowrap;
                    }

                    /* Hover state */
                    div[data-testid="stTabs"] button[role="tab"]:hover {
                        color: #1E293B !important;
                        background: #E2E8F0 !important;
                        border-color: #CBD5E1 !important;
                    }

                    /* Active / selected tab */
                    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
                        background: linear-gradient(135deg, #6366F1 0%, #8B5CF6 100%) !important;
                        color: #FFFFFF !important;
                        font-weight: 700 !important;
                        box-shadow: 0 4px 16px rgba(99,102,241,0.45) !important;
                        border-color: transparent !important;
                    }

                    /* Hide the default red underline / ink bar */
                    div[data-testid="stTabs"] button[role="tab"]::after,
                    div[data-testid="stTabs"] [data-baseweb="tab-highlight"] {
                        display: none !important;
                        background: transparent !important;
                    }

                    /* Tab panel area */
                    div[data-testid="stTabs"] [role="tabpanel"] {
                        padding-top: 4px;
                    }
                </style>
            """, unsafe_allow_html=True)

            # ── CUSTOM CSS FOR PROFILE BUTTONS & CONTAINER ──────────────────
            st.markdown("""
                <style>
                    /* See Channel Button (primary link button) */
                    [data-testid="baseButton-primary"],
                    a[data-testid="stLinkButton"] button,
                    a[data-testid="stLinkButton"] {
                        background: linear-gradient(135deg, #EF4444 0%, #B91C1C 100%) !important;
                        color: #FFFFFF !important;
                        border-radius: 14px !important;
                        padding: 0.75rem 1.5rem !important;
                        border: none !important;
                        box-shadow: 0 6px 20px rgba(239, 68, 68, 0.45) !important;
                        transition: all 0.3s ease !important;
                        text-decoration: none !important;
                        font-family: 'Outfit', sans-serif !important;
                        font-weight: 700 !important;
                        font-size: 0.95rem !important;
                        letter-spacing: 0.3px !important;
                        display: flex; justify-content: center;
                    }
                    [data-testid="baseButton-primary"]:hover,
                    a[data-testid="stLinkButton"]:hover {
                        transform: translateY(-3px) !important;
                        box-shadow: 0 10px 30px rgba(239, 68, 68, 0.6) !important;
                    }

                    /* Explore Analytics Button (secondary) */
                    [data-testid="baseButton-secondary"] {
                        background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%) !important;
                        color: #C4B5FD !important;
                        border-radius: 14px !important;
                        padding: 0.75rem 1.5rem !important;
                        border: 1.5px solid rgba(139,92,246,0.55) !important;
                        box-shadow: 0 6px 20px rgba(99,102,241,0.25) !important;
                        transition: all 0.3s ease !important;
                        font-family: 'Outfit', sans-serif !important;
                        font-weight: 700 !important;
                        font-size: 0.95rem !important;
                        letter-spacing: 0.3px !important;
                        width: 100% !important;
                    }
                    [data-testid="baseButton-secondary"]:hover {
                        transform: translateY(-3px) !important;
                        border-color: #8B5CF6 !important;
                        box-shadow: 0 10px 28px rgba(139,92,246,0.5) !important;
                        color: #FFFFFF !important;
                    }

                    /* Keep sidebar navigation in the same global light style after analysis */
                    section[data-testid="stSidebar"] [data-testid="baseButton-secondary"],
                    section[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {
                        background: transparent !important;
                        background-image: none !important;
                        color: #3F3F46 !important;
                        border: 1px solid #C9CDD4 !important;
                        border-radius: 12px !important;
                        box-shadow: none !important;
                        width: 100% !important;
                        min-height: 2.85rem !important;
                        height: 2.85rem !important;
                        padding: 0.38rem 0.78rem !important;
                        font-size: 0.98rem !important;
                        line-height: 1.15 !important;
                        letter-spacing: 0.1px !important;
                        font-weight: 600 !important;
                        transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease !important;
                    }
                    section[data-testid="stSidebar"] [data-testid="baseButton-secondary"]:hover,
                    section[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:hover {
                        background: #F5F7FB !important;
                        color: #1F2937 !important;
                        border-color: #B7BECB !important;
                        transform: none !important;
                    }

                    /* ✕ Close button — dark red */
                    [data-testid="baseButton-secondary"][data-testid*="btn_explore_analytics"],
                    /* ── Analytics Container Border & Shadow ── */

                    /* Graph card containers */
                    .explore-graph-card {
                        border: 2.5px solid #1E293B;
                        border-radius: 16px;
                        padding: 16px 16px 8px 16px;
                        background: #FFFFFF;
                        box-shadow: 0 6px 24px rgba(15,23,42,0.12);
                        margin-bottom: 16px;
                    }
                    .explore-graph-card .card-title {
                        font-family: 'Outfit', sans-serif;
                        font-size: 1rem;
                        font-weight: 700;
                        color: #1E293B;
                        margin-bottom: 8px;
                        padding-bottom: 8px;
                        border-bottom: 1.5px solid #E2E8F0;
                    }

                    /* Explore tab: clear panel background + differentiated bordered sections */
                    div[data-testid="stTabs"] [role="tabpanel"] {
                        background: linear-gradient(180deg, #F8FAFC 0%, #F1F5F9 100%);
                        border: 1px solid #E2E8F0;
                        border-radius: 18px;
                        padding: 18px 14px 14px 14px;
                        margin-top: 10px;
                    }
                    div[data-testid="stTabs"] [role="tabpanel"] div[data-testid="stVerticalBlockBorderWrapper"] {
                        border: 1.5px solid #CBD5E1 !important;
                        border-radius: 16px !important;
                        background: linear-gradient(135deg, #FFFFFF 0%, #F8FAFC 100%) !important;
                        box-shadow: 0 8px 20px rgba(15, 23, 42, 0.08) !important;
                    }
                    div[data-testid="stTabs"] [role="tabpanel"] details {
                        border: 1px solid #DCE4EF;
                        border-radius: 12px;
                        background: #FFFFFF;
                    }
                    div[data-testid="stTabs"] [role="tabpanel"] div[data-testid="stDataFrame"] {
                        border: 1px solid #CBD5E1;
                        border-radius: 14px;
                        box-shadow: 0 10px 20px rgba(15, 23, 42, 0.08);
                        overflow: hidden;
                    }

                    /* Brighter raw table skin in Explore */
                    div[data-testid="stTabs"] [role="tabpanel"] div[data-testid="stDataFrame"] [role="columnheader"] {
                        background: linear-gradient(135deg, #0EA5E9 0%, #2563EB 100%) !important;
                        color: #FFFFFF !important;
                        font-weight: 700 !important;
                        border-right: 1px solid rgba(255,255,255,0.18) !important;
                    }
                    div[data-testid="stTabs"] [role="tabpanel"] div[data-testid="stDataFrame"] [role="gridcell"] {
                        background-color: #FFFFFF !important;
                        color: #0F172A !important;
                        font-size: 0.93rem !important;
                        font-weight: 500 !important;
                        border-bottom: 1px solid #E2E8F0 !important;
                    }
                </style>
            """, unsafe_allow_html=True)

            # ── BUTTONS: See Channel + Explore Analytics ─────────────────
            st.write("") # Spacer
            if st.session_state['gp_explore']:
                # Scoped CSS: override secondary button to dark red for ✕ close icon
                st.markdown("""
                    <style>
                    div[data-testid="column"]:last-of-type [data-testid="baseButton-secondary"] {
                        background: linear-gradient(135deg, #DC2626 0%, #991B1B 100%) !important;
                        color: #FFFFFF !important;
                        border: 2px solid #7F1D1D !important;
                        box-shadow: 0 4px 16px rgba(220,38,38,0.55) !important;
                        font-size: 1.15rem !important;
                        font-weight: 900 !important;
                        border-radius: 10px !important;
                        padding: 0.35rem !important;
                        min-width: 40px;
                    }
                    div[data-testid="column"]:last-of-type [data-testid="baseButton-secondary"]:hover {
                        box-shadow: 0 6px 22px rgba(220,38,38,0.8) !important;
                        transform: scale(1.1) !important;
                        border-color: #DC2626 !important;
                    }
                    </style>
                """, unsafe_allow_html=True)
                _, btn_col_right = st.columns([9, 1])
                with btn_col_right:
                    st.button(
                        "✕",
                        use_container_width=True,
                        key="btn_explore_analytics",
                        help="Close Analytics",
                        on_click=_close_gp_explore,
                    )

            # ── ANALYTICS SECTION (shown only when Explore is ON) ────────
            if st.session_state['gp_explore']:
                st.write("") # Spacer
                tab1, tab2, tab3 = st.tabs(["🏡  Overview & Strategy", "📈  Deep Dive Analytics", "💾  Raw Data"])



            
                # Pre-calculate video URLs for consistency
                df['video_url'] = "https://www.youtube.com/watch?v=" + df['video_id']
            
                with tab1:
                    st.markdown("### 🌟 Star Performer")

                    top_v = df.loc[df['view_count'].idxmax()]
                    sp1, sp2 = st.columns([1, 2])
                    with sp1: safe_image(top_v['v_thumb'], use_container_width=True)
                    with sp2:
                        st.markdown(f"#### [{top_v['title']}]({top_v['video_url']})")
                        st.caption(f"Published: {top_v['published_at']}")
                        st.markdown(f"**{top_v['view_count']:,}** Views • **{top_v['like_count']:,}** Likes • **{top_v['comment_count']:,}** Comments")
                        st.info("This is your highest performing video and currently your strongest benchmark for future content planning.")

                with tab2:
                    # Inject graph border CSS for this tab
                    st.markdown("""
                        <style>
                        /* Remove generic stPlotlyChart border since we use custom cards */
                        div[data-testid="stPlotlyChart"] {
                            border: none !important;
                            padding: 0 !important;
                            background: transparent !important;
                            box-shadow: none !important;
                            margin-bottom: 0 !important;
                        }
                        </style>
                    """, unsafe_allow_html=True)
                    # Content Reach
                    st.markdown("### 📊 Performance Reach: Top Video Diagnostics")
                    c_col1, c_col2 = st.columns(2)
                    with c_col1:
                        with st.container(border=True):
                            st.markdown("**📈 Most Viewed Videos**")
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
                                paper_bgcolor='#F0FDFA',
                                plot_bgcolor='#ECFEFF',
                                margin=dict(l=0, r=20, t=10, b=30),
                                yaxis=dict(visible=False, showticklabels=False),
                                xaxis=dict(gridcolor='#A5F3FC', title='view_count'),
                                hoverlabel=dict(
                                    bgcolor='#0F172A',
                                    font_color='#FFFFFF',
                                    bordercolor='#22D3EE',
                                    font_size=13,
                                    font_family='Inter'
                                )
                            )
                            st.plotly_chart(fig_v, use_container_width=True)
                        with st.expander("🔗 View Links for Top 10 Viewed"):
                            view_links_df = top10_v.sort_values('view_count', ascending=False)[['title', 'video_url']].rename(columns={
                                'title': 'Title',
                                'video_url': 'YouTube Link'
                            })
                            render_premium_table(view_links_df, table_id='top_viewed_links', link_cols={'YouTube Link': 'Watch Video'}, max_height=360)
                
                    with c_col2:
                        with st.container(border=True):
                            st.markdown("**💖 Most Liked Videos**")
                            top10_l = df.nlargest(10, 'like_count').sort_values('like_count', ascending=True)
                            fig_l = go.Figure()
                            fig_l.add_trace(go.Bar(
                                x=top10_l['like_count'],
                                y=top10_l['title'],
                                orientation='h',
                                marker=dict(
                                    color=top10_l['like_count'].tolist(),
                                    colorscale='Plasma',
                                    showscale=True,
                                    colorbar=dict(title="like_count", thickness=15, len=0.7)
                                ),
                                hovertemplate="<b>%{y}</b><br>Likes: %{x:,}<extra></extra>"
                            ))
                            fig_l.update_layout(
                                height=400, template='plotly_white',
                                paper_bgcolor='#FDF2F8',
                                plot_bgcolor='#FCE7F3',
                                margin=dict(l=0, r=20, t=10, b=30),
                                yaxis=dict(visible=False, showticklabels=False),
                                xaxis=dict(gridcolor='#F9A8D4', title='like_count'),
                                hoverlabel=dict(
                                    bgcolor='#0F172A',
                                    font_color='#FFFFFF',
                                    bordercolor='#F43F5E',
                                    font_size=13,
                                    font_family='Inter'
                                )
                            )
                            st.plotly_chart(fig_l, use_container_width=True)
                        with st.expander("🔗 View Links for Top 10 Liked"):
                            liked_links_df = top10_l.sort_values('like_count', ascending=False)[['title', 'video_url']].rename(columns={
                                'title': 'Title',
                                'video_url': 'YouTube Link'
                            })
                            render_premium_table(liked_links_df, table_id='top_liked_links', link_cols={'YouTube Link': 'Watch Video'}, max_height=360)

                    st.divider()

                    # Upload Schedule Analysis
                    st.markdown("### 📅 Upload Rhythm: Calendar Distribution")
                    # CRITICAL: Deduplicate by video_id to prevent duplicate rows from SQL JOIN
                    df_sch = df.drop_duplicates(subset=['video_id']).copy()
                    df_sch['published_at_dt'] = pd.to_datetime(df_sch['published_at'])
                    df_sch['month'] = df_sch['published_at_dt'].dt.to_period('M').astype(str)
                    df_sch['day_name'] = df_sch['published_at_dt'].dt.day_name()
                
                    s1, s2 = st.columns(2)
                    with s1:
                        with st.container(border=True):
                            st.markdown("**📅 Uploads by Month**")
                            m_data = df_sch.groupby('month').size().reset_index(name='count')
                            m_data = m_data.sort_values('count', ascending=False)
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
                            fig_p.update_layout(showlegend=True, height=350, template='plotly_white',
                                paper_bgcolor='#F8FAFC', plot_bgcolor='#F8FAFC',
                                hoverlabel=dict(
                                    bgcolor='#0F172A',
                                    font_color='#FFFFFF',
                                    bordercolor='#6366F1',
                                    font_size=13,
                                    font_family='Inter'
                                ))
                            st.plotly_chart(fig_p, use_container_width=True)
                        # Clarity Point
                        best_month = month_labels[0]
                        best_month_count = month_values[0]
                        st.markdown(f"""
                            <div class='highlight-box'>
                                🎯 <b>Monthly Highlight:</b> Most uploads (<b>{best_month_count}</b>) occurred in <b>{best_month}</b>. 
                                Consistency during peak periods often correlates with sustained viewership growth.
                            </div>
                        """, unsafe_allow_html=True)

                    with s2:
                        with st.container(border=True):
                            st.markdown("**📆 Uploads by Day of Week**")
                            d_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                            day_counts_series = df_sch['day_name'].value_counts()
                            day_values = [int(day_counts_series.get(d, 0)) for d in d_order]
                            fig_d = go.Figure(data=[go.Bar(
                                x=d_order,
                                y=day_values,
                                text=day_values,
                                textposition='outside',
                                textfont=dict(size=13, family='Outfit', color='#1E293B'),
                                cliponaxis=False,
                                marker=dict(
                                    color=day_values,
                                    colorscale='Turbo',
                                    showscale=True,
                                    colorbar=dict(title='Uploads', thickness=15, len=0.7)
                                ),
                                hovertemplate="<b>%{x}</b><br>Uploads: %{y}<extra></extra>"
                            )])
                            fig_d.update_layout(
                                showlegend=False, height=350, template='plotly_white',
                                paper_bgcolor='#EEF2FF', plot_bgcolor='#E0E7FF',
                                margin=dict(l=20, r=20, t=40, b=40),
                                yaxis=dict(
                                    title='Uploads',
                                    gridcolor='#C7D2FE',
                                    zeroline=False,
                                    range=[0, max(day_values) * 1.2 + 1]
                                ),
                                xaxis=dict(title='Day of Week', categoryorder='array', categoryarray=d_order),
                                hoverlabel=dict(
                                    bgcolor='#0F172A',
                                    font_color='#FFFFFF',
                                    bordercolor='#3B82F6',
                                    font_size=13,
                                    font_family='Inter'
                                )
                            )
                            st.plotly_chart(fig_d, use_container_width=True)
                        # Highlight
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
                    st.markdown("### 💾 Raw Data Audit Table")
                    st.caption("Direct dataset view for detailed review, manual validation, and quick link access.")
                    raw_df = df.copy()
                    raw_df['Mins'] = raw_df['duration'].apply(lambda x: round(parse_duration(x)/60, 1))
                    raw_show = raw_df[['title', 'published_at', 'view_count', 'like_count', 'comment_count', 'Mins', 'video_url']].rename(columns={
                        'title': 'Title',
                        'published_at': 'Published',
                        'view_count': 'Views',
                        'like_count': 'Likes',
                        'comment_count': 'Comments',
                        'video_url': 'Watch URL'
                    }).copy()
                    raw_show['Published'] = pd.to_datetime(raw_show['Published'], format='ISO8601').dt.strftime('%b %d, %Y')
                    render_premium_table(raw_show, table_id='raw_data_table', link_cols={'Watch URL': 'Open Video'}, max_height=520)

# --- PAGE: PROFILE (Cleaned up Intelligence Analytics) ---
elif st.session_state['page'] == 'profile':
    if not st.session_state['active_channel_id']:
        st.warning("Please select a channel from the sidebar.")
    else:
        render_help_widget('profile')
        chid = st.session_state['active_channel_id']
        df = get_channel_data(chid)
        if not df.empty:
            df = Caluclate_engagement_rate(df)
            df = Calculate_sub_to_view_ratio(df)
            df = Calculate_content_score(df)
            df = benchmark_videos(df)
            c = df.iloc[0]

            st.markdown("""
                <style>
                    .profile-shell {
                        background: linear-gradient(180deg, #F8FAFC 0%, #F1F5F9 100%);
                        border: 1px solid #E2E8F0;
                        border-radius: 18px;
                        padding: 16px;
                        margin-bottom: 16px;
                        box-shadow: 0 8px 20px rgba(15, 23, 42, 0.06);
                    }
                    .profile-band {
                        border-left: 4px solid #2563EB;
                        background: linear-gradient(90deg, #DBEAFE 0%, rgba(219, 234, 254, 0) 100%);
                        border-radius: 8px;
                        padding: 9px 12px;
                        margin-bottom: 10px;
                    }
                    .profile-band p {
                        margin: 0;
                        font-family: 'Outfit', sans-serif;
                        font-weight: 700;
                        font-size: 1rem;
                        color: #1E3A8A !important;
                    }
                    .profile-kpi-chip {
                        display: inline-block;
                        border-radius: 999px;
                        padding: 4px 10px;
                        font-family: 'Outfit', sans-serif;
                        font-size: 0.78rem;
                        font-weight: 700;
                        margin-bottom: 6px;
                        border: 1px solid transparent;
                    }
                </style>
            """, unsafe_allow_html=True)
            
            st.markdown(f"""
                <style>
                    .profile-hero-wrap {{
                        display: flex;
                        justify-content: center;
                        margin: 4px 0 12px 0;
                    }}
                    .profile-hero {{
                        width: min(980px, 96%);
                        background: linear-gradient(135deg, #F8FAFC 0%, #FFF4E6 50%, #F5E6FF 100%);
                        border: 1px solid #D8C7F5;
                        border-radius: 16px;
                        padding: 16px 18px;
                        box-shadow: 0 10px 24px rgba(79, 70, 229, 0.08);
                    }}
                    .profile-hero h2 {{
                        margin: 0;
                        text-align: center;
                        font-family: 'Outfit', sans-serif;
                        font-size: 2rem;
                        font-weight: 800;
                        color: #3730A3 !important;
                    }}
                    .profile-hero p {{
                        margin: 8px 0 0 0;
                        text-align: center;
                        color: #5B21B6 !important;
                        font-size: 1.05rem;
                        font-weight: 500;
                    }}
                </style>
                <div class='profile-hero-wrap'>
                    <div class='profile-hero'>
                        <h2>👤 {c['channel_name']}</h2>
                        <p>Channel Performance & Insights</p>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            # Gauge Section
            st.markdown("""
                <div class='profile-band'>
                    <p>💎 Key Performance Indicators</p>
                </div>
            """, unsafe_allow_html=True)
            k1, k2, k3, k4 = st.columns(4)
            
            def create_gauge(value, title, color="#FF0000", max_val=100, suffix="", format_str="", panel_bg="#F8FAFC", track_bg="#F1F5F9"):
                # Hide the default number by removing 'number' from mode parameter
                fig = go.Figure(go.Indicator(
                    mode = "gauge", 
                    value = value,
                    title = {'text': title, 'font': {'size': 16, 'color': '#64748B'}},
                    gauge = {
                        'axis': {'range': [None, max_val], 'tickwidth': 1, 'tickcolor': "#CBD5E1"},
                        'bar': {'color': color},
                        'bgcolor': track_bg,  # Creates the pale track
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
                fig.update_layout(
                    height=180,
                    margin=dict(l=10, r=10, t=70, b=10),
                    paper_bgcolor=panel_bg,
                    plot_bgcolor=panel_bg
                )
                return fig
            
            # Determine a safe max scale for the subs/view ratio gauge so the meter actually fills
            sv_max = max(1.0, df['sub_to_view_ratio'].mean() * 1.5)

            with k1:
                with st.container(border=True):
                    st.markdown("<span class='profile-kpi-chip' style='background:#DBEAFE; color:#1E40AF; border-color:#93C5FD;'>💙 Engagement Quality</span>", unsafe_allow_html=True)
                    st.plotly_chart(
                        create_gauge(df['engagement_rate'].mean(), "Engage Rate", "#3B82F6", max_val=20, suffix="%", panel_bg="#EFF6FF", track_bg="#DBEAFE"),
                        use_container_width=True,
                        config={'displayModeBar': True}
                    )
            with k2:
                with st.container(border=True):
                    st.markdown("<span class='profile-kpi-chip' style='background:#FEF3C7; color:#92400E; border-color:#FCD34D;'>🧡 Content Strength</span>", unsafe_allow_html=True)
                    st.plotly_chart(
                        create_gauge(df['content_performance_score'].mean(), "Content Score", "#F59E0B", max_val=100, format_str="{:.1f}/100", panel_bg="#FFFBEB", track_bg="#FEF3C7"),
                        use_container_width=True,
                        config={'displayModeBar': True}
                    )
            with k3:
                with st.container(border=True):
                    st.markdown("<span class='profile-kpi-chip' style='background:#DCFCE7; color:#166534; border-color:#86EFAC;'>💚 Audience Loyalty</span>", unsafe_allow_html=True)
                    st.plotly_chart(
                        create_gauge(df['sub_to_view_ratio'].mean(), "Subs / View", "#10B981", max_val=sv_max, format_str="{:.3f}", panel_bg="#ECFDF5", track_bg="#D1FAE5"),
                        use_container_width=True,
                        config={'displayModeBar': True}
                    )
            with k4:
                with st.container(border=True):
                    st.markdown("<span class='profile-kpi-chip' style='background:#FEE2E2; color:#991B1B; border-color:#FCA5A5;'>❤️ Reach Momentum</span>", unsafe_allow_html=True)
                    st.plotly_chart(
                        create_gauge(df['view_count'].mean()/1000, "Avg Views", "#EF4444", max_val=max(10, df['view_count'].max()/500), suffix="k", format_str="{:.0f}k", panel_bg="#FEF2F2", track_bg="#FEE2E2"),
                        use_container_width=True,
                        config={'displayModeBar': True}
                    )

            st.divider()

            # Timing & Mix
            c1, c2 = st.columns([2, 1])
            with c1:
                st.markdown("""
                    <div class='profile-band'>
                        <p>🕒 Optimal Timing Analysis</p>
                    </div>
                """, unsafe_allow_html=True)
                
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
                    font=dict(family="Outfit"),
                    paper_bgcolor='#FFF7ED',
                    plot_bgcolor='#FFFBF5'
                )
                
                st.plotly_chart(fig_time, use_container_width=True, config={'displayModeBar': True})
                
                upload_peak_hour = opt['video_count'].idxmax()
                st.info(f"💡 **Strategic Window:** You upload most often at **{upload_peak_hour}:00**, but your views actually peak when you post at **{view_peak_hour}:00**.")
            
            with c2:
                st.markdown("""
                    <div class='profile-band'>
                        <p>📊 Performance Distribution</p>
                    </div>
                """, unsafe_allow_html=True)
                ranks = df['performance_rank'].value_counts()
                fig_res = px.pie(values=ranks.values, names=ranks.index, hole=0.6, color_discrete_sequence=['#10B981', '#F59E0B', '#EF4444'])
                
                # Relocated legend to bottom to prevent modebar overlap in top right corner
                fig_res.update_layout(
                    margin=dict(l=0, r=0, t=10, b=30), 
                    height=320, 
                    showlegend=True,
                    legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5),
                    paper_bgcolor='#ECFEFF',
                    plot_bgcolor='#ECFEFF'
                )
                st.plotly_chart(fig_res, use_container_width=True, config={'displayModeBar': True})
                st.caption(f"You have **{ranks.get('High Performer', 0)}** High Performing videos.")

            st.divider()

            st.markdown("""
                <div class='profile-band'>
                    <p>📈 Video Ranking Detail</p>
                </div>
            """, unsafe_allow_html=True)
            prof_rank = df[['title', 'view_count', 'engagement_rate', 'performance_rank']].sort_values(by='view_count', ascending=False).rename(columns={
                'title': 'Title',
                'view_count': 'Views',
                'engagement_rate': 'Engagement %',
                'performance_rank': 'Performance Rank'
            })
            render_premium_table(
                prof_rank,
                table_id='profile_rank_table',
                max_height=460,
                formatters={'Engagement %': '{:.2f}%'}
            )

# ═══════════════════════════════════════════════════════════════
# PAGE: BATTLE ARENA — Complete Implementation
# ═══════════════════════════════════════════════════════════════
elif st.session_state['page'] == 'battle':
    st.markdown("""
        <style>
            .battle-band {
                border-left: 4px solid #6366F1;
                background: linear-gradient(90deg, #EEF2FF 0%, rgba(238, 242, 255, 0) 100%);
                border-radius: 8px;
                padding: 10px 12px;
                margin: 12px 0 12px 0;
            }
            .battle-band p {
                margin: 0;
                font-family: 'Outfit', sans-serif;
                font-weight: 700;
                font-size: 1rem;
                color: #312E81 !important;
            }
            .battle-note {
                background: linear-gradient(135deg, #FFFFFF 0%, #F8FAFC 100%);
                border: 1px solid #E2E8F0;
                border-radius: 12px;
                padding: 10px 12px;
                margin-bottom: 10px;
                box-shadow: 0 6px 16px rgba(15, 23, 42, 0.05);
            }
        </style>
    """, unsafe_allow_html=True)

    st.markdown("""
        <style>
            .battle-hero-wrap {
                display: flex;
                justify-content: center;
                margin: 4px 0 12px 0;
            }
            .battle-hero {
                width: min(980px, 96%);
                background: linear-gradient(135deg, #F8FAFC 0%, #FFE6E6 50%, #FFE5E5 100%);
                border: 1px solid #F5C5C5;
                border-radius: 16px;
                padding: 16px 18px;
                box-shadow: 0 10px 24px rgba(239, 68, 68, 0.08);
            }
            .battle-hero h2 {
                margin: 0;
                text-align: center;
                font-family: 'Outfit', sans-serif;
                font-size: 2rem;
                font-weight: 800;
                color: #7F1D1D !important;
            }
            .battle-hero p {
                margin: 8px 0 0 0;
                text-align: center;
                color: #B91C1C !important;
                font-size: 1.05rem;
                font-weight: 500;
            }
        </style>
        <div class='battle-hero-wrap'>
            <div class='battle-hero'>
                <h2>⚔️ Creator Battle Arena</h2>
                <p>Compare channels across subscribers, views, and engagement</p>
            </div>
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
                st.markdown("""
                    <div class='battle-band'>
                        <p>📊 Head-to-Head Comparison</p>
                    </div>
                """, unsafe_allow_html=True)

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
                        xaxis=dict(title="Channel", gridcolor='#C7D2FE', tickfont=dict(size=12)),
                        yaxis=dict(title="Total Subscribers (Log Scale)", type='log', gridcolor='#C7D2FE', zeroline=False),
                        font=dict(family="Outfit", size=13),
                        margin=dict(l=20, r=20, t=100, b=60),
                        showlegend=False,
                        plot_bgcolor='#EEF2FF',
                        paper_bgcolor='#F5F3FF',
                        hoverlabel=dict(bgcolor='#0F172A', font_color='white', bordercolor='#6366F1', font_size=13)
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
                        xaxis=dict(title="Channel", gridcolor='#FBD5B5', tickfont=dict(size=12)),
                        yaxis=dict(title="Total Views (Log Scale)", type='log', gridcolor='#FBD5B5', zeroline=False),
                        font=dict(family="Outfit", size=13),
                        margin=dict(l=20, r=20, t=100, b=60),
                        showlegend=False,
                        plot_bgcolor='#FFF1E6',
                        paper_bgcolor='#FFF7ED',
                        hoverlabel=dict(bgcolor='#0F172A', font_color='white', bordercolor='#EA580C', font_size=13)
                    )
                    st.plotly_chart(fig_views, use_container_width=True)

                st.divider()

                # ─────────────────────────────────────────────────────
                # FETCH VIDEO-LEVEL DATA for Bubble + Funnel
                # ─────────────────────────────────────────────────────
                q_vids = f"""
                    SELECT
                        c.channel_name,
                        v.video_id,
                        v.title,
                        v.published_at,
                        v.duration,
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
                    v_df_raw = pd.read_sql(text(q_vids), conn)
                v_df = apply_global_filters(v_df_raw)

                # ─────────────────────────────────────────────────────
                # SECTION 2: BUBBLE CHART — Engagement Matrix (Channel Level)
                # ─────────────────────────────────────────────────────
                st.markdown("""
                    <div class='battle-band'>
                        <p>🫧 Engagement Strength Matrix</p>
                    </div>
                """, unsafe_allow_html=True)
                st.markdown("<div class='battle-note'>Each bubble = <b>One Channel</b>. Size = total engagement. Color = channel. Ideal positioning is top-right.</div>", unsafe_allow_html=True)

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
                            gridcolor='#DDD6FE',
                            zeroline=False
                        ),
                        yaxis=dict(
                            title="Overall Quality Score % (engagement/views × 100)",
                            gridcolor='#DDD6FE',
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
                        plot_bgcolor='#F5F3FF',
                        paper_bgcolor='#FAF5FF',
                        hoverlabel=dict(bgcolor='#0F172A', font_color='white', bordercolor='#8B5CF6', font_size=13)
                    )
                    st.plotly_chart(fig_bubble, use_container_width=True)

                st.divider()

                # ─────────────────────────────────────────────────────
                # SECTION 3: RADAR CHART — Multichannel Capabilities
                # ─────────────────────────────────────────────────────
                st.markdown("""
                    <div class='battle-band'>
                        <p>🕸️ Multichannel Capabilities Radar</p>
                    </div>
                """, unsafe_allow_html=True)
                st.markdown("<div class='battle-note'>A multi-dimensional comparison of reach, production output, and engagement depth.</div>", unsafe_allow_html=True)

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
                    yaxis=dict(title="Normalized Score (0 to 1.0)", range=[0, 1.05], gridcolor='#BAE6D6', zeroline=False),
                    xaxis=dict(gridcolor='#BAE6D6'),
                    plot_bgcolor='#ECFDF5',
                    paper_bgcolor='#F0FDF4',
                    hoverlabel=dict(bgcolor='#0F172A', font_color='white', bordercolor='#10B981', font_size=13),
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
                st.markdown("""
                    <div class='battle-band'>
                        <p>📋 Channel Summary Stats</p>
                    </div>
                """, unsafe_allow_html=True)
                
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
                
                table_formatters = {
                    'Subscribers': '{:,.0f}',
                    'Total Views': '{:,.0f}',
                    'Videos': '{:,.0f}'
                }
                if 'Avg Quality %' in display_cdf.columns:
                    table_formatters['Avg Quality %'] = '{:.2f}%'

                render_premium_table(
                    display_cdf,
                    table_id='battle_summary_table',
                    max_height=420,
                    formatters=table_formatters
                )

                st.divider()

                # ─────────────────────────────────────────────────────
                # SECTION 5: BATTLE BENCHMARK ANALYSIS (migrated from Compare)
                # ─────────────────────────────────────────────────────
                st.markdown("""
                    <div class='battle-band'>
                        <p>📏 Channel vs Database Benchmark</p>
                    </div>
                """, unsafe_allow_html=True)
                st.markdown("<div class='battle-note'>Use <b>Benchmark Setup</b> filter in the sidebar to compare one channel against database averages.</div>", unsafe_allow_html=True)

                # Build full channel pool for database-average baseline
                all_ids_b = [r['id'] for r in recent]
                all_id_str_b = "','".join(all_ids_b)
                q_all_b = f"""
                    SELECT c.channel_id, c.channel_name, c.subscribers, c.views, c.total_videos
                    FROM channels c
                    WHERE c.channel_id IN ('{all_id_str_b}')
                """
                with engine.connect() as conn:
                    all_ch_b = pd.read_sql(text(q_all_b), conn)

                if not all_ch_b.empty:
                    year_clause = ""
                    selected_year_val = st.session_state.get('v_selected_year', 'All Years')
                    if selected_year_val != "All Years":
                        year_clause = f"AND v.published_at LIKE '{selected_year_val}%'"

                    q_vid_b = f"""
                        SELECT c.channel_name,
                               SUM(s.view_count) as total_vid_views,
                               SUM(s.like_count) as total_likes,
                               SUM(s.comment_count) as total_comments
                        FROM videos v
                        JOIN channels c ON v.channel_id = c.channel_id
                        JOIN video_statistics s ON v.video_id = s.video_id
                        WHERE v.channel_id IN ('{all_id_str_b}')
                          AND s.captured_at = (SELECT MAX(s2.captured_at) FROM video_statistics s2 WHERE s2.video_id = v.video_id)
                          {year_clause}
                        GROUP BY c.channel_name
                    """
                    with engine.connect() as conn:
                        vid_agg_b = pd.read_sql(text(q_vid_b), conn)

                    if not vid_agg_b.empty:
                        vid_agg_b['avg_engagement'] = (
                            (vid_agg_b['total_likes'] + vid_agg_b['total_comments']) /
                            vid_agg_b['total_vid_views'].replace(0, np.nan) * 100
                        ).fillna(0).round(2)
                        all_ch_b = all_ch_b.merge(vid_agg_b[['channel_name', 'avg_engagement']], on='channel_name', how='left')
                    else:
                        all_ch_b['avg_engagement'] = 0.0

                    all_ch_b['avg_engagement'] = all_ch_b['avg_engagement'].fillna(0.0)
                    bench_channel_b = st.session_state.get('b_bench_ch')

                    if not bench_channel_b or bench_channel_b not in all_ch_b['channel_name'].values:
                        st.info("🎯 Select a benchmark channel from Battle sidebar to view ratio analysis.")
                    else:
                        ch_row_b = all_ch_b[all_ch_b['channel_name'] == bench_channel_b].iloc[0]
                        db_avg_b = all_ch_b[['subscribers', 'views', 'avg_engagement', 'total_videos']].mean()
                        metrics_bench_b = ['Subscribers', 'Total Views', 'Engagement %', 'Total Videos']
                        ch_vals_b = [ch_row_b['subscribers'], ch_row_b['views'], ch_row_b['avg_engagement'], ch_row_b['total_videos']]
                        avg_vals_b = [db_avg_b['subscribers'], db_avg_b['views'], db_avg_b['avg_engagement'], db_avg_b['total_videos']]

                        b1, b2, b3, b4 = st.columns(4)
                        for col_w, label, ch_v, av_v in zip([b1, b2, b3, b4], metrics_bench_b, ch_vals_b, avg_vals_b):
                            diff_pct = ((ch_v - av_v) / av_v * 100) if av_v > 0 else 0
                            is_pos = diff_pct >= 0
                            arrow = "↑" if is_pos else "↓"
                            card_cls = "perf-card-pos" if is_pos else "perf-card-neg"
                            pill_cls = "compare-pill-pos" if is_pos else "compare-pill-neg"

                            if label in ['Subscribers', 'Total Views']:
                                val_str = fmt_k_m(ch_v)
                            elif label == 'Engagement %':
                                val_str = f"{ch_v:.2f}%"
                            else:
                                val_str = f"{int(ch_v):,}"

                            col_w.markdown(f"""
                                <div class='compare-perf-card {card_cls}'>
                                    <p class='perf-label'>{label}</p>
                                    <p class='perf-value'>{val_str}</p>
                                    <div class='compare-pill {pill_cls}'>
                                        {arrow} {abs(diff_pct):.1f}% vs avg
                                    </div>
                                </div>
                            """, unsafe_allow_html=True)

                        fig_bench_b = go.Figure()
                        fig_bench_b.add_trace(go.Bar(
                            x=metrics_bench_b,
                            y=[ch_v / max(av_v, 0.01) for ch_v, av_v in zip(ch_vals_b, avg_vals_b)],
                            name=bench_channel_b,
                            marker=dict(color='#6366F1', cornerradius=4, line=dict(color='white', width=1.5)),
                            hovertemplate="<b>%{x}</b><br>Ratio: %{y:.2f}x<extra></extra>"
                        ))
                        fig_bench_b.add_trace(go.Bar(
                            x=metrics_bench_b,
                            y=[1, 1, 1, 1],
                            name='Database Average',
                            marker=dict(color='#CBD5E1', cornerradius=4, line=dict(color='white', width=1.5)),
                            hovertemplate="<b>%{x}</b><br>Baseline: 1.0x<extra></extra>"
                        ))
                        fig_bench_b.update_layout(
                            barmode='group', template='plotly_white', height=400,
                            yaxis=dict(title='Ratio (1.0 = Average)', gridcolor='#F1F5F9', zeroline=True, zerolinecolor='#CBD5E1'),
                            xaxis=dict(gridcolor='#F1F5F9'),
                            font=dict(family='Outfit', size=13),
                            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='center', x=0.5),
                            margin=dict(l=30, r=20, t=60, b=40),
                            shapes=[dict(type='line', x0=-0.5, x1=3.5, y0=1, y1=1, line=dict(color='#EF4444', width=2, dash='dash'))]
                        )
                        st.plotly_chart(fig_bench_b, use_container_width=True)
                        st.caption("🔴 Dashed red line = database average (1.0x). Bars above the line = above average.")

                st.divider()

                # ─────────────────────────────────────────────────────
                # SECTION 6: BATTLE TREND COMPARISON (migrated from Compare)
                # ─────────────────────────────────────────────────────
                st.markdown("""
                    <div class='battle-band'>
                        <p>📈 Trend Comparison</p>
                    </div>
                """, unsafe_allow_html=True)
                st.markdown("<div class='battle-note'>Use <b>Trend Scope</b> and <b>Trend Chart Settings</b> in the Battle sidebar.</div>", unsafe_allow_html=True)

                trend_channels_b = st.session_state.get('b_selected', [])
                trend_metric_label_b = st.session_state.get('b_trend_m', 'Views')
                trend_metric_opts_b = {'Views': 'view_count', 'Likes': 'like_count', 'Comments': 'comment_count'}
                trend_metric_b = trend_metric_opts_b[trend_metric_label_b]
                chart_type_b = st.session_state.get('b_trend_t', 'Grouped Bar')

                if len(trend_channels_b) >= 2:
                    trend_ids_b = [r['id'] for r in recent if r['name'] in trend_channels_b]
                    t_id_str_b = "','".join(trend_ids_b)
                    q_trend_b = f"""
                        SELECT c.channel_name,
                               v.video_id,
                               v.title,
                               v.published_at,
                               v.duration,
                               s.view_count,
                               s.like_count,
                               s.comment_count
                        FROM videos v
                        JOIN channels c ON v.channel_id = c.channel_id
                        JOIN video_statistics s ON v.video_id = s.video_id
                        WHERE v.channel_id IN ('{t_id_str_b}')
                          AND s.captured_at = (SELECT MAX(s2.captured_at) FROM video_statistics s2 WHERE s2.video_id = v.video_id)
                    """
                    with engine.connect() as conn:
                        t_df_b_raw = pd.read_sql(text(q_trend_b), conn)
                    t_df_b = apply_global_filters(t_df_b_raw)

                    if not t_df_b.empty:
                        t_df_b['published_at_dt'] = pd.to_datetime(t_df_b['published_at'], format='ISO8601')
                        t_df_b['month'] = t_df_b['published_at_dt'].dt.to_period('M').astype(str)
                        trend_data_b = t_df_b.groupby(['channel_name', 'month'])[trend_metric_b].sum().reset_index()

                        all_months_b = sorted(trend_data_b['month'].unique())
                        full_index_b = pd.MultiIndex.from_product([trend_channels_b, all_months_b], names=['channel_name', 'month'])
                        trend_data_b = trend_data_b.set_index(['channel_name', 'month']).reindex(full_index_b, fill_value=0).reset_index()
                        trend_data_b = trend_data_b.sort_values('month')

                        max_trend_val_b = float(trend_data_b[trend_metric_b].max()) if not trend_data_b.empty else 0.0
                        min_visible_bar_b = max_trend_val_b * 0.02 if max_trend_val_b > 0 else 0.0
                        trend_colors_b = ['#3B82F6', '#EF4444', '#10B981', '#F59E0B', '#8B5CF6', '#EC4899', '#06B6D4', '#F97316']

                        fig_trend_b = go.Figure()
                        for i, ch_name in enumerate(trend_channels_b):
                            ch_data = trend_data_b[trend_data_b['channel_name'] == ch_name]
                            color = trend_colors_b[i % len(trend_colors_b)]

                            if chart_type_b == 'Grouped Bar':
                                actual_vals_b = ch_data[trend_metric_b].tolist()
                                display_vals_b = [(min_visible_bar_b if (v > 0 and v < min_visible_bar_b) else v) for v in actual_vals_b]
                                fig_trend_b.add_trace(go.Bar(
                                    x=ch_data['month'].tolist(), y=display_vals_b,
                                    name=ch_name,
                                    marker=dict(color=color, cornerradius=3, line=dict(color='white', width=1.3)),
                                    text=[f"{v:,.0f}" if v > 0 else "" for v in actual_vals_b],
                                    textposition='outside', textfont=dict(size=9, color=color),
                                    customdata=actual_vals_b,
                                    hovertemplate=(
                                        f"<b>{ch_name}</b><br>"
                                        "Month: <b>%{x}</b><br>"
                                        f"{trend_metric_label_b}: <b>%{{customdata:,.0f}}</b>"
                                        "<extra></extra>"
                                    )
                                ))
                            elif chart_type_b == 'Area':
                                hex_c = color.lstrip('#')
                                fill_c = f"rgba({int(hex_c[0:2],16)},{int(hex_c[2:4],16)},{int(hex_c[4:6],16)},0.15)"
                                fig_trend_b.add_trace(go.Scatter(
                                    x=ch_data['month'].tolist(), y=ch_data[trend_metric_b].tolist(),
                                    mode='lines', name=ch_name, fill='tozeroy',
                                    line=dict(color=color, width=2), fillcolor=fill_c,
                                    hovertemplate=f"<b>{ch_name}</b><br>%{{x}}<br>{trend_metric_label_b}: %{{y:,.0f}}<extra></extra>"
                                ))
                            else:
                                fig_trend_b.add_trace(go.Scatter(
                                    x=ch_data['month'].tolist(), y=ch_data[trend_metric_b].tolist(),
                                    mode='lines+markers', name=ch_name,
                                    line=dict(color=color, width=3),
                                    marker=dict(size=10, color=color, line=dict(color='white', width=2), symbol='diamond'),
                                    hovertemplate=f"<b>{ch_name}</b><br>%{{x}}<br>{trend_metric_label_b}: %{{y:,.0f}}<extra></extra>"
                                ))

                        barmode_b = 'group' if chart_type_b == 'Grouped Bar' else None
                        fig_trend_b.update_layout(
                            template='plotly_white', height=500, barmode=barmode_b,
                            xaxis=dict(title='Month', gridcolor='#F1F5F9', tickangle=-45, categoryorder='category ascending'),
                            yaxis=dict(title=f'Total {trend_metric_label_b}', gridcolor='#F1F5F9', tickformat='.2s'),
                            font=dict(family='Outfit', size=13, color='#334155'),
                            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='center', x=0.5, font=dict(size=11, color='#1E293B')),
                            margin=dict(l=40, r=20, t=60, b=80), bargap=0.22, bargroupgap=0.08,
                            hovermode='closest', plot_bgcolor='white',
                            hoverlabel=dict(bgcolor='#0B1220', bordercolor='#60A5FA', font=dict(color='#F8FAFC', size=14, family='Outfit'))
                        )
                        st.plotly_chart(fig_trend_b, use_container_width=True)

                        if chart_type_b == 'Grouped Bar' and max_trend_val_b > 0 and (trend_data_b[trend_metric_b].gt(0) & trend_data_b[trend_metric_b].lt(min_visible_bar_b)).any():
                            st.caption("ℹ️ Tiny non-zero bars are visually lifted for readability; hover shows exact original values.")

                        st.markdown("<h4 style='color:#0F172A;'>📋 Channel Summary Comparison</h4>", unsafe_allow_html=True)
                        summary_rows_b = []
                        for ch_name in trend_channels_b:
                            ch_d = trend_data_b[trend_data_b['channel_name'] == ch_name]
                            total = ch_d[trend_metric_b].sum()
                            avg = ch_d[trend_metric_b].mean()
                            peak_month = ch_d.loc[ch_d[trend_metric_b].idxmax(), 'month'] if total > 0 else 'N/A'
                            peak_val = ch_d[trend_metric_b].max()
                            summary_rows_b.append({
                                'Channel': ch_name,
                                f'Total {trend_metric_label_b}': total,
                                'Avg Monthly': avg,
                                'Peak Month': peak_month,
                                'Peak Value': peak_val,
                                'Active Months': int((ch_d[trend_metric_b] > 0).sum())
                            })
                        trend_summary_df_b = pd.DataFrame(summary_rows_b)
                        render_premium_table(
                            trend_summary_df_b,
                            table_id='battle_trend_summary_table',
                            max_height=360,
                            formatters={
                                f'Total {trend_metric_label_b}': '{:,.0f}',
                                'Avg Monthly': '{:,.0f}',
                                'Peak Value': '{:,.0f}',
                                'Active Months': '{:d}'
                            }
                        )
                    else:
                        st.warning("No video data available for the selected trend channels.")
                else:
                    st.info("👆 Select at least **2 channels** in Battle sidebar Trend Scope to compare monthly trends.")


# --- PAGE: VISUALS (Task 12 & 13: Pro Intelligence) ---
# --- PAGE: VISUALS (Task 12 & 13: Ultimate Strategic Suite) ---
elif st.session_state['page'] == 'vis':
    if not st.session_state['active_channel_id']:
        st.warning("Please select a channel from the sidebar to view analysis.")
    else:
        render_help_widget('visuals')
        chid = st.session_state['active_channel_id']
        df = get_channel_data(chid)
        if not df.empty:
            st.markdown("""
                <style>
                    .vis-hero {
                        background: linear-gradient(135deg, #0F172A 0%, #17233F 50%, #1D2B4A 100%);
                        border: 1px solid #334155;
                        border-radius: 18px;
                        padding: 16px 18px;
                        margin-bottom: 12px;
                        box-shadow: 0 14px 28px rgba(15,23,42,0.22);
                    }
                    .vis-hero h3 {
                        margin: 0;
                        font-family: 'Outfit', sans-serif;
                        font-size: 1.18rem;
                        color: #E2E8F0 !important;
                    }
                    .vis-hero p {
                        margin: 6px 0 0 0;
                        color: #A5B4FC !important;
                        font-size: 0.92rem;
                    }
                    .vis-title-wrap {
                        background: linear-gradient(135deg, #111827 0%, #17233F 50%, #1D2B4A 100%);
                        border: 1px solid #334155;
                        border-radius: 18px;
                        padding: 14px 18px;
                        margin: 4px auto 10px auto;
                        max-width: 620px;
                        box-shadow: 0 14px 26px rgba(15,23,42,0.24), inset 0 1px 0 rgba(255,255,255,0.06);
                    }
                    .vis-title-row {
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        gap: 16px;
                    }
                    .vis-title-icon {
                        width: 40px;
                        height: 40px;
                        border-radius: 10px;
                        display: inline-flex;
                        align-items: center;
                        justify-content: center;
                        background: linear-gradient(135deg, #1D4ED8 0%, #2563EB 100%);
                        color: #FFFFFF;
                        box-shadow: 0 5px 12px rgba(37, 99, 235, 0.25);
                    }
                    .vis-title-text {
                        margin: 0;
                        font-family: 'Outfit', sans-serif;
                        font-size: 2.1rem;
                        font-weight: 900;
                        letter-spacing: 0.3px;
                        color: #F8FAFC !important;
                        line-height: 1.05;
                        text-shadow: 0 2px 8px rgba(15,23,42,0.35);
                    }
                    .vis-title-sub {
                        margin: 4px 0 0 0;
                        text-align: center;
                        color: #93C5FD !important;
                        font-size: 0.95rem;
                        font-weight: 700;
                    }
                    .vis-band {
                        border-left: 4px solid #818CF8;
                        background: linear-gradient(90deg, #1E293B 0%, #1E293B 45%, rgba(30,41,59,0.04) 100%);
                        border-radius: 8px;
                        padding: 10px 12px;
                        margin: 8px 0 8px 0;
                    }
                    .vis-band p {
                        margin: 0;
                        font-family: 'Outfit', sans-serif;
                        font-size: 1rem;
                        font-weight: 700;
                        color: #E2E8F0 !important;
                    }

                    /* Tab strip for Visuals */
                    div[data-testid="stTabs"] > div[data-baseweb="tab-list"] {
                        gap: 8px !important;
                        padding-bottom: 6px !important;
                    }
                    div[data-testid="stTabs"] button[role="tab"] {
                        background: #F8FAFC !important;
                        color: #334155 !important;
                        border: 1px solid #D3DAE7 !important;
                        border-radius: 999px !important;
                        padding: 9px 18px !important;
                        font-size: 0.9rem !important;
                        font-weight: 700 !important;
                        box-shadow: none !important;
                    }
                    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
                        background: linear-gradient(135deg, #6366F1 0%, #8B5CF6 100%) !important;
                        color: #FFFFFF !important;
                        border-color: #6366F1 !important;
                        box-shadow: 0 6px 16px rgba(99,102,241,0.35) !important;
                    }

                    /* Plot cards in Visuals page */
                    div[data-testid="stPlotlyChart"] {
                        border: 1px solid #334155 !important;
                        border-radius: 16px !important;
                        padding: 8px !important;
                        background: linear-gradient(180deg, #1C2A46 0%, #18253F 100%) !important;
                        box-shadow: 0 10px 22px rgba(15,23,42,0.18) !important;
                    }
                </style>
            """, unsafe_allow_html=True)

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
            
            
            st.markdown("""
                <style>
                    .vis-hero-wrap {
                        display: flex;
                        justify-content: center;
                        margin: 4px 0 12px 0;
                    }
                    .vis-hero-card {
                        width: min(980px, 96%);
                        background: linear-gradient(135deg, #F8FAFC 0%, #E6F9F3 50%, #E0F7EE 100%);
                        border: 1px solid #B8E5D5;
                        border-radius: 16px;
                        padding: 16px 18px;
                        box-shadow: 0 10px 24px rgba(5, 150, 105, 0.08);
                    }
                    .vis-hero-card h2 {
                        margin: 0;
                        text-align: center;
                        font-family: 'Outfit', sans-serif;
                        font-size: 2rem;
                        font-weight: 800;
                        color: #065F46 !important;
                    }
                    .vis-hero-card p {
                        margin: 8px 0 0 0;
                        text-align: center;
                        color: #047857 !important;
                        font-size: 1.05rem;
                        font-weight: 500;
                    }
                </style>
                <div class='vis-hero-wrap'>
                    <div class='vis-hero-card'>
                        <h2>📊 Visualizations</h2>
                        <p>Deep-dive analytics with charts, heatmaps, and performance insights</p>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
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
                    st.markdown("""
                        <div class='vis-band'><p>📈 Monthly Engagement Trends</p></div>
                    """, unsafe_allow_html=True)
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
                            plot_bgcolor='#F8FAFC',
                            paper_bgcolor='#F8FAFC',
                            hoverlabel=dict(bgcolor='#0F172A', font_color='white', bordercolor='#6366F1', font_size=13)
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
                    st.markdown("""
                        <div class='vis-band'><p>🗓️ Upload Frequency Heatmap (Month × Day of Week)</p></div>
                    """, unsafe_allow_html=True)
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
                        plot_bgcolor='#F0FDF4',
                        paper_bgcolor='#F0FDF4',
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
                    st.markdown("""
                        <div class='vis-band'><p>🧠 Expert Channel Health Analytics</p></div>
                    """, unsafe_allow_html=True)
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
                        st.markdown("""
                            <div class='vis-band'><p>◆ Consistency Score</p></div>
                        """, unsafe_allow_html=True)
                        st.caption("Stability index from your selected videos")
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
                                bgcolor='#F8FAFC',
                                borderwidth=0,
                                steps=[
                                    dict(range=[0, 40],  color='#FECACA'),
                                    dict(range=[40, 70], color='#FEF08A'),
                                    dict(range=[70, 100],color='#A7F3D0'),
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
                            margin=dict(l=30, r=30, t=20, b=30),
                            paper_bgcolor='#FFF8DC'
                        )
                        st.plotly_chart(fig_ring, use_container_width=True)
                        st.markdown(f"""
                        <div style='background:linear-gradient(135deg,#DBEAFE,#BFDBFE);
                                    border:1px solid #93C5FD; border-radius:12px;
                                    padding:15px 20px; margin-top:6px; min-height:190px;'>
                            <p style='margin:0 0 8px 0; font-size:0.95rem; font-weight:700; color:#1E40AF;'>
                                📋 Consistency Reading
                            </p>
                            <ul style='margin:0; padding-left:18px; font-size:0.92rem; color:#1E3A8A; line-height:1.7;'>
                                <li><b>Score:</b> <b>{stability_score}</b>/100 categorized as <b>{score_label.lower()}</b>.</li>
                                <li><b>Interpretation:</b> {score_msg}</li>
                            </ul>
                        </div>
                        """, unsafe_allow_html=True)

                    with c_h2:
                        st.markdown("""
                            <div class='vis-band'><p>📦 Performance Box Plot</p></div>
                        """, unsafe_allow_html=True)
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
                            template='plotly_white', height=460,
                            yaxis=dict(title=sel_metric_label, gridcolor='#F1F5F9', tickformat=tickformat),
                            font=dict(family="Inter", size=13),
                            showlegend=False,
                            margin=dict(l=30, r=15, t=20, b=30),
                            paper_bgcolor='#D1FAE5',
                            plot_bgcolor='#E7FDF3',
                            hoverlabel=dict(bgcolor='#0F172A', font_color='white', bordercolor='#10B981', font_size=13)
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
                        <div style='background:linear-gradient(135deg,#DCFCE7,#BBF7D0);
                                    border:1px solid #6EE7B7; border-radius:12px;
                                    padding:15px 20px; margin-top:6px; min-height:190px;'>
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
                    st.markdown("""
                        <div class='vis-band'><p>📊 View Count Distribution (Histogram)</p></div>
                    """, unsafe_allow_html=True)
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
                        margin=dict(l=30, r=30, t=20, b=40),
                        paper_bgcolor='#EEF2FF',
                        plot_bgcolor='#EDE9FE',
                        hoverlabel=dict(bgcolor='#0F172A', font_color='white', bordercolor='#6366F1', font_size=13)
                    )
                    st.plotly_chart(fig_hist, use_container_width=True)
                    st.caption(f"X-axis units: **{tick_sfx if tick_sfx else 'absolute count'}**. Each bar = a range of view counts. Taller bars = more videos in that bracket.")

                    st.divider()

                    # ── KEYWORDS ──────────────────────────────────────────────
                    st.markdown("""
                        <div class='vis-band'><p>🏷️ Topic Intelligence: Winning Keywords</p></div>
                    """, unsafe_allow_html=True)
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
                                plot_bgcolor='#FDF4FF', paper_bgcolor='#FAF5FF',
                                hoverlabel=dict(bgcolor='#0F172A', font_color='white', bordercolor='#A855F7', font_size=13)
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
                    st.markdown("""
                        <div class='vis-band'><p>🗺️ Content Impact Architecture — Top 15 Videos</p></div>
                    """, unsafe_allow_html=True)

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
                            paper_bgcolor='#F8FAFC'
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
                        st.markdown("""
                            <div class='vis-band'><p>🎯 Best Video Signature Radar</p></div>
                        """, unsafe_allow_html=True)
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
                                paper_bgcolor='#EFF6FF',
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
                        st.markdown("""
                            <div class='vis-band'><p>🌪️ Audience Conversion Funnel</p></div>
                        """, unsafe_allow_html=True)
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
                                paper_bgcolor='#FFF7ED',
                                plot_bgcolor='#FFF7ED'
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
        df_raw = get_channel_data(chid)

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

            st.markdown("""
                <style>
                    .search-hero-wrap {
                        display: flex;
                        justify-content: center;
                        margin: 4px 0 12px 0;
                    }
                    .search-hero {
                        width: min(980px, 96%);
                        background: linear-gradient(135deg, #F8FAFC 0%, #EEF2FF 55%, #ECFEFF 100%);
                        border: 1px solid #CBD5E1;
                        border-radius: 16px;
                        padding: 16px 18px;
                        box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
                    }
                    .search-hero h2 {
                        margin: 0;
                        text-align: center;
                        font-family: 'Outfit', sans-serif;
                        font-size: 2rem;
                        font-weight: 800;
                        color: #1E293B !important;
                    }
                    .search-hero p {
                        margin: 8px 0 0 0;
                        text-align: center;
                        color: #334155 !important;
                        font-size: 1.05rem;
                        font-weight: 500;
                    }
                    .search-kpi-grid {
                        display: grid;
                        grid-template-columns: repeat(5, minmax(0, 1fr));
                        gap: 12px;
                        margin: 12px 0 6px 0;
                    }
                    .search-kpi-card {
                        border-radius: 14px;
                        border: 1px solid #D8E1EE;
                        padding: 12px 12px;
                        box-shadow: 0 6px 16px rgba(15,23,42,0.06);
                        background: #FFFFFF;
                    }
                    .search-kpi-label {
                        font-family: 'Outfit', sans-serif;
                        color: #475569;
                        font-size: 0.92rem;
                        font-weight: 700;
                        margin-bottom: 6px;
                    }
                    .search-kpi-value {
                        font-family: 'Outfit', sans-serif;
                        color: #0F172A;
                        font-size: 1.65rem;
                        line-height: 1.05;
                        font-weight: 900;
                    }
                    .search-kpi-sub {
                        color: #64748B;
                        font-size: 0.8rem;
                        font-weight: 600;
                        margin-top: 2px;
                    }
                </style>
            """, unsafe_allow_html=True)

            # ── Page Header ──
            c_name = df_s.iloc[0]['channel_name']
            st.markdown(f"""
                <div class='search-hero-wrap'>
                    <div class='search-hero'>
                        <h2>🔍 Smart Video Search & Filter</h2>
                        <p>Deep-dive into <b>{c_name}</b>'s library of <b>{total_videos}</b> videos</p>
                    </div>
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
            avg_views = fmt_k_m(filt['view_count'].mean()) if n_results else "—"
            avg_likes = fmt_k_m(filt['like_count'].mean()) if n_results else "—"
            avg_eng = f"{filt['engagement_rate'].mean():.2f}%" if n_results else "—"
            avg_dur = f"{filt['duration_min'].mean():.1f}m" if n_results else "—"

            st.markdown(f"""
                <div class='search-kpi-grid'>
                    <div class='search-kpi-card' style='background:linear-gradient(135deg,#EEF2FF 0%, #FFFFFF 100%);'>
                        <div class='search-kpi-label'>📹 Results</div>
                        <div class='search-kpi-value'>{n_results} / {total_videos}</div>
                        <div class='search-kpi-sub'>Filtered vs Library</div>
                    </div>
                    <div class='search-kpi-card' style='background:linear-gradient(135deg,#ECFEFF 0%, #FFFFFF 100%);'>
                        <div class='search-kpi-label'>👁️ Avg Views</div>
                        <div class='search-kpi-value'>{avg_views}</div>
                        <div class='search-kpi-sub'>Across filtered videos</div>
                    </div>
                    <div class='search-kpi-card' style='background:linear-gradient(135deg,#FEF3C7 0%, #FFFFFF 100%);'>
                        <div class='search-kpi-label'>❤️ Avg Likes</div>
                        <div class='search-kpi-value'>{avg_likes}</div>
                        <div class='search-kpi-sub'>Audience reaction level</div>
                    </div>
                    <div class='search-kpi-card' style='background:linear-gradient(135deg,#FCE7F3 0%, #FFFFFF 100%);'>
                        <div class='search-kpi-label'>💎 Avg Engagement</div>
                        <div class='search-kpi-value'>{avg_eng}</div>
                        <div class='search-kpi-sub'>Interaction quality score</div>
                    </div>
                    <div class='search-kpi-card' style='background:linear-gradient(135deg,#E0F2FE 0%, #FFFFFF 100%);'>
                        <div class='search-kpi-label'>⏱️ Avg Duration</div>
                        <div class='search-kpi-value'>{avg_dur}</div>
                        <div class='search-kpi-sub'>Video length profile</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

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
                            if thumb_url: st.image(thumb_url, use_container_width=True)
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
        <style>
            .compare-hero-wrap {
                display: flex;
                justify-content: center;
                margin: 4px 0 12px 0;
            }
            .compare-hero {
                width: min(980px, 96%);
                background: linear-gradient(135deg, #F8FAFC 0%, #F5E6FF 50%, #EDE9FE 100%);
                border: 1px solid #D5C5F0;
                border-radius: 16px;
                padding: 16px 18px;
                box-shadow: 0 10px 24px rgba(147, 51, 234, 0.08);
            }
            .compare-hero h2 {
                margin: 0;
                text-align: center;
                font-family: 'Outfit', sans-serif;
                font-size: 2rem;
                font-weight: 800;
                color: #581C87 !important;
            }
            .compare-hero p {
                margin: 8px 0 0 0;
                text-align: center;
                color: #7C3AED !important;
                font-size: 1.05rem;
                font-weight: 500;
            }
        </style>
        <div class='compare-hero-wrap'>
            <div class='compare-hero'>
                <h2>📦 Exports & Reporting Hub</h2>
                <p>Leaderboard rankings and export-ready analytics intelligence</p>
            </div>
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

            # --- END GLOBAL CAPTURE ---
            
            # ═══════════════════════════════════════════════════
            # SECTION 1: LEADERBOARD
            # ═══════════════════════════════════════════════════
            st.markdown("""
                <div class='compare-super-heading'>
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

            # Top 3 highlight cards
            top3 = lb.head(3).copy()
            medal_styles = [
                ("🥇 Gold Leader", "linear-gradient(135deg,#FFF8E1,#FDE68A)", "#B45309", "#F59E0B"),
                ("🥈 Silver Leader", "linear-gradient(135deg,#F8FAFC,#E2E8F0)", "#475569", "#94A3B8"),
                ("🥉 Bronze Leader", "linear-gradient(135deg,#FFF1E6,#FDBA74)", "#9A3412", "#EA580C"),
            ]
            t1, t2, t3 = st.columns(3)
            for col, (_, row), style in zip([t1, t2, t3], top3.iterrows(), medal_styles):
                title, bg, text_c, border_c = style
                col.markdown(f"""
                    <div style='background:{bg}; border:1.5px solid {border_c}; border-radius:16px; padding:16px 16px 14px 16px; min-height:170px;'>
                        <p style='margin:0; font-weight:800; color:{text_c}; font-size:0.95rem;'>{title}</p>
                        <p style='margin:8px 0 0 0; font-size:1.35rem; font-weight:900; color:#0F172A;'>{row['channel_name']}</p>
                        <p style='margin:8px 0 0 0; color:#334155; font-size:0.9rem;'>👥 <b>{int(row['subscribers']):,}</b> Subs</p>
                        <p style='margin:3px 0 0 0; color:#334155; font-size:0.9rem;'>👁️ <b>{int(row['views']):,}</b> Views</p>
                        <p style='margin:3px 0 0 0; color:#334155; font-size:0.9rem;'>💎 <b>{float(row['avg_engagement']):.2f}%</b> Engagement</p>
                    </div>
                """, unsafe_allow_html=True)

            st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

            # Premium table style aligned with Raw Data design
            render_premium_table(
                show_lb,
                table_id='compare_leaderboard_table',
                max_height=520,
                formatters={
                    'Engagement %': '{:.2f}%'
                }
            )

            st.divider()

            # ═══════════════════════════════════════════════════
            # SECTION 4: EXPORT & DATA HUB
            # ═══════════════════════════════════════════════════
            st.markdown("""
                <div class='compare-super-heading'>
                    <h3 style='margin:0; color:#0F172A;'>💎 Analytics Data Hub</h3>
                    <p style='margin:0; color:#64748B; font-size:0.9rem;'>Premium CSV exports with deep architectural insights</p>
                </div>
            """, unsafe_allow_html=True)

            from io import BytesIO

            def _to_excel_bytes(sheets_dict):
                def _excel_engine_available():
                    try:
                        import xlsxwriter  # noqa: F401  # type: ignore
                        return 'xlsxwriter'
                    except Exception:
                        try:
                            import openpyxl  # noqa: F401  # type: ignore
                            return 'openpyxl'
                        except Exception:
                            return None

                excel_engine = _excel_engine_available()
                if not excel_engine:
                    return None

                output = BytesIO()
                with pd.ExcelWriter(output, engine=excel_engine) as writer:
                    for sheet_name, df_sheet in sheets_dict.items():
                        safe_name = str(sheet_name)[:31]
                        df_sheet.to_excel(writer, index=False, sheet_name=safe_name)
                output.seek(0)
                return output.getvalue()

            # Styled CSV Cards
            export_lb = all_ch[['channel_name','subscribers','views','avg_engagement','total_videos']].rename(columns={
                'channel_name':'Channel','subscribers':'Subscribers','views':'Total Views','avg_engagement':'Avg Engagement %','total_videos':'Total Videos'
            }).sort_values('Subscribers', ascending=False)
            leaderboard_xlsx = _to_excel_bytes({'Leaderboard': export_lb})
            
            channel_name_default = st.session_state.get('active_channel_id') and next((r['name'] for r in recent if r['id'] == st.session_state.get('active_channel_id')), '') or ''
            channel_name_input = st.text_input("🔎 Channel Name", value=channel_name_default, key='hub_channel_name')
            matched_channel = all_ch[all_ch['channel_name'].str.lower() == str(channel_name_input).strip().lower()]

            exp_c1, exp_c2, exp_c3 = st.columns(3)
            
            with exp_c1:
                st.markdown("""
                    <div class='compare-export-card compare-export-blue'>
                        <h4>📊 Leaderboard Matrix</h4>
                        <p>Strategic channel rankings and relative positioning.</p>
                        <p style='margin-top:8px; color:#1E3A8A; font-weight:700;'>📄 CSV + 📗 XLSX export supported</p>
                    </div>
                """, unsafe_allow_html=True)
                st.markdown("<style>div[data-testid='stHorizontalBlock'] div[key='csv_lb'] button {background:#3B82F6 !important; color:white !important; border:none !important;}</style>", unsafe_allow_html=True)
                dl1, dl2 = st.columns(2)
                with dl1:
                    st.download_button("📄 CSV", export_lb.to_csv(index=False).encode('utf-8'), 'leaderboard.csv', 'text/csv', use_container_width=True, key='csv_lb')
                with dl2:
                    if leaderboard_xlsx is not None:
                        st.download_button("📗 XLSX", leaderboard_xlsx, 'leaderboard.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', use_container_width=True, key='xlsx_lb')
                    else:
                        st.info("XLSX export unavailable. Install `XlsxWriter` or `openpyxl` in current venv.")

            with exp_c2:
                st.markdown("""
                    <div class='compare-export-card compare-export-violet'>
                        <h4>📌 Top 10 by Current Rank</h4>
                        <p>Focused shortlist based on active leaderboard ranking metric.</p>
                    </div>
                """, unsafe_allow_html=True)
                st.markdown("<style>div[data-testid='stHorizontalBlock'] div[key='csv_top10'] button {background:#8B5CF6 !important; color:white !important; border:none !important;}</style>", unsafe_allow_html=True)
                top10_export = show_lb.head(10)
                st.download_button("📥 Download Top 10", top10_export.to_csv(index=False).encode('utf-8'), 'leaderboard_top10.csv', 'text/csv', use_container_width=True, key='csv_top10')

            with exp_c3:
                st.markdown("""
                    <div class='compare-export-card compare-export-amber'>
                        <h4>🧾 Channel Deep Workbook</h4>
                        <p>Enter one channel name to export a detailed XLSX with analysis tabs.</p>
                    </div>
                """, unsafe_allow_html=True)
                st.markdown("<style>div[data-testid='stHorizontalBlock'] div[key='xlsx_channel_detail'] button {background:#F59E0B !important; color:white !important; border:none !important;}</style>", unsafe_allow_html=True)
                if not matched_channel.empty:
                    target_name = matched_channel.iloc[0]['channel_name']
                    target_id = all_ch[all_ch['channel_name'] == target_name]['channel_id'].iloc[0]
                    q_detail = """
                        SELECT v.video_id, v.title, v.published_at, v.duration, s.view_count, s.like_count, s.comment_count
                        FROM videos v
                        JOIN video_statistics s ON v.video_id = s.video_id
                        WHERE v.channel_id = :channel_id
                          AND s.captured_at = (SELECT MAX(s2.captured_at) FROM video_statistics s2 WHERE s2.video_id = v.video_id)
                    """
                    with engine.connect() as conn:
                        detail_df = pd.read_sql(text(q_detail), conn, params={'channel_id': target_id})

                    if not detail_df.empty:
                        detail_df['published_at_dt'] = pd.to_datetime(detail_df['published_at'], errors='coerce')
                        detail_df['month'] = detail_df['published_at_dt'].dt.to_period('M').astype(str)
                        detail_df['week'] = detail_df['published_at_dt'].dt.strftime('%Y-W%U')
                        detail_df['day'] = detail_df['published_at_dt'].dt.strftime('%Y-%m-%d')
                        detail_df['engagement_rate'] = ((detail_df['like_count'] + detail_df['comment_count']) / detail_df['view_count'].replace(0, np.nan) * 100).fillna(0).round(2)

                        overview_df = pd.DataFrame([{
                            'Channel': target_name,
                            'Subscribers': int(matched_channel.iloc[0]['subscribers']),
                            'Total Views': int(matched_channel.iloc[0]['views']),
                            'Avg Engagement %': float(matched_channel.iloc[0]['avg_engagement']),
                            'Total Videos': int(matched_channel.iloc[0]['total_videos'])
                        }])
                        monthly_df = detail_df.groupby('month')[['view_count','like_count','comment_count']].sum().reset_index().rename(columns={'view_count':'Views','like_count':'Likes','comment_count':'Comments'})
                        weekly_df = detail_df.groupby('week')[['view_count','like_count','comment_count']].sum().reset_index().rename(columns={'view_count':'Views','like_count':'Likes','comment_count':'Comments'})
                        daily_df = detail_df.groupby('day')[['view_count','like_count','comment_count']].sum().reset_index().rename(columns={'view_count':'Views','like_count':'Likes','comment_count':'Comments'})
                        top_videos_df = detail_df.sort_values('view_count', ascending=False).head(50)[['title','published_at','view_count','like_count','comment_count','engagement_rate']].rename(columns={'published_at':'Published At','view_count':'Views','like_count':'Likes','comment_count':'Comments','engagement_rate':'Engagement %'})
                        insights_df = pd.DataFrame([
                            {'Insight': 'Average Views per Video', 'Value': round(float(detail_df['view_count'].mean()), 2)},
                            {'Insight': 'Median Engagement %', 'Value': round(float(detail_df['engagement_rate'].median()), 2)},
                            {'Insight': 'Top Video Views', 'Value': int(detail_df['view_count'].max())},
                            {'Insight': 'Total Videos Analysed', 'Value': int(len(detail_df))},
                        ])

                        workbook_bytes = _to_excel_bytes({
                            'Overview': overview_df,
                            'Videos Raw': detail_df[['video_id','title','published_at','duration','view_count','like_count','comment_count','engagement_rate']],
                            'Monthly Trend': monthly_df,
                            'Weekly Trend': weekly_df,
                            'Daily Trend': daily_df,
                            'Top Videos': top_videos_df,
                            'Insights': insights_df
                        })
                        if workbook_bytes is not None:
                            st.download_button(
                                "📥 Download Channel XLSX",
                                workbook_bytes,
                                f"{target_name.replace(' ', '_').lower()}_deep_analysis.xlsx",
                                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                use_container_width=True,
                                key='xlsx_channel_detail'
                            )
                        else:
                            st.info("Channel XLSX export unavailable. Install XlsxWriter or openpyxl in current venv.")
                    else:
                        st.caption("No detailed video rows found for this channel yet.")
                else:
                    st.caption("Enter an exact channel name from leaderboard to enable detailed XLSX export.")

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
            if '_rpt_period' not in st.session_state: st.session_state['_rpt_period'] = 'Overall'

            st.markdown("<h4 style='color:#0F172A; margin-bottom:15px;'>📄 PDF Report Builder</h4>", unsafe_allow_html=True)
            
            # Show saved Battle rivals status
            saved_rivals = st.session_state.get('b_selected', [])
            if saved_rivals and len(saved_rivals) >= 2:
                rivals_display = ", ".join(saved_rivals[:3]) + (f" + {len(saved_rivals)-3} more" if len(saved_rivals) > 3 else "")
                st.success(f"⚔️ Battle Arena Data Ready: {len(saved_rivals)} rivals ({rivals_display}) will be included in your report.")
            elif saved_rivals:
                st.info(f"⚔️ Not Ready: {len(saved_rivals)} rival selected. Go to Battle page and select at least 2 rivals for Battle charts.")
            else:
                st.info("⚔️ No Battle rivals selected yet. Go to Battle page to select rivals for comparison charts.")
            st.markdown("")
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
                    all_secs_opt = ['Channel Overview', 'Leaderboard Rankings', 'Benchmark Analysis', 'Growth Velocity', 'Audience Quality', 'Strategic Insights', 'Key Insights', 'Performance Summary', 'Dashboard Insights', 'Profile Insights', 'Battle Insights', 'Visual Insights', 'Trend Analysis']
                    
                    c1, c2 = st.columns([2, 1])
                    with c1:
                        sel_secs = st.multiselect("📝 Included Sections", all_secs_opt, default=[s for s in st.session_state['_rpt_secs'] if s in all_secs_opt])
                    with c2:
                        sel_ttl = st.text_input("📌 Report Title", value=st.session_state['_rpt_ttl'])
                        sel_period = st.selectbox("📅 Report Granularity", ['Overall', 'Monthly', 'Weekly', 'Daily'], index=['Overall', 'Monthly', 'Weekly', 'Daily'].index(st.session_state.get('_rpt_period', 'Overall')))
                    
                    st.divider()
                    b1, b2 = st.columns([1, 1])
                    if b1.button("⬅️ Back to Templates", use_container_width=True):
                        st.session_state['_rpt_step'] = 1
                        st.rerun()
                    if b2.button("🚀 Prepare Download", use_container_width=True, type="primary"):
                        st.session_state['_rpt_secs'] = sel_secs
                        st.session_state['_rpt_ttl'] = sel_ttl
                        st.session_state['_rpt_period'] = sel_period
                        st.session_state['_rpt_step'] = 3
                        st.rerun()

            # --- STEP 3: PREVIEW & DOWNLOAD ---
            elif step == 3:
                bench_channel = st.session_state.get('b_bench_ch')
                report_period = st.session_state.get('_rpt_period', 'Overall')
                focus_context = f" for **{bench_channel}**" if bench_channel else ""
                st.info(f"✨ **Ready!** Your {report_period.lower()} report '{st.session_state['_rpt_ttl']}'{focus_context} is prepared with {len(st.session_state['_rpt_secs'])} sections.")
                
                # Initialize data for PDF generation
                active_ch_id = st.session_state.get('active_channel_id')
                ch_df_pdf = pd.DataFrame()
                if active_ch_id:
                    ch_df_pdf = get_channel_data(active_ch_id)
                    if not ch_df_pdf.empty:
                        ch_df_pdf = ch_df_pdf.drop_duplicates(subset=['video_id']).copy()
                        ch_df_pdf['published_at_dt'] = pd.to_datetime(ch_df_pdf['published_at'], errors='coerce')
                        ch_df_pdf = ch_df_pdf.dropna(subset=['published_at_dt'])
                        ch_df_pdf = Caluclate_engagement_rate(ch_df_pdf)
                        ch_df_pdf = Calculate_sub_to_view_ratio(ch_df_pdf)
                        ch_df_pdf = Calculate_content_score(ch_df_pdf)
                        ch_df_pdf['day_name'] = ch_df_pdf['published_at_dt'].dt.day_name()
                        ch_df_pdf['year'] = ch_df_pdf['published_at_dt'].dt.year
                        ch_df_pdf['engagement_rate'] = ((
                            ch_df_pdf['like_count'] + ch_df_pdf['comment_count']
                        ) / ch_df_pdf['view_count'].replace(0, np.nan) * 100).fillna(0)

                        def _pdf_detect_type(row):
                            dur = parse_duration(row['duration'])
                            has_tag = '#shorts' in str(row['title']).lower()
                            return 'Shorts' if has_tag or dur <= 100 else 'Long-form'

                        ch_df_pdf['is_short'] = ch_df_pdf.apply(_pdf_detect_type, axis=1)
                
                try:
                    from fpdf import FPDF
                    from datetime import datetime
                    
                    class AnalyticsPDF(FPDF):
                        def _safe_pdf_text(self, value):
                            if value is None:
                                return ''
                            s = str(value)
                            # Normalize common Unicode glyphs that Helvetica cannot encode.
                            s = (s
                                 .replace('—', '-')
                                 .replace('–', '-')
                                 .replace('…', '...')
                                 .replace('•', '*')
                                 .replace('✅', '[OK]')
                                 .replace('📈', '[Trend]')
                                 .replace('📊', '[Chart]')
                                 .replace('📌', '[Pin]')
                                 .replace('📅', '[Date]')
                                 .replace('📄', '[PDF]')
                                 .replace('📦', '[Data]')
                                 .replace('💎', '[Hub]')
                                 .replace('🔎', '[Search]')
                                 .replace('🚀', '[Go]')
                                 .replace('⬅️', '<-')
                                 .replace('🔙', '<-')
                                 .replace('✨', '*'))
                            return s.encode('latin-1', 'replace').decode('latin-1')

                        def cell(self, *args, **kwargs):
                            if len(args) >= 3:
                                args = list(args)
                                args[2] = self._safe_pdf_text(args[2])
                                args = tuple(args)
                            elif 'txt' in kwargs:
                                kwargs['txt'] = self._safe_pdf_text(kwargs.get('txt'))
                            elif 'text' in kwargs:
                                kwargs['text'] = self._safe_pdf_text(kwargs.get('text'))
                            try:
                                return super().cell(*args, **kwargs)
                            except Exception as e:
                                if 'Not enough horizontal space' not in str(e):
                                    raise

                                # Fallback: move to a safe position and clamp width to available space.
                                h = float(args[1]) if len(args) >= 2 else float(kwargs.get('h', 0) or 0)
                                txt = ''
                                if len(args) >= 3:
                                    txt = str(args[2])
                                elif 'txt' in kwargs:
                                    txt = str(kwargs.get('txt') or '')
                                elif 'text' in kwargs:
                                    txt = str(kwargs.get('text') or '')

                                if self.get_x() >= (self.w - self.r_margin - 2):
                                    self.set_x(self.l_margin)
                                    if h > 0:
                                        self.ln(h)
                                    else:
                                        self.ln(5)

                                avail = self.w - self.r_margin - self.get_x()
                                if avail < 2:
                                    self.add_page()
                                    self.set_x(self.l_margin)
                                    avail = self.w - self.r_margin - self.get_x()

                                safe_h = max(4.0, h if h > 0 else 6.0)
                                safe_txt = self._safe_pdf_text(txt)[:80]
                                return super().cell(max(2.0, avail), safe_h, safe_txt, align='L')

                        def multi_cell(self, *args, **kwargs):
                            if len(args) >= 3:
                                args = list(args)
                                args[2] = self._safe_pdf_text(args[2])
                                args = tuple(args)
                            elif 'txt' in kwargs:
                                kwargs['txt'] = self._safe_pdf_text(kwargs.get('txt'))
                            elif 'text' in kwargs:
                                kwargs['text'] = self._safe_pdf_text(kwargs.get('text'))
                            try:
                                return super().multi_cell(*args, **kwargs)
                            except Exception as e:
                                if 'Not enough horizontal space' not in str(e):
                                    raise

                                h = float(args[1]) if len(args) >= 2 else float(kwargs.get('h', 0) or 0)
                                txt = ''
                                if len(args) >= 3:
                                    txt = str(args[2])
                                elif 'txt' in kwargs:
                                    txt = str(kwargs.get('txt') or '')
                                elif 'text' in kwargs:
                                    txt = str(kwargs.get('text') or '')

                                if self.get_x() >= (self.w - self.r_margin - 2):
                                    self.set_x(self.l_margin)

                                avail = self.w - self.r_margin - self.get_x()
                                if avail < 2:
                                    self.add_page()
                                    self.set_x(self.l_margin)
                                    avail = self.w - self.r_margin - self.get_x()

                                safe_h = max(4.0, h if h > 0 else 6.0)
                                safe_txt = self._safe_pdf_text(txt)[:240]
                                return super().multi_cell(max(2.0, avail), safe_h, safe_txt, align='L')

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
                            # Ensure we have enough space for header, add more buffer to prevent overlaps
                            self.ensure_page_fit(35)
                            self.ln(6)
                            self.set_fill_color(*color); self.set_text_color(255, 255, 255)
                            self.set_font('Helvetica', 'B', 12)
                            self.cell(0, 10, f'  {title}', fill=True, new_x='LMARGIN', new_y='NEXT')
                            self.ln(4); self.set_text_color(30, 41, 59)
                            
                        def smart_table(self, headers, data, col_widths=None, h_color=(59,130,246), highlight_val=None):
                            n_cols = max(1, len(headers))
                            if not col_widths:
                                col_widths = [190 // n_cols] * n_cols

                            # Match width list to header count.
                            col_widths = list(col_widths[:n_cols]) + [24] * max(0, n_cols - len(col_widths))

                            # Compute usable table width and scale column widths to fit.
                            usable_w = self.w - self.l_margin - self.r_margin
                            total_w = float(sum(col_widths)) if col_widths else 0.0
                            if total_w <= 0:
                                col_widths = [usable_w / n_cols] * n_cols
                            else:
                                scale = usable_w / total_w
                                col_widths = [max(8.0, w * scale) for w in col_widths]

                            # Fix possible rounding drift by adjusting last column.
                            drift = usable_w - sum(col_widths)
                            col_widths[-1] = max(8.0, col_widths[-1] + drift)

                            def safe_truncate(text, width):
                                t = '' if text is None else str(text).replace('\n', ' ')
                                # Conservative estimate for Helvetica 7pt width.
                                max_chars = max(1, int((width - 2) / 1.8))
                                if len(t) <= max_chars:
                                    return t
                                if max_chars <= 3:
                                    return t[:max_chars]
                                return t[:max_chars - 3] + '...'

                            def print_hdr():
                                self.set_x(self.l_margin)
                                self.set_font('Helvetica', 'B', 7)
                                self.set_fill_color(*h_color)
                                self.set_text_color(255, 255, 255)
                                for i, h in enumerate(headers):
                                    self.cell(col_widths[i], 8, safe_truncate(h, col_widths[i]), border=0, fill=True, align='C')
                                self.ln()
                                self.set_text_color(30, 41, 59)
                                self.set_font('Helvetica', '', 7)

                            self.ensure_page_fit(20)
                            print_hdr()
                            for ri, row in enumerate(data):
                                if self.get_y() + 10 > self.page_break_trigger:
                                    self.add_page()
                                    print_hdr()

                                row_highlight = highlight_val and any(str(highlight_val).lower() == str(cell).lower() for cell in row)
                                if row_highlight:
                                    self.set_fill_color(254, 252, 232)
                                elif ri % 2 == 0:
                                    self.set_fill_color(248, 250, 252)
                                else:
                                    self.set_fill_color(255, 255, 255)

                                self.set_x(self.l_margin)
                                for i in range(n_cols):
                                    v = row[i] if i < len(row) else ''
                                    if row_highlight:
                                        self.set_font('Helvetica', 'B', 7)
                                    else:
                                        self.set_font('Helvetica', '', 7)
                                    self.cell(col_widths[i], 7, safe_truncate(v, col_widths[i]), border=0, fill=True, align='C')
                                self.ln()
                            self.ln(2)

                        def draw_kpi_cards(self, kpis):
                            """Draw KPI cards in 2-column grid. kpis = [(label, value, color_hex), ...]"""
                            if len(kpis) < 2:
                                return
                            self.ensure_page_fit(50)
                            kpi_x_positions = [12, 105]
                            kpi_y_start = self.get_y()
                            
                            for idx, (label, value, color_hex) in enumerate(kpis[:4]):  # Max 4 cards
                                row = idx // 2
                                col = idx % 2
                                x = kpi_x_positions[col]
                                y = kpi_y_start + (row * 22)
                                
                                try:
                                    r, g, b = tuple(int(color_hex[i:i+2], 16) for i in (1, 3, 5))
                                except:
                                    r, g, b = 59, 130, 246
                                
                                self.set_fill_color(r, g, b)
                                self.rect(x, y, 85, 18, 'F')
                                
                                self.set_text_color(255, 255, 255)
                                self.set_font('Helvetica', 'B', 8)
                                self.set_xy(x + 2, y + 2)
                                self.cell(81, 4, label[:25], new_x='LMARGIN')
                                
                                self.set_font('Helvetica', 'B', 12)
                                self.set_xy(x + 2, y + 8)
                                self.cell(81, 7, str(value)[:20], new_x='LMARGIN')
                            
                            self.set_y(kpi_y_start + (((len(kpis)-1)//2 + 1) * 22))
                            self.ln(2)
                            self.set_text_color(0, 0, 0)

                    pdf = AnalyticsPDF()
                    pdf.title = st.session_state['_rpt_ttl']
                    pdf.add_page()
                    pdf.set_auto_page_break(auto=True, margin=15)
                    
                    # ═══════════════════════════════════════════════════
                    # SECTION 1: ANALYZED CHANNEL HERO + KPIs
                    # ═══════════════════════════════════════════════════
                    analyzed_channel = st.session_state.get('active_channel_id')
                    analyzed_ch_name = 'General Analysis'
                    
                    if analyzed_channel and ch_df_pdf is not None and not ch_df_pdf.empty:
                        analyzed_ch_name = ch_df_pdf.iloc[0]['channel_name']
                    elif bench_channel:
                        analyzed_ch_name = bench_channel
                    
                    # Channel Hero Header - Fixed to prevent overlap
                    pdf.set_fill_color(31, 41, 55)
                    pdf.rect(10, 56, 190, 20, 'F')
                    pdf.set_font('Helvetica', 'B', 14)
                    pdf.set_text_color(255, 255, 255)
                    pdf.set_xy(15, 61)
                    ch_name_display = (analyzed_ch_name[:35].upper()) if len(analyzed_ch_name) > 35 else analyzed_ch_name.upper()
                    pdf.cell(170, 10, ch_name_display, new_x='LMARGIN', new_y='NEXT')
                    pdf.ln(6)
                    
                    # Channel KPIs
                    if analyzed_channel and ch_df_pdf is not None and not ch_df_pdf.empty:
                        print_kpi_summary = lambda ch_data: [
                            [f"Total Videos", f"{len(ch_data):,}"],
                            [f"Avg Views/Video", f"{ch_data['view_count'].mean():,.0f}"],
                            [f"Avg Likes/Video", f"{ch_data['like_count'].mean():,.0f}"],
                            [f"Avg Engagement %", f"{((ch_data['like_count'] + ch_data['comment_count']) / ch_data['view_count'].replace(0, np.nan) * 100).fillna(0).mean():.2f}%"]
                        ]
                        kpi_summary = print_kpi_summary(ch_df_pdf)
                        pdf.section_header(f'Channel KPIs: {analyzed_ch_name}', (59, 130, 246))
                        pdf.smart_table(['KPI', 'Value'], kpi_summary, [100, 90], (59, 130, 246))
                        pdf.ln(5)
                    elif bench_channel:
                        bench_row = all_ch[all_ch['channel_name'] == bench_channel]
                        if not bench_row.empty:
                            br = bench_row.iloc[0]
                            kpi_tbl = [
                                ['Subscribers', f"{int(br['subscribers']):,}"],
                                ['Total Views', f"{int(br['views']):,}"],
                                ['Total Videos', f"{int(br['total_videos']):,}"],
                                ['Avg Engagement %', f"{float(br['avg_engagement']):.2f}%"]
                            ]
                            pdf.section_header(f'Channel KPIs: {bench_channel}', (59, 130, 246))
                            pdf.smart_table(['KPI', 'Value'], kpi_tbl, [100, 90], (59, 130, 246))
                            pdf.ln(5)
                    
                    # Summary Header
                    pdf.set_font('Helvetica', 'B', 11); pdf.set_text_color(30, 41, 59)
                    pdf.cell(0, 6, f'Report: {st.session_state.get("_rpt_ttl", "YouTube Analytics Report")}', new_x='LMARGIN', new_y='NEXT')
                    pdf.set_font('Helvetica', '', 8); pdf.set_text_color(71, 85, 105)
                    pdf.cell(0, 5, f'Generated: {datetime.now().strftime("%B %d, %Y")} | {len(all_ch)} Channels Analyzed | Granularity: {report_period}', new_x='LMARGIN', new_y='NEXT')
                    pdf.ln(4)

                    r_secs = st.session_state['_rpt_secs']
                    
                    # ═══════════════════════════════════════════════════
                    # SECTION 2: PAGE GRAPHS (Dashboard → Profile → Battle → Visuals)
                    # ═══════════════════════════════════════════════════
                    
                    if 'Dashboard Insights' in r_secs:
                        pdf.section_header('Dashboard: Content Performance & Upload Rhythm', (37, 99, 235))
                        if ch_df_pdf.empty:
                            pdf.set_font('Helvetica', 'I', 8); pdf.set_text_color(100, 116, 139)
                            pdf.cell(0, 5, "[No data available. Analyze a channel first.]")
                            pdf.ln(5)
                        else:
                            try:
                                # Dashboard Chart 1: Top 10 Videos by Views
                                dash_plot = ch_df_pdf.sort_values('view_count', ascending=False).head(10)
                                plt.figure(figsize=(10, 4))
                                plt.barh(dash_plot['title'].str.slice(0, 40)[::-1], dash_plot['view_count'][::-1], color='#2563EB', alpha=0.85)
                                plt.title('Top 10 Videos by Views', fontsize=11, fontweight='bold')
                                plt.xlabel('Views', fontsize=9)
                                plt.grid(axis='x', linestyle=':', alpha=0.3)
                                plt.tight_layout()
                                d_img_1 = 'temp_dashboard_top_videos.png'
                                plt.savefig(d_img_1, dpi=120)
                                plt.close()
                                if os.path.exists(d_img_1):
                                    pdf.ensure_page_fit(65)
                                    pdf.set_font('Helvetica', '', 7); pdf.set_text_color(100, 116, 139)
                                    pdf.cell(0, 3, 'Top performing videos ranked by total views')
                                    pdf.ln(3)
                                    pdf.image(d_img_1, x=10, w=190)
                                    os.remove(d_img_1)
                                pdf.ln(2)
                                
                                # Dashboard Chart 2: Upload Rhythm - Uploads by Month & Day
                                monthly_uploads = ch_df_pdf.groupby(ch_df_pdf['published_at_dt'].dt.strftime('%b %Y')).size().reset_index(name='count')
                                monthly_uploads.columns = ['month', 'count']  # Fix column naming
                                day_uploads = ch_df_pdf.groupby(ch_df_pdf['published_at_dt'].dt.day_name()).size()
                                day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                                day_uploads = day_uploads.reindex(day_order, fill_value=0)
                                
                                if len(monthly_uploads) > 1:
                                    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.8))
                                    
                                    colors_pie = plt.cm.Set3(range(min(len(monthly_uploads), 12)))
                                    wedges, texts, autotexts = ax1.pie(monthly_uploads['count'], labels=monthly_uploads['month'], autopct='%1.1f%%',
                                           startangle=90, colors=colors_pie, textprops={'fontsize': 7})
                                    ax1.set_title('Uploads by Month', fontsize=10, fontweight='bold')
                                    
                                    ax2.bar([d[:3] for d in day_order], day_uploads.values, color='#F59E0B', alpha=0.85)
                                    ax2.set_title('Uploads by Day of Week', fontsize=10, fontweight='bold')
                                    ax2.set_ylabel('Upload Count', fontsize=8)
                                    ax2.grid(axis='y', alpha=0.3)
                                    ax2.tick_params(axis='x', labelsize=8)
                                    
                                    plt.tight_layout()
                                    d_img_2 = 'temp_dashboard_upload_rhythm.png'
                                    plt.savefig(d_img_2, dpi=120)
                                    plt.close()
                                    if os.path.exists(d_img_2):
                                        pdf.ensure_page_fit(75)
                                        pdf.set_font('Helvetica', '', 7); pdf.set_text_color(100, 116, 139)
                                        pdf.cell(0, 3, 'Upload distribution across months and days to identify content rhythm patterns')
                                        pdf.ln(3)
                                        pdf.image(d_img_2, x=10, w=190)
                                        os.remove(d_img_2)
                                    pdf.ln(2)
                            except Exception as e:
                                pdf.set_font('Helvetica', 'I', 7); pdf.set_text_color(220, 38, 38)
                                pdf.cell(0, 4, f"[Dashboard chart error: {str(e)[:40]}]")
                                pdf.ln(4)

                    if 'Profile Insights' in r_secs:
                        pdf.section_header('Profile: Channel Analytics & Performance', (16, 185, 129))
                        if ch_df_pdf.empty:
                            pdf.set_font('Helvetica', 'I', 8); pdf.set_text_color(100, 116, 139)
                            pdf.cell(0, 5, "[No data available. Analyze a channel first.]")
                            pdf.ln(5)
                        else:
                            try:
                                ch_df_plot = ch_df_pdf.copy()
                                
                                # Profile KPI cards aligned to Profile page gauge formulas
                                eng_rate = ch_df_plot['engagement_rate'].mean() if 'engagement_rate' in ch_df_plot.columns else ((ch_df_plot['like_count'] + ch_df_plot['comment_count']) / ch_df_plot['view_count'].replace(0, np.nan) * 100).mean()
                                eng_rate = 0 if pd.isna(eng_rate) else eng_rate
                                content_strength = ch_df_plot['content_performance_score'].mean() if 'content_performance_score' in ch_df_plot.columns else 0
                                content_strength = 0 if pd.isna(content_strength) else content_strength
                                audience_loyalty = ch_df_plot['sub_to_view_ratio'].mean() if 'sub_to_view_ratio' in ch_df_plot.columns else 0
                                audience_loyalty = 0 if pd.isna(audience_loyalty) else audience_loyalty
                                reach_momentum_k = ch_df_plot['view_count'].mean() / 1000
                                reach_momentum_k = 0 if pd.isna(reach_momentum_k) else reach_momentum_k
                                
                                kpi_cards = [
                                    ('Engagement Quality', f'{eng_rate:.1f}%', '#3B82F6'),
                                    ('Content Strength', f'{content_strength:.1f}/100', '#F59E0B'),
                                    ('Audience Loyalty', f'{audience_loyalty:.3f}', '#10B981'),
                                    ('Reach Momentum', f'{reach_momentum_k:.0f}k', '#EF4444')
                                ]
                                pdf.draw_kpi_cards(kpi_cards)
                                pdf.ln(2)
                                ch_df_plot['month'] = ch_df_plot['published_at_dt'].dt.to_period('M').astype(str)

                                # Profile original chart family 1: monthly uploads + monthly views
                                monthly_data = ch_df_plot.groupby('month').agg(
                                    uploads=('video_id', 'count'),
                                    views=('view_count', 'sum')
                                ).reset_index()

                                fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
                                ax1.plot(monthly_data['month'], monthly_data['uploads'], marker='o', color='#10B981', linewidth=2.2)
                                ax1.set_title('Monthly Uploads', fontsize=11, fontweight='bold')
                                ax1.set_ylabel('Video Count', fontsize=9)
                                ax1.grid(alpha=0.3)
                                ax1.tick_params(axis='x', rotation=45, labelsize=8)

                                ax2.bar(monthly_data['month'], monthly_data['views'], color='#059669', alpha=0.8)
                                ax2.set_title('Monthly Total Views', fontsize=11, fontweight='bold')
                                ax2.set_ylabel('Views (×10⁶)', fontsize=9)  # Scale label for millions
                                # Convert y-axis to millions
                                ax2_ticks = ax2.get_yticks()
                                ax2.set_yticklabels([f'{int(y/1e6)}' if y >= 1e6 else f'{y:.0f}' for y in ax2_ticks], fontsize=8)
                                ax2.grid(axis='y', alpha=0.3)
                                ax2.tick_params(axis='x', rotation=45, labelsize=8)

                                plt.tight_layout()
                                p_img_1 = 'temp_profile_graph_1.png'
                                plt.savefig(p_img_1, dpi=120)
                                plt.close()
                                if os.path.exists(p_img_1):
                                    pdf.ensure_page_fit(65)
                                    pdf.set_font('Helvetica', '', 7); pdf.set_text_color(100, 116, 139)
                                    pdf.cell(0, 3, 'Shows video upload frequency and total views generated each month')
                                    pdf.ln(3)
                                    pdf.image(p_img_1, x=10, w=190)
                                    os.remove(p_img_1)
                                pdf.ln(2)

                                # Profile original chart family 2: optimal timing (hour vs avg views) with peak highlight
                                timing_df = ch_df_plot.copy()
                                timing_df['publish_hour'] = timing_df['published_at_dt'].dt.hour
                                timing_agg = timing_df.groupby('publish_hour')['view_count'].mean().reindex(range(24), fill_value=0).reset_index()

                                plt.figure(figsize=(10, 3.6))
                                # Find peak hour
                                peak_idx = timing_agg['view_count'].idxmax()
                                peak_hour = timing_agg.loc[peak_idx, 'publish_hour']
                                peak_views = timing_agg.loc[peak_idx, 'view_count']
                                
                                # Plot bars with peak hour highlighted in red
                                colors = ['#EF4444' if h == peak_hour else '#2563EB' for h in timing_agg['publish_hour']]
                                plt.bar(timing_agg['publish_hour'], timing_agg['view_count'], color=colors, alpha=0.75, width=0.8)
                                
                                # Add peak hour annotation
                                plt.scatter([peak_hour], [peak_views], color='#EF4444', s=250, zorder=5, marker='*', edgecolors='darkred', linewidth=1.5)
                                plt.annotate(f'Peak: {int(peak_hour)}:00 hrs\n({peak_views:,.0f} views)', 
                                           xy=(peak_hour, peak_views), xytext=(peak_hour+1.5, peak_views*0.85),
                                           fontsize=8, fontweight='bold', color='#EF4444',
                                           bbox=dict(boxstyle='round,pad=0.5', facecolor='white', alpha=0.8, edgecolor='#EF4444'),
                                           arrowprops=dict(arrowstyle='->', color='#EF4444', lw=1.5))
                                
                                plt.title('Optimal Timing Analysis - Peak Publication Hour', fontsize=11, fontweight='bold')
                                plt.xlabel('Hour of Day (24-hour format)', fontsize=9)
                                plt.ylabel('Avg Views (×10³)', fontsize=9)
                                plt.xticks(range(0, 24, 2), fontsize=8)
                                # Format y-axis to show thousands
                                ax_timing = plt.gca()
                                ax_timing_ticks = ax_timing.get_yticks()
                                ax_timing.set_yticklabels([f'{int(y/1e3)}' if y >= 1e3 else f'{y:.0f}' for y in ax_timing_ticks], fontsize=8)
                                plt.grid(alpha=0.25, axis='y')
                                plt.xlim(-0.5, 23.5)
                                plt.tight_layout()
                                p_img_2 = 'temp_profile_graph_2.png'
                                plt.savefig(p_img_2, dpi=120)
                                plt.close()
                                if os.path.exists(p_img_2):
                                    pdf.ensure_page_fit(65)
                                    pdf.set_font('Helvetica', '', 7); pdf.set_text_color(100, 116, 139)
                                    pdf.cell(0, 3, 'Peak hour highlighted in red - shows when your audience is most engaged. Best time to publish for maximum views.')
                                    pdf.ln(3)
                                    pdf.image(p_img_2, x=10, w=190)
                                    os.remove(p_img_2)
                                pdf.ln(2)

                                # Profile original chart family 3: performance distribution pie
                                rank_df = benchmark_videos(ch_df_plot.copy())
                                rank_counts = rank_df['performance_rank'].value_counts()
                                labels = ['High Performer', 'Average', 'Underperforming']
                                vals = [int(rank_counts.get(lbl, 0)) for lbl in labels]
                                if sum(vals) > 0:
                                    plt.figure(figsize=(6.8, 4.2))
                                    plt.pie(vals, labels=labels, autopct='%1.1f%%', startangle=120,
                                            colors=['#10B981', '#F59E0B', '#EF4444'], wedgeprops={'width': 0.45})
                                    plt.title('Performance Distribution', fontsize=11, fontweight='bold')
                                    plt.tight_layout()
                                    p_img_3 = 'temp_profile_graph_3.png'
                                    plt.savefig(p_img_3, dpi=120)
                                    plt.close()
                                    if os.path.exists(p_img_3):
                                        pdf.ensure_page_fit(70)
                                        pdf.set_font('Helvetica', '', 7); pdf.set_text_color(100, 116, 139)
                                        pdf.cell(0, 3, 'Categorizes videos into performance tiers: High Performers, Average, and Underperforming based on benchmark metrics')
                                        pdf.ln(3)
                                        pdf.image(p_img_3, x=40, w=130)
                                        os.remove(p_img_3)
                                    pdf.ln(3)
                            except Exception as e:
                                pdf.set_font('Helvetica', 'I', 7); pdf.set_text_color(220, 38, 38)
                                pdf.cell(0, 4, f"[Profile chart error: {str(e)[:40]}]")
                                pdf.ln(4)

                    if 'Battle Insights' in r_secs:
                        pdf.ln(2)
                        
                        # Get rivals from persistent session state
                        rivals_now = st.session_state.get('b_selected', [])
                        
                        # Ensure we have the rival data from all_ch
                        rival_df = all_ch[all_ch['channel_name'].isin(rivals_now)].copy() if len(rivals_now) >= 2 else pd.DataFrame()
                        
                        if rival_df.empty or len(rivals_now) < 2:
                            pdf.set_font('Helvetica', 'I', 8); pdf.set_text_color(100, 116, 139)
                            pdf.cell(0, 5, "[No Battle comparison data found. Please go to Battle page, select at least 2 rivals, then return to Compare page.]")
                            pdf.ln(5)
                        else:
                            try:
                                rival_df_top = rival_df.sort_values('subscribers', ascending=False).head(10)

                                # ═════════════════════════════════════════════════════════════
                                # BATTLE CHART 1: HEAD-TO-HEAD SUBSCRIBERS & VIEWS
                                # ═════════════════════════════════════════════════════════════
                                try:
                                    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.2))
                                    colors_rivals = ['#EF4444' if n == bench_channel else '#2563EB' for n in rival_df_top['channel_name']]
                                    ax1.bar(rival_df_top['channel_name'].str.slice(0, 14), rival_df_top['subscribers'], color=colors_rivals, alpha=0.85)
                                    ax1.set_title('Audience Battle - Subscribers', fontsize=10, fontweight='bold')
                                    ax1.set_ylabel('Subscribers (×10⁶)', fontsize=8)
                                    ax1.set_yscale('log')
                                    ax1_ticks = ax1.get_yticks()
                                    ax1.set_yticklabels([f'{int(y/1e6)}M' if y >= 1e6 else f'{int(y/1e3)}K' if y >= 1e3 else f'{int(y)}' for y in ax1_ticks], fontsize=7)
                                    ax1.grid(axis='y', alpha=0.3)
                                    ax1.tick_params(axis='x', rotation=45, labelsize=7)

                                    ax2.bar(rival_df_top['channel_name'].str.slice(0, 14), rival_df_top['views'], color=['#DC2626' for _ in range(len(rival_df_top))], alpha=0.85)
                                    ax2.set_title('Reach Battle - Total Views', fontsize=10, fontweight='bold')
                                    ax2.set_ylabel('Views (×10⁶)', fontsize=8)
                                    ax2.set_yscale('log')
                                    ax2_ticks = ax2.get_yticks()
                                    ax2.set_yticklabels([f'{int(y/1e6)}M' if y >= 1e6 else f'{int(y/1e3)}K' if y >= 1e3 else f'{int(y)}' for y in ax2_ticks], fontsize=7)
                                    ax2.grid(axis='y', alpha=0.3)
                                    ax2.tick_params(axis='x', rotation=45, labelsize=7)

                                    plt.tight_layout()
                                    b_img_1 = 'temp_battle_graph_1.png'
                                    plt.savefig(b_img_1, dpi=120)
                                    plt.close()
                                    if os.path.exists(b_img_1):
                                        pdf.ensure_page_fit(65)
                                        pdf.set_font('Helvetica', '', 7); pdf.set_text_color(100, 116, 139)
                                        pdf.cell(0, 3, 'Direct head-to-head comparison of subscriber counts (left, log scale) and total views (right, log scale). Red = analyzed channel.')
                                        pdf.ln(3)
                                        pdf.image(b_img_1, x=10, w=190)
                                        os.remove(b_img_1)
                                    pdf.ln(2)
                                except Exception as e:
                                    pdf.set_font('Helvetica', 'I', 7); pdf.set_text_color(220, 38, 38)
                                    pdf.cell(0, 3, f"[Battle Chart 1 error: {str(e)[:30]}]")
                                    pdf.ln(3)

                                # ═════════════════════════════════════════════════════════════
                                # BATTLE CHART 2: ENGAGEMENT QUALITY MATRIX (Direct from rival_df)
                                # ═════════════════════════════════════════════════════════════
                                try:
                                    # Use avg_engagement directly from rival_df
                                    if 'avg_engagement' in rival_df_top.columns:
                                        chart2_df = rival_df_top.copy()
                                        chart2_df['quality_score'] = chart2_df['avg_engagement']
                                        
                                        plt.figure(figsize=(10, 4.2))
                                        sizes = np.sqrt(chart2_df['views'] / 1e6) * 50  # Size based on views
                                        scatter = plt.scatter(chart2_df['views'] / 1e6, chart2_df['quality_score'], s=sizes,
                                                    c=np.arange(len(chart2_df)), cmap='viridis', alpha=0.75, edgecolors='white', linewidth=0.8)
                                        for _, r in chart2_df.iterrows():
                                            plt.annotate(str(r['channel_name'])[:12], (r['views']/1e6, r['quality_score']), fontsize=7, alpha=0.8)
                                        plt.title('Engagement Quality Matrix', fontsize=10, fontweight='bold')
                                        plt.xlabel('Total Views (Millions)', fontsize=8)
                                        plt.ylabel('Avg Engagement %', fontsize=8)
                                        plt.grid(alpha=0.25)
                                        plt.tight_layout()
                                        b_img_2 = 'temp_battle_graph_2.png'
                                        plt.savefig(b_img_2, dpi=120)
                                        plt.close()
                                        if os.path.exists(b_img_2):
                                            pdf.ensure_page_fit(65)
                                            pdf.set_font('Helvetica', '', 7); pdf.set_text_color(100, 116, 139)
                                            pdf.cell(0, 3, 'Bubble size = views (millions); X-axis = total views; Y-axis = engagement quality (%). Shows view-quality tradeoffs between rivals.')
                                            pdf.ln(3)
                                            pdf.image(b_img_2, x=10, w=190)
                                            os.remove(b_img_2)
                                        pdf.ln(2)
                                except Exception as e:
                                    pdf.set_font('Helvetica', 'I', 7); pdf.set_text_color(220, 38, 38)
                                    pdf.cell(0, 3, f"[Battle Chart 2 error: {str(e)[:30]}]")
                                    pdf.ln(3)

                                # ═════════════════════════════════════════════════════════════
                                # BATTLE CHART 3: MULTICHANNEL CAPABILITIES RADAR
                                # ═════════════════════════════════════════════════════════════
                                try:
                                    cap_df = rival_df_top.copy()
                                    # Normalize all metrics to 0-1 scale
                                    cap_df['views_norm'] = cap_df['views'] / max(float(cap_df['views'].max()), 1.0)
                                    cap_df['subs_norm'] = cap_df['subscribers'] / max(float(cap_df['subscribers'].max()), 1.0)
                                    cap_df['videos_norm'] = cap_df['total_videos'] / max(float(cap_df['total_videos'].max()), 1.0)
                                    cap_df['eng_norm'] = cap_df['avg_engagement'] / max(float(cap_df['avg_engagement'].max()), 1.0)

                                    x_idx = np.arange(len(cap_df))
                                    w = 0.18
                                    plt.figure(figsize=(10, 4))
                                    plt.bar(x_idx - 1.5*w, cap_df['views_norm'], width=w, label='Views Reach', color='#3B82F6', alpha=0.85)
                                    plt.bar(x_idx - 0.5*w, cap_df['subs_norm'], width=w, label='Subscribers', color='#EF4444', alpha=0.85)
                                    plt.bar(x_idx + 0.5*w, cap_df['videos_norm'], width=w, label='Video Volume', color='#10B981', alpha=0.85)
                                    plt.bar(x_idx + 1.5*w, cap_df['eng_norm'], width=w, label='Engagement %', color='#F59E0B', alpha=0.85)
                                    plt.xticks(x_idx, cap_df['channel_name'].str.slice(0, 14), rotation=30, ha='right', fontsize=7)
                                    plt.ylim(0, 1.05)
                                    plt.ylabel('Normalized Score (0-1)', fontsize=8)
                                    plt.title('Multichannel Capabilities Comparison', fontsize=10, fontweight='bold')
                                    plt.grid(axis='y', alpha=0.25)
                                    plt.legend(fontsize=7, loc='upper right')
                                    plt.tight_layout()
                                    b_img_3 = 'temp_battle_graph_3.png'
                                    plt.savefig(b_img_3, dpi=120)
                                    plt.close()
                                    if os.path.exists(b_img_3):
                                        pdf.ensure_page_fit(70)
                                        pdf.set_font('Helvetica', '', 7); pdf.set_text_color(100, 116, 139)
                                        pdf.cell(0, 3, 'Multi-dimensional comparison (0-1 scale): Views Reach, Subscribers, Video Volume, and Engagement. All normalized for fair comparison across dimensions.')
                                        pdf.ln(3)
                                        pdf.image(b_img_3, x=10, w=190)
                                        os.remove(b_img_3)
                                    pdf.ln(2)
                                except Exception as e:
                                    pdf.set_font('Helvetica', 'I', 7); pdf.set_text_color(220, 38, 38)
                                    pdf.cell(0, 3, f"[Battle Chart 3 error: {str(e)[:30]}]")
                                    pdf.ln(3)
                                    
                            except Exception as e:
                                pdf.set_font('Helvetica', 'I', 7); pdf.set_text_color(220, 38, 38)
                                pdf.cell(0, 4, f"[Battle section error: {str(e)[:40]}]")
                                pdf.ln(4)

                    if 'Visual Insights' in r_secs:
                        pdf.section_header('Visuals: Performance Distribution', (139, 92, 246))
                        if ch_df_pdf.empty:
                            pdf.set_font('Helvetica', 'I', 8); pdf.set_text_color(100, 116, 139)
                            pdf.cell(0, 5, "[No data available. Analyze a channel first.]")
                            pdf.ln(5)
                        else:
                            try:
                                vis_df = ch_df_pdf.copy()
                                metric_opt_pdf = {
                                    'Views': 'view_count',
                                    'Likes': 'like_count',
                                    'Comments': 'comment_count',
                                    'Quality %': 'engagement_rate'
                                }
                                sel_metric_lbl_pdf = st.session_state.get('v_metric', 'Views')
                                sel_metric_pdf = metric_opt_pdf.get(sel_metric_lbl_pdf, 'view_count')
                                sel_year_pdf = st.session_state.get('v_years', sorted(vis_df['year'].unique().tolist()))
                                sel_types_pdf = st.session_state.get('v_types', ['Long-form', 'Shorts'])
                                sel_days_pdf = st.session_state.get('v_days', ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'])
                                sel_period_pdf = st.session_state.get('v_period', 'All Time')

                                f_vis = vis_df[
                                    (vis_df['year'].isin(sel_year_pdf)) &
                                    (vis_df['is_short'].isin(sel_types_pdf)) &
                                    (vis_df['day_name'].isin(sel_days_pdf))
                                ].copy()

                                if not f_vis.empty:
                                    max_date = f_vis['published_at_dt'].max()
                                    if sel_period_pdf == 'Last 30 Days':
                                        f_vis = f_vis[f_vis['published_at_dt'] >= (max_date - pd.Timedelta(days=30))]
                                    elif sel_period_pdf == 'Last 6 Months':
                                        f_vis = f_vis[f_vis['published_at_dt'] >= (max_date - pd.Timedelta(days=180))]
                                    elif sel_period_pdf == 'Last 1 Year':
                                        f_vis = f_vis[f_vis['published_at_dt'] >= (max_date - pd.Timedelta(days=365))]

                                if f_vis.empty:
                                    f_vis = vis_df.copy()

                                # Visual original chart family 1: monthly trend panels (views/likes/comments)
                                trend = vis_df.copy()
                                trend['period_start'] = trend['published_at_dt'].dt.to_period('M').dt.to_timestamp()
                                monthly = trend.groupby('period_start').agg(
                                    views=('view_count', 'sum'),
                                    likes=('like_count', 'sum'),
                                    comments=('comment_count', 'sum')
                                ).reset_index()

                                if len(monthly) > 1:
                                    fig, axes = plt.subplots(3, 1, figsize=(10, 5.5), sharex=True)
                                    series_spec = [
                                        ('views', '#3B82F6', 'Monthly Views'),
                                        ('likes', '#10B981', 'Monthly Likes'),
                                        ('comments', '#F97316', 'Monthly Comments'),
                                    ]
                                    for ax, (col, color, title) in zip(axes, series_spec):
                                        ax.plot(monthly['period_start'], monthly[col], color=color, linewidth=2.2, marker='o', markersize=3)
                                        ax.fill_between(monthly['period_start'], monthly[col], color=color, alpha=0.12)
                                        ax.set_title(title, fontsize=10, fontweight='bold')
                                        ax.grid(alpha=0.25)
                                    axes[-1].tick_params(axis='x', rotation=35, labelsize=8)
                                    plt.tight_layout()
                                    v_img_1 = 'temp_visual_graph_1.png'
                                    plt.savefig(v_img_1, dpi=120)
                                    plt.close()
                                    if os.path.exists(v_img_1):
                                        pdf.ensure_page_fit(90)
                                        pdf.set_font('Helvetica', '', 7); pdf.set_text_color(100, 116, 139)
                                        pdf.cell(0, 3, 'Tracks cumulative engagement metrics across months to reveal performance trends')
                                        pdf.ln(3)
                                        pdf.image(v_img_1, x=10, w=190)
                                        os.remove(v_img_1)
                                    pdf.ln(2)

                                # Visual original chart family 2: topic impact + day impact
                                stops = {'the', 'to', 'in', 'for', 'of', 'and', 'with', 'on', 'how', 'is', 'it', 'at', 'this', 'that', 'you', 'my', 'from'}
                                words = " ".join(f_vis['title'].astype(str).str.lower()).split()
                                kws = [w for w in words if len(w) > 3 and w not in stops]
                                top_kw = pd.Series(kws).value_counts().head(6).index.tolist() if kws else []

                                kw_rows = []
                                for kw in top_kw:
                                    avg_m = f_vis[f_vis['title'].str.contains(kw, case=False, regex=False)][sel_metric_pdf].mean()
                                    kw_rows.append({'kw': kw.capitalize(), 'val': float(avg_m) if pd.notna(avg_m) else 0.0})
                                kw_df = pd.DataFrame(kw_rows).sort_values('val', ascending=True) if kw_rows else pd.DataFrame(columns=['kw', 'val'])

                                day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                                day_df = f_vis.groupby('day_name')[sel_metric_pdf].mean().reindex(day_order).fillna(0).reset_index()

                                fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.8))
                                if not kw_df.empty:
                                    ax1.barh(kw_df['kw'], kw_df['val'], color='#10B981')
                                ax1.set_title(f'Topic Impact ({sel_metric_lbl_pdf})', fontsize=10, fontweight='bold')
                                ax1.grid(axis='x', alpha=0.25)

                                ax2.bar(day_df['day_name'].str[:3], day_df[sel_metric_pdf], color='#F59E0B')
                                ax2.set_title(f'Day-of-Week Impact ({sel_metric_lbl_pdf})', fontsize=10, fontweight='bold')
                                ax2.grid(axis='y', alpha=0.25)
                                plt.tight_layout()
                                v_img_2 = 'temp_visual_graph_2.png'
                                plt.savefig(v_img_2, dpi=120)
                                plt.close()
                                if os.path.exists(v_img_2):
                                    pdf.ensure_page_fit(65)
                                    pdf.set_font('Helvetica', '', 7); pdf.set_text_color(100, 116, 139)
                                    pdf.cell(0, 3, 'Identifies top keywords and optimal posting days that drive higher engagement')
                                    pdf.ln(3)
                                    pdf.image(v_img_2, x=10, w=190)
                                    os.remove(v_img_2)
                                pdf.ln(2)

                                # Visual original chart family 3: performance scatter + stability distribution
                                fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.8))
                                ax1.scatter(f_vis['view_count'], f_vis['like_count'], alpha=0.5, color='#8B5CF6', s=45,
                                            edgecolors='white', linewidth=0.4)
                                ax1.set_title('Views vs Likes', fontsize=10, fontweight='bold')
                                ax1.set_xlabel('Views', fontsize=8)
                                ax1.set_ylabel('Likes', fontsize=8)
                                ax1.grid(alpha=0.25)

                                ax2.hist(f_vis['engagement_rate'].fillna(0), bins=16, color='#7C3AED', alpha=0.8, edgecolor='white')
                                ax2.set_title('Engagement Stability', fontsize=10, fontweight='bold')
                                ax2.set_xlabel('Engagement %', fontsize=8)
                                ax2.set_ylabel('Video Count', fontsize=8)
                                ax2.grid(axis='y', alpha=0.25)
                                plt.tight_layout()
                                v_img_3 = 'temp_visual_graph_3.png'
                                plt.savefig(v_img_3, dpi=120)
                                plt.close()
                                if os.path.exists(v_img_3):
                                    pdf.ensure_page_fit(65)
                                    pdf.set_font('Helvetica', '', 7); pdf.set_text_color(100, 116, 139)
                                    pdf.cell(0, 3, 'Compares view vs like performance and shows engagement rate distribution across videos')
                                    pdf.ln(3)
                                    pdf.image(v_img_3, x=10, w=190)
                                    os.remove(v_img_3)
                                pdf.ln(3)
                            except Exception as e:
                                pdf.set_font('Helvetica', 'I', 7); pdf.set_text_color(220, 38, 38)
                                pdf.cell(0, 4, f"[Visuals chart error: {str(e)[:40]}]")
                                pdf.ln(4)
                    
                    # ═══════════════════════════════════════════════════
                    # SECTION 3: STRATEGIC TABLES
                    # ═══════════════════════════════════════════════════

                    if 'Leaderboard Rankings' in r_secs:
                        pdf.section_header('Global Channel Rankings (Top 20)', (124, 58, 237))
                        lb_pdf = all_ch.sort_values('subscribers', ascending=False).head(20).reset_index(drop=True)
                        lb_rows = []
                        for i, row in lb_pdf.iterrows():
                            rank = i + 1
                            medal = '🥇' if rank == 1 else ('🥈' if rank == 2 else ('🥉' if rank == 3 else f'#{rank}'))
                            lb_rows.append([
                                medal,
                                str(row['channel_name']),
                                f"{int(row['subscribers']):,}",
                                f"{int(row['views']):,}",
                                f"{float(row['avg_engagement']):.2f}%",
                                f"{int(row['total_videos']):,}"
                            ])
                        pdf.smart_table(
                            ['Rank', 'Channel', 'Subscribers', 'Views', 'Engagement', 'Videos'],
                            lb_rows,
                            [18, 56, 30, 34, 24, 28],
                            (124, 58, 237),
                            highlight_val=analyzed_ch_name
                        )
                        pdf.ln(2)


                    
                    if 'Growth Velocity' in r_secs:
                        pdf.section_header('Growth Velocity & Efficiency', (5, 150, 105))
                        all_ch['velocity'] = all_ch['views'] / all_ch['subscribers'].replace(0, 1)
                        gv_s = all_ch.sort_values('velocity', ascending=False).head(15).reset_index(drop=True)
                        data = [[str(i+1), str(r['channel_name']), f"{r['velocity']:.1f}x", f"{int(r['total_videos']):,}", f"{int(r['views']/max(r['total_videos'],1)):,}"] for i,r in gv_s.iterrows()]
                        pdf.smart_table(['#','Channel','Reach Multiplier','Videos','Views/Video'], data, [10,60,40,40,40], (5, 150, 105), highlight_val=analyzed_ch_name)
                        pdf.ln(2)

                    if 'Audience Quality' in r_secs:
                        pdf.section_header('Audience Quality Scorecard', (190, 18, 60))
                        all_ch['aq_score'] = (all_ch['avg_engagement'] * 10) / np.log10(all_ch['subscribers'].replace(0, 10))
                        aq_s = all_ch.sort_values('aq_score', ascending=False).head(15).reset_index(drop=True)
                        data = [[str(i+1), str(r['channel_name']), f"{r['aq_score']:.1f}", f"{r['avg_engagement']:.2f}%", f"{int(r['subscribers']):,}"] for i,r in aq_s.iterrows()]
                        pdf.smart_table(['#','Channel','Quality Score','Engagement','Subscribers'], data, [10,60,40,40,40], (190, 18, 60), highlight_val=analyzed_ch_name)
                        pdf.ln(2)
                    
                    # ═══════════════════════════════════════════════════
                    # SECTION 4: OVERALL INSIGHTS & CARD-STYLE RECOMMENDATIONS
                    # ═══════════════════════════════════════════════════
                    pdf.section_header('Strategic Insights & Recommendations', (6, 182, 212))

                    def draw_insight_card(title, points, header_color=(30, 64, 175), body_fill=(248, 250, 252)):
                        card_height = 8 + (len(points) * 6) + 4
                        pdf.ensure_page_fit(card_height + 4)

                        pdf.set_fill_color(*header_color)
                        pdf.set_text_color(255, 255, 255)
                        pdf.set_font('Helvetica', 'B', 10)
                        pdf.cell(0, 8, f'  {title}', fill=True, new_x='LMARGIN', new_y='NEXT')

                        pdf.set_fill_color(*body_fill)
                        pdf.set_text_color(51, 65, 85)
                        pdf.set_font('Helvetica', '', 9)
                        for p in points:
                            pdf.cell(0, 6, f'  - {p}', fill=True, new_x='LMARGIN', new_y='NEXT')
                        pdf.ln(2)

                    top_v = all_ch.loc[all_ch['avg_engagement'].idxmax()] if not all_ch.empty else {'channel_name': analyzed_ch_name}

                    draw_insight_card(
                        'Primary Recommendation',
                        [
                            f"Focus on {top_v['channel_name']} patterns - highest engagement performer",
                            "Implement interaction stacking in first-hour comments",
                            "Maintain upload frequency at 2+ videos/week for retention"
                        ],
                        header_color=(30, 64, 175),
                        body_fill=(239, 246, 255)
                    )

                    draw_insight_card(
                        'Channel Health Alert',
                        [
                            "View-to-subscriber ratio shows room for optimization",
                            "Optimize end screens and playlist transitions for session duration",
                            "Compare conversion rate against leaderboard top quartile"
                        ],
                        header_color=(180, 83, 9),
                        body_fill=(255, 247, 237)
                    )

                    draw_insight_card(
                        'Key Performance Factors',
                        [
                            "Engagement quality remains the strongest reach multiplier",
                            "Top percentile channels sustain compounding growth cycles",
                            "Target engagement baseline > 3.5% for scalable momentum",
                            "Audience loyalty and content consistency correlate with long-term growth"
                        ],
                        header_color=(22, 101, 52),
                        body_fill=(240, 253, 244)
                    )
                    pdf.ln(1)


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
            <h1 style='margin:0;'>Strategic Intelligence Blueprint</h1>
            <p style='margin-top:10px;'>A modular roadmap for the professional analytics ecosystem</p>
        </div>
    """, unsafe_allow_html=True)

    # --- MODULAR ENCYCLOPEDIA (PREMIUM 3-COLUMN GRID) ---
    st.markdown("### 🧩 Core Ecosystem Modules")
    
    # Row 1
    m1c1, m1c2, m1c3 = st.columns(3)
    with m1c1:
        st.markdown(f"""
            <div class='creative-red-card'>
                <div class='icon-zoom'>🏠</div>
                <h4 style='margin:0;'>Dashboard</h4>
                <p style='font-size:0.85rem; color:#64748B; margin:8px 0;'><i>Real-time performance auditing.</i></p>
                <p style='font-size:0.9rem; color:#475569;'>Audit your channel health with <b>Reality Meters</b> showing view spikes and engagement rates.</p>
                <div class='intel-box'>
                    <b>🧠 Intelligence Insight</b>
                    Spots performance velocity compared to historical norms.
                </div>
            </div>
        """, unsafe_allow_html=True)
    with m1c2:
        st.markdown(f"""
            <div class='creative-red-card'>
                <div class='icon-zoom'>🏆</div>
                <h4 style='margin:0;'>Profile</h4>
                <p style='font-size:0.85rem; color:#64748B; margin:8px 0;'><i>Channel DNA & Identity.</i></p>
                <p style='font-size:0.9rem; color:#475569;'>Deep metadata extraction of <b>Viral Hit-Lists</b> and niche <b>Keyword Clouds</b>.</p>
                <div class='intel-box'>
                    <b>🧠 Intelligence Insight</b>
                    Ucovers which content themes drive maximum Subscriber ROI.
                </div>
            </div>
        """, unsafe_allow_html=True)
    with m1c3:
        st.markdown(f"""
            <div class='creative-red-card'>
                <div class='icon-zoom'>⚖️</div>
                <h4 style='margin:0;'>Battle Arena</h4>
                <p style='font-size:0.85rem; color:#64748B; margin:8px 0;'><i>Head-to-head Rivalry.</i></p>
                <p style='font-size:0.9rem; color:#475569;'>Benchmarking rivals to see who is winning the <b>Reach Battle</b> and <b>Share of Voice</b>.</p>
                <div class='intel-box'>
                    <b>🧠 Intelligence Insight</b>
                    Reveals engagement dominance regardless of channel size.
                </div>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom:25px;'></div>", unsafe_allow_html=True)
    
    # Row 2
    m2c1, m2c2, m2c3 = st.columns(3)
    with m2c1:
        st.markdown(f"""
            <div class='creative-red-card'>
                <div class='icon-zoom'>📈</div>
                <h4 style='margin:0;'>Visuals</h4>
                <p style='font-size:0.85rem; color:#64748B; margin:8px 0;'><i>Pattern Recognition.</i></p>
                <p style='font-size:0.9rem; color:#475569;'>Deep-dive analytics using <b>Post-Time Heatmaps</b> and <b>Topic Treemaps</b>.</p>
                <div class='intel-box'>
                    <b>🧠 Intelligence Insight</b>
                    Identifies exactly when and what to upload for maximum impact.
                </div>
            </div>
        """, unsafe_allow_html=True)
    with m2c2:
        st.markdown(f"""
            <div class='creative-red-card'>
                <div class='icon-zoom'>🔍</div>
                <h4 style='margin:0;'>Search</h4>
                <p style='font-size:0.85rem; color:#64748B; margin:8px 0;'><i>The Archive Toolkit.</i></p>
                <p style='font-size:0.9rem; color:#475569;'>Precision video discovery with <b>Range Filters</b> and <b>Bulk CSV Export</b>.</p>
                <div class='intel-box'>
                    <b>🧠 Intelligence Insight</b>
                    Provides raw data portability for deeper research.
                </div>
            </div>
        """, unsafe_allow_html=True)
    with m2c3:
        st.markdown(f"""
            <div class='creative-red-card'>
                <div class='icon-zoom'>📊</div>
                <h4 style='margin:0;'>Compare</h4>
                <p style='font-size:0.85rem; color:#64748B; margin:8px 0;'><i>Strategic Intelligence.</i></p>
                <p style='font-size:0.9rem; color:#475569;'>Automated <b>Report Wizard</b> creating PDF dossiers for stakeholders.</p>
                <div class='intel-box'>
                    <b>🧠 Intelligence Insight</b>
                    Synthesizes data into high-fidelity executive briefings.
                </div>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom:25px;'></div>", unsafe_allow_html=True)

    # Row 3 (Single card for Help as we have 7 core features left)
    st.markdown(f"""
        <div class='glassy-card-indigo'>
            <h4 style='margin:0; color:#3730A3 !important;'>🛡️ Help & FAQ (Support Repository)</h4>
            <div style='display:flex; gap:20px; align-items:center;'>
                <div style='flex:1;'>
                    <p style='font-size:0.9rem; color:#4C51BF; margin-top:10px;'>High-contrast knowledge base with <b>Collapsible Categories</b> and <b>System Health Diagnostics</b>. Designed for creators who need answers fast.</p>
                </div>
                <div class='intel-box' style='flex:1; border-color:#6366F1; background:rgba(99, 102, 241, 0.05);'>
                    <b style='color:#3730A3;'>🧠 Intelligence Insight</b>
                    <span style='color:#4C51BF;'>Ensures your project stays stable with real-time API and DB connectivity checks.</span>
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    st.divider()

    # --- THE MISSION & TARGET AUDIENCE (PREMIUM WRAP-UP) ---
    st.markdown("<div style='margin-top:40px;'></div>", unsafe_allow_html=True)
    bc1, bc2 = st.columns([1.2, 2])
    with bc1:
        st.markdown(f"""
            <div class='glassy-card-teal' style='text-align:center; padding:40px;'>
                 <div style='font-size:4rem; margin-bottom:10px;'>🎯</div>
                 <h2 style='margin:0; color:#0D9488 !important;'>The Mission</h2>
                 <p style='margin-top:15px; font-size:1rem; line-height:1.6; color:#059669;'>
                    To eliminate "Vague Guessing" from the creator economy by providing industrial-grade data tools for independent growth strategists.
                 </p>
            </div>
        """, unsafe_allow_html=True)
    with bc2:
        st.markdown(f"""
            <div class='glassy-card-purple'>
                <h3 style='margin:0; font-size:1.8rem; color:#6D28D9;'>Elite Target Audience</h3>
                <p style='font-size:1.1rem; margin-top:20px; line-height:1.5; color:#7C3AED;'>
                    The <b style='color:#6D28D9;'>Strategic Blueprint</b> is engineered for <b style='color:#6D28D9;'>High-Speed Creators</b>, <b style='color:#6D28D9;'>Growth Strategists</b>, and <b style='color:#6D28D9;'>Agency Managers</b> who demand high-fidelity, actionable intelligence to outperform the algorithm.
                </p>
                <div style='display:flex; justify-content:center; gap:12px; margin-top:30px; flex-wrap:wrap;'>
                    <span style='background:rgba(109,40,217,0.08); border:1.5px solid rgba(109,40,217,0.3); color:#6D28D9; padding:8px 18px; border-radius:20px; font-size:0.9rem; font-weight:700;'>👤 CREATORS</span>
                    <span style='background:rgba(109,40,217,0.08); border:1.5px solid rgba(109,40,217,0.3); color:#6D28D9; padding:8px 18px; border-radius:20px; font-size:0.9rem; font-weight:700;'>📈 STRATEGISTS</span>
                    <span style='background:rgba(109,40,217,0.08); border:1.5px solid rgba(109,40,217,0.3); color:#6D28D9; padding:8px 18px; border-radius:20px; font-size:0.9rem; font-weight:700;'>💼 MANAGERS</span>
                    <span style='background:rgba(109,40,217,0.08); border:1.5px solid rgba(109,40,217,0.3); color:#6D28D9; padding:8px 18px; border-radius:20px; font-size:0.9rem; font-weight:700;'>🔬 ANALYSTS</span>
                </div>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("<p style='text-align:center; color:#94A3B8; font-size:0.85rem; margin-top:50px;'>YouTube Pro Dash v2.6 | Strategic Intelligence Blueprint</p>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# PAGE: HELP & FAQ — Elite Support Repository
# ═══════════════════════════════════════════════════════════════
elif st.session_state['page'] == 'help':
    st.markdown("""
        <div class='help-page-hero'>
            <h1>📚 Help & Support Center</h1>
            <p>Comprehensive guide to using YouTube Pro Dash. Learn about each page, features, and what the metrics mean.</p>
        </div>
    """, unsafe_allow_html=True)
    
    # --- QUICK START GUIDE (USER POV) ---
    st.markdown("### 🗺️ Quick Start: Your 3-Step Velocity Roadmap")
    s1, s2, s3 = st.columns(3)
    with s1:
        st.markdown("""
            <div style='background: linear-gradient(135deg, rgba(219, 234, 254, 0.8) 0%, rgba(191, 219, 254, 0.7) 100%); backdrop-filter:blur(10px); border:2px solid rgba(59, 130, 246, 0.3); border-radius:20px; padding:30px; text-align:center; min-height:220px;'>
                <div style='font-size:3rem;'>📥</div>
                <b style='font-size:1.2rem; color:#1e40af;'>INPUT ID</b>
                <p style='font-size:0.9rem; margin-top:12px; color:#1e3a8a; line-height:1.5;'>Paste any <b>YouTube Channel ID</b> into the sidebar and hit <b>Run Analysis</b>. The system builds your database instantly.</p>
            </div>
        """, unsafe_allow_html=True)
    with s2:
        st.markdown("""
            <div style='background: linear-gradient(135deg, rgba(220, 252, 231, 0.8) 0%, rgba(187, 247, 208, 0.7) 100%); backdrop-filter:blur(10px); border:2px solid rgba(34, 197, 94, 0.3); border-radius:20px; padding:30px; text-align:center; min-height:220px;'>
                <div style='font-size:3rem;'>🔍</div>
                <b style='font-size:1.2rem; color:#15803d;'>EXPLORE METRICS</b>
                <p style='font-size:0.9rem; margin-top:12px; color:#166534; line-height:1.5;'>Use <b>Battle Page</b> to benchmark rivals or <b>Visuals</b> to see heatmap patterns for optimal posting times.</p>
            </div>
        """, unsafe_allow_html=True)
    with s3:
        st.markdown("""
            <div style='background: linear-gradient(135deg, rgba(254, 243, 199, 0.8) 0%, rgba(253, 230, 138, 0.7) 100%); backdrop-filter:blur(10px); border:2px solid rgba(234, 179, 8, 0.3); border-radius:20px; padding:30px; text-align:center; min-height:220px;'>
                <div style='font-size:3rem;'>📊</div>
                <b style='font-size:1.2rem; color:#92400e;'>EXPORT REPORT</b>
                <p style='font-size:0.9rem; margin-top:12px; color:#b45309; line-height:1.5;'>Head to <b>Report Wizard</b> to download a high-fidelity PDF dossier for your brand sponsors or agency leads.</p>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom:50px;'></div>", unsafe_allow_html=True)

    # --- STRATEGIC USER JOURNEYS ---
    st.markdown("### 🏹 Choose Your Strategic Path")
    j1, j2 = st.columns(2)
    with j1:
        st.markdown("""
            <div style='background: linear-gradient(135deg, rgba(238, 242, 255, 0.8) 0%, rgba(224, 231, 255, 0.7) 100%); backdrop-filter:blur(10px); border-left:6px solid #6366F1; border-radius:16px; padding:28px;'>
                <h4 style='margin:0; color:#3730A3;'>👤 For Content Creators</h4>
                <p style='font-size:0.95rem; color:#4C51BF; margin-top:15px;'><b>Primary Goal:</b> Maximize engagement and consistency.<br>
                <b style='color:#3730A3;'>Workflow:</b> <span style='color:#6366F1;'>Visuals (Heatmaps) ➔ Metrics Library (Stability Score) ➔ Search (Trend Research)</span>.</p>
            </div>
        """, unsafe_allow_html=True)
    with j2:
        st.markdown("""
            <div style='background: linear-gradient(135deg, rgba(240, 253, 250, 0.8) 0%, rgba(204, 251, 241, 0.7) 100%); backdrop-filter:blur(10px); border-left:6px solid #10B981; border-radius:16px; padding:28px;'>
                <h4 style='margin:0; color:#0D9488;'>📈 For Growth Strategists</h4>
                <p style='font-size:0.95rem; color:#059669; margin-top:15px;'><b>Primary Goal:</b> Niche dominance and brand deals.<br>
                <b style='color:#0D9488;'>Workflow:</b> <span style='color:#10B981;'>Battle Page (Share of Voice) ➔ Report Wizard (PDF Dossiers) ➔ Compare (Rival Benchmarking)</span>.</p>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom:40px;'></div>", unsafe_allow_html=True)

    # --- SEARCHABLE RED FAQ ENGINE ---
    st.markdown("### ❓ Support & Strategic FAQ")
    search_q = st.text_input("", placeholder="Search knowledge base (e.g., 'API', 'Metrics', 'Channel ID')", label_visibility="collapsed", key="faq_search_input_v2")

    faq_repo = [
        {"cat": "🚀 Getting Started", "q": "Where do I find my Channel ID?", "a": "Go to any YouTube channel, click 'About', then 'Share', and select 'Copy Channel ID'. It starts with 'UC'."},
        {"cat": "🔧 Running Analysis", "q": "How long does a full sync take?", "a": "Typically 5-15 seconds depending on the channel size. We fetch metadata, tags, and full statistics instantly."},
        {"cat": "📊 Understanding Data", "q": "What is 'Velocity Index'?", "a": "It maps your library's growth speed. Use it in the Visual Intelligence module to spot outlier videos."},
        {"cat": "🛡️ Troubleshooting", "q": "Why am I getting a 403 error?", "a": "You've exceeded your 10,000 unit daily API quota. Wait 24 hours for a reset or use a different API key."}
    ]

    filtered_faqs = [f for f in faq_repo if not search_q or search_q.lower() in f['q'].lower() or search_q.lower() in f['a'].lower()]

    if not filtered_faqs:
        st.warning("No matching questions found. Try a different keyword.")
    else:
        for faq in filtered_faqs:
            with st.expander(f"**{faq['q']}**"):
                st.markdown(f"<p style='color:#475569; padding:10px 0;'>{faq['a']}</p>", unsafe_allow_html=True)
                st.markdown(f"<span style='background:#F1F5F9; color:#64748B; font-size:0.7rem; padding:3px 8px; border-radius:4px;'>{faq['cat']}</span>", unsafe_allow_html=True)

    # --- MORE FAQ BUTTON & VAULT ---
    st.markdown("<div style='margin-bottom:20px;'></div>", unsafe_allow_html=True)
    if 'show_faq_vault' not in st.session_state:
        st.session_state.show_faq_vault = False

    def toggle_vault():
        st.session_state.show_faq_vault = not st.session_state.show_faq_vault

    col_btn, _ = st.columns([1, 4])
    with col_btn:
        st.button("📦 Explore Elite FAQ Vault", on_click=toggle_vault, use_container_width=True)

    if st.session_state.show_faq_vault:
        st.markdown("""
            <div style='background: linear-gradient(180deg, rgba(255,255,255,0.95) 0%, rgba(248,250,252,0.95) 100%); border:2px solid #E2E8F0; border-radius:24px; padding:50px 40px; margin-top:30px; box-shadow:0 20px 60px rgba(0,0,0,0.08);'>
                <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:40px; padding-bottom:25px; border-bottom:2px solid #E2E8F0;'>
                    <div>
                        <h2 style='margin:0; color:#0F172A; font-size:2.2rem;'>🏛️ Elite Knowledge Vault</h2>
                        <p style='margin:8px 0 0 0; color:#64748B; font-size:0.95rem;'>Deep-dive technical, strategic, and policy insights</p>
                    </div>
                </div>
                <div style='display:flex; gap:30px; margin-bottom:20px;'>
                    <div style='flex:1; background: linear-gradient(135deg, rgba(219, 234, 254, 0.6) 0%, rgba(191, 219, 254, 0.4) 100%); border-left:5px solid #3B82F6; border-radius:16px; padding:32px;'>
                        <h4 style='margin:0 0 20px 0; color:#1e40af; font-size:1.15rem;'><span style='font-size:1.3rem;'>🚀</span> Advanced Tech Stack</h4>
                        <details style='margin-bottom:16px;' open><summary style='font-weight:700; cursor:pointer; color:#1e3a8a;'>⚙️ Database Sync Architecture</summary><p style='font-size:0.9rem; color:#1e40af; margin-top:10px; line-height:1.6;'>We use SQLAlchemy with a MySQL backend for sub-millisecond query performance on large video datasets.</p></details>
                        <details style='margin-bottom:16px;'><summary style='font-weight:700; cursor:pointer; color:#1e3a8a;'>📡 API Optimization</summary><p style='font-size:0.9rem; color:#1e40af; margin-top:10px; line-height:1.6;'>Our extractor uses field filtering to minimize quota usage, fetching only essential metrics per call.</p></details>
                        <details style='margin-bottom:0;'><summary style='font-weight:700; cursor:pointer; color:#1e3a8a;'>💾 Data Persistence</summary><p style='font-size:0.9rem; color:#1e40af; margin-top:10px; line-height:1.6;'>Your analyzed channels are stored permanently. No need to re-run analysis for the same channel twice.</p></details>
                    </div>
                    <div style='flex:1; background: linear-gradient(135deg, rgba(220, 252, 231, 0.6) 0%, rgba(187, 247, 208, 0.4) 100%); border-left:5px solid #10B981; border-radius:16px; padding:32px;'>
                        <h4 style='margin:0 0 20px 0; color:#0D9488; font-size:1.15rem;'><span style='font-size:1.3rem;'>🏹</span> Growth Strategy</h4>
                        <details style='margin-bottom:16px;' open><summary style='font-weight:700; cursor:pointer; color:#15803d;'>🎯 Rival Mapping Framework</summary><p style='font-size:0.9rem; color:#059669; margin-top:10px; line-height:1.6;'>Use the 'Battle' module to see if a rival's growth is organic or driven by a few viral 'outliers'.</p></details>
                        <details style='margin-bottom:16px;'><summary style='font-weight:700; cursor:pointer; color:#15803d;'>🔥 Engagement Hooks</summary><p style='font-size:0.9rem; color:#059669; margin-top:10px; line-height:1.6;'>High 'Engagement Velocity' in the first 24h is the strongest predictor of long-term algorithm success.</p></details>
                        <details style='margin-bottom:0;'><summary style='font-weight:700; cursor:pointer; color:#15803d;'>❤️ Channel Health Metrics</summary><p style='font-size:0.9rem; color:#059669; margin-top:10px; line-height:1.6;'>A stability score above 7.0 indicates a loyal fanbase that watches regardless of topic trend.</p></details>
                    </div>
                    <div style='flex:1; background: linear-gradient(135deg, rgba(245, 243, 255, 0.6) 0%, rgba(233, 213, 255, 0.4) 100%); border-left:5px solid #8B5CF6; border-radius:16px; padding:32px;'>
                        <h4 style='margin:0 0 20px 0; color:#6D28D9; font-size:1.15rem;'><span style='font-size:1.3rem;'>⚖️</span> Policy & Rules</h4>
                        <details style='margin-bottom:16px;' open><summary style='font-weight:700; cursor:pointer; color:#6D28D9;'>📋 Copyright Hub</summary><p style='font-size:0.9rem; color:#7C3AED; margin-top:10px; line-height:1.6;'>Check the YouTube Creator Studio for specific 'Claim' details; our dashboard shows raw performance data only.</p></details>
                        <details style='margin-bottom:16px;'><summary style='font-weight:700; cursor:pointer; color:#6D28D9;'>✨ Fair Use Logic</summary><p style='font-size:0.9rem; color:#7C3AED; margin-top:10px; line-height:1.6;'>Transformative commentary is key. Use our data to back up your claims in fair-use content reviews.</p></details>
                        <details style='margin-bottom:0;'><summary style='font-weight:700; cursor:pointer; color:#6D28D9;'>🔄 Platform Stability</summary><p style='font-size:0.9rem; color:#7C3AED; margin-top:10px; line-height:1.6;'>The YouTube API updates views every 15-30 minutes. Real-time counts may vary slightly from the dashboard.</p></details>
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)
        # Add a streamlit button for safe closing
        col_close_btn, _ = st.columns([1, 4])
        with col_close_btn:
            st.button("❌ Close Vault", on_click=toggle_vault, key="real_close_btn", use_container_width=True)

    st.markdown("<div style='margin-bottom:50px;'></div>", unsafe_allow_html=True)

    # --- EXPERT TIPS & GLOSSARY (COMPATIBLE CARDS) ---
    st.markdown("### 💡 Expert Intelligence Briefings")
    g1, g2, g3, g4 = st.columns(4)
    with g1:
        st.markdown("<div style='background: linear-gradient(135deg, rgba(219, 234, 254, 0.7) 0%, rgba(191, 219, 254, 0.6) 100%); border-left:4px solid #3B82F6; border-radius:12px; padding:20px;'><b style='color:#1e40af;'>📊 Engagement Velocity</b><p style='font-size:0.8rem; margin:10px 0; color:#1e3a8a;'>Interaction speed per 1k views.</p></div>", unsafe_allow_html=True)
    with g2:
        st.markdown("<div style='background: linear-gradient(135deg, rgba(220, 252, 231, 0.7) 0%, rgba(187, 247, 208, 0.6) 100%); border-left:4px solid #10B981; border-radius:12px; padding:20px;'><b style='color:#0D9488;'>👥 Subscriber ROI</b><p style='font-size:0.8rem; margin:10px 0; color:#15803d;'>Conversion efficiency of content.</p></div>", unsafe_allow_html=True)
    with g3:
        st.markdown("<div style='background: linear-gradient(135deg, rgba(254, 243, 199, 0.7) 0%, rgba(253, 230, 138, 0.6) 100%); border-left:4px solid #EAAB08; border-radius:12px; padding:20px;'><b style='color:#92400e;'>⚡ Stability Score</b><p style='font-size:0.8rem; margin:10px 0; color:#b45309;'>Foundation vs. Viral Luck.</p></div>", unsafe_allow_html=True)
    with g4:
        st.markdown("<div style='background: linear-gradient(135deg, rgba(245, 243, 255, 0.7) 0%, rgba(233, 213, 255, 0.6) 100%); border-left:4px solid #8B5CF6; border-radius:12px; padding:20px;'><b style='color:#6D28D9;'>🎯 Share of Voice</b><p style='font-size:0.8rem; margin:10px 0; color:#7C3AED;'>Niche dominance view %.</p></div>", unsafe_allow_html=True)

    st.markdown("<p style='text-align:center; color:#94A3B8; font-size:0.85rem; margin-top:50px;'>YouTube Pro Dash v2.6 | User-Centric Support Repository</p>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# Render the floating AI assistant globally on all pages
render_ai_assistant()


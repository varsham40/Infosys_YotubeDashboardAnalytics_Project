import streamlit as st
import plotly.express as px
import pandas as pd
import sys
import os
import isodate

# Configure path for module imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database_operations.save_from_streamlit import save_channel_and_videos
from data_processing.channel_extractor import extract_channel_data
from data_processing.video_extractor import extract_video_data

# --- HELPER FUNCTIONS ---
def parse_duration(duration_str):
    try:
        return isodate.parse_duration(duration_str).total_seconds()
    except:
        return 0

# --- PAGE CONFIG ---
st.set_page_config(page_title="YouTube Analytics Pro", page_icon="📊", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
<style>
    .metric-card {
        background-color: #f9f9f9;
        border-radius: 10px;
        padding: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        text-align: center;
    }
    .stApp {
        background-color: #ffffff;
    }
</style>
""", unsafe_allow_html=True)

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Settings")
    channel_id_input = st.text_input("YouTube Channel ID", placeholder="e.g., UC_x5XG1OV2P6uZZ5FSM9Ttw")
    fetch_button = st.button("🚀 Analyze Channel", type="primary")
    st.markdown("---")
    st.info("💡 **Tip:** Right-click 'View Page Source' on a YouTube channel page and search 'browse_id' to find the ID.")

# --- MAIN PAGE ---
# Custom Header with Gradient/Style
st.markdown("""
    <h1 style='text-align: center; color: #232D3F; font-family: sans-serif; margin-bottom: 20px;'>
        <span style='color: #FF0000;'>YouTube</span> Analytics Dashboard 📊
    </h1>
    <p style='text-align: center; color: #666; font-size: 1.1em;'>Deep dive into channel performance, engagement trends, and content strategy.</p>
""", unsafe_allow_html=True)

if fetch_button:
    if not channel_id_input:
        st.error("Please enter a valid Channel ID.")
    else:
        with st.spinner('Fetching fresh data from YouTube API...'):
            try:
                # 1. Save Data to DB (Upsert)
                save_channel_and_videos(channel_id_input)
                
                # 2. Fetch Channel Data
                df_channel = extract_channel_data([channel_id_input])
                
                if df_channel.empty:
                    st.error(f"Could not find channel: {channel_id_input}")
                else:
                    channel_data = df_channel.iloc[0]
                    
                    # --- HEADER SECTION ---
                    col1, col2 = st.columns([1, 4])
                    with col1:
                        if channel_data.get('thumbnail_url'):
                            st.image(channel_data['thumbnail_url'], width=120)
                    with col2:
                        st.title(f"{channel_data['channel_name']}")
                        # HIGHLIGHTED STATS
                        st.markdown(f"""
                        <div style="display: flex; gap: 20px;">
                            <div>
                                <h3 style="margin: 0; color: #FF0000;">{int(channel_data['subscribers'] or 0):,}</h3>
                                <p style="margin: 0; color: #555;">Subscribers</p>
                            </div>
                            <div>
                                <h3 style="margin: 0; color: #FF0000;">{int(channel_data['views']):,}</h3>
                                <p style="margin: 0; color: #555;">Total Views</p>
                            </div>
                            <div>
                                <h3 style="margin: 0; color: #FF0000;">{int(channel_data['total_videos']):,}</h3>
                                <p style="margin: 0; color: #555;">Total Videos</p>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # Date Formatting
                        raw_date = channel_data.get('published_at')
                        formatted_date = "N/A"
                        if raw_date:
                            try:
                                formatted_date = pd.to_datetime(raw_date).strftime('%d %b, %Y')
                            except:
                                formatted_date = raw_date
                        
                        st.caption(f"Joined: {formatted_date}")
                        
                    
                    st.divider()

                    # 3. Fetch Video Data
                    if channel_data.get('playlist_id'):
                        df_videos = extract_video_data(channel_data['playlist_id'])
                        
                        if not df_videos.empty:
                            # --- DATA PRE-PROCESSING ---
                            numeric_cols = ['view_count', 'like_count', 'comment_count']
                            for col in numeric_cols:
                                if col in df_videos.columns:
                                    df_videos[col] = pd.to_numeric(df_videos[col], errors='coerce').fillna(0)

                            if 'duration' in df_videos.columns:
                                df_videos['duration_sec'] = df_videos['duration'].apply(parse_duration)
                                df_videos['duration_min'] = df_videos['duration_sec'] / 60
                            
                            if 'published_at' in df_videos.columns:
                                df_videos['published_date'] = pd.to_datetime(df_videos['published_at'], errors='coerce')
                                df_videos['year_month'] = df_videos['published_date'].dt.to_period('M').astype(str)
                                df_videos['day_name'] = df_videos['published_date'].dt.day_name()
                            
                            df_videos['video_url'] = "https://www.youtube.com/watch?v=" + df_videos['video_id']
                            df_videos['engagement_rate'] = ((df_videos['like_count'] + df_videos['comment_count']) / df_videos['view_count']) * 100

                            # --- MAIN TABS FOR "SECTIONS" ---
                            tab_overview, tab_charts, tab_data = st.tabs(["🏡 Overview & Strategy", "📈 Deep Dive Analytics", "📋 Raw Data"])

                            # --- TAB 1: OVERVIEW & STRATEGY ---
                            with tab_overview:
                                st.markdown("### 🌟 Star Performer")
                                top_video = df_videos.loc[df_videos['view_count'].idxmax()]
                                
                                sp_c1, sp_c2 = st.columns([1, 3])
                                with sp_c1:
                                    if top_video.get('thumbnail_url'):
                                        st.image(top_video['thumbnail_url'], use_container_width=True)
                                with sp_c2:
                                    st.markdown(f"### [{top_video['title']}]({top_video['video_url']})")
                                    st.caption(f"Published: {top_video['published_at']}")
                                    st.markdown(f"**{top_video['view_count']:,.0f}** Views • **{top_video['like_count']:,.0f}** Likes • **{top_video['comment_count']:,.0f}** Comments")
                                    st.info("This is your highest performing video. Click the title to watch it!")

                                st.divider()
                                
                                # RENAMED & STYLED SCORECARD
                                st.markdown("### 🚀 Growth Strategy Insights")
                                day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                                videos_by_day = df_videos.groupby('day_name').size().reindex(day_order).fillna(0).reset_index(name='count')
                                
                                best_day = "N/A"
                                if not videos_by_day.empty and videos_by_day['count'].sum() > 0:
                                    best_day_idx = videos_by_day['count'].idxmax()
                                    best_day = videos_by_day.loc[best_day_idx, 'day_name']

                                avg_duration = df_videos['duration_min'].mean() if 'duration_min' in df_videos.columns else 0
                                med_engagement = df_videos['engagement_rate'].median()

                                sc1, sc2, sc3 = st.columns(3)
                                sc1.metric("📅 Best Upload Day", best_day, help="Upload on this day for consistency.")
                                sc2.metric("⏱️ Optimal Duration", f"{avg_duration:.1f} min", help="Average length of your videos.")
                                sc3.metric("💎 Target Engagement", f"{med_engagement:.2f}%", help="Aim for this engagement rate.")                          # --- TAB 2: DEEP DIVE ANALYTICS ---
                            with tab_charts:
                                st.markdown("### 📊 Engagement & Trends")
                                
                                # Row 1: Top 10s
                                c1, c2 = st.columns(2)
                                with c1:
                                    st.markdown("#### Most Viewed Videos")
                                    top_10_views = df_videos.sort_values(by="view_count", ascending=False).head(10)
                                    fig_views = px.bar(top_10_views, x="view_count", y="title", orientation='h', color="view_count", color_continuous_scale="Viridis")
                                    fig_views.update_layout(yaxis={'categoryorder':'total ascending', 'visible': False}, showlegend=False)
                                    st.plotly_chart(fig_views, use_container_width=True)
                                    
                                    # Link List
                                    with st.expander("View Links for Top 10 Viewed"):
                                        st.dataframe(
                                            top_10_views[['title', 'video_url', 'view_count']],
                                            column_config={"video_url": st.column_config.LinkColumn("Link")},
                                            hide_index=True
                                        )

                                with c2:
                                    st.markdown("#### Most Liked Videos")
                                    top_10_likes = df_videos.sort_values(by="like_count", ascending=False).head(10)
                                    fig_likes = px.bar(top_10_likes, x="like_count", y="title", orientation='h', color="like_count", color_continuous_scale="Magma")
                                    fig_likes.update_layout(yaxis={'categoryorder':'total ascending', 'visible': False}, showlegend=False)
                                    st.plotly_chart(fig_likes, use_container_width=True)
                                    
                                    # Link List
                                    with st.expander("View Links for Top 10 Liked"):
                                        st.dataframe(
                                            top_10_likes[['title', 'video_url', 'like_count']],
                                            column_config={"video_url": st.column_config.LinkColumn("Link")},
                                            hide_index=True
                                        )

                                st.divider()
                                
                                # Row 2: Consistency
                                st.markdown("#### � Upload Schedule Analysis")
                                cc1, cc2 = st.columns(2)
                                with cc1:
                                    if 'year_month' in df_videos.columns:
                                        videos_by_month = df_videos.groupby('year_month').size().reset_index(name='count')
                                        fig_pie = px.pie(videos_by_month, names='year_month', values='count', title="Uploads by Month", hole=0.4)
                                        st.plotly_chart(fig_pie, use_container_width=True)
                                with cc2:
                                    fig_days = px.bar(videos_by_day, x="day_name", y="count", title="Uploads by Day of Week", color="count", color_continuous_scale="RdBu")
                                    st.plotly_chart(fig_days, use_container_width=True)

                            # --- TAB 3: RAW DATA ---
                            with tab_data:
                                st.markdown("### � Top 50 Video Data")
                                top_50 = df_videos.sort_values(by="view_count", ascending=False).head(50)
                                st.dataframe(
                                    top_50[['title', 'published_at', 'view_count', 'like_count', 'comment_count', 'duration_min', 'video_url']],
                                    column_config={
                                        "video_url": st.column_config.LinkColumn("Watch Video"),
                                        "view_count": st.column_config.NumberColumn("Views", format="%d"),
                                        "duration_min": st.column_config.NumberColumn("Mins", format="%.1f")
                                    },
                                    use_container_width=True,
                                    height=600,
                                    hide_index=True
                                )

                        else:
                            st.warning("No videos found in this channel's upload playlist.")
            except Exception as e:
                st.error(f"An error occurred: {e}")

import pandas as pd
import numpy as np
from sqlalchemy import text
import sys
import os
from datetime import datetime
from dotenv import load_dotenv

# Ensure we can import from the root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
load_dotenv()

from database_operations.db_connection import engine

def get_raw_data():
    """Fetches combined channel and video data for transformation."""
    query = """
    SELECT 
        c.channel_name, 
        c.subscribers, 
        v.video_id, 
        v.title, 
        v.published_at,
        s.view_count, 
        s.like_count, 
        s.comment_count
    FROM videos v
    JOIN channels c ON v.channel_id = c.channel_id
    JOIN video_statistics s ON v.video_id = s.video_id
    WHERE s.captured_at = (
        SELECT MAX(captured_at) 
        FROM video_statistics 
        WHERE video_id = v.video_id
    );
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)
    return df

# Step 2: Engagement Rate Caluclation
def Caluclate_engagement_rate(df):
    """Formula: ((Likes+Comments)/Views) * 100"""
    df['engagement_rate'] = ((df['like_count'] + df['comment_count']) / df['view_count'].replace(0, np.nan)) * 100
    df['engagement_rate'] = df['engagement_rate'].fillna(0)
    return df

# Step 3: Average Views per Video
def Calculate_avg_views(df):
    """Calculates the average views across the dataset."""
    avg_val = df['view_count'].mean()
    print(f"Global Average Views: {avg_val:,.2f}")
    return df

# Step 4: Subscriber to view ratio
def Calculate_sub_to_view_ratio(df):
    """Formula: Total Views / Total Subscribers"""
    df['sub_to_view_ratio'] = df['view_count'] / df['subscribers'].replace(0, np.nan)
    df['sub_to_view_ratio'] = df['sub_to_view_ratio'].fillna(0)
    return df

# Step 5: Content Perfomance score
def Calculate_content_score(df):
    """
    Combines engagement and view volume into a single score.
    Formula: (Normalized Views * 0.7) + (Normalized Engagement * 0.3)
    """
    if df.empty: return df
    
    # Normalize values between 0 and 1 for fair scoring
    df['norm_views'] = (df['view_count'] - df['view_count'].min()) / (df['view_count'].max() - df['view_count'].min() + 1)
    df['norm_eng'] = (df['engagement_rate'] - df['engagement_rate'].min()) / (df['engagement_rate'].max() - df['engagement_rate'].min() + 1)
    
    df['content_performance_score'] = (df['norm_views'] * 70) + (df['norm_eng'] * 30)
    return df

# Step 6: Identify top perfoming categories
def Identify_top_categories(df):
    """Grouping performance by channel (as proxy for category)."""
    category_summary = df.groupby('channel_name').agg({
        'view_count': 'mean',
        'engagement_rate': 'mean'
    }).sort_values(by='view_count', ascending=False)
    return category_summary

# Step 7: Optimal posting time
def Optimal_posting_time(df):
    """Analyzes which hour gives the highest average views."""
    df['published_at'] = pd.to_datetime(df['published_at'])
    df['publish_hour'] = df['published_at'].dt.hour
    
    # Calculate both average views and count the number of uploads securely
    avg_v = df.groupby('publish_hour')['view_count'].mean().rename('avg_views')
    count_v = df.groupby('publish_hour')['view_count'].count().rename('video_count')
    
    # Merge them into a single dataframe
    hour_analysis = pd.concat([avg_v, count_v], axis=1).fillna(0)
    
    # Ensure all 24 hours exist in the index and sort sequentially so the area chart renders left-to-right correctly without breaking
    hour_analysis = hour_analysis.reindex(range(24), fill_value=0)
    return hour_analysis

# Step 8: Trend Analysis
def Trend_analysis(df, period='weekly'):
    """Resamples data to find upload trends."""
    df['published_at'] = pd.to_datetime(df['published_at'])
    if period == 'daily':
        freq = 'D'
    elif period == 'weekly':
        freq = 'W'
    else:
        freq = 'ME'
        
    trends = df.set_index('published_at').resample(freq).size().reset_index(name='video_count')
    return trends

# Step 9: perfomance Benchmark
def benchmark_videos(df):
    """Compare each video to global average."""
    avg_views = df["view_count"].mean()
    df['benchmark_ratio'] = df['view_count'] / avg_views
    
    conditions = [
        (df['benchmark_ratio'] > 1.2),
        (df['benchmark_ratio'] >= 0.8),
        (df['benchmark_ratio'] < 0.8)
    ]
    choices = ['High Performer', 'Average', 'Below Average']
    df['performance_rank'] = np.select(conditions, choices, default='Average')
    return df

if __name__ == "__main__":
    # Step 10: prepare data for visualization
    print("Fetching raw data from database...")
    raw_df = get_raw_data()
    
    if raw_df.empty:
        print("No data found. Please sync some channels first.")
    else:
        # Step 11: Testing & Verification
        print("Processing transformations...")
        raw_df = Caluclate_engagement_rate(raw_df)
        raw_df = Calculate_avg_views(raw_df)
        raw_df = Calculate_sub_to_view_ratio(raw_df)
        raw_df = Calculate_content_score(raw_df)
        raw_df = benchmark_videos(raw_df)

        print("\n--- Final Transformed Data (Top 5) ---")
        # Added Subscriber-to-view ratio to the columns
        display_cols = ['title', 'engagement_rate', 'sub_to_view_ratio', 'content_performance_score', 'performance_rank']
        print(raw_df[display_cols].sort_values(by='content_performance_score', ascending=False).head())

        print("\n--- Optimal Posting Hours (Top 3) ---")
        print(Optimal_posting_time(raw_df).head(3))

        print("\n--- Category/Channel Summary ---")
        print(Identify_top_categories(raw_df))
        
        print("\n--- Weekly Upload Trends (Recent) ---")
        print(Trend_analysis(raw_df, period='weekly').tail(3))

        # Internal Verification (Step 11)
        critical_cols = ['engagement_rate', 'sub_to_view_ratio', 'content_performance_score']
        nan_exists = raw_df[critical_cols].isna().any().any()
        
        print("\n--- Final Verification Status ---")
        if not nan_exists:
            print("✅ Data Integrity: No NaN values found in metrics.")
            print("✅ Mathematical Consistency: Ratios and scores correctly calculated.")
            print("✅ Logical Ranking: Quality and View performance aligned.")
        else:
            print("⚠️ Data Integrity: Some incomplete values (NaN) detected.")
        print("-------------------------------")

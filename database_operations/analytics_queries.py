import pandas as pd
from sqlalchemy import text
import sys
import os

# Ensure we can import from the root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database_operations.db_connection import DATABASE_URL
from sqlalchemy import create_engine

# Use a separate engine with echo=False for clean CLI output
engine = create_engine(DATABASE_URL, echo=False)

def run_query(query):
    """Utility function to run a SQL query and return a DataFrame."""
    with engine.connect() as conn:
        return pd.read_sql(text(query), conn)

def get_top_10_most_viewed():
    """1) Returns the top 10 most viewed videos across all channels."""
    query = """
    SELECT v.title, s.view_count, c.channel_name, v.video_id
    FROM videos v
    JOIN video_statistics s ON v.video_id = s.video_id
    JOIN channels c ON v.channel_id = c.channel_id
    WHERE s.captured_at = (
        SELECT MAX(captured_at) 
        FROM video_statistics 
        WHERE video_id = v.video_id
    )
    ORDER BY s.view_count DESC
    LIMIT 10;
    """
    return run_query(query)

def get_avg_video_duration():
    """2) Returns the raw video titles and durations for processing."""
    query = """
    SELECT c.channel_name, v.duration
    FROM videos v
    JOIN channels c ON v.channel_id = c.channel_id;
    """
    return run_query(query)

def get_engagement_rate_analysis():
    """3 & 4) Returns engagement rates for all videos."""
    query = """
    SELECT v.title, s.view_count, s.like_count, s.comment_count,
           ((s.like_count + s.comment_count) / NULLIF(s.view_count, 0)) * 100 as engagement_rate
    FROM videos v
    JOIN video_statistics s ON v.video_id = s.video_id
    WHERE s.captured_at = (
        SELECT MAX(captured_at) 
        FROM video_statistics 
        WHERE video_id = v.video_id
    )
    ORDER BY engagement_rate DESC;
    """
    return run_query(query)

def get_posting_frequency_analysis():
    """5) Calculates posts per day per channel."""
    query = """
    SELECT c.channel_name, 
           COUNT(v.video_id) as total_videos,
           DATEDIFF(MAX(v.published_at), MIN(v.published_at)) as days_active,
           COUNT(v.video_id) / NULLIF(DATEDIFF(MAX(v.published_at), MIN(v.published_at)), 0) as posts_per_day
    FROM videos v
    JOIN channels c ON v.channel_id = c.channel_id
    GROUP BY c.channel_id;
    """
    return run_query(query)

def get_monthly_upload_trends():
    """6) Monthly upload counting."""
    query = """
    SELECT DATE_FORMAT(published_at, '%Y-%m') as month, COUNT(*) as video_count
    FROM videos
    GROUP BY month
    ORDER BY month;
    """
    return run_query(query)

if __name__ == "__main__":
    print("\n--- Top 10 Most Viewed Videos ---")
    print(get_top_10_most_viewed())
    
    print("\n--- Engagement Rate Analysis ---")
    print(get_engagement_rate_analysis().head(10))
    
    print("\n--- Posting Frequency ---")
    print(get_posting_frequency_analysis())
    
    print("\n--- Monthly Upload Trends ---")
    print(get_monthly_upload_trends())

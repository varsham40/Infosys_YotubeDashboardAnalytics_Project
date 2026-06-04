import pandas as pd
try:
    from .youtube_api import get_youtube_client, get_video_ids, get_video_details, get_channel_details, get_video_ids_for_year
except ImportError:
    from youtube_api import get_youtube_client, get_video_ids, get_video_details, get_channel_details, get_video_ids_for_year

def extract_video_data(playlist_id, limit=100):
    """
    Fetches videos from a playlist and returns a Pandas DataFrame.
    """
    youtube = get_youtube_client()
    if not youtube or not playlist_id:
        return pd.DataFrame()

    print(f"Fetching videos for Playlist ID: {playlist_id}")
    video_ids = get_video_ids(youtube, playlist_id, limit)
    
    if not video_ids:
        print("No videos found.")
        return pd.DataFrame()
        
    print(f"Fetching details for {len(video_ids)} videos...")
    video_data = get_video_details(youtube, video_ids)
    
    if video_data:
        df = pd.DataFrame(video_data)
        # Ensure we have all columns even if empty
        cols = ['video_id', 'title', 'published_at', 'view_count', 'like_count', 'comment_count', 'duration', 'definition', 'caption', 'thumbnail_url']
        df = df[[c for c in cols if c in df.columns]]
        return df
    else:
        return pd.DataFrame()

def extract_video_data_for_year(channel_id, year, limit=50):
    """
    Fetches videos from a specific channel and year, and returns a Pandas DataFrame.
    """
    youtube = get_youtube_client()
    if not youtube or not channel_id:
        return pd.DataFrame()

    print(f"Fetching videos for Channel ID {channel_id} in Year {year}")
    video_ids = get_video_ids_for_year(youtube, channel_id, year, limit)
    
    if not video_ids:
        print(f"No videos found for year {year}.")
        return pd.DataFrame()
        
    print(f"Fetching details for {len(video_ids)} videos...")
    video_data = get_video_details(youtube, video_ids)
    
    if video_data:
        df = pd.DataFrame(video_data)
        # Ensure we have all columns even if empty
        cols = ['video_id', 'title', 'published_at', 'view_count', 'like_count', 'comment_count', 'duration', 'definition', 'caption', 'thumbnail_url']
        df = df[[c for c in cols if c in df.columns]]
        return df
    else:
        return pd.DataFrame()

if __name__ == "__main__":
    # Test Block
    # 1. Get Google Developers Channel
    youtube = get_youtube_client()
    channel_id = "UC_x5XG1OV2P6uZZ5FSM9Ttw"
    
    print("--- Starting Video Extraction Test ---")
    channel_info = get_channel_details(youtube, channel_id)
    
    if channel_info and channel_info.get('playlist_id'):
        uploads_id = channel_info['playlist_id']
        df_videos = extract_video_data(uploads_id)
        
        print("\n--- Extraction Complete ---")
        print(df_videos.head())
        print("\n--- Data Types ---")
        print(df_videos.dtypes)
    else:
        print("Could not get playlist ID for test.")

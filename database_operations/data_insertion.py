from database_operations.db_connection import SessionLocal
from database_operations.db_model import Channel, Video, VideoStats
from data_processing.channel_extractor import extract_channel_data
from data_processing.video_extractor import extract_video_data
from sqlalchemy.orm import Session
import pandas as pd
import streamlit as st

# --- HELPER: DATA VALIDATION (Step 4) ---
def validate_data(data, required_fields):
    """Ensure required fields exist and are not null."""
    for field in required_fields:
        if field not in data or pd.isna(data[field]) or data[field] is None:
            return False, f"Missing or null required field: {field}"
    return True, "Valid"

# --- STEP 3: CHECK IF CHANNEL EXISTS ---
def channel_exists(session: Session, channel_id: str) -> bool:
    return session.query(Channel).filter(Channel.channel_id == channel_id).first() is not None

# --- STEP 4: INSERT OR UPDATE CHANNEL ---
def insert_or_update_channel(session: Session, channel_data: dict):
    # Validation
    required = ["channel_id", "channel_name", "views", "total_videos"]
    is_valid, msg = validate_data(channel_data, required)
    if not is_valid:
        raise ValueError(f"Channel validation failed: {msg}")

    # Create model instance
    channel = Channel(
        channel_id=channel_data["channel_id"],
        channel_name=channel_data["channel_name"],
        subscribers=int(channel_data["subscribers"]) if pd.notna(channel_data.get("subscribers")) else 0,
        views=int(channel_data["views"]),
        total_videos=int(channel_data["total_videos"]),
        playlist_id=channel_data.get("playlist_id"),
        published_at=channel_data.get("published_at"),
        thumbnail_url=channel_data.get("thumbnail_url"),
        description=channel_data.get("description")
    )
    
    # Upsert Logic (Insert or Update via session.merge)
    session.merge(channel)
    session.flush() # Ensure it's ready for foreign key relations
    return channel

# --- STEP 5: INSERT VIDEO METADATA ---
def insert_video(session: Session, video_data: dict, channel_id: str):
    required = ["video_id", "title"]
    is_valid, msg = validate_data(video_data, required)
    if not is_valid:
        print(f"⚠️ Skipping invalid video: {msg}")
        return None

    video = Video(
        video_id=video_data["video_id"],
        channel_id=channel_id,
        title=video_data["title"],
        published_at=video_data.get("published_at"),
        duration=video_data.get("duration"),
        thumbnail_url=video_data.get("thumbnail_url")
    )
    session.merge(video)
    return video

# --- STEP 6: INSERT VIDEO STATISTICS ---
def insert_video_statistics(session: Session, stats_data: dict):
    stats = VideoStats(
        video_id=stats_data["video_id"],
        view_count=int(stats_data.get("view_count", 0)),
        like_count=int(stats_data.get("like_count", 0)),
        comment_count=int(stats_data.get("comment_count", 0))
    )
    session.add(stats)

# --- STEP 7: COMBINE EVERYTHING (MAIN WRAPPER) ---
def store_channel_data(channel_id: str):
    session = SessionLocal()
    summary = {"channel_name": "Unknown", "videos_processed": 0, "status": "Error", "message": ""}
    try:
        # Step 4: Save Channel
        df_channel = extract_channel_data([channel_id])
        if df_channel.empty:
            summary["message"] = f"No data found for channel: {channel_id}"
            return summary

        ch_dict = df_channel.iloc[0].to_dict()
        summary["channel_name"] = ch_dict["channel_name"]
        
        channel = insert_or_update_channel(session, ch_dict)

        # Steps 5 & 6: Save Videos and Stats
        if channel.playlist_id:
            df_videos = extract_video_data(channel.playlist_id)
            for _, row in df_videos.iterrows():
                v_dict = row.to_dict()
                insert_video(session, v_dict, channel.channel_id)
                insert_video_statistics(session, v_dict)
            summary["videos_processed"] = len(df_videos)
        
        session.commit()
        summary["status"] = "Success"
        return summary
    except Exception as e:
        session.rollback()
        summary["message"] = str(e)
        return summary
    finally:
        session.close()

# --- STEP 6: RECENT CHANNELS ---
@st.cache_data(ttl=600)
def get_recent_channels(limit=5):
    session = SessionLocal()
    try:
        channels = session.query(Channel).limit(limit).all()
        return [
            {
                "name": c.channel_name, 
                "id": c.channel_id,
                "thumbnail_url": c.thumbnail_url,
                "subscribers": c.subscribers
            } for c in channels
        ]
    except:
        return []
    finally:
        session.close()

if __name__ == "__main__":
    # Example usage
    res = store_channel_data("UC_x5XG1OV2P6uZZ5FSM9Ttw")
    print(res)
    print(get_recent_channels())

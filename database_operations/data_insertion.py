from database_operations.db_connection import SessionLocal
from database_operations.db_model import Channel, Video, VideoStats
from data_processing.channel_extractor import extract_channel_data
from data_processing.video_extractor import extract_video_data, extract_video_data_for_year
from data_processing.url_resolver import resolve_channel_input
from sqlalchemy.orm import Session
import pandas as pd
import streamlit as st
import sys
import traceback

def _log(msg):
    """Unified debug logger visible in Streamlit Cloud logs."""
    print(f"[DATA_INSERTION] {msg}", flush=True)
    print(f"[DATA_INSERTION] {msg}", file=sys.stderr, flush=True)

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

def store_channel_data(channel_id: str, limit: int = 50):
    _log(f"=== store_channel_data called for input='{channel_id}' ===")
    session = SessionLocal()
    summary = {"channel_name": "Unknown", "videos_processed": 0, "status": "Error", "message": "", "resolved_id": ""}
    try:
        # --- Step 0: Resolve URL/handle/ID to a canonical Channel ID ---
        try:
            from data_processing.youtube_api import get_youtube_client
            youtube_client = get_youtube_client()
            resolved_id = resolve_channel_input(channel_id, youtube_client)
            _log(f"Input '{channel_id}' resolved to Channel ID: '{resolved_id}'")
            summary["resolved_id"] = resolved_id
        except ValueError as e:
            _log(f"URL resolution failed: {e}")
            summary["message"] = str(e)
            return summary

        # Step 4: Save Channel
        _log("Calling extract_channel_data...")
        df_channel = extract_channel_data([resolved_id])
        _log(f"extract_channel_data returned DataFrame shape: {df_channel.shape}")
        if df_channel.empty:
            _log("DataFrame is empty — no channel data returned.")
            summary["message"] = f"No data found for channel: {resolved_id}. The channel ID may be invalid or the YouTube API key may be misconfigured."
            return summary

        ch_dict = df_channel.iloc[0].to_dict()
        summary["channel_name"] = ch_dict["channel_name"]
        _log(f"Channel resolved: '{ch_dict['channel_name']}', playlist_id='{ch_dict.get('playlist_id')}'")
        
        channel = insert_or_update_channel(session, ch_dict)
        _log("Channel inserted/updated in database.")

        # Steps 5 & 6: Save Videos and Stats
        if channel.playlist_id:
            _log(f"Fetching videos for playlist: {channel.playlist_id}")
            df_videos = extract_video_data(channel.playlist_id, limit=limit)
            _log(f"Videos fetched: {len(df_videos)} rows")
            if not df_videos.empty:
                existing_video_ids = {
                    r[0] for r in session.query(Video.video_id)
                    .filter(Video.channel_id == channel.channel_id)
                    .all()
                }
                _log(f"Existing video IDs in DB: {len(existing_video_ids)}")

                new_videos = []
                videos_to_update = []
                stats_objects = []

                for _, row in df_videos.iterrows():
                    v_dict = row.to_dict()
                    
                    is_valid, msg = validate_data(v_dict, ["video_id", "title"])
                    if not is_valid:
                        continue

                    vid_id = v_dict["video_id"]
                    
                    video_obj = Video(
                        video_id=vid_id,
                        channel_id=channel.channel_id,
                        title=v_dict["title"],
                        published_at=v_dict.get("published_at"),
                        duration=v_dict.get("duration"),
                        thumbnail_url=v_dict.get("thumbnail_url")
                    )

                    if vid_id in existing_video_ids:
                        videos_to_update.append({
                            "video_id": vid_id,
                            "title": v_dict["title"],
                            "published_at": v_dict.get("published_at"),
                            "duration": v_dict.get("duration"),
                            "thumbnail_url": v_dict.get("thumbnail_url")
                        })
                    else:
                        new_videos.append(video_obj)

                    stats_obj = VideoStats(
                        video_id=vid_id,
                        view_count=int(v_dict.get("view_count", 0)),
                        like_count=int(v_dict.get("like_count", 0)),
                        comment_count=int(v_dict.get("comment_count", 0))
                    )
                    stats_objects.append(stats_obj)

                _log(f"Bulk save: {len(new_videos)} new, {len(videos_to_update)} updates, {len(stats_objects)} stats")
                if new_videos:
                    session.bulk_save_objects(new_videos)
                if videos_to_update:
                    session.bulk_update_mappings(Video, videos_to_update)
                if stats_objects:
                    session.bulk_save_objects(stats_objects)

                summary["videos_processed"] = len(df_videos)
        else:
            _log("WARNING: Channel has no playlist_id — cannot fetch videos.")
        
        session.commit()
        _log("Session committed successfully.")
        summary["status"] = "Success"
        return summary
    except ValueError as e:
        _log(f"ValueError in store_channel_data: {e}")
        session.rollback()
        summary["message"] = str(e)
        return summary
    except Exception as e:
        _log(f"Unexpected exception in store_channel_data: {e}")
        _log(traceback.format_exc())
        session.rollback()
        summary["message"] = f"Internal error: {e}"
        return summary
    finally:
        session.close()
        _log("Session closed.")

def store_channel_data_for_year(channel_id: str, year: int, limit: int = 50):
    session = SessionLocal()
    summary = {"channel_name": "Unknown", "videos_processed": 0, "status": "Error", "message": ""}
    try:
        # Check if channel exists in DB
        channel = session.query(Channel).filter(Channel.channel_id == channel_id).first()
        if not channel:
            summary["message"] = f"Channel {channel_id} not found in database. Sync the channel first."
            return summary
            
        summary["channel_name"] = channel.channel_name
        
        # Save Videos and Stats for the specific year
        df_videos = extract_video_data_for_year(channel_id, year, limit=limit)
        if not df_videos.empty:
            # Get existing video IDs in a single query
            existing_video_ids = {
                r[0] for r in session.query(Video.video_id)
                .filter(Video.channel_id == channel_id)
                .all()
            }

            new_videos = []
            videos_to_update = []
            stats_objects = []

            for _, row in df_videos.iterrows():
                v_dict = row.to_dict()
                
                # Validation
                is_valid, msg = validate_data(v_dict, ["video_id", "title"])
                if not is_valid:
                    continue

                vid_id = v_dict["video_id"]
                
                video_obj = Video(
                    video_id=vid_id,
                    channel_id=channel_id,
                    title=v_dict["title"],
                    published_at=v_dict.get("published_at"),
                    duration=v_dict.get("duration"),
                    thumbnail_url=v_dict.get("thumbnail_url")
                )

                if vid_id in existing_video_ids:
                    videos_to_update.append({
                        "video_id": vid_id,
                        "title": v_dict["title"],
                        "published_at": v_dict.get("published_at"),
                        "duration": v_dict.get("duration"),
                        "thumbnail_url": v_dict.get("thumbnail_url")
                    })
                else:
                    new_videos.append(video_obj)

                stats_obj = VideoStats(
                    video_id=vid_id,
                    view_count=int(v_dict.get("view_count", 0)),
                    like_count=int(v_dict.get("like_count", 0)),
                    comment_count=int(v_dict.get("comment_count", 0))
                )
                stats_objects.append(stats_obj)

            # Bulk inserts and updates
            if new_videos:
                session.bulk_save_objects(new_videos)
            if videos_to_update:
                session.bulk_update_mappings(Video, videos_to_update)
            if stats_objects:
                session.bulk_save_objects(stats_objects)

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

def discard_channel_data_for_year(channel_id: str, year: int):
    """
    Deletes all videos and their statistics for a specific year and channel,
    EXCEPT for the most recent 50 videos of the channel (to protect the core context).
    """
    session = SessionLocal()
    summary = {"status": "Error", "message": ""}
    try:
        # 1. Query the video_ids of the most recent 50 videos for this channel to protect them
        recent_video_ids = [
            r[0] for r in session.query(Video.video_id)
            .filter(Video.channel_id == channel_id)
            .order_by(Video.published_at.desc())
            .limit(50)
            .all()
        ]
        
        # 2. Find the video_ids of the videos for this channel published in the target year
        # that are not in the recent_video_ids list.
        videos_to_delete_query = session.query(Video.video_id).filter(
            Video.channel_id == channel_id,
            Video.published_at.like(f"{year}%")
        )
        if recent_video_ids:
            videos_to_delete_query = videos_to_delete_query.filter(Video.video_id.notin_(recent_video_ids))
            
        videos_to_delete = [r[0] for r in videos_to_delete_query.all()]
        
        if not videos_to_delete:
            summary["status"] = "Success"
            summary["message"] = f"No discardable cached videos found for {year}."
            return summary
            
        # 3. Delete comments first
        from database_operations.db_model import Comment
        session.query(Comment).filter(Comment.video_id.in_(videos_to_delete)).delete(synchronize_session=False)
        
        # 4. Delete video statistics
        session.query(VideoStats).filter(VideoStats.video_id.in_(videos_to_delete)).delete(synchronize_session=False)
        
        # 5. Delete videos
        session.query(Video).filter(Video.video_id.in_(videos_to_delete)).delete(synchronize_session=False)
        
        session.commit()
        summary["status"] = "Success"
        summary["message"] = f"Successfully discarded {len(videos_to_delete)} videos cached for {year}."
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

from database_operations.db_connection import SessionLocal
from database_operations.db_model import Channel, Video, VideoStats

from data_processing.channel_extractor import extract_channel_data
from data_processing.video_extractor import extract_video_data


def save_channel_and_videos(channel_id):
    session = SessionLocal()

    # -------- CHANNEL ----------
    df_channel = extract_channel_data([channel_id])
    if df_channel.empty:
        print("No channel data")
        return

    ch = df_channel.iloc[0]

    channel = Channel(
        channel_id=ch["channel_id"],
        channel_name=ch["channel_name"],
        subscribers=int(ch["subscribers"]) if str(ch["subscribers"]).isdigit() else None,
        views=int(ch["views"]),
        total_videos=int(ch["total_videos"]),
        playlist_id=ch["playlist_id"],
        published_at=ch["published_at"],
        thumbnail_url=ch["thumbnail_url"],
        description=ch["description"]
    )

    session.merge(channel)
    session.commit()

    # -------- VIDEOS ----------
    df_videos = extract_video_data(ch["playlist_id"])

    for _, row in df_videos.iterrows():

        video = Video(
            video_id=row["video_id"],
            channel_id=channel.channel_id,
            title=row["title"],
            published_at=row["published_at"],
            duration=row["duration"],
            thumbnail_url=row["thumbnail_url"]
        )

        session.merge(video)
        session.commit()

        stats = VideoStats(
            video_id=row["video_id"],
            view_count=row["view_count"],
            like_count=row["like_count"],
            comment_count=row["comment_count"]
        )

        session.add(stats)

    session.commit()
    session.close()

    print("✅ Saved channel + videos to DB")

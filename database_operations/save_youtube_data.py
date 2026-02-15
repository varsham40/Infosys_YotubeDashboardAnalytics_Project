from database_operations.db_connection import SessionLocal
from database_operations.db_model import Channel, Video, VideoStats
from data_processing.channel_extractor import extract_channel_data
from data_processing.video_extractor import extract_video_data


def save_channel_and_videos(channel_id):

    session = SessionLocal()

    # -------- CHANNEL DATA --------
    ch_df = extract_channel_data([channel_id])

    if ch_df.empty:
        print("No channel data")
        return

    ch = ch_df.iloc[0]

    channel = Channel(
        channel_id=ch["channel_id"],
        channel_name=ch["channel_name"],
        subscribers=int(ch.get("subscribers", 0)),
        views=int(ch.get("views", 0)),
        total_videos=int(ch.get("total_videos", 0)),
        playlist_id=ch.get("playlist_id"),
        published_at=ch.get("published_at"),
        thumbnail_url=ch.get("thumbnail_url"),
        description=ch.get("description"),
    )

    session.merge(channel)

    # -------- VIDEO DATA --------
    playlist_id = ch["playlist_id"]
    vid_df = extract_video_data(playlist_id)

    if vid_df.empty:
        print("No video data")
        session.commit()
        session.close()
        return

    for _, v in vid_df.iterrows():

        video = Video(
            video_id=v["video_id"],
            channel_id=channel_id,
            title=v["title"],
            published_at=v.get("published_at"),
            duration=v.get("duration"),
            thumbnail_url=v.get("thumbnail_url"),
        )

        session.merge(video)

        stats = VideoStats(
            video_id=v["video_id"],
            view_count=int(v.get("view_count", 0)),
            like_count=int(v.get("like_count", 0)),
            comment_count=int(v.get("comment_count", 0)),
        )

        session.add(stats)

    session.commit()
    session.close()

    print("✅ Data Saved to MySQL!")


if __name__ == "__main__":
    save_channel_and_videos("UC_x5XG1OV2P6uZZ5FSM9Ttw")

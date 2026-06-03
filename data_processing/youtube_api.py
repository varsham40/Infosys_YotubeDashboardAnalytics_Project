import os
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Load environment variables
load_dotenv()

def get_youtube_client():
    """
    Initializes and returns an authenticated YouTube Data API client.
    """
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        raise ValueError("Error: YOUTUBE_API_KEY not found in .env file.")

    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        return youtube
    except HttpError as e:
        print(f"An error occurred connecting to YouTube API: {e}")
        return None

def get_channel_details(youtube, channel_id):
    """
    Fetches detailed information for a given YouTube Channel ID.
    Params:
        youtube: The authenticated YouTube client object.
        channel_id: The ID of the YouTube channel (e.g., 'UC_x5XG1OV2P6uZZ5FSM9Ttw').
    Returns:
        dict: A dictionary containing channel details or None if failed.
    """
    try:
        request = youtube.channels().list(
            part="snippet,statistics,contentDetails",
            id=channel_id
        )
        response = request.execute()

        if "items" in response and len(response["items"]) > 0:
            item = response["items"][0]
            snippet = item["snippet"]
            stats = item["statistics"]
            content_details = item.get("contentDetails", {})
            related_playlists = content_details.get("relatedPlaylists", {})

            data = {
                "channel_name": snippet["title"],
                "subscribers": stats.get("subscriberCount", "Hidden"),
                "views": stats.get("viewCount", 0),
                "total_videos": stats.get("videoCount", 0),
                "description": snippet["description"],
                "playlist_id": related_playlists.get("uploads"),
                "published_at": snippet.get("publishedAt"),
                "thumbnail_url": snippet.get("thumbnails", {}).get("high", {}).get("url")
            }
            return data
        else:
            print(f"Error: Channel with ID {channel_id} not found.")
            return None

    except HttpError as e:
        print(f"API Error: {e}")
        return None
    except Exception as e:
        print(f"Unexpected Error: {e}")
        return None

def get_video_ids(youtube, playlist_id):
    """
    Fetches all video IDs from a playlist using pagination.
    """
    video_ids = []
    next_page_token = None
    try:
        while True:
            request = youtube.playlistItems().list(
                part="contentDetails",
                playlistId=playlist_id,
                maxResults=50,
                pageToken=next_page_token
            )
            response = request.execute()
            
            for item in response.get("items", []):
                video_ids.append(item["contentDetails"]["videoId"])
                
            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break
                
        return video_ids
    except HttpError as e:
        print(f"Error fetching video IDs: {e}")
        return video_ids

def get_video_details(youtube, video_ids):
    """
    Fetches details for a list of Video IDs.
    """
    video_data = []
    # API allows max 50 IDs per request
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i+50]
        try:
            request = youtube.videos().list(
                part="snippet,statistics,contentDetails",
                id=",".join(chunk)
            )
            response = request.execute()
            
            for item in response.get("items", []):
                snippet = item["snippet"]
                stats = item["statistics"]
                content = item["contentDetails"]
                
                video_data.append({
                    "video_id": item["id"],
                    "title": snippet["title"],
                    "published_at": snippet["publishedAt"],
                    "thumbnail_url": snippet.get("thumbnails", {}).get("high", {}).get("url"),
                    "view_count": int(stats.get("viewCount", 0)),
                    "like_count": int(stats.get("likeCount", 0)),
                    "comment_count": int(stats.get("commentCount", 0)),
                    "duration": content.get("duration"),
                    "definition": content.get("definition"),
                    "caption": content.get("caption")
                })
        except HttpError as e:
            print(f"Error fetching video details: {e}")
            
    return video_data

if __name__ == "__main__":
    # Simple test block
    print("Testing YouTube API Connection...")
    try:
        yt = get_youtube_client()
        # Test with Google Developers channel ID
        test_channel_id = "UC_x5XG1OV2P6uZZ5FSM9Ttw" 
        print(f"Fetching details for Channel ID: {test_channel_id}")
        
        details = get_channel_details(yt, test_channel_id)
        if details:
            print("Successfully connected!")
            print(f"Channel Name: {details['channel_name']}")
            print(f"Subscribers: {details['subscribers']}")
            print(f"Playlist ID: {details['playlist_id']}")
            
            if details['playlist_id']:
                print("\nFetching Videos...")
                v_ids = get_video_ids(yt, details['playlist_id'])
                print(f"Found {len(v_ids)} videos.")
                
                if v_ids:
                    print("Fetching First Video Details...")
                    v_stats = get_video_details(yt, v_ids[:1])
                    print(v_stats)
            
    except ValueError as e:
        print(e)

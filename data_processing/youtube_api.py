import os
import sys
import json
import traceback
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Load environment variables
load_dotenv()

_youtube_client = None

def _log(msg):
    """Unified logger that writes to both stdout and stderr for Streamlit Cloud visibility."""
    print(f"[YOUTUBE_API] {msg}", flush=True)
    print(f"[YOUTUBE_API] {msg}", file=sys.stderr, flush=True)

def get_youtube_client():
    """
    Initializes and returns an authenticated YouTube Data API client.
    Caches the client globally to avoid recreating it and downloading the discovery doc repeatedly.
    """
    global _youtube_client
    if _youtube_client is not None:
        _log("Returning cached YouTube client.")
        return _youtube_client

    api_key = os.getenv("YOUTUBE_API_KEY")
    _log(f"API Key loaded: {'YES' if api_key else 'NO (MISSING!)'}")
    if api_key:
        _log(f"API Key prefix: {api_key[:6]}*** (length={len(api_key)})")
    else:
        _log("WARNING: YOUTUBE_API_KEY is not set in environment variables or Streamlit Secrets!")

    if not api_key:
        raise ValueError(
            "YOUTUBE_API_KEY not found! "
            "If running locally, check your .env file. "
            "If deployed on Streamlit Cloud, go to App Settings > Secrets and add: YOUTUBE_API_KEY = \"your_api_key\""
        )

    try:
        _log("Building YouTube API client with static_discovery=True...")
        _youtube_client = build('youtube', 'v3', developerKey=api_key, static_discovery=True)
        _log("YouTube client built successfully!")
        return _youtube_client
    except HttpError as e:
        try:
            error_details = json.loads(e.content.decode('utf-8'))
            msg = error_details.get('error', {}).get('message', str(e))
            code = error_details.get('error', {}).get('code', 'unknown')
        except:
            msg = str(e)
            code = 'unknown'
        _log(f"HttpError while building client: code={code}, message={msg}")
        raise ValueError(f"Failed to connect to YouTube API (HTTP {code}): {msg}")
    except Exception as e:
        _log(f"Unexpected error building YouTube client: {e}")
        _log(traceback.format_exc())
        raise ValueError(f"Unexpected error initializing YouTube client: {e}")

def get_channel_details(youtube, channel_id):
    """
    Fetches detailed information for a given YouTube Channel ID.
    """
    _log(f"Querying channel details for ID: {channel_id}")
    try:
        request = youtube.channels().list(
            part="snippet,statistics,contentDetails",
            id=channel_id
        )
        response = request.execute()
        _log(f"API response received. Items count: {len(response.get('items', []))}")

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
            _log(f"Channel found: {data['channel_name']} | playlist_id={data['playlist_id']}")
            return data
        else:
            _log(f"Channel ID '{channel_id}' returned no items. Raw response keys: {list(response.keys())}")
            raise ValueError(
                f"No YouTube channel found with ID: '{channel_id}'. "
                f"Please double-check the channel ID — it must start with 'UC' and be exactly 24 characters long."
            )

    except HttpError as e:
        try:
            error_details = json.loads(e.content.decode('utf-8'))
            msg = error_details.get('error', {}).get('message', str(e))
            code = error_details.get('error', {}).get('code', 'unknown')
            errors = error_details.get('error', {}).get('errors', [])
            reason = errors[0].get('reason', '') if errors else ''
        except:
            msg = str(e)
            code = 'unknown'
            reason = ''
        _log(f"HttpError fetching channel details: code={code}, reason={reason}, message={msg}")
        raise ValueError(f"YouTube API Error (HTTP {code}, reason={reason}): {msg}")
    except ValueError as e:
        raise
    except Exception as e:
        _log(f"Unexpected error fetching channel details: {e}")
        _log(traceback.format_exc())
        raise ValueError(f"Unexpected Error fetching channel details: {e}")

def get_video_ids(youtube, playlist_id, limit=100):
    """
    Fetches video IDs from a playlist using pagination up to a limit.
    """
    _log(f"Fetching video IDs from playlist: {playlist_id} (limit={limit})")
    video_ids = []
    next_page_token = None
    try:
        while True:
            page_limit = min(50, limit - len(video_ids)) if limit else 50
            if page_limit <= 0:
                break

            request = youtube.playlistItems().list(
                part="contentDetails",
                playlistId=playlist_id,
                maxResults=page_limit,
                pageToken=next_page_token
            )
            response = request.execute()
            
            for item in response.get("items", []):
                video_ids.append(item["contentDetails"]["videoId"])
                
            if limit and len(video_ids) >= limit:
                break
                
            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break
                
        _log(f"Total video IDs fetched: {len(video_ids)}")
        return video_ids
    except HttpError as e:
        try:
            error_details = json.loads(e.content.decode('utf-8'))
            msg = error_details.get('error', {}).get('message', str(e))
            code = error_details.get('error', {}).get('code', 'unknown')
        except:
            msg = str(e)
            code = 'unknown'
        _log(f"HttpError fetching video IDs: code={code}, message={msg}")
        raise ValueError(f"YouTube API Error fetching videos (HTTP {code}): {msg}")

def get_video_details(youtube, video_ids):
    """
    Fetches details for a list of Video IDs.
    """
    _log(f"Fetching details for {len(video_ids)} video IDs")
    video_data = []
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
            try:
                error_details = json.loads(e.content.decode('utf-8'))
                msg = error_details.get('error', {}).get('message', str(e))
                code = error_details.get('error', {}).get('code', 'unknown')
            except:
                msg = str(e)
                code = 'unknown'
            _log(f"HttpError fetching video details (chunk {i}): code={code}, message={msg}")
            raise ValueError(f"YouTube API Error fetching video details (HTTP {code}): {msg}")
            
    _log(f"Total video details fetched: {len(video_data)}")
    return video_data

def get_video_ids_for_year(youtube, channel_id, year, limit=50):
    """
    Searches for video IDs from a specific channel published in a specific year.
    """
    _log(f"Searching video IDs for channel={channel_id}, year={year}, limit={limit}")
    video_ids = []
    next_page_token = None
    published_after = f"{year}-01-01T00:00:00Z"
    published_before = f"{year}-12-31T23:59:59Z"
    
    try:
        while True:
            page_limit = min(50, limit - len(video_ids)) if limit else 50
            if page_limit <= 0:
                break
                
            request = youtube.search().list(
                part="id",
                channelId=channel_id,
                publishedAfter=published_after,
                publishedBefore=published_before,
                type="video",
                maxResults=page_limit,
                pageToken=next_page_token
            )
            response = request.execute()
            
            for item in response.get("items", []):
                if "videoId" in item.get("id", {}):
                    video_ids.append(item["id"]["videoId"])
                    
            if limit and len(video_ids) >= limit:
                break
                
            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break
                
        _log(f"Total video IDs found for year {year}: {len(video_ids)}")
        return video_ids
    except HttpError as e:
        try:
            error_details = json.loads(e.content.decode('utf-8'))
            msg = error_details.get('error', {}).get('message', str(e))
            code = error_details.get('error', {}).get('code', 'unknown')
        except:
            msg = str(e)
            code = 'unknown'
        _log(f"HttpError searching video IDs for year {year}: code={code}, message={msg}")
        raise ValueError(f"YouTube API Error searching videos for year {year} (HTTP {code}): {msg}")


if __name__ == "__main__":
    # Simple test block
    print("Testing YouTube API Connection...")
    try:
        yt = get_youtube_client()
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

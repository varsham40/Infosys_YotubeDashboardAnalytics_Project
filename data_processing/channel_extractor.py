import os
import sys
import traceback
import pandas as pd

try:
    from .youtube_api import get_youtube_client, get_channel_details
except ImportError:
    from youtube_api import get_youtube_client, get_channel_details

def _log(msg):
    """Unified logger that writes to both stdout and stderr so it appears in Streamlit Cloud logs."""
    print(f"[CHANNEL_EXTRACTOR] {msg}", flush=True)
    print(f"[CHANNEL_EXTRACTOR] {msg}", file=sys.stderr, flush=True)

def extract_channel_data(channel_ids):
    """
    Fetches details for a list of channel IDs and returns a Pandas DataFrame.
    
    Args:
        channel_ids (list): A list of YouTube Channel ID strings.
        
    Returns:
        pd.DataFrame: A DataFrame containing channel details.
    Raises:
        ValueError: With a descriptive message if the API or channel lookup fails.
    """
    _log(f"=== extract_channel_data called with IDs: {channel_ids} ===")
    _log(f"Python version: {sys.version}")
    _log(f"Environment YOUTUBE_API_KEY present: {'YOUTUBE_API_KEY' in os.environ}")
    _log(f"Environment YOUTUBE_API_KEY length: {len(os.environ.get('YOUTUBE_API_KEY', ''))}")

    try:
        _log("Calling get_youtube_client()...")
        youtube = get_youtube_client()
        _log(f"YouTube client obtained: {youtube is not None}")
    except ValueError as e:
        _log(f"FAILED to get YouTube client: {e}")
        raise  # Re-raise to propagate to data_insertion.py with proper message
    except Exception as e:
        _log(f"UNEXPECTED ERROR getting YouTube client: {e}")
        _log(traceback.format_exc())
        raise ValueError(f"Failed to initialize YouTube API client: {e}")

    data_list = []
    
    for channel_id in channel_ids:
        _log(f"--- Fetching channel details for ID: {channel_id} ---")
        try:
            details = get_channel_details(youtube, channel_id)
            _log(f"Channel details fetched successfully: {details.get('channel_name', 'Unknown')}")
            # Add the ID itself to the data dict
            details['channel_id'] = channel_id
            data_list.append(details)
        except ValueError as e:
            _log(f"ValueError for channel {channel_id}: {e}")
            raise  # Propagate clean error message up
        except Exception as e:
            _log(f"Unexpected error for channel {channel_id}: {e}")
            _log(traceback.format_exc())
            raise ValueError(f"Failed to get channel details for {channel_id}: {e}")

    _log(f"Data collection complete. Total channels collected: {len(data_list)}")

    # Convert to DataFrame
    if data_list:
        df = pd.DataFrame(data_list)
        # Reorder columns for better readability
        cols = ['channel_id', 'channel_name', 'subscribers', 'views', 'total_videos', 'playlist_id', 'published_at', 'thumbnail_url', 'description']
        # Only select columns that exist in the dataframe
        df = df[[c for c in cols if c in df.columns]]
        _log(f"DataFrame created with shape: {df.shape}")
        return df
    else:
        _log("No data collected - returning empty DataFrame")
        return pd.DataFrame()

if __name__ == "__main__":
    # Test with valid and invalid IDs
    test_ids = [
        "UC_x5XG1OV2P6uZZ5FSM9Ttw", # Google Developers (Valid)
        "UC0RhatS1pyxInC00YKjjBqQ", # GeeksforGeeks (Valid)
        "INVALID_ID_123"            # Invalid
    ]
    
    print("--- Starting Channel Data Extraction ---")
    df = extract_channel_data(test_ids)
    
    if not df.empty:
        print("\n--- Extraction Complete ---")
        print(df)
        print("\n--- Data Types ---")
        print(df.dtypes)
    else:
        print("No data extracted.")

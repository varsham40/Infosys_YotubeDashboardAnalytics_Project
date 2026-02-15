import pandas as pd
try:
    from .youtube_api import get_youtube_client, get_channel_details
except ImportError:
    from youtube_api import get_youtube_client, get_channel_details

def extract_channel_data(channel_ids):
    """
    Fetches details for a list of channel IDs and returns a Pandas DataFrame.
    
    Args:
        channel_ids (list): A list of YouTube Channel ID strings.
        
    Returns:
        pd.DataFrame: A DataFrame containing channel details.
    """
    youtube = get_youtube_client()
    if not youtube:
        return pd.DataFrame() # Return empty if API connection fails

    data_list = []
    
    for channel_id in channel_ids:
        print(f"Fetching data for: {channel_id}")
        details = get_channel_details(youtube, channel_id)
        
        if details:
            # Add the ID itself to the data dict
            details['channel_id'] = channel_id
            data_list.append(details)
        else:
            print(f"Skipping invalid or private channel: {channel_id}")

    # Convert to DataFrame
    if data_list:
        df = pd.DataFrame(data_list)
        # Reorder columns for better readability
        cols = ['channel_id', 'channel_name', 'subscribers', 'views', 'total_videos', 'playlist_id', 'published_at', 'thumbnail_url', 'description']
        # Only select columns that exist in the dataframe
        df = df[[c for c in cols if c in df.columns]]
        return df
    else:
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

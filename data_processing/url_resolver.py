"""
url_resolver.py
───────────────
Resolves any YouTube channel URL or handle into a canonical UC... Channel ID.

Supported input formats:
  1. Raw Channel ID       → UCsq4gc-EDXqxZZbaRjqFeTw
  2. /channel/ URL        → https://www.youtube.com/channel/UCsq4gc-EDXqxZZbaRjqFeTw
  3. @handle URL          → https://www.youtube.com/@VedantuTelugu
  4. Bare @handle         → @VedantuTelugu
  5. /c/ custom URL       → https://www.youtube.com/c/VedantuTelugu
  6. /user/ legacy URL    → https://www.youtube.com/user/someusername
"""

import re
import sys

def _log(msg):
    """Debug logger visible in Streamlit Cloud logs."""
    print(f"[URL_RESOLVER] {msg}", flush=True)
    print(f"[URL_RESOLVER] {msg}", file=sys.stderr, flush=True)


def _clean_input(user_input: str) -> str:
    """Strip whitespace, trailing slashes, and query params."""
    cleaned = user_input.strip().rstrip("/")
    # Remove query params like ?sub_confirmation=1
    cleaned = re.split(r"\?", cleaned)[0]
    return cleaned


def _is_channel_id(text: str) -> bool:
    """Returns True if text is already a UC... Channel ID."""
    return bool(re.match(r"^UC[a-zA-Z0-9_-]{22}$", text))


def _extract_channel_id_from_url(url: str):
    """
    Directly extracts UC... Channel ID from /channel/ URLs.
    Returns the ID string or None.
    """
    match = re.search(r"/channel/(UC[a-zA-Z0-9_-]{22})", url)
    if match:
        return match.group(1)
    return None


def _extract_handle_from_url(url: str):
    """
    Extracts the handle name from @handle URLs.
    e.g. https://www.youtube.com/@VedantuTelugu  →  VedantuTelugu
    Also handles bare @VedantuTelugu input.
    Returns handle string (without @) or None.
    """
    # Match bare @handle
    bare = re.match(r"^@([a-zA-Z0-9._-]+)$", url)
    if bare:
        return bare.group(1)
    # Match URL with @handle
    url_match = re.search(r"/@([a-zA-Z0-9._-]+)", url)
    if url_match:
        return url_match.group(1)
    return None


def _extract_custom_name_from_url(url: str):
    """
    Extracts custom name from /c/ URLs.
    e.g. https://www.youtube.com/c/VedantuTelugu  →  VedantuTelugu
    Returns name string or None.
    """
    match = re.search(r"/c/([a-zA-Z0-9._-]+)", url)
    if match:
        return match.group(1)
    return None


def _extract_username_from_url(url: str):
    """
    Extracts username from legacy /user/ URLs.
    e.g. https://www.youtube.com/user/someusername  →  someusername
    Returns username string or None.
    """
    match = re.search(r"/user/([a-zA-Z0-9._-]+)", url)
    if match:
        return match.group(1)
    return None


def _resolve_by_handle(handle: str, youtube) -> str:
    """
    Resolves a @handle to a Channel ID using the YouTube API.
    Uses channels.list with forHandle parameter.
    """
    _log(f"Resolving by handle: @{handle}")
    request = youtube.channels().list(
        part="id",
        forHandle=handle
    )
    response = request.execute()
    items = response.get("items", [])
    if items:
        channel_id = items[0]["id"]
        _log(f"Resolved @{handle} → {channel_id}")
        return channel_id
    raise ValueError(
        f"Could not find a YouTube channel for handle '@{handle}'. "
        f"Please verify the handle is correct."
    )


def _resolve_by_username(username: str, youtube) -> str:
    """
    Resolves a legacy username to a Channel ID using the YouTube API.
    Uses channels.list with forUsername parameter.
    """
    _log(f"Resolving by username: {username}")
    request = youtube.channels().list(
        part="id",
        forUsername=username
    )
    response = request.execute()
    items = response.get("items", [])
    if items:
        channel_id = items[0]["id"]
        _log(f"Resolved username '{username}' → {channel_id}")
        return channel_id
    raise ValueError(
        f"Could not find a YouTube channel for username '{username}'. "
        f"Try using the channel's URL or @handle instead."
    )


def _resolve_by_search(name: str, youtube) -> str:
    """
    Resolves a /c/ custom channel name using YouTube Search API.
    This is a fallback since /c/ URLs are deprecated.
    """
    _log(f"Resolving by search (custom name): {name}")
    request = youtube.search().list(
        part="id,snippet",
        q=name,
        type="channel",
        maxResults=1
    )
    response = request.execute()
    items = response.get("items", [])
    if items:
        channel_id = items[0]["id"]["channelId"]
        found_name = items[0]["snippet"]["channelTitle"]
        _log(f"Resolved '{name}' via search → {channel_id} ({found_name})")
        return channel_id
    raise ValueError(
        f"Could not find a YouTube channel for '{name}'. "
        f"Try using the channel's direct URL or @handle instead."
    )


def resolve_channel_input(user_input: str, youtube) -> str:
    """
    Main entry point. Takes any user input (URL or Channel ID) and
    returns a canonical UC... Channel ID.

    Args:
        user_input: Any YouTube channel URL, @handle, or Channel ID.
        youtube:    An authenticated YouTube API client object.

    Returns:
        str: A canonical YouTube Channel ID starting with 'UC'.

    Raises:
        ValueError: With a descriptive message if resolution fails.
    """
    text = _clean_input(user_input)
    _log(f"Resolving input: '{text}'")

    # --- Case 1: Already a raw Channel ID ---
    if _is_channel_id(text):
        _log(f"Input is already a valid Channel ID: {text}")
        return text

    # --- Case 2: /channel/UCxxxx URL → extract directly ---
    channel_id = _extract_channel_id_from_url(text)
    if channel_id:
        _log(f"Extracted Channel ID from /channel/ URL: {channel_id}")
        return channel_id

    # --- Case 3: @handle URL or bare @handle ---
    handle = _extract_handle_from_url(text)
    if handle:
        return _resolve_by_handle(handle, youtube)

    # --- Case 4: /user/ legacy URL ---
    username = _extract_username_from_url(text)
    if username:
        return _resolve_by_username(username, youtube)

    # --- Case 5: /c/ custom URL (deprecated, use search fallback) ---
    custom_name = _extract_custom_name_from_url(text)
    if custom_name:
        return _resolve_by_search(custom_name, youtube)

    # --- Case 6: Unknown format ---
    _log(f"Could not parse input format: '{text}'")
    raise ValueError(
        f"Unrecognized input format: '{text}'. "
        f"Please paste a YouTube channel URL (e.g. youtube.com/@ChannelName) "
        f"or a Channel ID (e.g. UCxxxxxxxxxxxxxxxxxxxxxxxx)."
    )


if __name__ == "__main__":
    """Quick test for all URL formats."""
    import os
    from dotenv import load_dotenv
    from googleapiclient.discovery import build

    load_dotenv()
    api_key = os.getenv("YOUTUBE_API_KEY")
    youtube = build("youtube", "v3", developerKey=api_key, static_discovery=True)

    test_cases = [
        # (input, expected_channel_id)
        ("UCsq4gc-EDXqxZZbaRjqFeTw",                              "UCsq4gc-EDXqxZZbaRjqFeTw"),   # Raw ID
        ("https://www.youtube.com/channel/UCsq4gc-EDXqxZZbaRjqFeTw", "UCsq4gc-EDXqxZZbaRjqFeTw"),# /channel/ URL
        ("https://www.youtube.com/@VedantuTelugu",                 "UCsq4gc-EDXqxZZbaRjqFeTw"),   # @handle URL
        ("@VedantuTelugu",                                         "UCsq4gc-EDXqxZZbaRjqFeTw"),   # Bare @handle
    ]

    print("\n=== URL Resolver Tests ===\n")
    for i, (inp, expected) in enumerate(test_cases, 1):
        try:
            result = resolve_channel_input(inp, youtube)
            status = "✅ PASS" if result == expected else f"⚠️ GOT {result}"
            print(f"Test {i}: {status} | Input: {inp}")
        except ValueError as e:
            print(f"Test {i}: ❌ ERROR | Input: {inp} | Error: {e}")
    print()

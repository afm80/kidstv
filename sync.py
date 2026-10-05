import json
import requests
import re
import os
import time
from typing import List, Dict, Optional

YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY')
FIREBASE_DB_URL = os.environ.get('FIREBASE_DB_URL')

if not YOUTUBE_API_KEY:
    raise Exception("YOUTUBE_API_KEY not found in environment")

if not FIREBASE_DB_URL:
    FIREBASE_CONFIG_JSON = os.environ.get('FIREBASE_CONFIG')
    if FIREBASE_CONFIG_JSON:
        try:
            firebase_config = json.loads(FIREBASE_CONFIG_JSON)
            FIREBASE_DB_URL = firebase_config.get('databaseURL')
        except Exception as e:
            print(f"[ERROR] parsing FIREBASE_CONFIG: {e}")

    if not FIREBASE_DB_URL:
        raise Exception("FIREBASE_DB_URL not found in environment")

FIREBASE_DB_URL = FIREBASE_DB_URL.rstrip('/')

with open('channels.txt', 'r', encoding='utf-8') as f:
    CHANNELS = [line.strip() for line in f if line.strip()]

session = requests.Session()


def get_video_id(url: str) -> Optional[str]:
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/|youtube\.com\/v\/|youtube\.com\/live\/)([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def get_channel_handle(url: str) -> Optional[str]:
    patterns = [
        (r'youtube\.com\/channel\/([a-zA-Z0-9_-]+)', 'id'),
        (r'youtube\.com\/c\/([a-zA-Z0-9_-]+)', 'username'),
        (r'youtube\.com\/@([a-zA-Z0-9_.-]+)', 'handle'),
        (r'youtube\.com\/user\/([a-zA-Z0-9_-]+)', 'username'),
    ]
    for pattern, kind in patterns:
        match = re.search(pattern, url)
        if match:
            return f"{kind}:{match.group(1)}"
    return None


def resolve_channel_id(value: str) -> Optional[str]:
    kind, val = value.split(':', 1)
    if kind == 'id':
        return val
    param_map = {'handle': 'forHandle', 'username': 'forUsername'}
    param = param_map.get(kind)
    if not param:
        return None
    url = f"https://www.googleapis.com/youtube/v3/channels?part=id&{param}={val}&key={YOUTUBE_API_KEY}"
    try:
        r = session.get(url, timeout=15)
        if r.status_code == 200:
            items = r.json().get('items', [])
            if items:
                return items[0]['id']
            print(f"[WARN] channel not found: {val}")
        else:
            print(f"[ERROR] resolve_channel_id({val}): {r.status_code} {r.text[:200]}")
    except requests.RequestException as e:
        print(f"[ERROR] resolve_channel_id({val}): {e}")
    return None


def get_uploads_playlist_id(channel_id: str) -> Optional[str]:
    url = f"https://www.googleapis.com/youtube/v3/channels?part=contentDetails&id={channel_id}&key={YOUTUBE_API_KEY}"
    try:
        r = session.get(url, timeout=15)
        if r.status_code == 200:
            items = r.json().get('items', [])
            if items:
                return items[0]['contentDetails']['relatedPlaylists']['uploads']
        else:
            print(f"[ERROR] get_uploads_playlist_id({channel_id}): {r.status_code} {r.text[:200]}")
    except requests.RequestException as e:
        print(f"[ERROR] get_uploads_playlist_id({channel_id}): {e}")
    return None


def get_playlist_videos(playlist_id: str, max_results: int = 10) -> List[str]:
    url = (
        f"https://www.googleapis.com/youtube/v3/playlistItems"
        f"?part=contentDetails&playlistId={playlist_id}"
        f"&maxResults={max_results}&key={YOUTUBE_API_KEY}"
    )
    try:
        r = session.get(url, timeout=15)
        if r.status_code == 200:
            return [item['contentDetails']['videoId'] for item in r.json().get('items', [])]
        print(f"[ERROR] get_playlist_videos({playlist_id}): {r.status_code} {r.text[:200]}")
    except requests.RequestException as e:
        print(f"[ERROR] get_playlist_videos({playlist_id}): {e}")
    return []


def get_videos_details(video_ids: List[str]) -> Dict[str, Dict]:
    """Fetch title + liveBroadcastContent for up to 50 videos per call."""
    result: Dict[str, Dict] = {}
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i + 50]
        url = (
            f"https://www.googleapis.com/youtube/v3/videos"
            f"?part=snippet&id={','.join(chunk)}&key={YOUTUBE_API_KEY}"
        )
        try:
            r = session.get(url, timeout=15)
            if r.status_code != 200:
                print(f"[ERROR] get_videos_details: {r.status_code} {r.text[:200]}")
                continue
            for item in r.json().get('items', []):
                vid = item['id']
                snippet = item['snippet']
                result[vid] = {
                    'title': snippet.get('title', 'Video from list'),
                    'isLive': snippet.get('liveBroadcastContent') == 'live',
                }
        except requests.RequestException as e:
            print(f"[ERROR] get_videos_details: {e}")
    return result


def get_existing_videos() -> Dict:
    url = f"{FIREBASE_DB_URL}/videos.json"
    try:
        r = session.get(url, timeout=15)
        if r.status_code == 200:
            return r.json() or {}
        print(f"[ERROR] get_existing_videos: {r.status_code} {r.text[:200]}")
    except requests.RequestException as e:
        print(f"[ERROR] get_existing_videos: {e}")
    return {}


def add_video_to_firebase(video_id: str, title: str, category: str):
    url = f"{FIREBASE_DB_URL}/videos/{video_id}.json"
    data = {
        'videoId': video_id,
        'categoryId': category,
        'title': title,
        'createdAt': int(time.time() * 1000),
    }
    try:
        r = session.put(url, json=data, timeout=15)
        if r.status_code not in (200, 201):
            print(f"[ERROR] add_video_to_firebase({video_id}): {r.status_code} {r.text[:200]}")
    except requests.RequestException as e:
        print(f"[ERROR] add_video_to_firebase({video_id}): {e}")


def delete_video_from_firebase(video_id: str):
    url = f"{FIREBASE_DB_URL}/videos/{video_id}.json"
    try:
        session.delete(url, timeout=15)
    except requests.RequestException as e:
        print(f"[ERROR] delete_video_from_firebase({video_id}): {e}")


def sync():
    print("Starting sync...")

    existing_videos = get_existing_videos()
    existing_ids = set(existing_videos.keys())

    # Collect video IDs
    manual_video_ids: List[str] = []
    channel_ids = set()

    for url in CHANNELS:
        vid = get_video_id(url)
        if vid:
            manual_video_ids.append(vid)
            continue
        handle = get_channel_handle(url)
        if handle:
            cid = resolve_channel_id(handle)
            if cid:
                channel_ids.add(cid)
            else:
                print(f"[WARN] could not resolve channel: {url}")
        else:
            print(f"[WARN] unrecognized url: {url}")

    # Gather candidate video IDs
    candidates: List[str] = list(manual_video_ids)
    for channel_id in channel_ids:
        playlist_id = get_uploads_playlist_id(channel_id)
        if not playlist_id:
            continue
        candidates.extend(get_playlist_videos(playlist_id, max_results=10))

    # Dedupe while preserving order
    seen = set()
    unique_candidates = []
    for vid in candidates:
        if vid not in seen:
            seen.add(vid)
            unique_candidates.append(vid)

    if not unique_candidates:
        print("No candidate videos found.")
        return

    # Fetch details (title + isLive) in bulk
    details = get_videos_details(unique_candidates)

    added_count = 0
    for vid in unique_candidates:
        info = details.get(vid)
        if not info:
            print(f"[WARN] no details for {vid}")
            continue

        title = info['title']
        category = 'live' if info['isLive'] else 'videos'

        if vid in existing_ids:
            # If category changed, update it
            old_cat = existing_videos.get(vid, {}).get('categoryId')
            if old_cat != category:
                add_video_to_firebase(vid, title, category)
                print(f"Updated category: {title} -> {category}")
            else:
                print(f"Skipped duplicate: {title}")
            continue

        add_video_to_firebase(vid, title, category)
        added_count += 1
        print(f"Added: {title} ({category})")

    print(f"Sync completed! Added: {added_count}")


if __name__ == "__main__":
    sync()

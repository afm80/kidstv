import json
import requests
import re
import os
import time
from typing import List, Dict, Optional, Set

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
            print(f"[ERROR] resolve_channel_id({val}): {r.status_code}")
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
    except requests.RequestException as e:
        print(f"[ERROR] get_uploads_playlist_id: {e}")
    return None


def get_playlist_videos(playlist_id: str, max_results: int = 10) -> List[Dict]:
    """Returns list of {videoId, title} from playlistItems (works without videos.list)."""
    url = (
        f"https://www.googleapis.com/youtube/v3/playlistItems"
        f"?part=snippet,contentDetails&playlistId={playlist_id}"
        f"&maxResults={max_results}&key={YOUTUBE_API_KEY}"
    )
    try:
        r = session.get(url, timeout=15)
        if r.status_code == 200:
            out = []
            for item in r.json().get('items', []):
                out.append({
                    'videoId': item['contentDetails']['videoId'],
                    'title': item['snippet'].get('title', 'Video from list'),
                })
            return out
        print(f"[ERROR] get_playlist_videos: {r.status_code} {r.text[:200]}")
    except requests.RequestException as e:
        print(f"[ERROR] get_playlist_videos: {e}")
    return []


def get_live_video_ids(channel_id: str) -> Set[str]:
    """Returns set of currently-live video IDs for a channel using search.list."""
    url = (
        f"https://www.googleapis.com/youtube/v3/search"
        f"?part=id&channelId={channel_id}&eventType=live&type=video"
        f"&key={YOUTUBE_API_KEY}"
    )
    try:
        r = session.get(url, timeout=15)
        if r.status_code == 200:
            return {item['id']['videoId'] for item in r.json().get('items', [])}
        print(f"[ERROR] get_live_video_ids({channel_id}): {r.status_code} {r.text[:200]}")
    except requests.RequestException as e:
        print(f"[ERROR] get_live_video_ids: {e}")
    return set()


def get_existing_videos() -> Dict:
    url = f"{FIREBASE_DB_URL}/videos.json"
    try:
        r = session.get(url, timeout=15)
        if r.status_code == 200:
            return r.json() or {}
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
        print(f"[ERROR] delete_video_from_firebase: {e}")


def sync():
    print("Starting sync...")

    existing_videos = get_existing_videos()
    existing_ids = set(existing_videos.keys())

    manual_videos: List[Dict] = []       # {videoId, title}
    channel_ids = set()

    # Step 1: parse channels.txt
    for url in CHANNELS:
        vid = get_video_id(url)
        if vid:
            # We'll fetch its title via playlist trick? No - store placeholder, resolve later
            manual_videos.append({'videoId': vid, 'title': None})
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

    # Step 2: collect videos from channels
    channel_videos: List[Dict] = []       # {videoId, title, isLive}
    for channel_id in channel_ids:
        # Live streams
        live_ids = get_live_video_ids(channel_id)

        # Recent uploads
        playlist_id = get_uploads_playlist_id(channel_id)
        if not playlist_id:
            continue
        uploads = get_playlist_videos(playlist_id, max_results=10)

        for v in uploads:
            v['isLive'] = v['videoId'] in live_ids
            channel_videos.append(v)

        # Add live videos that are NOT in uploads (rare but possible)
        upload_ids = {v['videoId'] for v in uploads}
        for lid in live_ids - upload_ids:
            channel_videos.append({'videoId': lid, 'title': 'Live stream', 'isLive': True})

    # Step 3: process channel videos
    added = 0
    for v in channel_videos:
        vid = v['videoId']
        title = v['title'] or 'Video from list'
        category = 'live' if v.get('isLive') else 'videos'

        if vid in existing_ids:
            old_cat = existing_videos.get(vid, {}).get('categoryId')
            if old_cat != category:
                add_video_to_firebase(vid, title, category)
                print(f"Updated: {title} -> {category}")
            continue

        add_video_to_firebase(vid, title, category)
        added += 1
        print(f"Added: {title} ({category})")

    print(f"Sync completed! Added: {added}")


if __name__ == "__main__":
    sync()

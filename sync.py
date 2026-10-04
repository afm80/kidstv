import json
import requests
import re
from typing import List, Dict, Optional

# Load config
with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

FIREBASE_DB_URL = config['firebase']['databaseURL']
YOUTUBE_API_KEY = config['youtube']['apiKey']

# Load channels
with open('channels.txt', 'r', encoding='utf-8') as f:
    CHANNELS = [line.strip() for line in f if line.strip()]

def get_video_id(url: str) -> Optional[str]:
    """Extract video ID from YouTube URL"""
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/|youtube\.com\/v\/)([a-zA-Z0-9_-]{11})',
        r'(?:youtube\.com\/live\/)([a-zA-Z0-9_-]{11})'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def get_channel_id(url: str) -> Optional[str]:
    """Extract channel ID from YouTube URL"""
    patterns = [
        r'youtube\.com\/channel\/([a-zA-Z0-9_-]+)',
        r'youtube\.com\/c\/([a-zA-Z0-9_-]+)',
        r'youtube\.com\/@([a-zA-Z0-9_-]+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def check_video_exists(video_id: str) -> bool:
    """Check if video exists on YouTube"""
    url = f"https://www.googleapis.com/youtube/v3/videos?part=status&id={video_id}&key={YOUTUBE_API_KEY}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if data.get('items'):
                return data['items'][0]['status']['uploadStatus'] == 'uploaded'
        return False
    except:
        return False

def get_video_title(video_id: str) -> Optional[str]:
    """Get video title from YouTube"""
    url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet&id={video_id}&key={YOUTUBE_API_KEY}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if data.get('items'):
                return data['items'][0]['snippet']['title']
    except:
        pass
    return None

def get_channel_videos(channel_id: str, max_results: int = 10) -> List[Dict]:
    """Get videos from a channel"""
    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&channelId={channel_id}&maxResults={max_results}&order=date&type=video&key={YOUTUBE_API_KEY}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            videos = []
            for item in data.get('items', []):
                video_id = item['id']['videoId']
                title = item['snippet']['title']
                videos.append({'videoId': video_id, 'title': title, 'isLive': False})
            return videos
    except:
        pass
    return []

def get_live_streams(channel_id: str) -> List[Dict]:
    """Get live streams from a channel"""
    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&channelId={channel_id}&eventType=live&type=video&key={YOUTUBE_API_KEY}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            streams = []
            for item in data.get('items', []):
                video_id = item['id']['videoId']
                title = item['snippet']['title']
                streams.append({'videoId': video_id, 'title': title, 'isLive': True})
            return streams
    except:
        pass
    return []

def get_existing_videos() -> Dict:
    """Get existing videos from Firebase"""
    url = f"{FIREBASE_DB_URL}/videos.json"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return response.json() or {}
    except:
        pass
    return {}

def add_video_to_firebase(video_id: str, title: str, category: str):
    """Add video to Firebase"""
    url = f"{FIREBASE_DB_URL}/videos/{video_id}.json"
    import time
    data = {
        'videoId': video_id,
        'categoryId': category,
        'title': title,
        'createdAt': int(time.time() * 1000)
    }
    try:
        requests.patch(url, json=data)
    except:
        pass

def delete_video_from_firebase(video_id: str):
    """Delete video from Firebase"""
    url = f"{FIREBASE_DB_URL}/videos/{video_id}.json"
    try:
        requests.delete(url)
    except:
        pass

def sync():
    """Main sync function"""
    print("Starting sync...")
    
    # Get existing videos
    existing_videos = get_existing_videos()
    existing_ids = set(existing_videos.keys())
    
    # Collect videos from channels.txt (handle both video URLs and channel URLs)
    all_videos = []
    channel_ids_from_videos = set()
    
    for url in CHANNELS:
        video_id = get_video_id(url)
        if video_id:
            # It's a video URL
            title = get_video_title(video_id) or 'Video from list'
            all_videos.append({'videoId': video_id, 'title': title, 'url': url, 'isLive': False})
        else:
            channel_id = get_channel_id(url)
            if channel_id:
                # It's a channel URL
                channel_ids_from_videos.add(channel_id)
    
    # Sync videos from channels
    for channel_id in channel_ids_from_videos:
        # Get regular videos
        videos = get_channel_videos(channel_id, max_results=5)
        all_videos.extend(videos)
        
        # Get live streams
        streams = get_live_streams(channel_id)
        all_videos.extend(streams)
    
    # Add new videos
    for video in all_videos:
        video_id = video['videoId']
        if video_id not in existing_ids:
            # Determine category (live vs video)
            is_live = video.get('isLive', False)
            category = 'live' if is_live else 'videos'
            add_video_to_firebase(video_id, video['title'], category)
            print(f"Added: {video['title']} ({category})")
    
    # Check and remove deleted videos
    for video_id in existing_ids:
        if not check_video_exists(video_id):
            delete_video_from_firebase(video_id)
            print(f"Deleted: {video_id}")
    
    print("Sync completed!")

if __name__ == "__main__":
    sync()

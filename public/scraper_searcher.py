from shared import YouTubeSearcherBase
import yt_dlp
import re
import requests
from urllib.parse import urlparse, parse_qs
import time
import os

class ScraperYouTubeSearcher(YouTubeSearcherBase):
    def __init__(self):
        super().__init__()
        self.current_handle = None
        self._ensure_cookie_file()
        self.ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'cookiefile': 'cookies.txt',
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
            },
            'extractor_args': {
                'youtube': {
                    'player_client': ['android'],
                    'max_comments': [0],
                }
            }
        }
        # Remove any proxy settings that might have been added

    def _ensure_cookie_file(self):
        """Create an empty cookie file if it doesn't exist"""
        if not os.path.exists('cookies.txt'):
            with open('cookies.txt', 'w') as f:
                f.write('')

    def search_channel(self, handle):
        if not handle.startswith('@'):
            handle = '@' + handle
            
        try:
            # Store the handle without @ for later use
            self.current_handle = handle[1:]
            
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                channel_url = f'https://www.youtube.com/{handle}'
                channel_info = ydl.extract_info(channel_url, download=False)
                return channel_info.get('id') or channel_info.get('channel_id')
        except Exception as e:
            raise ValueError(f"No channel found: {str(e)}")

    def get_videos_iterator(self, channel_id):
        cached_videos = self.cache.get_channel_videos(channel_id)
        if cached_videos:
            for video in cached_videos:
                yield video
            return

        videos = []
        try:
            ydl_opts = {
                **self.ydl_opts,
                'extract_flat': 'in_playlist',
                'playlistreverse': False,
                'playlistend': 1000,
                'sleep_interval': 1,
                'max_sleep_interval': 5,
                'retries': 3,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                url = f'https://www.youtube.com/@{self.current_handle}/videos'
                print(f"Fetching videos from: {url}")  # Debug line
                
                try:
                    playlist = ydl.extract_info(url, download=False)
                    if playlist and 'entries' in playlist:
                        for entry in playlist['entries']:
                            if entry:
                                video = {
                                    'id': entry['id'],
                                    'title': entry['title'],
                                    'published_at': entry.get('upload_date', '')
                                }
                                videos.append(video)
                                yield video
                                
                        self.cache.save_channel_videos(channel_id, videos)
                    else:
                        print("No entries found in playlist")  # Debug line
                        
                except Exception as e:
                    print(f"Error during video extraction: {str(e)}")  # Debug line
                    raise

        except Exception as e:
            print(f"Error fetching videos: {str(e)}")

    def _get_transcript(self, video_id):
        try:
            ydl_opts = {
                **self.ydl_opts,
                'skip_download': True,
                'writeautomaticsub': True,
                'writesubtitles': True,
                'subtitlesformat': 'srv1',
                'subtitleslangs': ['en', 'en-GB', 'en-US'],
                'retries': 3,
                'quiet': True
            }
            
            url = f'https://www.youtube.com/watch?v={video_id}'
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                # Try automatic captions first
                if info.get('automatic_captions'):
                    for lang in ['en', 'en-GB', 'en-US']:
                        if lang in info['automatic_captions']:
                            formats = info['automatic_captions'][lang]
                            for fmt in formats:
                                if fmt.get('ext') in ['srv1', 'srv2', 'srv3', 'vtt']:
                                    transcript = self._download_and_parse_transcript(fmt['url'])
                                    if transcript:
                                        return transcript
                            # Break after trying all formats for the first available language
                            break

                # Try manual subtitles only if we haven't found automatic ones
                if 'subtitles' in info:
                    for lang in ['en', 'en-GB', 'en-US']:
                        if lang in info['subtitles']:
                            formats = info['subtitles'][lang]
                            for fmt in formats:
                                if fmt.get('ext') in ['srv1', 'srv2', 'srv3', 'vtt']:
                                    transcript = self._download_and_parse_transcript(fmt['url'])
                                    if transcript:
                                        return transcript
                            # Break after trying all formats for the first available language
                            break
                
                return None
                
        except Exception as e:
            print(f"Error getting transcript for video {video_id}: {str(e)}")
            return None

    def _download_and_parse_transcript(self, url):
        try:
            response = requests.get(url)
            content = response.text
            
            # Parse VTT/SRT format
            transcript = []
            seen_texts = set()  # Track unique texts
            current_text = []
            current_start = None
            
            for line in content.split('\n'):
                # Check for timestamp line
                timestamp_match = re.search(r'(\d{2}:\d{2}:\d{2}[,.]\d{3})', line)
                if timestamp_match:
                    if current_text and current_start is not None:
                        text = ' '.join(current_text).strip()
                        # Only add if we haven't seen this text before
                        if text not in seen_texts:
                            transcript.append({
                                'text': text,
                                'start': current_start
                            })
                            seen_texts.add(text)
                    current_text = []
                    time_str = timestamp_match.group(1).replace(',', '.')
                    h, m, s = map(float, time_str.split(':'))
                    current_start = h * 3600 + m * 60 + s
                elif line.strip() and not line[0].isdigit() and '-->' not in line:
                    current_text.append(line.strip())
            
            # Add the last entry if it's unique
            if current_text and current_start is not None:
                text = ' '.join(current_text).strip()
                if text not in seen_texts:
                    transcript.append({
                        'text': text,
                        'start': current_start
                    })
            
            return transcript
            
        except Exception as e:
            print(f"Error parsing transcript: {str(e)}")
            return None
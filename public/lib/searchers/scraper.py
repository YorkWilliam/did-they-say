from lib.searchers.base import BaseSearcher
import yt_dlp
import json
import os
import requests
from xml.etree import ElementTree
import re
from typing import List, Dict

class ScraperSearcher(BaseSearcher):
    def __init__(self):
        super().__init__()
        self._ensure_cookie_file()
        self.ydl_opts = {
            'quiet': True,
            'retries': 3,
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
    
    def _ensure_cookie_file(self):
        if not os.path.exists('cookies.txt'):
            with open('cookies.txt', 'w') as f:
                f.write('# Netscape HTTP Cookie File')

    def search_channel(self, handle):
        clean_handle = handle[1:]

        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                channel_url = f'https://www.youtube.com/{clean_handle}'
                channel_info = ydl.extract_info(channel_url, download=False)
                channel_id = channel_info.get('channel_id')
        except Exception as e:
            raise ValueError(f"No channel found: {str(e)}")
        
        try:
            ydl_opts = {
                **self.ydl_opts,
                'extract_flat': 'in_playlist',
                'playlistreverse': False,
                'playlistend': 1000,
                'sleep_interval': 1,
                'max_sleep_interval': 5,
            }
            videos_url = f'https://www.youtube.com/{clean_handle}/videos'
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                playlist = ydl.extract_info(videos_url, download=False)
                if playlist and playlist.get('entries'):
                    videos = [entry['id'] for entry in playlist['entries']]
                else:
                    videos = []
        except Exception as e:
            raise ValueError(f"No videos found: {str(e)}")
        
        return {
            'handle': handle,
            'channel_id': channel_id,
            'video_list': videos
        }
        

    def search_video(self, handle, video_id):
        try:
            ydl_opts = {
                **self.ydl_opts,
                'skip_download': True,
                'writesubtitles': True,
                'writeautomaticsub': True,
                'subtitleslangs': self.language_codes,
                'subtitlesformat': 'srt',
            }
            video_url = f'https://www.youtube.com/watch?v={video_id}'
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                video_info = ydl.extract_info(video_url, download=False)
        except Exception as e:
            raise ValueError(f"No video found: {str(e)}")
        
        title = ""
        if video_info.get('title'):
            title = video_info['title']
        
        published_at = 0
        if video_info.get('upload_date'):
            upload_date = video_info['upload_date']
            published_at = self._parse_date(upload_date)
        
        transcript = []
        for src in ['subtitles', 'automatic_captions']:
            if video_info.get(src):
                for lang in self.language_codes:
                    if lang in video_info[src]:
                        for fmt in video_info[src][lang]:
                            transcript = self._download_and_parse_transcript(fmt['url'], fmt['ext'])
                            if transcript:
                                return {
                                    'video_id': video_id,
                                    'channel': handle,
                                    'title': title,
                                    'published_at': published_at,
                                    'transcript': transcript
                                }
        
        return None
    
    def _parse_date(self, date_str):
        if date_str:
            year = date_str[0:4]
            month = date_str[4:6]
            day = date_str[6:8]
            return f"{year}-{month}-{day}"
        return None

    def _download_and_parse_transcript(self, url, fmt):
        parser = SubtitleParser()

        try:
            response = requests.get(url)
            transcript = parser.parse_transcript(response.text, fmt)
            return transcript
                
        except requests.RequestException as e:
            print(f"Error downloading transcript: {str(e)}")
            # print(response.text[:100])
            return None
        except Exception as e:
            print(f"Error parsing transcript: {str(e)}")
            print(fmt)
            print(response.text[:300])      
            return None

class SubtitleParser:
    def parse_transcript(self, content: str, format_type: str) -> List[Dict]:
        """Parse transcript with specified format"""
        parsers = {
            'ttml': self._parse_ttml,
            'json3': self._parse_json3,
            'srv1': self._parse_srv1,
            'srv2': self._parse_srv2,
            'srv3': self._parse_srv3,
            'vtt': self._parse_vtt
        }
        
        parser = parsers.get(format_type)
        if not parser:
            raise ValueError(f"Unsupported format: {format_type}")
        
        return parser(content)

    def _parse_time(self, time_str: str) -> float:
        """Convert timestamp format HH:MM:SS.mmm to seconds"""
        h, m, s = time_str.split(':')
        return round(float(h) * 3600 + float(m) * 60 + float(s), 3)

    def _parse_json3(self, content: str) -> List[Dict]:
        """Parse JSON3 format (YouTube format)"""
        data = json.loads(content)
        transcript = []
        
        for event in data.get('events', []):
            if 'segs' in event and 'tStartMs' in event:
                text = ' '.join(seg.get('utf8', '') for seg in event['segs']).strip()
                if text:
                    transcript.append({
                        'start': round(event['tStartMs'] / 1000, 3),
                        'text': text
                    })
        
        return transcript

    def _parse_srv1(self, content: str) -> List[Dict]:
        """Parse SRV1 format (supports both JSON and XML)"""
        if content.startswith('{'):
            # JSON format
            data = json.loads(content)
            transcript = []
            for caption in data.get('captions', []):
                if 'startTime' in caption and 'text' in caption:
                    transcript.append({
                        'start': round(float(caption['startTime']), 3),
                        'text': caption['text'].strip()
                    })
            return transcript
        else:
            # XML format
            root = ElementTree.fromstring(content)
            transcript = []
            for text in root.findall('.//text'):
                start = text.get('start')
                content = text.text
                if start and content:
                    transcript.append({
                        'start': round(float(start), 3),
                        'text': content.strip()
                    })
            return transcript

    def _parse_srv2(self, content: str) -> List[Dict]:
        """Parse SRV2 format (supports both JSON and XML)"""
        if content.startswith('{'):
            # JSON format
            data = json.loads(content)
            transcript = []
            for event in data.get('events', []):
                if 'ts' in event and 'text' in event:
                    transcript.append({
                        'start': round(float(event['ts']), 3),
                        'text': event['text'].strip()
                    })
            return transcript
        else:
            # XML format
            return self._parse_srv1(content)  # XML format is same as SRV1

    def _parse_srv3(self, content: str) -> List[Dict]:
        """Parse SRV3 format (same as SRV2)"""
        return self._parse_srv2(content)

    def _parse_ttml(self, content: str) -> List[Dict]:
        """Parse TTML format"""
        root = ElementTree.fromstring(content)
        transcript = []
        
        for p in root.findall(".//{*}body/{*}div/{*}p"):
            start_time = p.get('begin')
            text = p.text.strip() if p.text else ""
            
            if start_time and text:
                start_seconds = self._parse_time(start_time)
                transcript.append({
                    'start': start_seconds,
                    'text': text
                })
        
        return transcript
    
    def _parse_vtt(self, content: str) -> List[Dict]:
        """Parse WebVTT format"""
        transcript = []
        lines = content.split('\n')
        
        # Skip WebVTT header
        i = 0
        while i < len(lines) and not lines[i].strip().startswith('0'):
            i += 1
        
        while i < len(lines):
            # Skip empty lines
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i >= len(lines):
                break
                
            # Skip sequence number if present
            if lines[i].strip().isdigit():
                i += 1
            if i >= len(lines):
                break
                
            # Parse timestamp line
            if '-->' in lines[i]:
                time_parts = lines[i].split('-->')[0].strip().split(':')
                if len(time_parts) == 2:
                    time_parts.insert(0, '00')  # Add hours if not present
                
                start_time = ':'.join(time_parts)
                start_seconds = self._parse_time(start_time)
                
                # Get text (can be multiple lines)
                i += 1
                text_lines = []
                while i < len(lines) and lines[i].strip():
                    text_lines.append(lines[i].strip())
                    i += 1
                
                if text_lines:
                    transcript.append({
                        'start': start_seconds,
                        'text': ' '.join(text_lines)
                    })
            i += 1
        
        return transcript
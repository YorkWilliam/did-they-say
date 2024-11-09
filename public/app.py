from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from flask import Flask, render_template, request, jsonify, Response
import pickle
import os
import json
import time

app = Flask(__name__)  # Add this back

CACHE_DIR = 'cache'
class TranscriptCache:
    def __init__(self):
        self.cache_dir = CACHE_DIR
        os.makedirs(self.cache_dir, exist_ok=True)
        
    def _get_cache_path(self, channel_id):
        return os.path.join(self.cache_dir, f'{channel_id}.json')
        
    def get_channel_cache(self, channel_id):
        cache_path = self._get_cache_path(channel_id)
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                return cache_data
            except:
                return {'videos': {}}
        return {'videos': {}}
        
    def save_channel_cache(self, channel_id, cache_data):
        cache_path = self._get_cache_path(channel_id)
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
            
    def get_video_transcript(self, channel_id, video_id):
        cache_data = self.get_channel_cache(channel_id)
        return cache_data['videos'].get(video_id)
        
    def save_video_transcript(self, channel_id, video_id, video_data):
        cache_data = self.get_channel_cache(channel_id)
        cache_data['videos'][video_id] = video_data
        self.save_channel_cache(channel_id, cache_data)

class YouTubeSearcher:
    def __init__(self):
        self.SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']
        self.language_codes = ['en', 'en-GB', 'en-US']
        self.cache = TranscriptCache()
        self.youtube = self._get_authenticated_service()

    def _get_authenticated_service(self):
        creds = None
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
                
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'client_secrets.json', 
                    self.SCOPES
                )
                # Specify the port explicitly
                creds = flow.run_local_server(port=8085)
                
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)

        return build('youtube', 'v3', credentials=creds)

    def _get_transcript(self, video_id):
        try:
            # Get list of available captions
            captions_request = self.youtube.captions().list(
                part="snippet",
                videoId=video_id
            )
            captions_response = captions_request.execute()

            # Find an English caption track
            caption_id = None
            for item in captions_response.get('items', []):
                lang = item['snippet']['language']
                if lang in self.language_codes:
                    caption_id = item['id']
                    break

            if not caption_id:
                return None

            # Download the caption track
            caption_request = self.youtube.captions().download(
                id=caption_id,
                tfmt='srt'  # Get in SRT format
            )
            
            # The caption download returns bytes
            caption_content = caption_request.execute()
            
            # Convert from SRT format to our transcript format
            return self._parse_srt_content(caption_content)

        except Exception as e:
            print(f"Error getting transcript: {str(e)}")
            return None

    def _parse_srt_content(self, srt_content):
        """Convert SRT format to our transcript format"""
        import re
        from datetime import datetime

        def time_to_seconds(time_str):
            # Convert SRT timestamp to seconds
            time_obj = datetime.strptime(time_str, '%H:%M:%S,%f')
            return time_obj.hour * 3600 + time_obj.minute * 60 + time_obj.second + time_obj.microsecond / 1000000

        transcript = []
        
        # Decode bytes to string
        content = srt_content.decode('utf-8')
        
        # Split into subtitle blocks
        subtitle_blocks = re.split('\n\n+', content.strip())
        
        for block in subtitle_blocks:
            lines = block.strip().split('\n')
            if len(lines) >= 3:  # Valid subtitle block should have at least 3 lines
                # Parse timestamp line
                timestamps = lines[1].split(' --> ')
                start_time = time_to_seconds(timestamps[0])
                
                # Join remaining lines as text
                text = ' '.join(lines[2:])
                
                transcript.append({
                    'text': text,
                    'start': start_time
                })

        return transcript

    def generate_results(self, handle, term):
        try:
            if not handle or not term:
                yield json.dumps({
                    'type': 'error',
                    'error': 'Please provide both channel handle and search term'
                }) + '\n'
                return

            try:
                channel_id = self.search_channel(handle)
            except Exception as e:
                yield json.dumps({
                    'type': 'error',
                    'error': f'Channel not found: {str(e)}'
                }) + '\n'
                return

            videos_processed = 0
            matches_found = 0
            cache_hits = 0
            
            for video in self.get_videos_iterator(channel_id):
                videos_processed += 1
                
                yield json.dumps({
                    'type': 'progress',
                    'videos_processed': videos_processed,
                    'matches_found': matches_found,
                    'cache_hits': cache_hits
                }) + '\n'

                # Check cache first
                cached_video = self.cache.get_video_transcript(channel_id, video['id'])
                if cached_video:
                    cache_hits += 1
                    result = self.search_cached_transcript(cached_video, term)
                else:
                    result = self.search_video_transcript(channel_id, video, term)
                
                if result:
                    matches_found += 1
                    yield json.dumps({
                        'type': 'match',
                        'data': result
                    }) + '\n'

            yield json.dumps({
                'type': 'complete',
                'videos_processed': videos_processed,
                'matches_found': matches_found,
                'cache_hits': cache_hits
            }) + '\n'

        except Exception as e:
            yield json.dumps({
                'type': 'error',
                'error': str(e)
            }) + '\n'

    def search_cached_transcript(self, video_data, search_term):
        matches = []
        for entry in video_data['transcript']:
            if search_term.lower() in entry['text'].lower():
                matches.append({
                    'text': entry['text'],
                    'timestamp': entry['start'],
                    'timestamp_formatted': self._format_timestamp(entry['start'])
                })
        
        if matches:
            return {
                'video_id': video_data['video_id'],
                'title': video_data['title'],
                'published_at': video_data['published_at'],
                'matches': matches
            }
        return None

    def search_video_transcript(self, channel_id, video, search_term):
        try:
            transcript = self._get_transcript(video['id'])
            if not transcript:
                return None

            # Save to cache
            video_data = {
                'video_id': video['id'],
                'title': video['title'],
                'published_at': video['published_at'],
                'transcript': transcript
            }
            self.cache.save_video_transcript(channel_id, video['id'], video_data)

            matches = []
            for entry in transcript:
                if search_term.lower() in entry['text'].lower():
                    matches.append({
                        'text': entry['text'],
                        'timestamp': entry['start'],
                        'timestamp_formatted': self._format_timestamp(entry['start'])
                    })
            
            if matches:
                return {
                    'video_id': video['id'],
                    'title': video['title'],
                    'published_at': video['published_at'],
                    'matches': matches
                }
            
        except Exception:
            return None
            
        return None

    def _format_timestamp(self, seconds):
        from datetime import timedelta
        return str(timedelta(seconds=int(seconds))).split('.')[0].zfill(8)

    def search_channel(self, handle):
        if not handle.startswith('@'):
            handle = '@' + handle
            
        request = self.youtube.search().list(
            part="snippet",
            q=handle,
            type="channel",
            maxResults=1
        )
        response = request.execute()
        
        if not response['items']:
            raise ValueError(f"No channel found for handle {handle}")
            
        return response['items'][0]['snippet']['channelId']

    def get_videos_iterator(self, channel_id):
        page_token = None
        while True:
            request = self.youtube.search().list(
                part="id,snippet",
                channelId=channel_id,
                maxResults=50,
                type="video",
                order="date",
                pageToken=page_token
            )
            response = request.execute()
            
            for item in response['items']:
                video = {
                    'id': item['id']['videoId'],
                    'title': item['snippet']['title'],
                    'published_at': item['snippet']['publishedAt']
                }
                yield video

            page_token = response.get('nextPageToken')
            if not page_token:
                break

searcher = YouTubeSearcher()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    data = request.get_json()
    handle = data.get('handle', '').strip()
    term = data.get('term', '').strip()
    
    def generate():
        yield from searcher.generate_results(handle, term)

    return Response(generate(), mimetype='text/plain')

if __name__ == '__main__':
    app.run(debug=True)

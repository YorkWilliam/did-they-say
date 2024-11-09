from flask import Flask, render_template, request, jsonify, Response
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from datetime import timedelta, datetime
from dotenv import load_dotenv
import json
import os
import time

app = Flask(__name__)
load_dotenv()

YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
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
    def __init__(self, api_key):
        self.youtube = build('youtube', 'v3', developerKey=api_key)
        self.language_codes = ['en', 'en-GB', 'en-US']
        self.cache = TranscriptCache()

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

    def _format_timestamp(self, seconds):
        return str(timedelta(seconds=int(seconds))).split('.')[0].zfill(8)

    def _get_transcript(self, video_id):
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            transcript = None
            
            # Try manual transcripts first
            for lang_code in self.language_codes:
                try:
                    transcript = transcript_list.find_manually_created_transcript([lang_code])
                    break
                except:
                    continue
            
            # Try auto-generated transcripts
            if not transcript:
                for lang_code in self.language_codes:
                    try:
                        transcript = transcript_list.find_generated_transcript([lang_code])
                        break
                    except:
                        continue
            
            # Try translated transcripts as last resort
            if not transcript:
                try:
                    transcript = transcript_list.find_transcript(self.language_codes)
                except:
                    return None
            
            return transcript.fetch()
            
        except Exception:
            return None

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

searcher = YouTubeSearcher(YOUTUBE_API_KEY)

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
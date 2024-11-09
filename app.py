from flask import Flask, render_template, request, jsonify, Response
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from datetime import timedelta
from dotenv import load_dotenv
import json
import os

app = Flask(__name__)
load_dotenv()

YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')

class YouTubeSearcher:
    def __init__(self, api_key):
        self.youtube = build('youtube', 'v3', developerKey=api_key)
        self.language_codes = ['en', 'en-GB', 'en-US']

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
            
            for video in self.get_videos_iterator(channel_id):
                videos_processed += 1
                
                if videos_processed % 10 == 0:
                    yield json.dumps({
                        'type': 'progress',
                        'videos_processed': videos_processed,
                        'matches_found': matches_found
                    }) + '\n'

                result = self.search_video_transcript(video, term)
                if result:
                    matches_found += 1
                    yield json.dumps({
                        'type': 'match',
                        'data': result
                    }) + '\n'

            yield json.dumps({
                'type': 'complete',
                'videos_processed': videos_processed,
                'matches_found': matches_found
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

    def search_video_transcript(self, video, search_term):
        try:
            transcript = self._get_transcript(video['id'])
            if not transcript:
                return None

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

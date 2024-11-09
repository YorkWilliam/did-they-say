from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from shared import YouTubeSearcherBase
import pickle
import os

class OAuthYouTubeSearcher(YouTubeSearcherBase):
    def __init__(self):
        super().__init__()
        self.SCOPES = [
            'https://www.googleapis.com/auth/youtube.force-ssl',
            'https://www.googleapis.com/auth/youtube.readonly',
            'https://www.googleapis.com/auth/youtubepartner'
        ]
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
                creds = flow.run_local_server(port=0)
                
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)

        return build('youtube', 'v3', credentials=creds)

    def search_channel(self, handle):
        if not handle.startswith('@'):
            handle = '@' + handle
            
        # Get cached videos to check channel ID
        cached_data = self.cache.get_channel_cache(handle)
        if cached_data.get('channel_id'):
            return cached_data['channel_id']
            
        # If not in cache, fetch from API
        request = self.youtube.channels().list(
            part="id",
            forHandle=handle[1:]
        )
        response = request.execute()

        if not response['items']:
            raise ValueError(f"No channel found for handle {handle}")
        
        channel_id = response['items'][0]['id']
        
        # Save channel ID to cache
        cached_data['channel_id'] = channel_id
        self.cache.save_channel_cache(handle, cached_data)
            
        return channel_id

    def _get_transcript(self, video_id):
        try:
            captions_request = self.youtube.captions().list(
                part="snippet",
                videoId=video_id
            )
            captions_response = captions_request.execute()

            caption_id = None
            for item in captions_response.get('items', []):
                lang = item['snippet']['language']
                if lang in self.language_codes:
                    caption_id = item['id']
                    break

            if not caption_id:
                return None

            caption_request = self.youtube.captions().download(
                id=caption_id,
                tfmt='srt'
            )
            
            caption_content = caption_request.execute()
            return self._parse_srt_content(caption_content)

        except Exception as e:
            print(f"Error getting transcript: {str(e)}")
            return None

    def _parse_srt_content(self, srt_content):
        import re
        from datetime import datetime

        def time_to_seconds(time_str):
            time_obj = datetime.strptime(time_str, '%H:%M:%S,%f')
            return time_obj.hour * 3600 + time_obj.minute * 60 + time_obj.second + time_obj.microsecond / 1000000

        seen_texts = set()  # Track unique texts to avoid duplicates
        transcript = []
        content = srt_content.decode('utf-8')
        subtitle_blocks = re.split('\n\n+', content.strip())
        
        for block in subtitle_blocks:
            lines = block.strip().split('\n')
            if len(lines) >= 3:
                timestamps = lines[1].split(' --> ')
                start_time = time_to_seconds(timestamps[0])
                text = ' '.join(lines[2:]).strip()
                
                # Only add if we haven't seen this text before
                if text not in seen_texts:
                    transcript.append({
                        'text': text,
                        'start': start_time
                    })
                    seen_texts.add(text)

        return transcript

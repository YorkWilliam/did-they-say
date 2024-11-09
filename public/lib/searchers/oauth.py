from lib.searchers.base import BaseSearcher
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import os
import pickle

class OAuthSearcher(BaseSearcher):
    def __init__(self):
        super().__init__()
        self.youtube = self._get_authenticated_service()
    
    def _get_authenticated_service(self):
        creds = None
        # Token pickle file stores the user's credentials from previously successful logins
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
                
        # If there are no valid credentials, let the user log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'client_secrets.json',
                    scopes=['https://www.googleapis.com/auth/youtube.force-ssl']
                )
                creds = flow.run_local_server(port=0)
            
            # Save the credentials for the next run
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)
        
        return build('youtube', 'v3', credentials=creds)
    
    def search_channel(self, handle):
        try:
            # First get channel details using handle
            request = self.youtube.search().list(
                part="snippet",
                q=handle,
                type="channel",
                maxResults=1
            )
            response = request.execute()
            
            if not response['items']:
                raise ValueError(f"No channel found for handle {handle}")
            
            channel_id = response['items'][0]['id']['channelId']
            
            # Get all video IDs from the channel
            videos = []
            next_page_token = None
            
            while True:
                playlist_request = self.youtube.search().list(
                    part="id",
                    channelId=channel_id,
                    maxResults=50,
                    type="video",
                    order="date",
                    pageToken=next_page_token
                )
                playlist_response = playlist_request.execute()
                
                for item in playlist_response['items']:
                    videos.append(item['id']['videoId'])
                
                next_page_token = playlist_response.get('nextPageToken')
                if not next_page_token or len(videos) >= 1000:
                    break
            
            return {
                'handle': handle,
                'channel_id': channel_id,
                'video_list': videos
            }
            
        except HttpError as e:
            raise ValueError(f"YouTube API error: {str(e)}")
    
    def search_video(self, handle, video_id):
        try:
            # Get video details
            video_request = self.youtube.videos().list(
                part="snippet",
                id=video_id
            )
            video_response = video_request.execute()
            
            if not video_response['items']:
                raise ValueError(f"No video found with ID {video_id}")
            
            video_info = video_response['items'][0]['snippet']
            
            # Get captions
            captions_request = self.youtube.captions().list(
                part="snippet",
                videoId=video_id
            )
            captions_response = captions_request.execute()
            
            transcript = []
            if captions_response.get('items'):
                # Try to find English captions
                caption_id = None
                for caption in captions_response['items']:
                    lang = caption['snippet']['language']
                    if lang in self.language_codes:
                        caption_id = caption['id']
                        break
                
                if caption_id:
                    # Download the caption track
                    caption_request = self.youtube.captions().download(
                        id=caption_id,
                        tfmt='srt'
                    )
                    caption_content = caption_request.execute().decode('utf-8')
                    
                    # Parse the SRT format
                    transcript = self._parse_srt(caption_content)
            
            return {
                'video_id': video_id,
                'channel': handle,
                'title': video_info['title'],
                'published_at': video_info['publishedAt'][:10],
                'transcript': transcript
            }
            
        except HttpError as e:
            raise ValueError(f"YouTube API error: {str(e)}")
    
    def _parse_srt(self, content):
        """Parse SRT format captions"""
        transcript = []
        current_text = []
        current_start = None
        
        for line in content.split('\n'):
            line = line.strip()
            
            if not line:
                if current_start is not None and current_text:
                    transcript.append({
                        'start': current_start,
                        'text': ' '.join(current_text)
                    })
                current_text = []
                current_start = None
                continue
            
            if ' --> ' in line:
                time_parts = line.split(' --> ')[0].split(':')
                hours = int(time_parts[0])
                minutes = int(time_parts[1])
                seconds = float(time_parts[2].replace(',', '.'))
                current_start = hours * 3600 + minutes * 60 + seconds
            elif not line.isdigit():
                current_text.append(line)
        
        return transcript
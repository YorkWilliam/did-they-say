from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from shared import YouTubeSearcherBase
import os

class APIKeyYouTubeSearcher(YouTubeSearcherBase):
    def __init__(self, api_key):
        super().__init__()
        self.youtube = build('youtube', 'v3', developerKey=api_key)

    def search_channel(self, handle):
        if not handle.startswith('@'):
            handle = '@' + handle
            
        request = self.youtube.channels().list(
            part="id",
            forHandle=handle[1:]
        )
        response = request.execute()
        
        if not response['items']:
            raise ValueError(f"No channel found for handle {handle}")
            
        return response['items'][0]['id']

    def _get_transcript(self, video_id):
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            transcript = None
            
            for lang_code in self.language_codes:
                try:
                    transcript = transcript_list.find_manually_created_transcript([lang_code])
                    break
                except:
                    continue
            
            if not transcript:
                for lang_code in self.language_codes:
                    try:
                        transcript = transcript_list.find_generated_transcript([lang_code])
                        break
                    except:
                        continue
            
            if not transcript:
                try:
                    transcript = transcript_list.find_transcript(self.language_codes)
                except:
                    return None
            
            return transcript.fetch()
            
        except Exception as e:
            print(f"Error getting transcript: {str(e)}")
            return None
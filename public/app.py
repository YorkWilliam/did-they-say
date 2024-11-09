from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import pickle
import os.path

class YouTubeSearcher:
    def __init__(self):
        self.SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']
        self.language_codes = ['en', 'en-GB', 'en-US']
        self.cache = TranscriptCache()
        self.youtube = self._get_authenticated_service()

    def _get_authenticated_service(self):
        creds = None
        # The file token.pickle stores the user's credentials from previously successful logins
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
                
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'client_secrets.json', 
                    self.SCOPES
                )
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
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

from flask import Flask, render_template, request, Response
# from api_key_searcher import APIKeyYouTubeSearcher # Uncomment to use API Key
# from oauth_searcher import OAuthYouTubeSearcher  # Uncomment to use OAuth
from scraper_searcher import ScraperYouTubeSearcher
from dotenv import load_dotenv
import os

app = Flask(__name__)
load_dotenv()

# Choose one of these three options:

# 1. API Key version
# searcher = APIKeyYouTubeSearcher(os.getenv('YOUTUBE_API_KEY'))

# 2. OAuth version
# searcher = OAuthYouTubeSearcher()

# 3. Scraper version (no API quotas!)
searcher = ScraperYouTubeSearcher()

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

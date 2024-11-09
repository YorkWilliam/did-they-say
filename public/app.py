from flask import Flask, render_template, request, Response
from lib.searchers.oauth import OAuthSearcher
from lib.searchers.apikey import APIKeySearcher
from lib.searchers.scraper import ScraperSearcher
from dotenv import load_dotenv
import os

app = Flask(__name__)
load_dotenv()

# Initialize all searchers once
searchers = {
    'oauth': OAuthSearcher(),
    'apikey': APIKeySearcher(os.getenv('YOUTUBE_API_KEY')),
    'scraper': ScraperSearcher()
}

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    data = request.get_json()
    handle = data.get('handle', '').strip()
    term = data.get('term', '').strip()
    searcher_type = data.get('type', 'oauth').strip()  # Default to oauth
    
    if searcher_type not in searchers:
        return Response(
            '{"type": "error", "error": "Invalid searcher type"}\n',
            mimetype='text/plain'
        )
    
    def generate():
        yield from searchers[searcher_type].generate_results(handle, term)

    return Response(generate(), mimetype='text/plain')

if __name__ == '__main__':
    app.run(debug=True)
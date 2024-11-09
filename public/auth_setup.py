from oauth_searcher import OAuthYouTubeSearcher  # Import your searcher class

def setup_auth():
    print("Starting authentication setup...")
    searcher = OAuthYouTubeSearcher()
    print("Authentication complete! Token saved.")

if __name__ == "__main__":
    setup_auth()

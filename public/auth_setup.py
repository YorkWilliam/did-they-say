from app import YouTubeSearcher  # Import your searcher class

def setup_auth():
    print("Starting authentication setup...")
    searcher = YouTubeSearcher()
    print("Authentication complete! Token saved.")

if __name__ == "__main__":
    setup_auth()

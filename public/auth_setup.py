from lib.searchers.oauth import OAuthSearcher  # Import your searcher class

def setup_auth():
    print("Starting authentication setup...")
    searcher = OAuthSearcher()
    print("Authentication complete! Token saved.")

if __name__ == "__main__":
    setup_auth()

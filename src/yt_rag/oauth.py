import os
import json
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials


# Get Client ID and Secret from environment variables
# Instructions:
# 1. Copy .env.example to .env
# 2. Add your credentials
# 3. Load with: python-dotenv or set them in your shell
YOUTUBE_CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET")

# This tells Google what permissions we're asking for
# "youtube.readonly" = Read-only access to watch history (not write/delete)
SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]


def get_credentials_path():
    """Return the path where we store the saved token."""
    from .config import get_config_dir
    return get_config_dir() / "youtube_token.json"


def authenticate_youtube():
    """
    Start the OAuth flow and return credentials.

    This function:
    1. Opens the user's browser
    2. User sees a Google consent screen ("Allow this app to access your videos?")
    3. User clicks "Allow"
    4. Browser redirects back to us with a code
    5. We exchange the code for a token
    6. We save the token locally

    Returns: Google credentials object
    """
    creds = None
    creds_path = get_credentials_path()

    # Check if we already have a saved token
    if creds_path.exists():
        creds = Credentials.from_authorized_user_file(creds_path, SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            save_credentials(creds)
        return creds

    # If no saved token, start the OAuth flow
    # This opens the browser for the user to sign in
    flow = InstalledAppFlow.from_client_secrets_dict(
        {
            "installed": {
                "client_id": YOUTUBE_CLIENT_ID,
                "client_secret": YOUTUBE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost:8080/"],
            }
        },
        scopes=SCOPES,
    )

    # This opens the browser automatically
    creds = flow.run_local_server(port=8080)

    # Save the token for next time
    save_credentials(creds)

    return creds


def save_credentials(creds):
    """Save the credentials to a file for future use."""
    creds_path = get_credentials_path()
    creds_path.parent.mkdir(parents=True, exist_ok=True)

    with open(creds_path, "w") as token_file:
        token_file.write(creds.to_json())


def load_credentials():
    """Load previously saved credentials if they exist."""
    creds_path = get_credentials_path()

    if not creds_path.exists():
        return None

    creds = Credentials.from_authorized_user_file(creds_path, SCOPES)

    # If token expired, refresh it
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        save_credentials(creds)

    return creds


def is_authenticated():
    """Check if user has already authenticated."""
    return get_credentials_path().exists()

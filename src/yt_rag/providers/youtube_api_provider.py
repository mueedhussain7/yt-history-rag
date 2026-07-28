from typing import List, Dict, Any
from .base import HistoryProvider
from ..youtube_api import YouTubeAPI


class YouTubeAPIProvider(HistoryProvider):
    """Provider for fetching videos from YouTube API (watch history)."""

    def __init__(self):
        """Initialize YouTube API provider."""
        self.youtube_api = YouTubeAPI()

    def get_videos(self) -> List[Dict[str, Any]]:
        """
        Fetch videos from YouTube API watch history.

        Returns:
            List of videos with keys: video_id, title, url, watch_date
        """
        return self.youtube_api.fetch_watch_history()

from abc import ABC, abstractmethod
from typing import List, Dict, Any


class HistoryProvider(ABC):
    """Abstract base class for YouTube history providers."""

    @abstractmethod
    def get_videos(self) -> List[Dict[str, Any]]:
        """
        Get videos from this provider.

        Returns:
            List of dicts with keys:
            - video_id: str (YouTube video ID)
            - title: str (video title)
            - url: str (full YouTube URL)
            - watch_date: str (ISO format datetime)
        """
        pass

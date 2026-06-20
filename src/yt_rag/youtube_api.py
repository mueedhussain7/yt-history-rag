from typing import List, Dict, Any, Optional
from datetime import datetime
from googleapiclient.discovery import build
from .oauth import load_credentials


class YouTubeAPI:
    """
    Handles all communication with YouTube API.
    """

    def __init__(self):
        """Initialize YouTube API connection."""
        self.credentials = load_credentials()
        if not self.credentials:
            raise Exception("Not authenticated with YouTube. Run 'yt-rag init' first.")

        # Build the YouTube service (like opening a phone line to YouTube)
        self.youtube = build("youtube", "v3", credentials=self.credentials)

    def fetch_watch_history(self, max_results: int = 50) -> List[Dict[str, Any]]:
        """
        Fetch videos from the user's watch history.

        Args:
            max_results: How many videos to get at a time (max 50)

        Returns:
            List of videos with metadata
        """
        videos = []
        next_page_token = None

        while True:
            try:
                # Ask YouTube for the next batch of videos
                request = self.youtube.activities().list(
                    part="snippet,contentDetails",
                    forMine=True,  # Get videos watched by THIS user
                    maxResults=max_results,
                    pageToken=next_page_token,
                    fields="items(snippet(title,publishedAt),contentDetails(upload(videoId))),nextPageToken",
                )
                response = request.execute()

                # Process each video in the response
                for item in response.get("items", []):
                    video = self._parse_video_item(item)
                    if video:  # Only add if it's a valid video
                        videos.append(video)

                # Check if there are more pages
                next_page_token = response.get("nextPageToken")
                if not next_page_token:
                    break  # No more pages, we're done

            except Exception as e:
                print(f"Error fetching videos: {str(e)}")
                break

        return videos

    def _parse_video_item(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Convert YouTube's response into our format.
        """
        try:
            snippet = item.get("snippet", {})
            content_details = item.get("contentDetails", {})
            upload = content_details.get("upload", {})

            video_id = upload.get("videoId")
            if not video_id:
                return None  # Skip if no video ID

            return {
                "video_id": video_id,
                "title": snippet.get("title", "Unknown"),
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "watch_date": snippet.get("publishedAt", ""),
            }
        except Exception:
            return None

    def get_video_details(self, video_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed info about a single video.
        Returns: duration, channel name, description, etc.
        """
        try:
            request = self.youtube.videos().list(
                part="snippet,contentDetails",
                id=video_id,
                fields="items(snippet(title,channelTitle,description),contentDetails(duration))",
            )
            response = request.execute()

            if not response.get("items"):
                return None

            item = response["items"][0]
            snippet = item.get("snippet", {})
            content = item.get("contentDetails", {})

            return {
                "video_id": video_id,
                "title": snippet.get("title"),
                "channel": snippet.get("channelTitle"),
                "description": snippet.get("description"),
                "duration": content.get("duration"),  # Format: PT10M30S (10 minutes 30 seconds)
            }
        except Exception as e:
            print(f"Error getting video details: {str(e)}")
            return None

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from yt_rag.youtube_api import YouTubeAPI


@pytest.fixture
def mock_credentials():
    """Create mock credentials."""
    mock_creds = MagicMock()
    mock_creds.valid = True
    return mock_creds


def test_youtube_api_init_with_no_credentials():
    """Test that YouTubeAPI raises error when not authenticated."""
    with patch("yt_rag.youtube_api.load_credentials", return_value=None):
        with pytest.raises(Exception, match="Not authenticated"):
            YouTubeAPI()


def test_youtube_api_init_with_credentials(mock_credentials):
    """Test that YouTubeAPI initializes when authenticated."""
    with patch("yt_rag.youtube_api.load_credentials", return_value=mock_credentials):
        with patch("yt_rag.youtube_api.build") as mock_build:
            api = YouTubeAPI()
            assert api.credentials is not None
            mock_build.assert_called_once()


def test_parse_video_item_valid():
    """Test parsing a valid video item from YouTube response."""
    with patch("yt_rag.youtube_api.load_credentials", return_value=MagicMock()):
        with patch("yt_rag.youtube_api.build"):
            api = YouTubeAPI()

            video_item = {
                "snippet": {
                    "title": "How to Code",
                    "publishedAt": "2026-06-21T10:00:00Z",
                },
                "contentDetails": {
                    "upload": {
                        "videoId": "dQw4w9WgXcQ",
                    }
                },
            }

            result = api._parse_video_item(video_item)

            assert result is not None
            assert result["video_id"] == "dQw4w9WgXcQ"
            assert result["title"] == "How to Code"
            assert "youtube.com/watch?v=" in result["url"]


def test_parse_video_item_missing_video_id():
    """Test parsing a video item without video ID (should skip)."""
    with patch("yt_rag.youtube_api.load_credentials", return_value=MagicMock()):
        with patch("yt_rag.youtube_api.build"):
            api = YouTubeAPI()

            video_item = {
                "snippet": {"title": "No ID Video"},
                "contentDetails": {"upload": {}},  # No videoId
            }

            result = api._parse_video_item(video_item)

            assert result is None  # Should skip videos without IDs


def test_fetch_watch_history_single_page(mock_credentials):
    """Test fetching videos when there's only one page."""
    with patch("yt_rag.youtube_api.load_credentials", return_value=mock_credentials):
        with patch("yt_rag.youtube_api.build") as mock_build:
            # Setup mock YouTube API
            mock_youtube = MagicMock()
            mock_build.return_value = mock_youtube

            # Mock the response
            mock_response = {
                "items": [
                    {
                        "snippet": {
                            "title": "Video 1",
                            "publishedAt": "2026-06-21T10:00:00Z",
                        },
                        "contentDetails": {"upload": {"videoId": "vid1"}},
                    },
                    {
                        "snippet": {
                            "title": "Video 2",
                            "publishedAt": "2026-06-20T10:00:00Z",
                        },
                        "contentDetails": {"upload": {"videoId": "vid2"}},
                    },
                ],
                "nextPageToken": None,  # No more pages
            }

            mock_youtube.activities().list().execute.return_value = mock_response

            api = YouTubeAPI()
            videos = api.fetch_watch_history()

            assert len(videos) == 2
            assert videos[0]["video_id"] == "vid1"
            assert videos[1]["video_id"] == "vid2"


def test_fetch_watch_history_multiple_pages(mock_credentials):
    """Test fetching videos across multiple pages."""
    with patch("yt_rag.youtube_api.load_credentials", return_value=mock_credentials):
        with patch("yt_rag.youtube_api.build") as mock_build:
            mock_youtube = MagicMock()
            mock_build.return_value = mock_youtube

            # First page response
            page1_response = {
                "items": [
                    {
                        "snippet": {"title": "Video 1", "publishedAt": "2026-06-21T10:00:00Z"},
                        "contentDetails": {"upload": {"videoId": "vid1"}},
                    }
                ],
                "nextPageToken": "NEXT_PAGE",  # More pages
            }

            # Second page response
            page2_response = {
                "items": [
                    {
                        "snippet": {"title": "Video 2", "publishedAt": "2026-06-20T10:00:00Z"},
                        "contentDetails": {"upload": {"videoId": "vid2"}},
                    }
                ],
                "nextPageToken": None,  # No more pages
            }

            # Setup mock to return different responses on successive calls
            mock_youtube.activities().list().execute.side_effect = [
                page1_response,
                page2_response,
            ]

            api = YouTubeAPI()
            videos = api.fetch_watch_history()

            assert len(videos) == 2
            assert videos[0]["video_id"] == "vid1"
            assert videos[1]["video_id"] == "vid2"


def test_get_video_details(mock_credentials):
    """Test getting detailed info about a single video."""
    with patch("yt_rag.youtube_api.load_credentials", return_value=mock_credentials):
        with patch("yt_rag.youtube_api.build") as mock_build:
            mock_youtube = MagicMock()
            mock_build.return_value = mock_youtube

            mock_response = {
                "items": [
                    {
                        "snippet": {
                            "title": "Python Tutorial",
                            "channelTitle": "Tech Channel",
                            "description": "Learn Python basics",
                        },
                        "contentDetails": {
                            "duration": "PT10M30S",  # 10 minutes 30 seconds
                        },
                    }
                ]
            }

            mock_youtube.videos().list().execute.return_value = mock_response

            api = YouTubeAPI()
            details = api.get_video_details("vid123")

            assert details is not None
            assert details["title"] == "Python Tutorial"
            assert details["channel"] == "Tech Channel"
            assert details["duration"] == "PT10M30S"


def test_get_video_details_not_found(mock_credentials):
    """Test getting details for a video that doesn't exist."""
    with patch("yt_rag.youtube_api.load_credentials", return_value=mock_credentials):
        with patch("yt_rag.youtube_api.build") as mock_build:
            mock_youtube = MagicMock()
            mock_build.return_value = mock_youtube

            mock_response = {"items": []}  # No videos found

            mock_youtube.videos().list().execute.return_value = mock_response

            api = YouTubeAPI()
            details = api.get_video_details("nonexistent")

            assert details is None

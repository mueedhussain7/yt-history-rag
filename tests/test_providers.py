import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from yt_rag.providers.base import HistoryProvider
from yt_rag.providers.takeout_provider import GoogleTakeoutProvider
from yt_rag.providers.browser_extension_provider import BrowserExtensionProvider


class TestHistoryProvider:
    """Test the abstract base class."""

    def test_history_provider_is_abstract(self):
        """HistoryProvider should not be instantiable."""
        with pytest.raises(TypeError):
            HistoryProvider()

    def test_history_provider_requires_get_videos(self):
        """Subclasses must implement get_videos()."""
        class IncompleteProvider(HistoryProvider):
            pass

        with pytest.raises(TypeError):
            IncompleteProvider()


class TestGoogleTakeoutProvider:
    """Test Google Takeout HTML parsing."""

    @pytest.fixture
    def sample_takeout_html(self):
        """Sample Google Takeout watch-history.html content."""
        return """
        <!DOCTYPE html>
        <html>
        <body>
        <div>
            <a href="https://www.youtube.com/watch?v=dQw4w9WgXcQ">Never Gonna Give You Up</a>
            <br>
            <div class="content-cell">Watched on Oct 15, 2024</div>
        </div>
        <div>
            <a href="https://www.youtube.com/watch?v=jNQXAC9IVRw">Me at the zoo</a>
            <br>
            <div class="content-cell">Watched on Sep 23, 2005</div>
        </div>
        <div>
            <a href="https://www.youtube.com/watch?v=9bZkp7q19f0">Video with &amp; entity</a>
            <br>
            <div class="content-cell">Watched on Jan 1, 2023</div>
        </div>
        </body>
        </html>
        """

    def test_takeout_provider_parses_html(self, sample_takeout_html):
        """Test that GoogleTakeoutProvider can parse watch-history.html."""
        with tempfile.TemporaryDirectory() as tmpdir:
            html_file = Path(tmpdir) / "watch-history.html"
            html_file.write_text(sample_takeout_html)

            provider = GoogleTakeoutProvider(str(html_file))
            videos = provider.get_videos()

            assert len(videos) == 3
            assert videos[0]["video_id"] == "dQw4w9WgXcQ"
            assert videos[0]["title"] == "Never Gonna Give You Up"
            assert "youtube.com/watch?v=dQw4w9WgXcQ" in videos[0]["url"]
            assert "2024" in videos[0]["watch_date"]

    def test_takeout_provider_handles_html_entities(self, sample_takeout_html):
        """Test that HTML entities are unescaped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            html_file = Path(tmpdir) / "watch-history.html"
            html_file.write_text(sample_takeout_html)

            provider = GoogleTakeoutProvider(str(html_file))
            videos = provider.get_videos()

            # Third video has &amp; which should be decoded to &
            assert videos[2]["title"] == "Video with & entity"

    def test_takeout_provider_extracts_dates(self, sample_takeout_html):
        """Test that watch dates are extracted and converted to ISO format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            html_file = Path(tmpdir) / "watch-history.html"
            html_file.write_text(sample_takeout_html)

            provider = GoogleTakeoutProvider(str(html_file))
            videos = provider.get_videos()

            # Check ISO date format
            assert videos[1]["watch_date"] == "2005-09-23T00:00:00"

    def test_takeout_provider_file_not_found(self):
        """Test error handling when file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            GoogleTakeoutProvider("/nonexistent/path/watch-history.html")

    def test_takeout_provider_invalid_file_type(self):
        """Test error handling when file is not HTML."""
        with tempfile.TemporaryDirectory() as tmpdir:
            txt_file = Path(tmpdir) / "watch-history.txt"
            txt_file.write_text("test")

            with pytest.raises(ValueError, match="must be an HTML file"):
                GoogleTakeoutProvider(str(txt_file))

    def test_takeout_provider_returns_empty_for_invalid_html(self):
        """Test graceful failure with invalid HTML."""
        with tempfile.TemporaryDirectory() as tmpdir:
            html_file = Path(tmpdir) / "watch-history.html"
            html_file.write_text("<html><body>No videos here</body></html>")

            provider = GoogleTakeoutProvider(str(html_file))
            videos = provider.get_videos()

            assert videos == []

    def test_takeout_provider_implements_interface(self, sample_takeout_html):
        """Test that GoogleTakeoutProvider implements HistoryProvider."""
        with tempfile.TemporaryDirectory() as tmpdir:
            html_file = Path(tmpdir) / "watch-history.html"
            html_file.write_text(sample_takeout_html)

            provider = GoogleTakeoutProvider(str(html_file))
            assert isinstance(provider, HistoryProvider)
            assert hasattr(provider, "get_videos")
            assert callable(provider.get_videos)


class TestBrowserExtensionProvider:
    """Test browser extension video storage and retrieval."""

    @pytest.fixture
    def temp_config_dir(self):
        """Temporarily mock the config directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("yt_rag.providers.browser_extension_provider.get_config_dir", return_value=Path(tmpdir)):
                yield Path(tmpdir)

    def test_browser_extension_provider_returns_empty_initially(self, temp_config_dir):
        """Test that provider returns empty list when no videos recorded."""
        provider = BrowserExtensionProvider()
        videos = provider.get_videos()

        assert videos == []

    def test_browser_extension_provider_records_video(self, temp_config_dir):
        """Test that videos can be recorded and retrieved."""
        provider = BrowserExtensionProvider()

        video_data = {
            "video_id": "dQw4w9WgXcQ",
            "title": "Never Gonna Give You Up",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "watch_date": "2024-10-15T10:30:00",
        }

        success = provider.record_video(video_data)
        assert success is True

        # Retrieve and verify
        videos = provider.get_videos()
        assert len(videos) == 1
        assert videos[0]["video_id"] == "dQw4w9WgXcQ"
        assert videos[0]["title"] == "Never Gonna Give You Up"

    def test_browser_extension_provider_prevents_duplicates(self, temp_config_dir):
        """Test that duplicate videos are not recorded."""
        provider = BrowserExtensionProvider()

        video_data = {
            "video_id": "dQw4w9WgXcQ",
            "title": "Never Gonna Give You Up",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "watch_date": "2024-10-15T10:30:00",
        }

        # Record twice
        success1 = provider.record_video(video_data)
        success2 = provider.record_video(video_data)

        assert success1 is True
        assert success2 is True  # Returns True but doesn't duplicate

        videos = provider.get_videos()
        assert len(videos) == 1  # Only one video stored

    def test_browser_extension_provider_records_multiple_videos(self, temp_config_dir):
        """Test that multiple videos can be recorded."""
        provider = BrowserExtensionProvider()

        videos_data = [
            {
                "video_id": "dQw4w9WgXcQ",
                "title": "Never Gonna Give You Up",
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "watch_date": "2024-10-15T10:30:00",
            },
            {
                "video_id": "jNQXAC9IVRw",
                "title": "Me at the zoo",
                "url": "https://www.youtube.com/watch?v=jNQXAC9IVRw",
                "watch_date": "2005-04-23T20:27:33",
            },
        ]

        for video_data in videos_data:
            success = provider.record_video(video_data)
            assert success is True

        videos = provider.get_videos()
        assert len(videos) == 2

    def test_browser_extension_provider_persists_to_file(self, temp_config_dir):
        """Test that videos persist to JSON file."""
        provider = BrowserExtensionProvider()

        video_data = {
            "video_id": "dQw4w9WgXcQ",
            "title": "Test Video",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "watch_date": "2024-10-15T10:30:00",
        }

        provider.record_video(video_data)

        # Check file exists and has correct structure
        storage_file = temp_config_dir / "browser_extension_videos.json"
        assert storage_file.exists()

        with open(storage_file) as f:
            data = json.load(f)
            assert "videos" in data
            assert len(data["videos"]) == 1
            assert data["videos"][0]["video_id"] == "dQw4w9WgXcQ"

    def test_browser_extension_provider_handles_corrupted_json(self, temp_config_dir):
        """Test graceful handling of corrupted JSON file."""
        storage_file = temp_config_dir / "browser_extension_videos.json"
        storage_file.write_text("{ invalid json }")

        provider = BrowserExtensionProvider()
        videos = provider.get_videos()

        assert videos == []  # Returns empty list on error

    def test_browser_extension_provider_implements_interface(self, temp_config_dir):
        """Test that BrowserExtensionProvider implements HistoryProvider."""
        provider = BrowserExtensionProvider()
        assert isinstance(provider, HistoryProvider)
        assert hasattr(provider, "get_videos")
        assert callable(provider.get_videos)


class TestYouTubeAPIProvider:
    """Test YouTube API provider (with mocking to avoid auth issues)."""

    def test_youtube_api_provider_graceful_empty_response(self):
        """Test that empty response is handled gracefully."""
        # Import first to avoid lazy loading issues
        import sys
        from yt_rag.providers import youtube_api_provider

        # Mock YouTubeAPI to return empty list
        with patch.object(youtube_api_provider, "YouTubeAPI") as mock_youtube:
            mock_instance = MagicMock()
            mock_instance.fetch_watch_history.return_value = []
            mock_youtube.return_value = mock_instance

            provider = youtube_api_provider.YouTubeAPIProvider()
            videos = provider.get_videos()

            assert videos == []

    def test_youtube_api_provider_returns_videos(self):
        """Test that videos are returned in correct format."""
        mock_videos = [
            {
                "video_id": "dQw4w9WgXcQ",
                "title": "Never Gonna Give You Up",
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "watch_date": "2024-10-15T10:30:00",
            }
        ]

        from yt_rag.providers import youtube_api_provider

        with patch.object(youtube_api_provider, "YouTubeAPI") as mock_youtube:
            mock_instance = MagicMock()
            mock_instance.fetch_watch_history.return_value = mock_videos
            mock_youtube.return_value = mock_instance

            provider = youtube_api_provider.YouTubeAPIProvider()
            videos = provider.get_videos()

            assert len(videos) == 1
            assert videos[0]["video_id"] == "dQw4w9WgXcQ"

    def test_youtube_api_provider_implements_interface(self):
        """Test that YouTubeAPIProvider implements HistoryProvider."""
        from yt_rag.providers import youtube_api_provider

        with patch.object(youtube_api_provider, "YouTubeAPI"):
            provider_class = youtube_api_provider.YouTubeAPIProvider
            # Check class structure without instantiating
            assert issubclass(provider_class, HistoryProvider)

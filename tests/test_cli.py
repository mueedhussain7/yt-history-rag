import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from yt_rag.cli import app


@pytest.fixture
def cli_runner():
    return CliRunner()


@pytest.fixture
def temp_config_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("yt_rag.config.get_config_dir", return_value=Path(tmpdir)):
            with patch("yt_rag.cli.get_config_dir", return_value=Path(tmpdir)):
                yield Path(tmpdir)


def test_init_command_without_oauth_credentials(cli_runner, temp_config_dir):
    """Test init when OAuth credentials are not set."""
    with patch("yt_rag.config.get_config_dir", return_value=temp_config_dir):
        with patch("yt_rag.cli.get_config_dir", return_value=temp_config_dir):
            # Clear OAuth env vars
            with patch.dict(os.environ, {"YOUTUBE_CLIENT_ID": "", "YOUTUBE_CLIENT_SECRET": ""}):
                result = cli_runner.invoke(app, ["init"])

    assert result.exit_code == 0
    assert "YouTube credentials not found!" in result.stdout
    assert "See .env.example for instructions" in result.stdout

    # Directories should still be created
    assert (temp_config_dir / "chroma_db").exists()
    assert (temp_config_dir / "neo4j_data").exists()


def test_init_command_with_oauth_credentials(cli_runner, temp_config_dir):
    """Test init when OAuth credentials are set."""
    with patch("yt_rag.config.get_config_dir", return_value=temp_config_dir):
        with patch("yt_rag.cli.get_config_dir", return_value=temp_config_dir):
            with patch("yt_rag.cli.authenticate_youtube") as mock_auth:
                # Set OAuth env vars
                mock_creds = MagicMock()
                mock_auth.return_value = mock_creds

                with patch.dict(
                    os.environ,
                    {
                        "YOUTUBE_CLIENT_ID": "test_client_id",
                        "YOUTUBE_CLIENT_SECRET": "test_secret",
                    },
                ):
                    result = cli_runner.invoke(app, ["init"])

    assert result.exit_code == 0, f"Exit code: {result.exit_code}, Output: {result.stdout}"
    assert "Project initialized successfully!" in result.stdout
    assert "Successfully authenticated with YouTube!" in result.stdout

    # Check directories were created
    assert (temp_config_dir / "chroma_db").exists()
    assert (temp_config_dir / "neo4j_data").exists()
    assert (temp_config_dir / "config.yaml").exists()


def test_init_command_legacy(cli_runner, temp_config_dir):
    """Test basic init command without OAuth (backward compatibility)."""
    with patch("yt_rag.config.get_config_dir", return_value=temp_config_dir):
        with patch("yt_rag.cli.get_config_dir", return_value=temp_config_dir):
            result = cli_runner.invoke(app, ["init"])

    assert result.exit_code == 0
    # Check that directories were created
    assert (temp_config_dir / "chroma_db").exists()
    assert (temp_config_dir / "neo4j_data").exists()
    # Check that config file was created
    assert (temp_config_dir / "config.yaml").exists()


def test_sync_command_not_authenticated(cli_runner, temp_config_dir):
    """Test sync command when user is not authenticated."""
    with patch("yt_rag.config.get_config_dir", return_value=temp_config_dir):
        with patch("yt_rag.cli.YouTubeAPI") as mock_api:
            mock_api.side_effect = Exception("Not authenticated")

            result = cli_runner.invoke(app, ["sync"])

    assert result.exit_code == 0
    assert "Not authenticated" in result.stdout


def test_sync_command_with_new_videos(cli_runner, temp_config_dir):
    """Test sync command successfully fetching new videos."""
    with patch("yt_rag.config.get_config_dir", return_value=temp_config_dir):
        with patch("yt_rag.cli.YouTubeAPI") as mock_api_class:
            # Mock the YouTube API
            mock_api = MagicMock()
            mock_api_class.return_value = mock_api

            # Mock fetch_watch_history to return videos
            mock_api.fetch_watch_history.return_value = [
                {"video_id": "vid1", "title": "Video 1", "url": "http://...", "watch_date": "2026-06-21"},
                {"video_id": "vid2", "title": "Video 2", "url": "http://...", "watch_date": "2026-06-20"},
            ]

            result = cli_runner.invoke(app, ["sync"])

    assert result.exit_code == 0
    assert "Sync complete!" in result.stdout
    assert "2" in result.stdout  # Should show 2 new videos


def test_sync_command_no_new_videos(cli_runner, temp_config_dir):
    """Test sync command when there are no new videos."""
    with patch("yt_rag.config.get_config_dir", return_value=temp_config_dir):
        with patch("yt_rag.cli.YouTubeAPI") as mock_api_class:
            with patch("yt_rag.cli.load_sync_state") as mock_load_state:
                # Setup: already have these videos
                mock_load_state.return_value = {
                    "indexed_video_ids": ["vid1", "vid2"],
                    "sync_stats": {"total_indexed": 2, "total_failed": 0},
                }

                mock_api = MagicMock()
                mock_api_class.return_value = mock_api
                mock_api.fetch_watch_history.return_value = [
                    {"video_id": "vid1", "title": "Video 1", "url": "http://...", "watch_date": "2026-06-21"},
                    {"video_id": "vid2", "title": "Video 2", "url": "http://...", "watch_date": "2026-06-20"},
                ]

                result = cli_runner.invoke(app, ["sync"])

    assert result.exit_code == 0
    assert "Nothing new to sync!" in result.stdout

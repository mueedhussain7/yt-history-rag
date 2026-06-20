import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from yt_rag.transcript import TranscriptExtractor
from yt_rag.config import get_transcript_path, transcript_exists, save_transcript, load_transcript


@pytest.fixture
def temp_config_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("yt_rag.transcript.get_config_dir", return_value=Path(tmpdir)):
            with patch("yt_rag.config.get_config_dir", return_value=Path(tmpdir)):
                yield Path(tmpdir)


@pytest.fixture
def extractor(temp_config_dir):
    """Create a TranscriptExtractor instance."""
    return TranscriptExtractor()


def test_extractor_init(extractor, temp_config_dir):
    """Test TranscriptExtractor initialization."""
    assert extractor.transcripts_dir.exists()
    assert extractor.transcripts_dir.name == "transcripts"


def test_get_transcript_path(extractor):
    """Test getting path for a transcript."""
    path = extractor.get_transcript_path("vid123")
    assert path.name == "vid123.txt"
    assert "transcripts" in str(path)


def test_transcript_exists_when_not_saved(extractor):
    """Test that transcript_exists returns False when not saved."""
    assert not extractor.transcript_exists("nonexistent")


def test_transcript_exists_when_saved(extractor):
    """Test that transcript_exists returns True when saved."""
    extractor._save_transcript("vid123", "Hello world")
    assert extractor.transcript_exists("vid123")


def test_save_and_load_transcript(extractor):
    """Test saving and loading a transcript."""
    video_id = "vid123"
    transcript_text = "This is a test transcript.\nWith multiple lines."

    # Save
    extractor._save_transcript(video_id, transcript_text)

    # Load
    loaded = extractor._load_transcript(video_id)

    assert loaded == transcript_text


def test_extract_transcript_when_already_cached(extractor):
    """Test that extract_transcript returns cached version if exists."""
    video_id = "vid123"
    cached_text = "Cached transcript"

    # Pre-save a transcript
    extractor._save_transcript(video_id, cached_text)

    # Extract should return cached version without calling APIs
    transcript, error = extractor.extract_transcript(video_id)

    assert transcript == cached_text
    assert error is None


@patch("yt_rag.transcript.subprocess.run")
def test_extract_with_yt_dlp_success(mock_run, extractor, temp_config_dir):
    """Test successful transcript extraction with yt-dlp."""
    video_id = "vid123"

    # Mock yt-dlp success
    mock_run.return_value = MagicMock(returncode=0, stderr="")

    # Create a fake subtitle file that yt-dlp would create
    subtitle_path = extractor.transcripts_dir / f"{video_id}.en.vtt"
    subtitle_path.write_text("WEBVTT\n\n00:00:00.000 --> 00:00:05.000\nHello world")

    # Extract
    transcript, error = extractor.extract_transcript(video_id)

    assert transcript is not None
    assert "Hello world" in transcript
    assert error is None
    # Subtitle file should be cleaned up
    assert not subtitle_path.exists()


def test_get_transcript(extractor):
    """Test the convenience method get_transcript."""
    video_id = "vid123"
    text = "Test transcript"

    extractor._save_transcript(video_id, text)
    result = extractor.get_transcript(video_id)

    assert result == text


# Config module tests

def test_transcript_exists_config(temp_config_dir):
    """Test transcript_exists from config module."""
    video_id = "test_vid"

    # Should not exist initially
    assert not transcript_exists(video_id)

    # After saving
    save_transcript(video_id, "Test text")
    assert transcript_exists(video_id)


def test_save_and_load_transcript_config(temp_config_dir):
    """Test save_transcript and load_transcript from config module."""
    video_id = "vid456"
    text = "Config test transcript"

    # Save
    save_transcript(video_id, text)

    # Load
    loaded = load_transcript(video_id)

    assert loaded == text


def test_load_nonexistent_transcript(temp_config_dir):
    """Test loading a transcript that doesn't exist."""
    result = load_transcript("nonexistent")
    assert result is None


def test_save_creates_directory(temp_config_dir):
    """Test that save_transcript creates the transcripts directory."""
    video_id = "vid789"

    # Transcripts directory should be created
    save_transcript(video_id, "Test")

    from yt_rag.config import get_transcripts_dir
    assert get_transcripts_dir().exists()

import subprocess
from typing import Optional, Tuple
from pathlib import Path
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound
from .config import get_config_dir


class TranscriptExtractor:
    """
    Extract transcripts from YouTube videos.
    """

    def __init__(self):
        """Initialize transcript extractor."""
        self.transcripts_dir = get_config_dir() / "transcripts"
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)

    def get_transcript_path(self, video_id: str) -> Path:
        """Get the path where transcript will be saved."""
        return self.transcripts_dir / f"{video_id}.txt"

    def transcript_exists(self, video_id: str) -> bool:
        """Check if transcript already downloaded."""
        return self.get_transcript_path(video_id).exists()

    def extract_transcript(self, video_id: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract transcript from a YouTube video.

        Two methods:
        1. yt-dlp (primary - most reliable)
        2. youtube-transcript-api (fallback)

        Returns:
            (transcript_text, error_message)
            - If success: (transcript_text, None)
            - If failed: (None, error_reason)
        """
        # Check if already extracted
        if self.transcript_exists(video_id):
            return self._load_transcript(video_id), None

        # Try Method 1: yt-dlp
        transcript, error = self._extract_with_yt_dlp(video_id)
        if transcript:
            self._save_transcript(video_id, transcript)
            return transcript, None

        # Try Method 2: youtube-transcript-api (fallback)
        transcript, error = self._extract_with_youtube_api(video_id)
        if transcript:
            self._save_transcript(video_id, transcript)
            return transcript, None

        # Both methods failed
        return None, error

    def _extract_with_yt_dlp(self, video_id: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Try to extract transcript using yt-dlp.

        yt-dlp is a tool that downloads YouTube videos + captions.
        """
        try:
            # Run yt-dlp to get subtitles
            # --write-auto-subs: Get auto-generated captions if no manual ones
            # --skip-download: Only get captions, don't download video
            # --sub-format: Get best quality captions
            command = [
                "yt-dlp",
                "--write-subs",
                "--write-auto-subs",
                "--skip-download",
                "--sub-format", "best",
                "--output", "%(id)s",
                f"https://www.youtube.com/watch?v={video_id}",
            ]

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                # yt-dlp succeeded, read the subtitle file
                # Usually saves as: video_id.en.vtt or similar
                subtitle_files = list(self.transcripts_dir.glob(f"{video_id}.*"))
                if subtitle_files:
                    # Find the subtitle file (usually .en.vtt or .vtt)
                    subtitle_file = next(
                        (f for f in subtitle_files if f.suffix in [".vtt", ".srt"]),
                        None,
                    )
                    if subtitle_file:
                        transcript = subtitle_file.read_text()
                        # Clean up the subtitle file
                        subtitle_file.unlink()
                        return transcript, None

            return None, f"yt-dlp failed: {result.stderr}"

        except subprocess.TimeoutExpired:
            return None, "yt-dlp timeout (video too long?)"
        except FileNotFoundError:
            return None, "yt-dlp not installed"
        except Exception as e:
            return None, f"yt-dlp error: {str(e)}"

    def _extract_with_youtube_api(self, video_id: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Try to extract transcript using youtube-transcript-api.
        Python library that gets transcripts via YouTube's API.
        """
        try:
            # Get transcript
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id)

            # Convert to text format
            # transcript_list is list of dicts: [{"text": "hello", "start": 0, "duration": 1}, ...]
            transcript_text = "\n".join([item["text"] for item in transcript_list])

            return transcript_text, None

        except TranscriptsDisabled:
            return None, "Transcripts disabled for this video"
        except NoTranscriptFound:
            return None, "No transcript found"
        except Exception as e:
            return None, f"youtube-transcript-api error: {str(e)}"

    def _save_transcript(self, video_id: str, transcript: str) -> None:
        """Save transcript to file."""
        path = self.get_transcript_path(video_id)
        path.write_text(transcript)

    def _load_transcript(self, video_id: str) -> Optional[str]:
        """Load previously saved transcript."""
        path = self.get_transcript_path(video_id)
        if path.exists():
            return path.read_text()
        return None

    def get_transcript(self, video_id: str) -> Optional[str]:
        """
        Get transcript for a video (extract if not already done).
        """
        transcript, _ = self.extract_transcript(video_id)
        return transcript

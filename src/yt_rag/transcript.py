import re
import json
import subprocess
import html
from typing import Optional, Tuple, List, Dict
from pathlib import Path
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound
from yt_dlp import YoutubeDL
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

    def get_timestamps_path(self, video_id: str) -> Path:
        """Get the path where timestamp index will be saved."""
        return self.transcripts_dir / f"{video_id}.timestamps.json"

    def get_duration_path(self, video_id: str) -> Path:
        """Get the path where duration metadata will be saved."""
        return self.transcripts_dir / f"{video_id}.duration.json"

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
            return self._load_transcript(video_id), None

        # Try Method 2: youtube-transcript-api (fallback)
        transcript, error = self._extract_with_youtube_api(video_id)
        if transcript:
            self._save_transcript(video_id, transcript)
            return self._load_transcript(video_id), None

        # Both methods failed
        return None, error

    def _extract_with_yt_dlp(self, video_id: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract transcript + metadata using yt-dlp.
        - Uses CLI for reliable subtitle download + timestamp extraction
        - Uses extract_info() for metadata-only duration capture (no video download)
        - Combined approach is efficient: no video download, one subtitle fetch
        """
        try:
            # First: get metadata (duration) using extract_info() — metadata only, no download
            ydl_opts = {'skip_download': True, 'quiet': True, 'no_warnings': True}
            duration = None

            try:
                with YoutubeDL(ydl_opts) as ydl:
                    url = f"https://www.youtube.com/watch?v={video_id}"
                    info = ydl.extract_info(url, download=False)
                    duration = info.get('duration')
                    if duration:
                        self._save_duration(video_id, duration)
            except Exception:
                pass  # Duration is optional, continue without it

            # Second: download and process subtitles using CLI
            command = [
                "python3", "-m", "yt_dlp",
                "--write-subs",
                "--write-auto-subs",
                "--skip-download",
                "--sub-format", "best",
                "--output", str(self.transcripts_dir / "%(id)s"),
                f"https://www.youtube.com/watch?v={video_id}",
            ]

            result = subprocess.run(command, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                # Find and read subtitle file
                subtitle_files = list(self.transcripts_dir.glob(f"{video_id}.*"))
                if subtitle_files:
                    subtitle_file = next(
                        (f for f in subtitle_files if f.suffix in [".vtt", ".srt"]),
                        None,
                    )
                    if subtitle_file:
                        vtt_text = subtitle_file.read_text()
                        subtitle_file.unlink()

                        # Process subtitle to extract timestamps
                        transcript_text, timestamps = self._process_subtitles(vtt_text)

                        if not transcript_text:
                            return None, "yt-dlp: Failed to process subtitles"

                        # Save timestamp index
                        if timestamps:
                            self._save_timestamps(video_id, timestamps)

                        return transcript_text, None

            return None, f"yt-dlp failed: {result.stderr}"

        except subprocess.TimeoutExpired:
            return None, "yt-dlp timeout"
        except Exception as e:
            return None, f"yt-dlp error: {str(e)}"

    def _process_subtitles(self, vtt_text: str) -> Tuple[Optional[str], List[Dict]]:
        """
        Process VTT subtitle text into transcript and timestamp index.

        Args:
            vtt_text: Raw VTT format subtitle text

        Returns:
            (transcript_text, timestamps_list)
        """
        if not vtt_text:
            return None, []

        # Extract timestamps while cleaning WEBVTT
        lines = vtt_text.split('\n')
        transcript_lines = []
        timestamps = []
        current_time = None

        for line in lines:
            # Skip headers
            if line.startswith('WEBVTT') or line.startswith('Kind:') or line.startswith('Language:'):
                continue

            # Extract timestamp from VTT format: HH:MM:SS.mmm --> HH:MM:SS.mmm
            if '-->' in line:
                match = re.search(r'(\d{2}):(\d{2}):(\d{2})', line)
                if match:
                    h, m, s = int(match.group(1)), int(match.group(2)), int(match.group(3))
                    current_time = h * 3600 + m * 60 + s
                continue

            # Skip standalone timestamp lines
            if re.match(r'^\d{2}:\d{2}:\d{2}\.\d{3}', line):
                continue

            # Clean inline tags, markup, and HTML entities
            cleaned = re.sub(r'<\d{2}:\d{2}:\d{2}\.\d{3}><c>', '', line)
            cleaned = re.sub(r'</c>', '', cleaned)
            cleaned = html.unescape(cleaned)
            cleaned = cleaned.strip()

            if not cleaned:
                continue

            # Skip duplicates
            if transcript_lines and cleaned == transcript_lines[-1]:
                continue

            transcript_lines.append(cleaned)

            # Record timestamp if available
            if current_time is not None:
                timestamps.append({
                    "timestamp": current_time,
                    "text": cleaned
                })

        transcript_text = '\n'.join(transcript_lines)
        return transcript_text if transcript_text else None, timestamps

    def _save_duration(self, video_id: str, duration: int) -> None:
        """Save video duration in seconds."""
        path = self.get_duration_path(video_id)
        path.write_text(json.dumps({"video_id": video_id, "duration_seconds": duration}))

    def _save_timestamps(self, video_id: str, timestamps: List[Dict]) -> None:
        """Save timestamp index for Neo4j Timestamp nodes."""
        path = self.get_timestamps_path(video_id)
        path.write_text(json.dumps(timestamps, indent=2))

    def _extract_with_youtube_api(self, video_id: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Try to extract transcript using youtube-transcript-api (v1.2.4+).
        Uses instance-based API: YouTubeTranscriptApi().fetch(video_id)
        """
        try:
            # Get transcript using the new instance-based API
            fetched_transcript = YouTubeTranscriptApi().fetch(video_id)

            # fetched_transcript is a FetchedTranscript object, convert to text
            # Each item is a FetchedTranscriptSnippet with .text, .start, .duration attributes
            transcript_text = "\n".join([item.text for item in fetched_transcript])

            return transcript_text, None

        except TranscriptsDisabled:
            return None, "Transcripts disabled for this video"
        except NoTranscriptFound:
            return None, "No transcript found"
        except Exception as e:
            return None, f"youtube-transcript-api error: {str(e)}"

    def _clean_webvtt(self, text: str) -> str:
        """
        Clean WEBVTT caption markup from raw transcript.
        Removes headers, timestamps, inline tags, HTML entities, and deduplicates.
        """
        lines = []

        for line in text.split('\n'):
            if line.startswith('WEBVTT') or line.startswith('Kind:') or line.startswith('Language:'):
                continue

            if '-->' in line or re.match(r'^\d{2}:\d{2}:\d{2}\.\d{3}', line):
                continue

            cleaned = re.sub(r'<\d{2}:\d{2}:\d{2}\.\d{3}><c>', '', line)
            cleaned = re.sub(r'</c>', '', cleaned)
            cleaned = html.unescape(cleaned)
            cleaned = cleaned.strip()

            if not cleaned:
                continue

            if lines and cleaned == lines[-1]:
                continue

            lines.append(cleaned)

        return '\n'.join(lines)

    def _save_transcript(self, video_id: str, transcript: str) -> None:
        """Save transcript to file, with WEBVTT markup cleaned."""
        clean_transcript = self._clean_webvtt(transcript)
        path = self.get_transcript_path(video_id)
        path.write_text(clean_transcript)

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

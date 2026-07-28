import re
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
from .base import HistoryProvider


class GoogleTakeoutProvider(HistoryProvider):
    """Provider for parsing watch history from Google Takeout HTML export."""

    def __init__(self, file_path: str):
        """
        Initialize Takeout provider with path to watch-history.html.

        Args:
            file_path: Path to watch-history.html from Google Takeout

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file is not valid HTML
        """
        self.file_path = Path(file_path)

        if not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {self.file_path}")

        if not self.file_path.name.endswith(".html"):
            raise ValueError("File must be an HTML file (watch-history.html)")

    def get_videos(self) -> List[Dict[str, Any]]:
        """
        Parse watch-history.html and extract videos.

        Returns:
            List of videos with keys: video_id, title, url, watch_date
        """
        videos = []

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            # Try with different encoding
            with open(self.file_path, "r", encoding="latin-1") as f:
                content = f.read()

        # Find all YouTube video links: <a href="https://www.youtube.com/watch?v=VIDEO_ID">Title</a>
        # Pattern: href="https://www.youtube.com/watch?v=..." followed by title in >text<
        pattern = r'<a href="(https://www\.youtube\.com/watch\?v=([a-zA-Z0-9_-]{11}))">([^<]+)</a>'

        matches = re.finditer(pattern, content)

        for match in matches:
            url = match.group(1)
            video_id = match.group(2)
            title = match.group(3)

            # Remove HTML entities (e.g., &amp; -> &, &#39; -> ')
            title = self._unescape_html(title)

            # Try to extract watch date from the text after the link
            watch_date = self._extract_watch_date(content, match.end())

            videos.append({
                "video_id": video_id,
                "title": title,
                "url": url,
                "watch_date": watch_date,
            })

        if not videos:
            import sys
            print(
                f"\n⚠️  WARNING: No videos found in {self.file_path}\n"
                "Make sure this is a valid watch-history.html from Google Takeout.\n",
                file=sys.stderr
            )

        return videos

    def _unescape_html(self, text: str) -> str:
        """Remove common HTML entities from text."""
        replacements = {
            "&amp;": "&",
            "&lt;": "<",
            "&gt;": ">",
            "&quot;": '"',
            "&#39;": "'",
            "&apos;": "'",
        }
        for entity, char in replacements.items():
            text = text.replace(entity, char)
        return text

    def _extract_watch_date(self, content: str, start_pos: int) -> str:
        """
        Extract watch date from HTML following a video link.

        Google Takeout format typically has:
        <a href="...">Title</a>
        <br>
        <div class="content-cell ...">
        Watched on Date
        </div>

        Returns ISO format date string or empty string if not found.
        """
        # Look ahead from start_pos for date pattern
        lookahead = content[start_pos:start_pos + 500]

        # Try to find "Watched on" followed by a date
        # Pattern: "Watched on" followed by date like "Oct 15, 2023" or similar
        date_pattern = r"Watched on\s+([A-Za-z]+ \d{1,2}, \d{4})"
        match = re.search(date_pattern, lookahead)

        if match:
            date_str = match.group(1)
            try:
                # Parse date and convert to ISO format
                dt = datetime.strptime(date_str, "%b %d, %Y")
                return dt.isoformat()
            except ValueError:
                return ""

        return ""

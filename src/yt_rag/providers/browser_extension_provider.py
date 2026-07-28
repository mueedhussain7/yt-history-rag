import json
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
from .base import HistoryProvider
from ..config import get_config_dir


class BrowserExtensionProvider(HistoryProvider):
    """Provider for videos recorded by the browser extension."""

    def __init__(self):
        """Initialize browser extension provider."""
        self.storage_file = get_config_dir() / "browser_extension_videos.json"

    def get_videos(self) -> List[Dict[str, Any]]:
        """
        Read videos from browser extension storage.

        Returns:
            List of videos with keys: video_id, title, url, watch_date
        """
        if not self.storage_file.exists():
            return []

        try:
            with open(self.storage_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("videos", [])
        except (json.JSONDecodeError, IOError):
            return []

    def record_video(self, video_data: Dict[str, str]) -> bool:
        """
        Record a video from the browser extension.

        Args:
            video_data: Dict with keys: video_id, title, url, watch_date

        Returns:
            True if successful, False otherwise
        """
        try:
            # Load existing videos
            if self.storage_file.exists():
                with open(self.storage_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = {"videos": []}

            # Check if video already exists (avoid duplicates)
            existing_ids = {v["video_id"] for v in data.get("videos", [])}
            if video_data["video_id"] in existing_ids:
                return True  # Already recorded

            # Add new video
            data["videos"].append(video_data)

            # Save back to file
            with open(self.storage_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            return True
        except Exception as e:
            import sys
            print(f"Error recording video: {str(e)}", file=sys.stderr)
            return False


def start_extension_server():
    """
    Start FastAPI server for receiving videos from browser extension.
    Listens on localhost:8765
    """
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn

    app = FastAPI(title="yt-rag Browser Extension Receiver")

    # Enable CORS for browser extension
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    provider = BrowserExtensionProvider()

    @app.post("/record_video")
    async def record_video(video: Dict[str, str]):
        """
        Receive a video recording from the browser extension.

        Expected JSON:
        {
            "video_id": "dQw4w9WgXcQ",
            "title": "Never Gonna Give You Up",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "watch_date": "2024-01-15T10:30:00"
        }
        """
        success = provider.record_video(video)

        if success:
            return {
                "status": "ok",
                "message": f"Recorded: {video.get('title', 'Unknown')}",
            }
        else:
            return {
                "status": "error",
                "message": "Failed to record video",
            }

    @app.get("/health")
    async def health():
        """Health check endpoint."""
        return {"status": "ok"}

    @app.on_event("startup")
    async def startup():
        """Print startup message."""
        print("✓ yt-rag extension receiver started on http://localhost:8765")
        print("  Waiting for videos from Chrome extension...")
        print("  Press Ctrl+C to stop")

    # Run server
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8765,
        log_level="info",
    )

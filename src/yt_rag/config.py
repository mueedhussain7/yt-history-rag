import os
import yaml
import json
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime


def get_config_dir() -> Path:
    return Path.home() / ".yt-rag"


def get_config_path() -> Path:
    return get_config_dir() / "config.yaml"


def create_config_template() -> Dict[str, Any]:
    return {
        "youtube": {
            "client_id": None,
            "client_secret": None,
        },
        "sync": {
            "schedule": "manual",
            "interval_hours": 24,
        },
        "embeddings": {
            "model": "sentence-transformers/all-MiniLM-L6-v2",
        },
        "concept_extraction": {
            "provider": "openrouter",
            "model": "meta-llama/llama-2-70b-chat",
        },
        "transcript": {
            "source": "yt-dlp",
        },
        "storage": {
            "chroma_db_path": str(get_config_dir() / "chroma_db"),
            "neo4j_uri": "bolt://localhost:7687",
        },
    }


def load_config() -> Dict[str, Any]:
    config_path = get_config_path()
    if not config_path.exists():
        return create_config_template()

    with open(config_path, "r") as f:
        return yaml.safe_load(f) or {}


def save_config(config: Dict[str, Any]) -> None:
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def get_sync_state_path() -> Path:
    """Get path to sync state file."""
    return get_config_dir() / "sync_state.json"


def create_sync_state_template() -> Dict[str, Any]:
    """
    Create a template for sync state.
    """
    return {
        "last_sync_time": None,
        "indexed_video_ids": [],
        "sync_stats": {
            "total_indexed": 0,
            "total_failed": 0,
        },
    }


def load_sync_state() -> Dict[str, Any]:
    """
    Load sync state from file.
    """
    sync_state_path = get_sync_state_path()

    if not sync_state_path.exists():
        return create_sync_state_template()

    try:
        with open(sync_state_path, "r") as f:
            return json.load(f)
    except Exception:
        return create_sync_state_template()


def save_sync_state(sync_state: Dict[str, Any]) -> None:
    """
    Save sync state to file.
    """
    sync_state_path = get_sync_state_path()
    sync_state_path.parent.mkdir(parents=True, exist_ok=True)

    with open(sync_state_path, "w") as f:
        json.dump(sync_state, f, indent=2)


def update_sync_state(video_ids: list, failed_count: int = 0) -> None:
    """
    Update sync state after fetching videos.

    Args:
        video_ids: List of video IDs we just fetched
        failed_count: How many videos failed to process
    """
    sync_state = load_sync_state()

    # Add new video IDs (avoid duplicates)
    existing_ids = set(sync_state.get("indexed_video_ids", []))
    new_ids = existing_ids.union(set(video_ids))

    sync_state.update({
        "last_sync_time": datetime.now().isoformat(),
        "indexed_video_ids": list(new_ids),
        "sync_stats": {
            "total_indexed": len(new_ids),
            "total_failed": sync_state.get("sync_stats", {}).get("total_failed", 0) + failed_count,
        },
    })

    save_sync_state(sync_state)


def get_transcripts_dir() -> Path:
    """Get directory where transcripts are stored."""
    return get_config_dir() / "transcripts"


def get_transcript_path(video_id: str) -> Path:
    """Get path to a specific transcript file."""
    return get_transcripts_dir() / f"{video_id}.txt"


def transcript_exists(video_id: str) -> bool:
    """Check if transcript already exists."""
    return get_transcript_path(video_id).exists()


def save_transcript(video_id: str, transcript_text: str) -> None:
    """
    Save transcript to file.

    Args:
        video_id: YouTube video ID
        transcript_text: The transcript text to save
    """
    transcripts_dir = get_transcripts_dir()
    transcripts_dir.mkdir(parents=True, exist_ok=True)

    transcript_path = get_transcript_path(video_id)
    transcript_path.write_text(transcript_text)


def load_transcript(video_id: str) -> Optional[str]:
    """
    Load transcript from file if it exists.

    Args:
        video_id: YouTube video ID

    Returns:
        Transcript text or None if not found
    """
    transcript_path = get_transcript_path(video_id)
    if transcript_path.exists():
        return transcript_path.read_text()
    return None


def get_all_transcripts() -> Dict[str, str]:
    """
    Get all saved transcripts.

    Returns:
        Dict mapping video_id to transcript text
    """
    transcripts_dir = get_transcripts_dir()
    if not transcripts_dir.exists():
        return {}

    transcripts = {}
    for transcript_file in transcripts_dir.glob("*.txt"):
        video_id = transcript_file.stem  # filename without .txt
        transcripts[video_id] = transcript_file.read_text()

    return transcripts

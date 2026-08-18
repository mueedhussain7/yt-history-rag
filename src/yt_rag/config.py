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


def get_config_value(key_path: str) -> Any:
    """
    Get a config value using dot notation (e.g., 'youtube.client_id').

    Args:
        key_path: Dot-separated path to config key

    Returns:
        The config value

    Raises:
        KeyError: If key path does not exist
    """
    config = load_config()
    keys = key_path.split('.')
    value = config

    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            valid_paths = _get_valid_paths(load_config())
            raise KeyError(
                f"Config key '{key_path}' not found.\n"
                f"Valid keys: {', '.join(sorted(valid_paths))}"
            )
    return value


def set_config_value(key_path: str, value: str) -> None:
    """
    Set a config value using dot notation (e.g., 'youtube.client_id').
    Performs type coercion based on existing value type.

    Args:
        key_path: Dot-separated path to config key
        value: String value to set

    Raises:
        KeyError: If key path does not exist
        ValueError: If type coercion fails
    """
    config = load_config()
    keys = key_path.split('.')
    current = config

    # Navigate to parent of final key
    for key in keys[:-1]:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            raise KeyError(f"Config path '{key_path}' does not exist")

    # Get final key and existing value
    final_key = keys[-1]
    if not isinstance(current, dict) or final_key not in current:
        raise KeyError(f"Config key '{key_path}' does not exist")

    existing_value = current[final_key]

    # Type coercion based on existing value type
    if isinstance(existing_value, bool):
        if value.lower() in ('true', '1', 'yes'):
            current[final_key] = True
        elif value.lower() in ('false', '0', 'no'):
            current[final_key] = False
        else:
            raise ValueError(f"Expected boolean for '{key_path}', got '{value}'")
    elif isinstance(existing_value, int):
        try:
            current[final_key] = int(value)
        except ValueError:
            raise ValueError(f"Expected integer for '{key_path}', got '{value}'")
    elif isinstance(existing_value, float):
        try:
            current[final_key] = float(value)
        except ValueError:
            raise ValueError(f"Expected numeric value for '{key_path}', got '{value}'")
    else:
        # String or None
        current[final_key] = value

    save_config(config)


def _get_valid_paths(config: Dict[str, Any], prefix: str = "") -> list:
    """Helper to list all valid config paths for error messages."""
    paths = []
    for key, value in config.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            paths.extend(_get_valid_paths(value, full_key))
        else:
            paths.append(full_key)
    return paths


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


def get_concepts_dir() -> Path:
    """Get directory where concepts are stored."""
    return get_config_dir() / "concepts"


def get_concept_path(video_id: str) -> Path:
    """Get path to a specific concept file."""
    return get_concepts_dir() / f"{video_id}.json"


def save_concepts(video_id: str, concepts: list) -> None:
    """
    Save extracted concepts to file.

    Args:
        video_id: YouTube video ID
        concepts: List of concept dicts with 'name' and 'description'
    """
    concepts_dir = get_concepts_dir()
    concepts_dir.mkdir(parents=True, exist_ok=True)

    concept_path = get_concept_path(video_id)
    with open(concept_path, "w") as f:
        json.dump(concepts, f, indent=2)


def load_concepts(video_id: str) -> Optional[list]:
    """
    Load extracted concepts from file.

    Args:
        video_id: YouTube video ID

    Returns:
        List of concepts or None if not found
    """
    concept_path = get_concept_path(video_id)
    if concept_path.exists():
        with open(concept_path, "r") as f:
            return json.load(f)
    return None


def concepts_exist(video_id: str) -> bool:
    """Check if concepts have been extracted for a video."""
    return get_concept_path(video_id).exists()


def load_timestamps(video_id: str) -> Optional[list]:
    """
    Load transcript timestamps from file.

    Args:
        video_id: YouTube video ID

    Returns:
        List of timestamps or None if not found
    """
    timestamps_path = get_config_dir() / "transcripts" / f"{video_id}.timestamps.json"
    if timestamps_path.exists():
        with open(timestamps_path, "r") as f:
            return json.load(f)
    return None


def find_timestamps_for_concept(concept_name: str, timestamps_data: list) -> list:
    """
    Find timestamps where concept appears using word-based matching (Option A).

    Splits concept name into significant words (len > 2, not stop words),
    matches if any word appears in timestamp text.

    Args:
        concept_name: Concept name (e.g., "Neural Networks")
        timestamps_data: List of {"timestamp": int, "text": str} dicts

    Returns:
        List of timestamp_seconds matching the concept
    """
    import string

    stop_words = {
        'the', 'a', 'an', 'and', 'or', 'is', 'are', 'was', 'were',
        'to', 'of', 'in', 'on', 'at', 'by', 'with', 'from', 'as',
        'that', 'this', 'it', 'for', 'be', 'have', 'has', 'had',
        'do', 'does', 'did', 'can', 'could', 'will', 'would', 'may',
        'might', 'must', 'should', 'shall', 'about', 'above', 'after'
    }

    # Extract significant words from concept name
    words = concept_name.lower().translate(
        str.maketrans('', '', string.punctuation)
    ).split()
    significant_words = [w for w in words if w and w not in stop_words and len(w) > 2]

    if not significant_words:
        return []

    matching_timestamps = []
    for ts_entry in timestamps_data:
        text = ts_entry["text"].lower().translate(
            str.maketrans('', '', string.punctuation)
        )
        text_words = text.split()

        # Match if ANY significant word appears in timestamp text
        if any(word in text_words for word in significant_words):
            matching_timestamps.append(ts_entry["timestamp"])

    return matching_timestamps

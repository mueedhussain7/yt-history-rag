import os
import yaml
from pathlib import Path
from typing import Any, Dict, Optional


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

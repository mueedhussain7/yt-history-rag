import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch
from yt_rag.config import (
    get_sync_state_path,
    create_sync_state_template,
    load_sync_state,
    save_sync_state,
    update_sync_state,
)


@pytest.fixture
def temp_config_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("yt_rag.config.get_config_dir", return_value=Path(tmpdir)):
            yield Path(tmpdir)


def test_get_sync_state_path(temp_config_dir):
    """Test that we get the correct path for sync state."""
    path = get_sync_state_path()
    assert path.name == "sync_state.json"


def test_create_sync_state_template():
    """Test creating a blank sync state template."""
    template = create_sync_state_template()

    assert "last_sync_time" in template
    assert "indexed_video_ids" in template
    assert "sync_stats" in template
    assert template["last_sync_time"] is None
    assert template["indexed_video_ids"] == []
    assert template["sync_stats"]["total_indexed"] == 0
    assert template["sync_stats"]["total_failed"] == 0


def test_load_sync_state_when_none_exist(temp_config_dir):
    """Test loading sync state when file doesn't exist."""
    state = load_sync_state()

    assert state is not None
    assert state["last_sync_time"] is None
    assert state["indexed_video_ids"] == []


def test_save_sync_state(temp_config_dir):
    """Test saving sync state to file."""
    sync_state = {
        "last_sync_time": "2026-06-21T10:30:00",
        "indexed_video_ids": ["vid1", "vid2", "vid3"],
        "sync_stats": {"total_indexed": 3, "total_failed": 0},
    }

    save_sync_state(sync_state)

    # Verify file was created
    sync_path = get_sync_state_path()
    assert sync_path.exists()

    # Verify contents
    with open(sync_path) as f:
        saved = json.load(f)
    assert saved == sync_state


def test_load_sync_state_after_save(temp_config_dir):
    """Test loading sync state after saving it."""
    original = {
        "last_sync_time": "2026-06-21T10:30:00",
        "indexed_video_ids": ["vid1", "vid2"],
        "sync_stats": {"total_indexed": 2, "total_failed": 0},
    }

    save_sync_state(original)
    loaded = load_sync_state()

    assert loaded == original


def test_update_sync_state_new_videos(temp_config_dir):
    """Test updating sync state with new videos."""
    # Start with empty state
    initial_state = load_sync_state()
    assert len(initial_state["indexed_video_ids"]) == 0

    # Add some videos
    new_video_ids = ["vid1", "vid2", "vid3"]
    update_sync_state(new_video_ids)

    # Load and verify
    updated_state = load_sync_state()
    assert len(updated_state["indexed_video_ids"]) == 3
    assert set(updated_state["indexed_video_ids"]) == set(new_video_ids)
    assert updated_state["sync_stats"]["total_indexed"] == 3


def test_update_sync_state_no_duplicates(temp_config_dir):
    """Test that updating sync state doesn't create duplicates."""
    # First update
    update_sync_state(["vid1", "vid2"])
    state1 = load_sync_state()
    assert len(state1["indexed_video_ids"]) == 2

    # Second update with same videos
    update_sync_state(["vid2", "vid3"])
    state2 = load_sync_state()

    # Should have 3 unique videos, not 4
    assert len(state2["indexed_video_ids"]) == 3
    assert set(state2["indexed_video_ids"]) == {"vid1", "vid2", "vid3"}


def test_update_sync_state_with_failures(temp_config_dir):
    """Test updating sync state and tracking failures."""
    update_sync_state(["vid1", "vid2"], failed_count=2)

    state = load_sync_state()
    assert state["sync_stats"]["total_indexed"] == 2
    assert state["sync_stats"]["total_failed"] == 2

    # Add more with failures
    update_sync_state(["vid3"], failed_count=1)
    state2 = load_sync_state()
    assert state2["sync_stats"]["total_indexed"] == 3
    assert state2["sync_stats"]["total_failed"] == 3


def test_sync_state_persistence(temp_config_dir):
    """Test that sync state persists across multiple saves/loads."""
    # Simulate multiple syncs
    update_sync_state(["vid1", "vid2"])
    update_sync_state(["vid3", "vid4"])
    update_sync_state(["vid5"])

    final_state = load_sync_state()
    assert len(final_state["indexed_video_ids"]) == 5
    assert final_state["sync_stats"]["total_indexed"] == 5

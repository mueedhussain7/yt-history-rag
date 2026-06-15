import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch
from yt_rag.config import (
    get_config_dir,
    get_config_path,
    create_config_template,
    load_config,
    save_config,
)


@pytest.fixture
def temp_config_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("yt_rag.config.get_config_dir", return_value=Path(tmpdir)):
            yield Path(tmpdir)


def test_create_config_template():
    config = create_config_template()

    assert "youtube" in config
    assert "sync" in config
    assert "embeddings" in config
    assert "concept_extraction" in config
    assert "transcript" in config
    assert "storage" in config

    assert config["youtube"]["data_api_key"] is None
    assert config["sync"]["schedule"] == "manual"


def test_save_and_load_config(temp_config_dir):
    config = create_config_template()
    save_config(config)

    loaded_config = load_config()
    assert loaded_config == config


def test_save_config_creates_directory(temp_config_dir):
    config = create_config_template()
    save_config(config)

    config_path = get_config_path()
    assert config_path.exists()
    assert config_path.parent.exists()


def test_load_config_returns_template_if_not_exists(temp_config_dir):
    loaded_config = load_config()
    template = create_config_template()

    assert loaded_config == template

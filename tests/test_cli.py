import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch
from typer.testing import CliRunner
from yt_rag.cli import app


@pytest.fixture
def cli_runner():
    return CliRunner()


@pytest.fixture
def temp_config_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("yt_rag.config.get_config_dir", return_value=Path(tmpdir)):
            with patch("yt_rag.cli.get_config_dir", return_value=Path(tmpdir)):
                yield Path(tmpdir)


def test_init_command(cli_runner, temp_config_dir):
    with patch("yt_rag.config.get_config_dir", return_value=temp_config_dir):
        with patch("yt_rag.cli.get_config_dir", return_value=temp_config_dir):
            result = cli_runner.invoke(app, [])

    assert result.exit_code == 0, f"Exit code: {result.exit_code}, Output: {result.stdout}"
    assert "Project initialized successfully!" in result.stdout

    # Check that directories were created
    assert (temp_config_dir / "chroma_db").exists()
    assert (temp_config_dir / "neo4j_data").exists()

    # Check that config file was created
    assert (temp_config_dir / "config.yaml").exists()

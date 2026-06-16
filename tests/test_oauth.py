import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from yt_rag.oauth import (
    authenticate_youtube,
    save_credentials,
    load_credentials,
    is_authenticated,
    get_credentials_path,
)


@pytest.fixture
def temp_config_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("yt_rag.config.get_config_dir", return_value=Path(tmpdir)):
            yield Path(tmpdir)


def test_get_credentials_path(temp_config_dir):
    """Test that we get the correct path for storing credentials."""
    creds_path = get_credentials_path()
    assert creds_path.name == "youtube_token.json"
    assert str(temp_config_dir) in str(creds_path)


def test_is_authenticated_when_no_credentials(temp_config_dir):
    """Test that is_authenticated returns False when no credentials exist."""
    result = is_authenticated()
    assert result is False


def test_is_authenticated_when_credentials_exist(temp_config_dir):
    """Test that is_authenticated returns True when credentials file exists."""
    creds_path = get_credentials_path()
    creds_path.parent.mkdir(parents=True, exist_ok=True)
    creds_path.write_text('{"type": "authorized_user"}')

    result = is_authenticated()
    assert result is True


def test_save_credentials(temp_config_dir):
    """Test that credentials are saved correctly to file."""
    # Create a mock credentials object
    mock_creds = MagicMock()
    mock_creds.to_json.return_value = '{"type": "authorized_user", "token": "abc123"}'

    save_credentials(mock_creds)

    # Check that the file was created
    creds_path = get_credentials_path()
    assert creds_path.exists()
    assert creds_path.read_text() == '{"type": "authorized_user", "token": "abc123"}'


def test_load_credentials_when_none_exist(temp_config_dir):
    """Test that load_credentials returns None when no credentials exist."""
    result = load_credentials()
    assert result is None


def test_load_credentials_when_they_exist(temp_config_dir):
    """Test that load_credentials loads saved credentials."""
    # Create a fake credentials file
    creds_path = get_credentials_path()
    creds_path.parent.mkdir(parents=True, exist_ok=True)
    creds_path.write_text('{"type": "authorized_user", "token": "test_token"}')

    with patch("yt_rag.oauth.Credentials.from_authorized_user_file") as mock_load:
        mock_creds = MagicMock()
        mock_creds.expired = False
        mock_load.return_value = mock_creds

        result = load_credentials()

        assert result is not None
        mock_load.assert_called_once()


def test_load_credentials_refreshes_expired_token(temp_config_dir):
    """Test that expired tokens are automatically refreshed."""
    creds_path = get_credentials_path()
    creds_path.parent.mkdir(parents=True, exist_ok=True)
    creds_path.write_text('{"type": "authorized_user"}')

    with patch("yt_rag.oauth.Credentials.from_authorized_user_file") as mock_load:
        with patch("yt_rag.oauth.Request"):
            with patch("yt_rag.oauth.save_credentials") as mock_save:
                mock_creds = MagicMock()
                mock_creds.expired = True
                mock_creds.refresh_token = "refresh_token_123"
                mock_load.return_value = mock_creds

                result = load_credentials()

                # Check that refresh was called
                mock_creds.refresh.assert_called_once()
                # Check that credentials were saved after refresh
                mock_save.assert_called_once()


@patch("yt_rag.oauth.InstalledAppFlow")
def test_authenticate_youtube_with_no_saved_credentials(
    mock_flow_class, temp_config_dir
):
    """Test the full OAuth flow when no credentials exist yet."""
    # Setup mock OAuth flow
    mock_flow = MagicMock()
    mock_flow_class.from_client_secrets_dict.return_value = mock_flow

    mock_creds = MagicMock()
    mock_creds.to_json.return_value = '{"type": "authorized_user"}'
    mock_flow.run_local_server.return_value = mock_creds

    # Call authenticate
    result = authenticate_youtube()

    # Verify the flow opened browser
    mock_flow.run_local_server.assert_called_once_with(port=8080)

    # Verify credentials were returned
    assert result is not None

    # Verify credentials were saved
    creds_path = get_credentials_path()
    assert creds_path.exists()


@patch("yt_rag.oauth.Credentials")
def test_authenticate_youtube_with_saved_credentials(mock_creds_class, temp_config_dir):
    """Test OAuth flow when valid credentials already exist."""
    # Create a fake credentials file
    creds_path = get_credentials_path()
    creds_path.parent.mkdir(parents=True, exist_ok=True)
    creds_path.write_text('{"type": "authorized_user"}')

    mock_creds = MagicMock()
    mock_creds.expired = False
    mock_creds_class.from_authorized_user_file.return_value = mock_creds

    result = authenticate_youtube()

    # Should load from file, not open browser again
    mock_creds_class.from_authorized_user_file.assert_called_once()
    assert result is not None

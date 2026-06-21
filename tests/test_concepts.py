import pytest
import tempfile
import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from yt_rag.concepts import ConceptExtractor
from yt_rag.config import (
    save_concepts,
    load_concepts,
    concepts_exist,
    get_concepts_dir,
)


@pytest.fixture
def temp_config_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("yt_rag.concepts.os.getenv") as mock_getenv:
            with patch("yt_rag.config.get_config_dir", return_value=Path(tmpdir)):
                def getenv_side_effect(key, default=None):
                    if key == "OPENROUTER_API_KEY":
                        return "test-api-key-123"
                    return default
                mock_getenv.side_effect = getenv_side_effect
                yield Path(tmpdir)


@pytest.fixture
def extractor(temp_config_dir):
    """Create a ConceptExtractor instance."""
    return ConceptExtractor()


def test_extractor_init_with_api_key(extractor):
    """Test ConceptExtractor initializes with valid API key."""
    assert extractor.api_key == "test-api-key-123"
    assert extractor.api_url == "https://openrouter.ai/api/v1/chat/completions"
    assert extractor.model == "openai/gpt-3.5-turbo"
    assert extractor.max_concepts == 10


def test_extractor_init_without_api_key():
    """Test ConceptExtractor raises error without API key."""
    with patch("yt_rag.concepts.os.getenv", return_value=None):
        with pytest.raises(ValueError, match="OPENROUTER_API_KEY not found"):
            ConceptExtractor()


def test_extract_concepts_empty_transcript(extractor):
    """Test extraction with empty transcript."""
    concepts, error = extractor.extract_concepts("")
    assert concepts is None
    assert error == "Transcript is empty"


def test_extract_concepts_whitespace_only(extractor):
    """Test extraction with whitespace-only transcript."""
    concepts, error = extractor.extract_concepts("   \n\n   ")
    assert concepts is None
    assert error == "Transcript is empty"


@patch("yt_rag.concepts.requests.post")
def test_extract_concepts_success(mock_post, extractor):
    """Test successful concept extraction."""
    # Mock API response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps([
                        {"name": "Python", "description": "A programming language"},
                        {"name": "Flask", "description": "A web framework"},
                    ])
                }
            }
        ]
    }
    mock_post.return_value = mock_response

    transcript = "This is a tutorial about Python and Flask web development."
    concepts, error = extractor.extract_concepts(transcript)

    assert error is None
    assert concepts is not None
    assert len(concepts) == 2
    assert concepts[0]["name"] == "Python"
    assert concepts[1]["name"] == "Flask"


@patch("yt_rag.concepts.requests.post")
def test_extract_concepts_api_error(mock_post, extractor):
    """Test handling of API errors."""
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.json.return_value = {"error": {"message": "Unauthorized"}}
    mock_post.return_value = mock_response

    transcript = "Some transcript"
    concepts, error = extractor.extract_concepts(transcript)

    assert concepts is None
    assert error is not None


@patch("yt_rag.concepts.requests.post")
def test_extract_concepts_timeout(mock_post, extractor):
    """Test handling of API timeout."""
    mock_post.side_effect = __import__("requests").Timeout()

    transcript = "Some transcript"
    concepts, error = extractor.extract_concepts(transcript)

    assert concepts is None
    assert error is not None


@patch("yt_rag.concepts.requests.post")
def test_extract_concepts_invalid_json(mock_post, extractor):
    """Test handling of invalid JSON response."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "This is not valid JSON"
                }
            }
        ]
    }
    mock_post.return_value = mock_response

    transcript = "Some transcript"
    concepts, error = extractor.extract_concepts(transcript)

    assert concepts is None
    assert error is not None


@patch("yt_rag.concepts.requests.post")
def test_extract_concepts_json_extraction_fallback(mock_post, extractor):
    """Test fallback JSON extraction when response has extra text."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "Here are the concepts:\n[{\"name\": \"Python\", \"description\": \"Language\"}]"
                }
            }
        ]
    }
    mock_post.return_value = mock_response

    transcript = "Python tutorial"
    concepts, error = extractor.extract_concepts(transcript)

    assert error is None
    assert concepts is not None
    assert len(concepts) == 1
    assert concepts[0]["name"] == "Python"


def test_create_prompt(extractor):
    """Test prompt creation."""
    transcript = "JavaScript is a programming language. Use npm to install packages."
    prompt = extractor._create_prompt(transcript)

    assert "JavaScript is a programming language" in prompt
    assert "Extract the top 10 key concepts" in prompt
    assert "[" in prompt  # Should mention JSON format


def test_create_prompt_truncation(extractor):
    """Test that long transcripts are truncated."""
    long_transcript = "word " * 1000  # Very long transcript
    prompt = extractor._create_prompt(long_transcript)

    assert "..." in prompt  # Should have truncation indicator
    assert len(prompt) < len(long_transcript) * 2


def test_parse_response_valid_json(extractor):
    """Test parsing valid JSON response."""
    response = json.dumps([
        {"name": "Python", "description": "A programming language"},
        {"name": "Flask", "description": "A web framework"},
    ])

    concepts = extractor._parse_response(response)

    assert concepts is not None
    assert len(concepts) == 2
    assert concepts[0]["name"] == "Python"


def test_parse_response_with_extra_fields(extractor):
    """Test parsing JSON with extra fields (should be ignored)."""
    response = json.dumps([
        {"name": "Python", "description": "Language", "extra_field": "value"},
        {"name": "Flask", "description": "Framework"},
    ])

    concepts = extractor._parse_response(response)

    assert concepts is not None
    assert len(concepts) == 2
    assert "extra_field" not in concepts[0]


def test_parse_response_missing_fields(extractor):
    """Test parsing JSON with missing required fields."""
    response = json.dumps([
        {"name": "Python"},  # Missing description
        {"description": "A framework"},  # Missing name
    ])

    concepts = extractor._parse_response(response)

    assert concepts is None or len(concepts) == 0


def test_parse_response_invalid_json(extractor):
    """Test parsing invalid JSON."""
    response = "Not valid JSON at all"
    concepts = extractor._parse_response(response)
    assert concepts is None


def test_parse_response_json_in_text(extractor):
    """Test extracting JSON from text."""
    response = "Here are the concepts:\n[{\"name\": \"Python\", \"description\": \"Language\"}]"
    concepts = extractor._parse_response(response)

    assert concepts is not None
    assert len(concepts) == 1
    assert concepts[0]["name"] == "Python"


# Config module tests

def test_save_and_load_concepts(temp_config_dir):
    """Test saving and loading concepts."""
    video_id = "vid123"
    concepts_data = [
        {"name": "Python", "description": "A language"},
        {"name": "Flask", "description": "A framework"},
    ]

    # Save
    save_concepts(video_id, concepts_data)

    # Load
    loaded = load_concepts(video_id)

    assert loaded == concepts_data


def test_concepts_exist_when_not_saved(temp_config_dir):
    """Test concepts_exist returns False when not saved."""
    assert not concepts_exist("nonexistent")


def test_concepts_exist_when_saved(temp_config_dir):
    """Test concepts_exist returns True when saved."""
    video_id = "vid123"
    concepts_data = [{"name": "Test", "description": "Concept"}]

    save_concepts(video_id, concepts_data)

    assert concepts_exist(video_id)


def test_load_nonexistent_concepts(temp_config_dir):
    """Test loading concepts that don't exist."""
    result = load_concepts("nonexistent")
    assert result is None


def test_concepts_dir_creation(temp_config_dir):
    """Test that concepts directory is created."""
    video_id = "vid123"
    concepts_data = [{"name": "Test", "description": "Concept"}]

    save_concepts(video_id, concepts_data)

    concepts_dir = get_concepts_dir()
    assert concepts_dir.exists()
    assert (concepts_dir / f"{video_id}.json").exists()

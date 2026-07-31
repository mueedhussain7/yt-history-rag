import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
from yt_rag.embeddings import EmbeddingGenerator


class TestEmbeddingGenerator:
    """Test EmbeddingGenerator class."""

    @pytest.fixture
    def temp_config_dir(self, monkeypatch):
        """Create temporary config directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("YT_RAG_CONFIG_DIR", tmpdir)
            yield tmpdir

    def test_chunk_transcript_basic(self, temp_config_dir):
        """Test basic transcript chunking."""
        generator = EmbeddingGenerator()

        # Simple 8-sentence transcript
        transcript = "Sentence one. Sentence two. Sentence three. Sentence four. Sentence five. Sentence six. Sentence seven. Sentence eight."

        chunks = generator.chunk_transcript(transcript, chunk_size=2)

        # Should create 4 chunks (8 sentences / 2 per chunk)
        assert len(chunks) == 4
        assert "Sentence one" in chunks[0]
        assert "Sentence two" in chunks[0]

    def test_chunk_transcript_uneven(self, temp_config_dir):
        """Test chunking with uneven number of sentences."""
        generator = EmbeddingGenerator()

        transcript = "One. Two. Three. Four. Five."
        chunks = generator.chunk_transcript(transcript, chunk_size=2)

        # Should create 3 chunks (5 sentences with chunk_size=2)
        assert len(chunks) == 3
        assert len(chunks[-1].split()) <= 4  # Last chunk has 1 sentence

    def test_chunk_transcript_empty(self, temp_config_dir):
        """Test chunking empty transcript."""
        generator = EmbeddingGenerator()

        chunks = generator.chunk_transcript("", chunk_size=2)
        assert chunks == []

    def test_embed_and_store(self, temp_config_dir):
        """Test embedding and storing chunks."""
        generator = EmbeddingGenerator()

        transcript = "Machine learning is great. It learns from data. Neural networks are powerful. They process information. This is important. Very important indeed."

        chunks_count = generator.embed_and_store(
            video_id="test_video_123",
            video_title="Test Video Title",
            transcript=transcript
        )

        # Should have created at least 2 chunks
        assert chunks_count >= 2

        # Collection should have items
        collection_count = generator.collection.count()
        assert collection_count == chunks_count

    def test_embed_and_store_empty_transcript(self, temp_config_dir):
        """Test embedding empty transcript."""
        generator = EmbeddingGenerator()

        chunks_count = generator.embed_and_store(
            video_id="empty_video",
            video_title="Empty Video",
            transcript=""
        )

        # Should not create any chunks
        assert chunks_count == 0

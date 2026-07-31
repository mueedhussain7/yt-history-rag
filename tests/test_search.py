import pytest
import tempfile
from unittest.mock import patch, MagicMock
from yt_rag.search import TranscriptSearcher
from yt_rag.embeddings import EmbeddingGenerator


class TestTranscriptSearcher:
    """Test TranscriptSearcher class."""

    @pytest.fixture
    def temp_config_dir(self, monkeypatch):
        """Create temporary config directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("YT_RAG_CONFIG_DIR", tmpdir)
            yield tmpdir

    @pytest.fixture
    def populated_searcher(self, temp_config_dir):
        """Create searcher with sample data."""
        # First, populate with embeddings
        generator = EmbeddingGenerator()

        transcripts = [
            {
                "video_id": "vid1",
                "title": "Python Basics",
                "text": "Python is a programming language. It is easy to learn. Variables store data. Functions are reusable. Classes define objects."
            },
            {
                "video_id": "vid2",
                "title": "Machine Learning Guide",
                "text": "Machine learning uses algorithms. Neural networks learn patterns. Training data is important. Models make predictions. Accuracy matters a lot."
            },
            {
                "video_id": "vid3",
                "title": "Web Development",
                "text": "HTML creates web pages. CSS styles elements. JavaScript adds interactivity. Servers handle requests. Databases store information."
            }
        ]

        for transcript in transcripts:
            generator.embed_and_store(
                transcript["video_id"],
                transcript["title"],
                transcript["text"]
            )

        return TranscriptSearcher()

    def test_search_initialization_no_collection(self, temp_config_dir):
        """Test searcher initialization when no embeddings exist."""
        searcher = TranscriptSearcher()
        assert searcher.collection is None

    def test_search_empty_collection(self, temp_config_dir):
        """Test search when collection is empty."""
        searcher = TranscriptSearcher()
        results = searcher.search("machine learning")
        assert results == []

    def test_search_basic(self, populated_searcher):
        """Test basic search functionality."""
        results = populated_searcher.search("machine learning", top_k=5)

        # Should find results
        assert len(results) > 0
        assert len(results) <= 5

        # Each result should have required fields
        for result in results:
            assert "video_id" in result
            assert "video_title" in result
            assert "chunk_text" in result
            assert "similarity_score" in result
            assert 0 <= result["similarity_score"] <= 1

    def test_search_python(self, populated_searcher):
        """Test searching for Python topic."""
        results = populated_searcher.search("python", top_k=3)

        # Should find results
        assert len(results) > 0

        # Top result should be from Python Basics video
        top_result = results[0]
        assert "python" in top_result["chunk_text"].lower() or "python" in top_result["video_title"].lower()

    def test_search_neural_networks(self, populated_searcher):
        """Test searching for neural networks."""
        results = populated_searcher.search("neural networks", top_k=3)

        assert len(results) > 0
        # Should find ML-related content
        assert any("Machine Learning" in r["video_title"] for r in results)

    def test_search_top_k_limit(self, populated_searcher):
        """Test that top_k parameter limits results."""
        results_3 = populated_searcher.search("learning", top_k=3)
        results_1 = populated_searcher.search("learning", top_k=1)

        assert len(results_3) <= 3
        assert len(results_1) <= 1

    def test_search_result_format(self, populated_searcher):
        """Test that search results have correct format."""
        results = populated_searcher.search("data", top_k=1)

        assert len(results) > 0
        result = results[0]

        # Check all required fields exist
        assert isinstance(result["video_id"], str)
        assert isinstance(result["video_title"], str)
        assert isinstance(result["chunk_text"], str)
        assert isinstance(result["similarity_score"], float)

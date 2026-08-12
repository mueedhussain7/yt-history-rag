"""Unit tests for KnowledgeGraph (mock-based, no Docker required)."""

import pytest
from unittest.mock import Mock, MagicMock, call

from src.yt_rag.knowledge_graph import KnowledgeGraph


@pytest.fixture
def mock_driver():
    """Create a mock Neo4j driver."""
    driver = Mock()
    driver.execute = MagicMock()
    driver.query = MagicMock(return_value=[])
    return driver


@pytest.fixture
def kg(mock_driver):
    """Create KnowledgeGraph with mock driver."""
    return KnowledgeGraph(mock_driver)


class TestVideoNodeCreation:
    """Test Video node creation."""

    def test_create_video_node_executes_correct_query(self, kg, mock_driver):
        """Verify Video node creation calls execute with correct Cypher."""
        kg.create_video_node(
            video_id="test_001",
            title="Test Video",
            url="https://youtube.com/watch?v=test_001",
            watch_date="2024-10-15T10:00:00Z",
            duration_seconds=600,
            provider="youtube_api",
        )

        # Verify execute was called
        mock_driver.execute.assert_called_once()
        call_args = mock_driver.execute.call_args

        # Verify parameters
        params = call_args[0][1]
        assert params["video_id"] == "test_001"
        assert params["title"] == "Test Video"
        assert params["duration_seconds"] == 600
        assert params["provider"] == "youtube_api"


class TestConceptNodeCreation:
    """Test Concept node creation."""

    def test_create_concept_node_executes_query(self, kg, mock_driver):
        """Verify Concept node creation."""
        kg.create_concept_node("Python", "Programming language")

        mock_driver.execute.assert_called_once()
        params = mock_driver.execute.call_args[0][1]
        assert params["name"] == "Python"
        assert "Programming" in params["description"]


class TestContainsRelationship:
    """Test Video -[contains]-> Concept relationship."""

    def test_create_contains_relationship(self, kg, mock_driver):
        """Verify contains relationship with occurrence_count."""
        kg.create_contains_relationship(
            video_id="video_001",
            concept_name="Python",
            occurrence_count=5,
        )

        mock_driver.execute.assert_called_once()
        params = mock_driver.execute.call_args[0][1]
        assert params["occurrence_count"] == 5
        assert params["concept_name"] == "Python"


class TestAppearsAtRelationship:
    """Test Concept -[appears_at]-> Timestamp relationship."""

    def test_create_appears_at_relationship(self, kg, mock_driver):
        """Verify appears_at relationship."""
        kg.create_appears_at_relationship(
            concept_name="Python",
            video_id="video_001",
            timestamp_seconds=15,
        )

        mock_driver.execute.assert_called_once()
        params = mock_driver.execute.call_args[0][1]
        assert params["timestamp_seconds"] == 15
        assert params["concept_name"] == "Python"


class TestIntroducedInRelationship:
    """Test Concept -[introduced_in]-> Timestamp relationship (provenance)."""

    def test_create_introduced_in_relationship(self, kg, mock_driver):
        """Verify introduced_in relationship for provenance."""
        kg.create_introduced_in_relationship(
            concept_name="Python",
            video_id="video_001",
            timestamp_seconds=5,
        )

        mock_driver.execute.assert_called_once()
        params = mock_driver.execute.call_args[0][1]
        assert params["timestamp_seconds"] == 5
        assert params["concept_name"] == "Python"


class TestCoOccursWithRelationship:
    """Test bidirectional Concept -[co_occurs_with]-> Concept relationships."""

    def test_create_bidirectional_co_occurs_with(self, kg, mock_driver):
        """Verify bidirectional co_occurs_with relationships with different scores."""
        kg.create_co_occurs_with_relationship(
            concept1_name="Python",
            concept2_name="Data Science",
            confidence_score_1_to_2=0.75,
            confidence_score_2_to_1=0.50,
        )

        # Should call execute twice (one for each direction)
        assert mock_driver.execute.call_count == 2

        # Verify first direction (Python -> Data Science)
        first_call = mock_driver.execute.call_args_list[0]
        first_params = first_call[0][1]
        assert first_params["concept1_name"] == "Python"
        assert first_params["concept2_name"] == "Data Science"
        assert first_params["confidence_score"] == 0.75

        # Verify second direction (Data Science -> Python)
        second_call = mock_driver.execute.call_args_list[1]
        second_params = second_call[0][1]
        assert second_params["concept1_name"] == "Python"
        assert second_params["concept2_name"] == "Data Science"
        assert second_params["confidence_score"] == 0.50

    def test_co_occurs_with_asymmetric_scores(self, kg, mock_driver):
        """Verify asymmetric confidence scores are preserved."""
        kg.create_co_occurs_with_relationship(
            concept1_name="A",
            concept2_name="B",
            confidence_score_1_to_2=0.9,  # A appears with B 90% of the time
            confidence_score_2_to_1=0.3,  # B appears with A 30% of the time
        )

        # Two relationships created with different scores
        assert mock_driver.execute.call_count == 2
        first_score = mock_driver.execute.call_args_list[0][0][1]["confidence_score"]
        second_score = mock_driver.execute.call_args_list[1][0][1]["confidence_score"]

        assert first_score == 0.9
        assert second_score == 0.3
        assert first_score != second_score


class TestGetMethods:
    """Test retrieval methods."""

    def test_get_video_by_id(self, kg, mock_driver):
        """Verify get_video_by_id queries correctly."""
        mock_driver.query.return_value = [{"v": {"video_id": "test_001", "title": "Test"}}]

        result = kg.get_video_by_id("test_001")

        mock_driver.query.assert_called_once()
        assert result is not None

    def test_get_concept_by_name(self, kg, mock_driver):
        """Verify get_concept_by_name queries correctly."""
        mock_driver.query.return_value = [{"c": {"name": "Python", "description": "Language"}}]

        result = kg.get_concept_by_name("Python")

        mock_driver.query.assert_called_once()
        assert result is not None

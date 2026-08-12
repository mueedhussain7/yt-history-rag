import pytest
from testcontainers.neo4j import Neo4jContainer
from neo4j import GraphDatabase

from src.yt_rag.neo4j_driver import Neo4jDriver
from src.yt_rag.knowledge_graph import KnowledgeGraph


@pytest.fixture(scope="function")
def neo4j_container():
    """Start Neo4j testcontainer for each test."""
    container = Neo4jContainer(image="neo4j:latest", env={"NEO4J_AUTH": "neo4j/password"})
    container.start()
    yield container
    container.stop()


@pytest.fixture
def neo4j_driver(neo4j_container):
    """Create Neo4j driver connected to testcontainer."""
    uri = neo4j_container.get_connection_url()
    driver = GraphDatabase.driver(uri, auth=("neo4j", "password"))

    # Create schema
    with driver.session() as session:
        session.run("CREATE CONSTRAINT video_id IF NOT EXISTS FOR (v:Video) REQUIRE v.video_id IS UNIQUE")
        session.run("CREATE CONSTRAINT concept_name IF NOT EXISTS FOR (c:Concept) REQUIRE c.name IS UNIQUE")

    yield driver
    driver.close()


@pytest.fixture
def kg(neo4j_driver, neo4j_container):
    """Create KnowledgeGraph instance using test driver."""
    kg_driver = Neo4jDriver(
        uri=neo4j_container.get_connection_url(),
        user="neo4j",
        password="password",
    )
    kg_driver.driver = neo4j_driver
    return KnowledgeGraph(kg_driver)


class TestKnowledgeGraphNodes:
    """Test node creation."""

    def test_create_video_node(self, kg):
        """Test Video node creation."""
        kg.create_video_node(
            video_id="dQw4w9WgXcQ",
            title="Never Gonna Give You Up",
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            watch_date="2024-10-15T10:30:00Z",
            duration_seconds=212,
            provider="youtube_api",
        )

        video = kg.get_video_by_id("dQw4w9WgXcQ")
        assert video is not None
        assert video["title"] == "Never Gonna Give You Up"
        assert video["duration_seconds"] == 212

    def test_create_concept_node(self, kg):
        """Test Concept node creation."""
        kg.create_concept_node(
            name="Music",
            description="Art form consisting of organized sounds and silences",
        )

        concept = kg.get_concept_by_name("Music")
        assert concept is not None
        assert concept["name"] == "Music"
        assert "Art form" in concept["description"]

    def test_create_timestamp_node(self, kg):
        """Test Timestamp node creation."""
        kg.create_timestamp_node(
            video_id="dQw4w9WgXcQ",
            timestamp_seconds=10,
            text="Never gonna give you up",
        )

        # Verify via query
        driver = kg.driver
        results = driver.query(
            "MATCH (t:Timestamp {video_id: $video_id, timestamp_seconds: $ts}) RETURN t",
            {"video_id": "dQw4w9WgXcQ", "ts": 10},
        )
        assert len(results) > 0
        assert results[0]["t"]["text"] == "Never gonna give you up"


class TestKnowledgeGraphRelationships:
    """Test all four relationship types."""

    def setup_method(self):
        """Create sample data for each test."""
        self.video_id = "test_video_001"
        self.concept1 = "Machine Learning"
        self.concept2 = "Neural Networks"

    def test_contains_relationship(self, kg):
        """Test Video -[contains {occurrence_count}]-> Concept."""
        kg.create_video_node(
            video_id=self.video_id,
            title="ML Basics",
            url="https://youtube.com/watch?v=test_video_001",
            watch_date="2024-10-15T10:00:00Z",
            duration_seconds=600,
            provider="youtube_api",
        )
        kg.create_concept_node(self.concept1, "Computer learning approach")

        kg.create_contains_relationship(
            video_id=self.video_id,
            concept_name=self.concept1,
            occurrence_count=5,
        )

        driver = kg.driver
        results = driver.query(
            """MATCH (v:Video {video_id: $vid})-[rel:contains]->(c:Concept {name: $concept})
               RETURN rel.occurrence_count as count""",
            {"vid": self.video_id, "concept": self.concept1},
        )
        assert len(results) > 0
        assert results[0]["count"] == 5

    def test_appears_at_relationship(self, kg):
        """Test Concept -[appears_at]-> Timestamp."""
        kg.create_concept_node(self.concept1, "Computer learning approach")
        kg.create_timestamp_node(
            video_id=self.video_id,
            timestamp_seconds=15,
            text="Discussing machine learning",
        )

        kg.create_appears_at_relationship(
            concept_name=self.concept1,
            video_id=self.video_id,
            timestamp_seconds=15,
        )

        driver = kg.driver
        results = driver.query(
            """MATCH (c:Concept {name: $concept})-[rel:appears_at]->
                     (t:Timestamp {video_id: $vid, timestamp_seconds: $ts})
               RETURN rel""",
            {"concept": self.concept1, "vid": self.video_id, "ts": 15},
        )
        assert len(results) > 0

    def test_introduced_in_relationship(self, kg):
        """Test Concept -[introduced_in]-> Timestamp (provenance)."""
        kg.create_concept_node(self.concept1, "Computer learning approach")
        kg.create_timestamp_node(
            video_id=self.video_id,
            timestamp_seconds=5,
            text="First mention of ML",
        )

        kg.create_introduced_in_relationship(
            concept_name=self.concept1,
            video_id=self.video_id,
            timestamp_seconds=5,
        )

        driver = kg.driver
        results = driver.query(
            """MATCH (c:Concept {name: $concept})-[rel:introduced_in]->
                     (t:Timestamp {video_id: $vid, timestamp_seconds: $ts})
               RETURN rel""",
            {"concept": self.concept1, "vid": self.video_id, "ts": 5},
        )
        assert len(results) > 0

    def test_co_occurs_with_bidirectional_relationships(self, kg):
        """Test bidirectional Concept -[co_occurs_with {confidence_score}]-> Concept."""
        kg.create_concept_node(self.concept1, "Computer learning approach")
        kg.create_concept_node(self.concept2, "Network structures in AI")

        # Create bidirectional relationships with different scores
        kg.create_co_occurs_with_relationship(
            concept1_name=self.concept1,
            concept2_name=self.concept2,
            confidence_score_1_to_2=0.75,  # ML appears with NN in 75% of ML occurrences
            confidence_score_2_to_1=0.50,  # NN appears with ML in 50% of NN occurrences
        )

        driver = kg.driver

        # Verify concept1 -> concept2 relationship
        results_1_to_2 = driver.query(
            """MATCH (c1:Concept {name: $c1})-[rel:co_occurs_with]->
                     (c2:Concept {name: $c2})
               RETURN rel.confidence_score as score""",
            {"c1": self.concept1, "c2": self.concept2},
        )
        assert len(results_1_to_2) > 0
        assert results_1_to_2[0]["score"] == 0.75

        # Verify concept2 -> concept1 relationship (reverse direction)
        results_2_to_1 = driver.query(
            """MATCH (c2:Concept {name: $c2})-[rel:co_occurs_with]->
                     (c1:Concept {name: $c1})
               RETURN rel.confidence_score as score""",
            {"c2": self.concept2, "c1": self.concept1},
        )
        assert len(results_2_to_1) > 0
        assert results_2_to_1[0]["score"] == 0.50


class TestKnowledgeGraphIntegration:
    """Integration test with all relationships."""

    def test_complete_knowledge_graph_flow(self, kg):
        """Test creating a complete mini knowledge graph."""
        video_id = "integration_test_001"
        concepts = [
            ("Python", "Programming language"),
            ("Data Science", "Field of study"),
        ]

        # Create video
        kg.create_video_node(
            video_id=video_id,
            title="Python for Data Science",
            url="https://youtube.com/watch?v=integration_test_001",
            watch_date="2024-10-15T12:00:00Z",
            duration_seconds=3600,
            provider="youtube_api",
        )

        # Create concepts
        for name, desc in concepts:
            kg.create_concept_node(name, desc)

        # Create timestamps
        timestamps = [
            (10, "Introduction to Python"),
            (60, "Python for data analysis"),
            (120, "Data science fundamentals"),
        ]
        for ts, text in timestamps:
            kg.create_timestamp_node(video_id, ts, text)

        # Create all relationships
        # Video contains concepts
        kg.create_contains_relationship(video_id, "Python", 3)
        kg.create_contains_relationship(video_id, "Data Science", 2)

        # Concepts appear at timestamps
        kg.create_appears_at_relationship("Python", video_id, 10)
        kg.create_appears_at_relationship("Python", video_id, 60)
        kg.create_appears_at_relationship("Data Science", video_id, 60)
        kg.create_appears_at_relationship("Data Science", video_id, 120)

        # First mention (introduced_in)
        kg.create_introduced_in_relationship("Python", video_id, 10)
        kg.create_introduced_in_relationship("Data Science", video_id, 120)

        # Co-occurrence
        kg.create_co_occurs_with_relationship(
            "Python",
            "Data Science",
            confidence_score_1_to_2=0.67,  # 2 of 3 Python mentions with Data Science
            confidence_score_2_to_1=1.0,   # All Data Science mentions with Python
        )

        # Verify all relationships exist
        driver = kg.driver

        # Check contains
        contains_results = driver.query(
            "MATCH (v:Video {video_id: $vid})-[r:contains]->(c:Concept) RETURN count(r) as count",
            {"vid": video_id},
        )
        assert contains_results[0]["count"] == 2

        # Check appears_at
        appears_results = driver.query(
            "MATCH (c:Concept)-[r:appears_at]->(t:Timestamp) RETURN count(r) as count",
        )
        assert appears_results[0]["count"] == 4

        # Check introduced_in
        introduced_results = driver.query(
            "MATCH (c:Concept)-[r:introduced_in]->(t:Timestamp) RETURN count(r) as count",
        )
        assert introduced_results[0]["count"] == 2

        # Check co_occurs_with (both directions)
        cooccurs_results = driver.query(
            "MATCH (c1:Concept)-[r:co_occurs_with]->(c2:Concept) RETURN count(r) as count",
        )
        assert cooccurs_results[0]["count"] == 2  # Bidirectional = 2 relationships

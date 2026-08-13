import os
from typing import Optional
from neo4j import GraphDatabase, Driver
from neo4j.exceptions import ServiceUnavailable


class Neo4jDriver:
    """Manage Neo4j connection and schema setup."""

    def __init__(self, uri: Optional[str] = None, user: Optional[str] = None, password: Optional[str] = None):
        """
        Initialize Neo4j driver.

        Args:
            uri: Neo4j connection URI (default: env NEO4J_URI or localhost:7687)
            user: Neo4j username (default: env NEO4J_USER or "neo4j")
            password: Neo4j password (default: env NEO4J_PASSWORD or "password")
        """
        self.uri = uri or os.getenv("NEO4J_URI", "neo4j://localhost:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "password")

        self.driver: Optional[Driver] = None
        self._connect()

    def _connect(self) -> None:
        """Connect to Neo4j."""
        try:
            self.driver = GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password),
                encrypted=False,
            )
            # Verify connection
            with self.driver.session() as session:
                session.run("RETURN 1")
        except ServiceUnavailable as e:
            raise Exception(f"Cannot connect to Neo4j at {self.uri}: {str(e)}")
        except Exception as e:
            raise Exception(f"Neo4j connection error: {str(e)}")

    def close(self) -> None:
        """Close connection."""
        if self.driver:
            self.driver.close()

    def create_schema(self) -> None:
        """Create schema constraints and indexes."""
        constraints = [
            "CREATE CONSTRAINT video_id IF NOT EXISTS FOR (v:Video) REQUIRE v.video_id IS UNIQUE",
            "CREATE CONSTRAINT concept_name IF NOT EXISTS FOR (c:Concept) REQUIRE c.name IS UNIQUE",
            "CREATE CONSTRAINT timestamp_unique IF NOT EXISTS FOR (t:Timestamp) REQUIRE (t.video_id, t.timestamp_seconds) IS UNIQUE",
            "CREATE INDEX video_title IF NOT EXISTS FOR (v:Video) ON (v.title)",
        ]

        with self.driver.session() as session:
            for constraint in constraints:
                try:
                    session.run(constraint)
                except Exception as e:
                    # Constraint might already exist; continue
                    pass

    def query(self, query: str, params: dict = None) -> list:
        """
        Execute a Cypher query.

        Args:
            query: Cypher query string
            params: Query parameters dict

        Returns:
            List of records
        """
        if params is None:
            params = {}

        with self.driver.session() as session:
            result = session.run(query, params)
            return [record for record in result]

    def execute(self, query: str, params: dict = None) -> None:
        """
        Execute a Cypher query without returning results.

        Args:
            query: Cypher query string
            params: Query parameters dict
        """
        if params is None:
            params = {}

        with self.driver.session() as session:
            session.run(query, params)

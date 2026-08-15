from typing import Optional, List, Dict, Any
from datetime import datetime
from .neo4j_driver import Neo4jDriver


class KnowledgeGraph:
    """Create and manage nodes and relationships in Neo4j knowledge graph."""

    def __init__(self, driver: Neo4jDriver):
        """
        Initialize knowledge graph manager.

        Args:
            driver: Neo4jDriver instance
        """
        self.driver = driver

    def create_video_node(
        self,
        video_id: str,
        title: str,
        url: str,
        watch_date: str,
        duration_seconds: int,
        provider: str,
    ) -> None:
        """
        Create Video node.

        Args:
            video_id: YouTube video ID
            title: Video title
            url: Full YouTube URL
            watch_date: ISO format timestamp
            duration_seconds: Video duration
            provider: Source provider (youtube_api, takeout, browser_extension)
        """
        query = """
            MERGE (v:Video {video_id: $video_id})
            SET v.title = $title,
                v.url = $url,
                v.watch_date = $watch_date,
                v.duration_seconds = $duration_seconds,
                v.provider = $provider,
                v.created_at = datetime()
        """
        self.driver.execute(query, {
            "video_id": video_id,
            "title": title,
            "url": url,
            "watch_date": watch_date,
            "duration_seconds": duration_seconds,
            "provider": provider,
        })

    def create_concept_node(self, name: str, description: str) -> None:
        """
        Create Concept node (if not exists).

        Args:
            name: Concept name (unique)
            description: Concept description
        """
        query = """
            MERGE (c:Concept {name: $name})
            SET c.description = $description,
                c.created_at = datetime()
        """
        try:
            self.driver.execute(query, {
                "name": name,
                "description": description,
            })
        except Exception:
            pass  # Concept already exists (unique constraint)

    def create_timestamp_node(self, video_id: str, timestamp_seconds: int, text: str) -> None:
        """
        Create Timestamp node.

        Args:
            video_id: YouTube video ID
            timestamp_seconds: Time in video (seconds)
            text: Transcript snippet at this time
        """
        query = """
            MERGE (t:Timestamp {video_id: $video_id, timestamp_seconds: $timestamp_seconds})
            SET t.text = $text,
                t.created_at = datetime()
        """
        self.driver.execute(query, {
            "timestamp_seconds": timestamp_seconds,
            "text": text,
            "video_id": video_id,
        })

    def create_contains_relationship(self, video_id: str, concept_name: str, occurrence_count: int) -> None:
        """
        Create Video -[contains {occurrence_count}]-> Concept relationship.

        Args:
            video_id: YouTube video ID
            concept_name: Concept name
            occurrence_count: How many times concept appears in video
        """
        query = """
            MATCH (v:Video {video_id: $video_id})
            MATCH (c:Concept {name: $concept_name})
            MERGE (v)-[rel:contains]->(c)
            SET rel.occurrence_count = $occurrence_count, rel.created_at = datetime()
        """
        self.driver.execute(query, {
            "video_id": video_id,
            "concept_name": concept_name,
            "occurrence_count": occurrence_count,
        })

    def create_appears_at_relationship(self, concept_name: str, video_id: str, timestamp_seconds: int) -> None:
        """
        Create Concept -[appears_at]-> Timestamp relationship.

        Args:
            concept_name: Concept name
            video_id: YouTube video ID
            timestamp_seconds: Time when concept appears
        """
        query = """
            MATCH (c:Concept {name: $concept_name})
            MATCH (t:Timestamp {video_id: $video_id, timestamp_seconds: $timestamp_seconds})
            MERGE (c)-[rel:appears_at]->(t)
            ON CREATE SET rel.created_at = datetime()
        """
        self.driver.execute(query, {
            "concept_name": concept_name,
            "video_id": video_id,
            "timestamp_seconds": timestamp_seconds,
        })

    def create_introduced_in_relationship(self, concept_name: str, video_id: str, timestamp_seconds: int) -> None:
        """
        Create Concept -[introduced_in]-> Timestamp relationship (provenance).

        This marks where/when a concept was first mentioned.

        Args:
            concept_name: Concept name
            video_id: YouTube video ID (first appearance)
            timestamp_seconds: Time of first appearance
        """
        query = """
            MATCH (c:Concept {name: $concept_name})
            MATCH (t:Timestamp {video_id: $video_id, timestamp_seconds: $timestamp_seconds})
            MERGE (c)-[rel:introduced_in]->(t)
            ON CREATE SET rel.created_at = datetime()
        """
        self.driver.execute(query, {
            "concept_name": concept_name,
            "video_id": video_id,
            "timestamp_seconds": timestamp_seconds,
        })

    def create_co_occurs_with_relationship(
        self,
        concept1_name: str,
        concept2_name: str,
        confidence_score_1_to_2: float,
        confidence_score_2_to_1: float,
    ) -> None:
        """
        Create bidirectional co_occurs_with relationships.

        Creates both:
        - Concept1 -[co_occurs_with {confidence_score}]-> Concept2
        - Concept2 -[co_occurs_with {confidence_score}]-> Concept1

        Scores are asymmetric: how often concept1 co-occurs with concept2
        is different from how often concept2 appears with concept1.

        Args:
            concept1_name: First concept
            concept2_name: Second concept
            confidence_score_1_to_2: How often concept1 appears with concept2 (0-1)
            confidence_score_2_to_1: How often concept2 appears with concept1 (0-1)
        """
        # Create concept1 -> concept2 relationship
        query1 = """
            MATCH (c1:Concept {name: $concept1_name})
            MATCH (c2:Concept {name: $concept2_name})
            MERGE (c1)-[rel:co_occurs_with]->(c2)
            SET rel.confidence_score = $confidence_score, rel.created_at = datetime()
        """
        self.driver.execute(query1, {
            "concept1_name": concept1_name,
            "concept2_name": concept2_name,
            "confidence_score": confidence_score_1_to_2,
        })

        # Create concept2 -> concept1 relationship
        query2 = """
            MATCH (c1:Concept {name: $concept1_name})
            MATCH (c2:Concept {name: $concept2_name})
            MERGE (c2)-[rel:co_occurs_with]->(c1)
            SET rel.confidence_score = $confidence_score, rel.created_at = datetime()
        """
        self.driver.execute(query2, {
            "concept1_name": concept1_name,
            "concept2_name": concept2_name,
            "confidence_score": confidence_score_2_to_1,
        })

    def get_concept_by_name(self, name: str) -> Optional[Dict]:
        """
        Retrieve concept node by name.

        Args:
            name: Concept name

        Returns:
            Concept dict or None if not found
        """
        query = "MATCH (c:Concept {name: $name}) RETURN c"
        results = self.driver.query(query, {"name": name})
        if results:
            return dict(results[0]["c"])
        return None

    def get_video_by_id(self, video_id: str) -> Optional[Dict]:
        """
        Retrieve video node by video_id.

        Args:
            video_id: YouTube video ID

        Returns:
            Video dict or None if not found
        """
        query = "MATCH (v:Video {video_id: $video_id}) RETURN v"
        results = self.driver.query(query, {"video_id": video_id})
        if results:
            return dict(results[0]["v"])
        return None

    def get_related_concepts(self, concept_names: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get concepts that co-occur with the given concepts.

        Args:
            concept_names: List of concept names to find related concepts for

        Returns:
            Dict mapping concept_name -> list of related concepts with confidence scores
            Format: {"concept": {"related_concept": confidence_score, ...}}
        """
        if not concept_names:
            return {}

        query = """
            MATCH (c1:Concept)-[r:co_occurs_with]->(c2:Concept)
            WHERE c1.name IN $concept_names
            RETURN c1.name as source_concept, c2.name as related_concept, r.confidence_score as confidence
        """
        results = self.driver.query(query, {"concept_names": concept_names})

        # Organize by source concept
        related = {}
        for r in results:
            source = r["source_concept"]
            if source not in related:
                related[source] = {}
            related[source][r["related_concept"]] = r["confidence"]

        return related

    def get_concept_provenance(self, concept_names: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Get first mention (provenance) for each concept.

        Args:
            concept_names: List of concept names

        Returns:
            Dict mapping concept_name -> {video_id, video_title, timestamp_seconds}
        """
        if not concept_names:
            return {}

        query = """
            MATCH (c:Concept)-[:introduced_in]->(t:Timestamp)
            WHERE c.name IN $concept_names
            MATCH (v:Video {video_id: t.video_id})
            RETURN c.name as concept, v.video_id as video_id, v.title as video_title, t.timestamp_seconds as timestamp
        """
        results = self.driver.query(query, {"concept_names": concept_names})

        # One entry per concept (first mention)
        provenance = {}
        for r in results:
            concept = r["concept"]
            if concept not in provenance:  # Keep first mention only
                provenance[concept] = {
                    "video_id": r["video_id"],
                    "video_title": r["video_title"],
                    "timestamp_seconds": r["timestamp"],
                }

        return provenance

    def get_concept_frequency(self, concept_names: List[str]) -> Dict[str, int]:
        """
        Get how many videos discuss each concept.

        Args:
            concept_names: List of concept names

        Returns:
            Dict mapping concept_name -> count of videos discussing it
        """
        if not concept_names:
            return {}

        query = """
            MATCH (c:Concept)<-[:contains]-(v:Video)
            WHERE c.name IN $concept_names
            RETURN c.name as concept, COUNT(DISTINCT v) as video_count
        """
        results = self.driver.query(query, {"concept_names": concept_names})

        return {r["concept"]: r["video_count"] for r in results}

    def get_concepts_for_chunk(
        self,
        video_id: str,
        start_seconds: Optional[int] = None,
        end_seconds: Optional[int] = None,
        window_margin: int = 30
    ) -> List[str]:
        """
        Get concepts for a specific chunk using timestamp-window matching (Tier 1).
        Falls back to all video concepts if no timestamp available (Tier 2).

        Tier 1 (precise): For chunks with start/end_seconds, find concepts that appear_at
        timestamps within [start_seconds - margin, end_seconds + margin].

        Tier 2 (fallback): If no confident Tier 1 match or no timestamps, return all
        concepts for the video.

        Args:
            video_id: YouTube video ID
            start_seconds: Start timestamp of chunk (optional)
            end_seconds: End timestamp of chunk (optional)
            window_margin: Seconds before/after chunk to include in match window

        Returns:
            List of concept names relevant to this chunk
        """
        # Tier 1: Precise timestamp-window matching
        if start_seconds is not None and end_seconds is not None:
            window_start = max(0, start_seconds - window_margin)
            window_end = end_seconds + window_margin

            query = """
                MATCH (c:Concept)-[appears:appears_at]->(t:Timestamp)
                WHERE t.video_id = $video_id
                  AND t.timestamp_seconds >= $window_start
                  AND t.timestamp_seconds <= $window_end
                RETURN DISTINCT c.name as concept
            """
            results = self.driver.query(query, {
                "video_id": video_id,
                "window_start": window_start,
                "window_end": window_end,
            })

            tier1_concepts = [r["concept"] for r in results]
            if tier1_concepts:
                return tier1_concepts

        # Tier 2: Fallback to all video concepts
        query = """
            MATCH (v:Video {video_id: $video_id})-[:contains]->(c:Concept)
            RETURN DISTINCT c.name as concept
        """
        results = self.driver.query(query, {"video_id": video_id})
        return [r["concept"] for r in results]

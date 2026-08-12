from typing import Optional, List, Dict, Tuple
from .embeddings import EmbeddingGenerator
from .search import TranscriptSearcher
from .knowledge_graph import KnowledgeGraph


class ConceptDeduplicator:
    """
    Deduplicate concepts across videos using semantic embeddings.

    Process:
    1. Embed each new concept description via EmbeddingGenerator
    2. Query Chroma for similar existing concepts (similarity > 0.85)
    3. Reuse matched Concept node or create new one

    Embeddings live in Chroma (for search), Neo4j only stores structure.
    """

    def __init__(self, kg: KnowledgeGraph):
        """
        Initialize deduplicator.

        Args:
            kg: KnowledgeGraph instance (for Neo4j node creation)
        """
        self.kg = kg
        self.embedding_gen = EmbeddingGenerator()
        self.searcher = TranscriptSearcher()

    def deduplicate_concepts(
        self,
        concepts: List[Dict[str, str]],
        video_id: str,
        similarity_threshold: float = 0.85,
    ) -> List[Tuple[str, bool]]:
        """
        Deduplicate a list of concepts, reusing or creating Neo4j nodes.

        Args:
            concepts: List of {"name": "...", "description": "..."} dicts
            video_id: YouTube video ID (for tracking origin)
            similarity_threshold: Similarity score threshold for matching (0-1)

        Returns:
            List of (concept_name, is_new) tuples
            - is_new=True: newly created Concept node
            - is_new=False: matched to existing concept
        """
        results = []

        for concept in concepts:
            name = concept.get("name", "").strip()
            description = concept.get("description", "").strip()

            if not name or not description:
                continue

            # Check if concept already exists in Neo4j
            existing = self.kg.get_concept_by_name(name)
            if existing:
                results.append((name, False))
                continue

            # Try to find semantically similar concept via Chroma
            matched_concept = self._find_similar_concept(
                description,
                similarity_threshold,
            )

            if matched_concept:
                # Reuse existing concept
                results.append((matched_concept, False))
            else:
                # Create new concept node
                self.kg.create_concept_node(name, description)
                results.append((name, True))

        return results

    def _find_similar_concept(
        self,
        description: str,
        similarity_threshold: float,
    ) -> Optional[str]:
        """
        Search Chroma for semantically similar concept description.

        Args:
            description: Concept description text
            similarity_threshold: Minimum similarity score (0-1)

        Returns:
            Matching concept name or None if no match above threshold
        """
        try:
            # Query Chroma using TranscriptSearcher (semantic similarity search)
            # Return top 3 results to look for a matching concept
            results = self.searcher.search(description, top_k=3)

            if not results:
                return None

            # Find best result with sufficient similarity
            best_result = results[0]
            score = best_result.get("similarity_score", 0.0)

            if score >= similarity_threshold:
                # Extract concept name from video title or metadata
                # This is a heuristic: concepts in Chroma are stored as chunks
                # We need a way to map back to concept names
                # For now, return None — this needs a proper mapping layer
                return None

            return None

        except Exception:
            return None

    def calculate_co_occurrence_scores(
        self,
        concept1_timestamps: List[int],
        concept2_timestamps: List[int],
        proximity_window: int = 60,
    ) -> Tuple[float, float]:
        """
        Calculate asymmetric co-occurrence confidence scores.

        Args:
            concept1_timestamps: Seconds where concept1 appears
            concept2_timestamps: Seconds where concept2 appears
            proximity_window: Concepts within N seconds count as co-occurring

        Returns:
            (score_1_to_2, score_2_to_1) tuple
            - score_1_to_2: proportion of concept1 occurrences near concept2
            - score_2_to_1: proportion of concept2 occurrences near concept1
        """
        score_1_to_2 = self._calculate_proximity_score(
            concept1_timestamps,
            concept2_timestamps,
            proximity_window,
        )
        score_2_to_1 = self._calculate_proximity_score(
            concept2_timestamps,
            concept1_timestamps,
            proximity_window,
        )

        return score_1_to_2, score_2_to_1

    def _calculate_proximity_score(
        self,
        source_timestamps: List[int],
        target_timestamps: List[int],
        proximity_window: int,
    ) -> float:
        """
        Calculate how often source timestamps co-occur with target.

        Args:
            source_timestamps: Primary concept timestamps
            target_timestamps: Secondary concept timestamps
            proximity_window: Time window for co-occurrence (seconds)

        Returns:
            Float 0-1: proportion of source occurrences within window of target
        """
        if not source_timestamps:
            return 0.0

        co_occurrence_count = 0

        for source_ts in source_timestamps:
            # Check if any target timestamp is within proximity window
            for target_ts in target_timestamps:
                if abs(source_ts - target_ts) <= proximity_window:
                    co_occurrence_count += 1
                    break  # Count each source occurrence once

        return min(co_occurrence_count / len(source_timestamps), 1.0)

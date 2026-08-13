from typing import List, Dict, Any, Optional
from sentence_transformers import SentenceTransformer
import chromadb
from .config import get_config_dir


class TranscriptSearcher:
    """Search transcript chunks by semantic similarity."""

    def __init__(self):
        """Initialize searcher with embedding model and Chroma DB."""
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.chroma_db_dir = get_config_dir() / "chroma_db"

        # Connect to Chroma
        self.client = chromadb.PersistentClient(
            path=str(self.chroma_db_dir)
        )
        try:
            self.collection = self.client.get_collection(
                name="transcript_chunks"
            )
        except ValueError:
            # Collection doesn't exist yet
            self.collection = None

    def search(
        self,
        query: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search for transcript chunks similar to query.

        Args:
            query: Search query
            top_k: Number of results to return

        Returns:
            List of results with format:
            {
                "video_id": "...",
                "video_title": "...",
                "chunk_text": "...",
                "similarity_score": 0.95,
                "start_seconds": 123,  (optional, None if not available)
                "end_seconds": 145,    (optional, None if not available)
            }
        """
        if not self.collection:
            return []

        # Generate embedding for query
        query_embedding = self.model.encode(query)

        # Search Chroma
        results = self.collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=top_k,
        )

        # Format results
        formatted_results = []
        if results["documents"] and len(results["documents"]) > 0:
            for i, chunk_text in enumerate(results["documents"][0]):
                metadata = results["metadatas"][0][i]
                distance = results["distances"][0][i]
                # Convert distance to similarity (cosine distance to similarity)
                similarity = 1 - distance

                result = {
                    "video_id": metadata["video_id"],
                    "video_title": metadata["video_title"],
                    "chunk_text": chunk_text,
                    "similarity_score": round(similarity, 3),
                }

                # Add timestamps if available
                if "start_seconds" in metadata:
                    result["start_seconds"] = metadata["start_seconds"]
                if "end_seconds" in metadata:
                    result["end_seconds"] = metadata["end_seconds"]

                formatted_results.append(result)

        return formatted_results

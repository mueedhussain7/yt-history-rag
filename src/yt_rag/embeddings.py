import json
import re
import string
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from sentence_transformers import SentenceTransformer
import chromadb
from .config import get_config_dir


class EmbeddingGenerator:
    """Generate and store embeddings for transcript chunks."""

    def __init__(self):
        """Initialize embedding model and Chroma vector DB."""
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.chroma_db_dir = get_config_dir() / "chroma_db"
        self.chroma_db_dir.mkdir(parents=True, exist_ok=True)

        # Initialize Chroma client
        self.client = chromadb.PersistentClient(
            path=str(self.chroma_db_dir)
        )
        self.collection = self.client.get_or_create_collection(
            name="transcript_chunks",
            metadata={"hnsw:space": "cosine"}
        )

    def _extract_significant_words(self, text: str) -> List[str]:
        """Extract significant words for timestamp matching."""
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'is', 'are', 'was', 'were',
            'to', 'of', 'in', 'on', 'at', 'by', 'with', 'from', 'as',
            'that', 'this', 'it', 'for', 'be', 'have', 'has', 'had',
            'do', 'does', 'did', 'can', 'could', 'will', 'would', 'may',
            'might', 'must', 'should', 'shall', 'about', 'above', 'after',
            'music', 'heat',
        }

        words = text.lower().translate(str.maketrans('', '', string.punctuation)).split()
        return [w for w in words if w and w not in stop_words and len(w) > 2]

    def _match_chunk_to_timestamps(
        self,
        chunk_text: str,
        timestamps: List[Dict[str, Any]],
        ts_index: int,
        min_word_matches: int = 2
    ) -> Tuple[Optional[int], Optional[int], int]:
        """
        Match a chunk to timestamps using greedy forward scan.

        Returns:
            (start_seconds, end_seconds, new_ts_index)
            - start_seconds/end_seconds are None if no confident match found
            - new_ts_index points to next unprocessed timestamp
        """
        chunk_words = set(self._extract_significant_words(chunk_text))

        if not chunk_words:
            return None, None, ts_index

        start_seconds = None
        end_seconds = None
        last_match_idx = None

        # Scan forward from ts_index
        for i in range(ts_index, len(timestamps)):
            ts_text = timestamps[i]["text"]
            ts_words = set(self._extract_significant_words(ts_text))

            matching_words = chunk_words & ts_words

            if len(matching_words) >= min_word_matches:
                if start_seconds is None:
                    start_seconds = timestamps[i]["timestamp"]

                end_seconds = timestamps[i]["timestamp"]
                last_match_idx = i
            else:
                # No match - if we had matches, stop scanning
                if start_seconds is not None:
                    break

        if start_seconds is None:
            return None, None, ts_index

        new_ts_index = last_match_idx + 1 if last_match_idx is not None else ts_index
        return start_seconds, end_seconds, new_ts_index

    def chunk_transcript(
        self,
        transcript: str,
        timestamps: Optional[List[Dict[str, Any]]] = None,
        chunk_size: int = 4
    ) -> List[Tuple[str, Optional[int], Optional[int]]]:
        """
        Split transcript into chunks of ~4 sentences, optionally with timestamps.

        Args:
            transcript: Full transcript text
            timestamps: Optional list of {"timestamp": seconds, "text": text} dicts
            chunk_size: Number of sentences per chunk

        Returns:
            List of (chunk_text, start_seconds, end_seconds) tuples
            - start_seconds/end_seconds are None if no confident timestamp match
        """
        # Split by sentence
        sentences = re.split(r'(?<=[.!?])\s+', transcript.strip())
        sentences = [s.strip() for s in sentences if s.strip()]

        chunks = []
        ts_index = 0

        for i in range(0, len(sentences), chunk_size):
            chunk = ' '.join(sentences[i:i + chunk_size])
            if not chunk.strip():
                continue

            # Match to timestamps if available
            start_sec = None
            end_sec = None

            if timestamps:
                start_sec, end_sec, ts_index = self._match_chunk_to_timestamps(
                    chunk, timestamps, ts_index, min_word_matches=2
                )

            chunks.append((chunk, start_sec, end_sec))

        return chunks

    def embed_and_store(
        self,
        video_id: str,
        video_title: str,
        transcript: str,
        timestamps: Optional[List[Dict[str, Any]]] = None
    ) -> int:
        """
        Generate embeddings for transcript chunks and store in Chroma.

        Args:
            video_id: YouTube video ID
            video_title: Video title
            transcript: Full transcript text
            timestamps: Optional list of {"timestamp": seconds, "text": text} dicts

        Returns:
            Number of chunks embedded
        """
        chunks_with_times = self.chunk_transcript(transcript, timestamps=timestamps)

        if not chunks_with_times:
            return 0

        # Extract chunk text for embedding
        chunk_texts = [chunk_text for chunk_text, _, _ in chunks_with_times]

        # Generate embeddings
        embeddings = self.model.encode(chunk_texts)

        # Prepare data for Chroma
        ids = [f"{video_id}_chunk_{i}" for i in range(len(chunks_with_times))]
        documents = chunk_texts
        metadatas = []

        for i, (chunk_text, start_sec, end_sec) in enumerate(chunks_with_times):
            metadata = {
                "video_id": video_id,
                "video_title": video_title,
                "chunk_index": i,
            }
            # Include timestamps if available (can be None)
            if start_sec is not None:
                metadata["start_seconds"] = start_sec
            if end_sec is not None:
                metadata["end_seconds"] = end_sec

            metadatas.append(metadata)

        # Store in Chroma
        self.collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings.tolist(),
            metadatas=metadatas,
        )

        return len(chunks_with_times)

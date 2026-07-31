import json
import re
from pathlib import Path
from typing import List, Dict, Any
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

    def chunk_transcript(self, transcript: str, chunk_size: int = 4) -> List[str]:
        """
        Split transcript into chunks of ~4 sentences.

        Args:
            transcript: Full transcript text
            chunk_size: Number of sentences per chunk

        Returns:
            List of text chunks
        """
        # Split by sentence (basic approach: period + space)
        sentences = re.split(r'(?<=[.!?])\s+', transcript.strip())
        sentences = [s.strip() for s in sentences if s.strip()]

        chunks = []
        for i in range(0, len(sentences), chunk_size):
            chunk = ' '.join(sentences[i:i + chunk_size])
            if chunk.strip():
                chunks.append(chunk)

        return chunks

    def embed_and_store(
        self,
        video_id: str,
        video_title: str,
        transcript: str
    ) -> int:
        """
        Generate embeddings for transcript chunks and store in Chroma.

        Returns:
            Number of chunks embedded
        """
        chunks = self.chunk_transcript(transcript)

        if not chunks:
            return 0

        # Generate embeddings
        embeddings = self.model.encode(chunks)

        # Prepare data for Chroma
        ids = [f"{video_id}_chunk_{i}" for i in range(len(chunks))]
        documents = chunks
        metadatas = [
            {
                "video_id": video_id,
                "video_title": video_title,
                "chunk_index": i,
            }
            for i in range(len(chunks))
        ]

        # Store in Chroma
        self.collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings.tolist(),
            metadatas=metadatas,
        )

        return len(chunks)

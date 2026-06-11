# ADR 0001: Use Graph RAG (Neo4j) Instead of Vector-Only RAG

## Status
Accepted

## Context
The system needs to search across a user's YouTube watch history and return relevant video segments. The core requirement is semantic search—finding conceptually similar content even when exact keywords don't match.

Two architectural approaches were considered:
1. **Vector-only RAG**: Use embeddings + vector search (Chroma) to find relevant transcripts
2. **Graph RAG**: Add a knowledge graph (Neo4j) tracking concepts and their relationships across videos

## Decision
Implement **Graph RAG with Neo4j**, not vector-only.

## Rationale

### 1. Ontology (Concept Relationships)
Video transcripts discuss interrelated concepts. A user searching "how do I authenticate users" should surface videos about:
- JWT tokens
- OAuth flows
- Session management
- Cookies

These are semantically related, but vector search alone doesn't capture these relationships explicitly. A knowledge graph tracks:
- Which concepts appear in which videos
- Which concepts co-occur (appear together)
- Concept definitions and context

This enables richer context in results and better ranking of related content.

### 2. Provenance (Grounding)
Users need to know *where* information came from to verify accuracy:
- Which video introduced a concept first?
- How many videos discuss this topic?
- What's the original context (timestamp, sentence)?

Graph nodes can link concepts directly to videos and timestamps, providing complete provenance. This is critical for trust and grounding in personal knowledge systems.

### 3. Complex Query Support
Graph traversal enables queries vector-only systems can't handle:
- "Show me all videos about authentication and related concepts"
- "What foundational concepts do I need to understand this topic?"
- "Concepts I've seen recently but rarely"

These queries require understanding relationships, not just similarity.

### 4. Future-Proof
Ontology and provenance are foundational to the system. Adding them later requires restructuring—extracting concepts retroactively from indexed vectors, rebuilding relationships, data migration. Building them in from day one is simpler.

## Trade-Offs

### Added Complexity
Graph RAG is more complex than vector-only:
- Requires Neo4j setup (Docker)
- Concept extraction pipeline (via OpenRouter LLM)
- Graph relationship management
- More complex data model

**Mitigation**: The added complexity is justified by the improved accuracy and semantic understanding. The benefits outweigh the cost.

### Performance
Graph queries are slower than pure vector similarity search. Concept extraction via LLM adds latency to sync.

**Mitigation**: 
- Sync happens offline (user doesn't wait)
- Search combines vector search (fast) + graph context (slower but adds value)
- Neo4j indexing keeps queries performant

## Implementation

### Technology Choices
- **Graph DB**: Neo4j (local Docker instance)
- **Graph Integration**: LlamaIndex GraphRAGIndex with Neo4j backend
- **Entity Extraction**: OpenRouter API (pluggable model selection)
- **Vector Search**: Chroma + sentence-transformers (unchanged)

### Data Model
```
Nodes:
- Video (id, title, url, watch_date)
- Concept (name, definition_snippet)
- Timestamp (video_id, seconds, transcript_snippet)

Edges:
- Video --"contains"--> Concept (occurrence_count)
- Concept --"appears_at"--> Timestamp
- Concept --"co_occurs_with"--> Concept (confidence)
- Concept --"introduced_in"--> Timestamp (first occurrence)
```

### Concept Extraction Pipeline
1. Fetch new video transcript via yt-dlp
2. Send transcript to OpenRouter LLM: "Extract key concepts (tools, frameworks, methodologies, patterns)"
3. Return concepts as JSON list with context snippets
4. Create concept nodes and edges in Neo4j
5. Generate embeddings for transcript (unchanged)

### Incremental Processing
Only new videos are processed on sync. The graph grows over time. Concept extraction quality improvements can be applied to the full graph in optional manual re-index runs.

## Alternatives Considered

### Vector-Only RAG
Simpler, faster, lower cost. Sufficient for basic fact retrieval ("find videos about JWT"). Insufficient for understanding concept relationships and providing rich provenance.

Rejected because the user prioritized accuracy and understanding complex queries over simplicity.

## Consequences

### Positive
- Richer semantic understanding across the knowledge base
- Complete provenance for all results (verifiable, trustworthy)
- Support for future complex queries
- Ontology available for export/analysis
- Better ranking and result diversity

### Negative
- More setup (Docker, Neo4j)
- Slower sync (LLM extraction adds latency)
- Higher API costs (OpenRouter calls for every video)
- More complex data model and codebase
- Requires ongoing maintenance of concept extraction quality

## Decision Log
- **2026-06-11**: Grilling session with user confirmed that accuracy and understanding concept relationships is more important than simplicity. Graph RAG approved.

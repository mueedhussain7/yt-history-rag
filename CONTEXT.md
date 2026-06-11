# GraphRAG YouTube History — Domain Glossary

## Core Entities

### Watch History
The complete record of videos a user has watched on their YouTube account. Syncing pulls new videos added to this history since the last sync. Watch history is the authoritative source of truth for what videos exist in the system.

### Video
A single YouTube video with metadata (title, URL, watch date, duration). A video may be **indexed** (transcript fetched and embedded) or **failed** (transcript extraction failed, not searchable).

### Transcript
The text content of a video's closed captions or auto-generated captions. Extracted via yt-dlp or youtube-transcript-api. Essential for semantic search—videos without transcripts are not indexed.

### Concept
A key technical term, tool, framework, or methodology extracted from video transcripts. Examples: "JWT", "OAuth", "REST API", "caching". Concepts are nodes in the knowledge graph and can be searched semantically.

## Search & Retrieval

### Semantic Search
Search based on meaning rather than exact keyword matching. A query like "how do I authenticate users" finds videos about JWT, OAuth, and sessions even if those exact words don't appear in the query. Powered by embeddings and vector similarity.

### Embedding
A vectorized representation of text (a concept, snippet, or query) in high-dimensional space. Similar concepts have similar embeddings, enabling semantic search. Generated locally via `sentence-transformers`.

### Vector Search
Similarity-based search that finds embeddings closest to a query embedding in vector space. Returns results ranked by relevance score (0-1).

### Retrieval Result
The output of a search query: video link, timestamp, transcript snippet showing the match, and relevance score.

## Knowledge Graph & Provenance

### Knowledge Graph
A graph database (Neo4j) storing concepts as nodes and their relationships as edges. Tracks which videos introduce which concepts, where concepts co-occur, and temporal relationships (first mention).

### Concept Node
A node in the knowledge graph representing an extracted concept. Contains the concept name and definition snippet from the original transcript context.

### Provenance
Metadata about where a concept came from: which video, which timestamp, the original transcript snippet. Essential for grounding results and verifying accuracy.

### Ontology
The structured set of relationships in the knowledge graph:
- **contains**: Video contains/discusses Concept (with occurrence count)
- **appears_at**: Concept mentioned at specific Timestamp
- **co_occurs_with**: Two concepts appear together in transcripts (confidence score)
- **introduced_in**: Concept's first mention (earliest timestamp)

### Concept Occurrence
A single mention of a concept in a transcript, linked to a specific timestamp. Multiple occurrences of the same concept in the same video are tracked separately.

## Sync & Indexing

### Sync
The process of pulling new videos from YouTube watch history and processing them for search:
1. Fetch new video IDs from YouTube account
2. For each new video: fetch transcript via yt-dlp
3. Extract concepts from transcript via OpenRouter LLM
4. Generate embeddings for transcript
5. Add video, concepts, and relationships to graph and vector DB

Sync is incremental—only new videos are processed. Existing videos are never re-processed.

### Indexed
A video is **indexed** when:
- Transcript was successfully fetched
- Concepts were extracted
- Embeddings were generated
- Data was persisted to vector DB and knowledge graph

An indexed video is fully searchable.

### Failed
A video is **failed** when transcript extraction was unsuccessful. Failed videos are tracked separately and not searchable. Users can see which videos failed and optionally retry.

### Sync State
Persistent metadata tracking:
- Which video IDs have been indexed
- Last sync timestamp
- Concept extraction statistics

## System Behavior

### Graceful Degradation (Per-Video)
If a single video's transcript fails to extract, the system logs the failure and continues with the next video. One video's failure does not block the entire sync.

### Critical Failures
Sync aborts if a critical error occurs:
- YouTube authentication expired
- Network unreachable
- Neo4j or Chroma unavailable

User sees a clear error message and must fix the issue before retrying.

### Query Scope
All search results are strictly from the user's watch history. No external content is included. The system is grounded in the user's personal data.

## Configuration

### One-Time Setup
Users authenticate with YouTube once via OAuth. The system stores the authentication token and syncs automatically per their configured schedule.

### Sync Schedule
User-configurable sync cadence:
- Manual (on-demand via CLI)
- Daily
- Weekly

The sync process runs in the background and updates the local graph and vector DB.

### Data Directory
All data persists locally in `~/.yt-rag/`:
- Config (OAuth tokens, sync preferences)
- Chroma vector DB
- Neo4j database
- Sync state
- Transcript cache (optional)

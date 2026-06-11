# GraphRAG YouTube History — Architecture Overview

## System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                         User's Machine                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────┐                                           │
│  │   CLI Interface  │ (Click/Typer)                             │
│  │  yt-rag init     │  - OAuth setup                            │
│  │  yt-rag sync     │  - Trigger sync                           │
│  │  yt-rag search   │  - Execute search                         │
│  └────────┬─────────┘                                           │
│           │                                                     │
│  ┌────────▼─────────────────────────────────────────────────┐  │
│  │            Sync Pipeline                                 │  │
│  ├──────────────────────────────────────────────────────────┤  │
│  │ 1. Fetch new video IDs (YouTube OAuth API)              │  │
│  │ 2. Download transcripts (yt-dlp + fallback)             │  │
│  │ 3. Extract concepts (OpenRouter LLM)                    │  │
│  │ 4. Generate embeddings (sentence-transformers)          │  │
│  │ 5. Update vector DB (Chroma)                            │  │
│  │ 6. Update knowledge graph (Neo4j)                       │  │
│  │ 7. Save sync state                                      │  │
│  └────────┬─────────────────────────────────────────────────┘  │
│           │                                                     │
│  ┌────────▼─────────────────────────────────────────────────┐  │
│  │         Search Pipeline                                  │  │
│  ├──────────────────────────────────────────────────────────┤  │
│  │ 1. Generate query embedding                             │  │
│  │ 2. Vector similarity search (Chroma)                    │  │
│  │ 3. Graph context lookup (Neo4j)                         │  │
│  │ 4. Rank & format results                                │  │
│  │ 5. Return to user                                       │  │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │         Local Data (~/.yt-rag/)                         │   │
│  ├─────────────────────────────────────────────────────────┤   │
│  │ • config.yaml (OAuth tokens, sync schedule)             │   │
│  │ • Chroma DB (embeddings, transcript vectors)            │   │
│  │ • Neo4j DB (concepts, relationships, provenance)        │   │
│  │ • sync_state.json (indexed videos, last sync time)      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
         │                           │
         │ (API calls, no data)      │
         ▼                           ▼
    ┌──────────┐           ┌────────────────┐
    │ YouTube  │           │  OpenRouter    │
    │  OAuth   │           │  (concept LLM) │
    │ Data API │           │                │
    └──────────┘           └────────────────┘
```

## Technology Stack

### Core Libraries
- **LlamaIndex** - RAG orchestration and document indexing
- **Chroma** - Vector database (local, embedded)
- **Neo4j** - Knowledge graph database (local, Docker)
- **sentence-transformers** - Local embeddings (all-MiniLM-L6-v2)
- **yt-dlp** - Transcript extraction
- **youtube-transcript-api** - Transcript fallback
- **OpenRouter SDK** - LLM API for concept extraction
- **Click/Typer** - CLI framework
- **APScheduler** - Sync scheduling

### Infrastructure
- **Python 3.10+** - Runtime
- **Docker** - Neo4j container
- **SQLite** - Sync state and config (local)

## Data Flow: Sync

```
1. [Trigger Sync]
   └─> OAuth token (from config)
       └─> YouTube API: Get watch history since last sync
           └─> New video IDs: [vid1, vid2, vid3...]

2. [For each new video]
   ├─> yt-dlp: Download transcript
   │   └─> Fallback to youtube-transcript-api if needed
   │   └─> Store transcript text
   │
   ├─> OpenRouter LLM: Extract concepts
   │   └─> Prompt: "Extract key technical concepts..."
   │   └─> Return: JSON list with concept names + context
   │
   ├─> sentence-transformers: Generate embeddings
   │   ├─> Full transcript embedding (for vector search)
   │   └─> Concept embeddings (for graph context)
   │
   ├─> Chroma: Store vector embeddings
   │   └─> Metadata: video_id, timestamp, concept
   │
   └─> Neo4j: Create/update graph
       ├─> Video node (title, url, watch_date)
       ├─> Concept nodes (name, definition_context)
       ├─> Timestamp nodes (video_id, seconds, snippet)
       ├─> Edges:
       │   ├─ Video --"contains"--> Concept
       │   ├─ Concept --"appears_at"--> Timestamp
       │   ├─ Concept --"co_occurs_with"--> Concept
       │   └─ Concept --"introduced_in"--> Timestamp
       └─> Update sync state

3. [Sync completes]
   └─> Report: X videos indexed, Y concepts extracted, Z failed
```

## Data Flow: Search

```
1. [User query]
   └─> "How do I authenticate users?"

2. [Generate embedding]
   └─> sentence-transformers: Embed query
       └─> Vector representation of query

3. [Vector search (Chroma)]
   └─> Find top-K most similar embeddings
       └─> Return: [(video_id, timestamp, snippet, score), ...]

4. [Graph context (Neo4j)]
   └─> For each result, find related concepts
       └─> Concepts that co-occur
       └─> When concept was first introduced
       └─> How many videos discuss it

5. [Rank & format]
   ├─> Sort by relevance score
   ├─> Add provenance (video link, timestamp)
   ├─> Format snippet with context
   └─> Return results to user

6. [Output]
   └─> 
   1. Video Title | youtube.com/watch?v=xyz | 12:34
      "...snippet of matched transcript..."
      Relevance: 92%
   
   2. Another Video | youtube.com/watch?v=abc | 05:12
      "...another relevant snippet..."
      Relevance: 88%
```

## Key Design Decisions

| Decision | Reasoning |
|----------|-----------|
| **Graph RAG** | Ontology + provenance for better accuracy and complex queries |
| **yt-dlp** | No API quota limits, more reliable for bulk extraction |
| **OpenRouter** | Vendor-independent LLM choice, quality concept extraction |
| **Chroma** | Lightweight embedded vector DB, no separate service needed |
| **Neo4j (Docker)** | Local graph DB, fully self-contained |
| **Incremental sync** | Only new videos processed, existing videos never re-indexed |
| **Per-video error handling** | One failed transcript doesn't block entire sync |
| **CLI + config file** | Simple DX, no web UI overhead for v1 |

See **docs/adr/** for detailed trade-offs on each decision.

## Configuration Example

```yaml
# ~/.yt-rag/config.yaml
youtube:
  oauth_token: "ya29.a0..."  # Auto-populated after `yt-rag init`

sync:
  schedule: "daily"  # or "manual", "weekly"
  start_date: "2024-01-01"  # Videos watched after this date

embeddings:
  model: "sentence-transformers/all-MiniLM-L6-v2"
  # To use API instead:
  # provider: "openai"
  # model: "text-embedding-3-small"
  # api_key: "${OPENAI_API_KEY}"

concept_extraction:
  provider: "openrouter"
  model: "mistral/mistral-large"
  api_key: "${OPENROUTER_API_KEY}"
  # Alternative: local_llm with ollama

transcript:
  primary_method: "yt-dlp"
  fallback_enabled: true

storage:
  data_dir: "~/.yt-rag"
  chroma_path: "~/.yt-rag/chroma_db"
  neo4j_path: "~/.yt-rag/neo4j_data"
```

## Deployment

### User Setup (One-Time)

```bash
# 1. Install
pip install yt-history-rag

# 2. Initialize (creates ~/.yt-rag, sets up Neo4j Docker)
yt-rag init
# → Opens browser for YouTube OAuth
# → Pulls Neo4j Docker image
# → Creates local Chroma DB

# 3. First sync (one-time full index)
yt-rag sync --full
# → Fetches all videos from watch history
# → Extracts transcripts and concepts
# → Builds initial knowledge graph

# 4. Configure sync schedule
yt-rag config set sync.schedule daily
# or manually: yt-rag sync
```

### Ongoing Usage

```bash
# Search
yt-rag search "authentication patterns"

# Manual sync
yt-rag sync

# Check status
yt-rag status
# → Last sync: 2 hours ago
# → Videos indexed: 1,247
# → Concepts extracted: 3,892
# → Failed videos: 3 (show which)
```

## Future Enhancements (Not in v1)

- Web UI for search and browsing
- Concept visualization (graph explorer)
- Advanced filtering (by date, speaker, topic)
- Custom concept tagging
- Export capabilities (graph, CSV, markdown)
- Multi-user cloud sync
- Local LLM fallback for concept extraction
- Fine-tuned embeddings for domain-specific accuracy

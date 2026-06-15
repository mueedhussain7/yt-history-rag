# Implementation Issues - Ready to Create

These issues are ready to be created on GitHub. Create them in this order (they reference previous issue numbers in the "Blocked by" field).

---

## Issue 1: Project Scaffold & Configuration Management

**Title**: `feat: project scaffold and configuration management`

**Labels**: `ready-for-agent`, `epic`

**Body**:
```
## What to build

Set up the Python project structure with all necessary dependencies and configuration management. Users should be able to run `yt-rag init` to create the ~/.yt-rag/ directory structure and config.yaml file.

This is the foundation for all other features—all subsequent features depend on this.

**End-to-end behavior**: 
- User runs `yt-rag init`
- System creates ~/.yt-rag/ directory with subdirectories (chroma_db, neo4j_data)
- System creates config.yaml template with required and optional keys
- System is ready for authentication setup

## Acceptance criteria

- [ ] pyproject.toml created with all dependencies (LlamaIndex, Chroma, Neo4j driver, yt-dlp, sentence-transformers, Click/Typer, APScheduler)
- [ ] Source structure created (src/yt_rag/)
- [ ] `yt-rag init` command creates ~/.yt-rag/ directory with subdirectories
- [ ] config.yaml template created with documented keys (youtube, sync, embeddings, concept_extraction, transcript, storage)
- [ ] Configuration can be read and written via YAML
- [ ] Tests pass for config management

## Blocked by

None - can start immediately

## User stories

- User story 12: "I want a simple one-time setup"
```

---

## Issue 2: YouTube OAuth Authentication

**Title**: `feat: YouTube OAuth authentication flow`

**Labels**: `ready-for-agent`

**Body**:
```
## What to build

Implement YouTube OAuth 2.0 authentication. Users authenticate once during `yt-rag init`, and the system stores the token locally in config.yaml for future API calls. Tokens should be refreshed automatically.

**End-to-end behavior**:
- User runs `yt-rag init`
- System opens browser for YouTube OAuth consent
- User grants permission to read watch history
- System stores token in ~/.yt-rag/config.yaml
- Subsequent API calls use stored token (with automatic refresh)

## Acceptance criteria

- [ ] YouTube OAuth app configured (client ID, redirect URI)
- [ ] OAuth flow opens browser and captures auth code
- [ ] Access token and refresh token stored in config.yaml
- [ ] Tokens are encrypted or stored securely
- [ ] Token refresh happens automatically when expired
- [ ] Clear error message if auth fails or is revoked
- [ ] Tests cover auth flow and token refresh

## Blocked by

- Issue 1

## User stories

- User story 2: "I want to authenticate with YouTube once via OAuth"
```

---

## Issue 3: Fetch Watch History from YouTube

**Title**: `feat: fetch YouTube watch history via Data API`

**Labels**: `ready-for-agent`

**Body**:
```
## What to build

Fetch the user's YouTube watch history from the YouTube Data API. Track which videos are new since the last sync. Implement sync state management to remember which videos have been processed.

**End-to-end behavior**:
- During sync, system calls YouTube Data API with stored auth token
- System fetches all videos from watch history since last sync date
- System identifies new videos (not in sync_state.json)
- System stores video metadata (id, title, url, watch_date, duration)
- sync_state.json is updated with processed video IDs

## Acceptance criteria

- [ ] YouTube Data API integration implemented
- [ ] Fetches videos from watch history with pagination support
- [ ] Identifies new videos (by video ID)
- [ ] Video metadata stored (id, title, url, watch_date, duration)
- [ ] sync_state.json tracks indexed videos and last sync timestamp
- [ ] Handles API errors gracefully (quota exceeded, auth failure, network error)
- [ ] Tests cover new video detection and state tracking

## Blocked by

- Issue 2

## User stories

- User story 1: "I want to import my YouTube watch history"
- User story 3: "I want to configure when syncing happens"
```

---

## Issue 4: Transcript Extraction Pipeline

**Title**: `feat: extract transcripts via yt-dlp with fallback`

**Labels**: `ready-for-agent`

**Body**:
```
## What to build

Extract transcripts from YouTube videos using yt-dlp as primary method and youtube-transcript-api as fallback. Mark videos as "failed" if both extraction methods fail. Never silently index videos without transcripts.

**End-to-end behavior**:
- For each new video (from Issue 3):
  - Attempt to extract transcript via yt-dlp
  - If yt-dlp fails, attempt youtube-transcript-api
  - If both fail, mark video as failed and skip to next video
  - If successful, store transcript text locally in memory or cache
  - Log all extraction attempts and failures

## Acceptance criteria

- [ ] yt-dlp integration for subtitle/caption extraction
- [ ] youtube-transcript-api integration as fallback
- [ ] Transcript stored with video ID reference
- [ ] Failed extractions logged with video ID and error reason
- [ ] Per-video failures don't block sync (continue to next video)
- [ ] Tests cover both yt-dlp and fallback scenarios
- [ ] Tests cover graceful failure handling

## Blocked by

- Issue 3

## User stories

- User story 9: "I want the system to skip unavailable transcripts"
- User story 18: "I want reliable transcript extraction"
```

---

## Issue 5: Concept Extraction via OpenRouter LLM

**Title**: `feat: extract concepts from transcripts via OpenRouter`

**Labels**: `ready-for-agent`

**Body**:
```
## What to build

Extract key concepts (tools, frameworks, methodologies, patterns) from video transcripts using OpenRouter LLM API. User configures preferred model in config.yaml. Concepts are parsed and stored for embedding and graph storage.

**End-to-end behavior**:
- For each transcript (from Issue 4):
  - Send transcript to OpenRouter API with structured prompt
  - LLM returns JSON list of concepts with context snippets
  - Parse JSON and validate structure
  - Store concepts locally for next steps
  - Log extraction statistics (concepts per video, extraction time)

## Acceptance criteria

- [ ] OpenRouter API integration implemented
- [ ] Prompt designed to extract technical concepts (tools, frameworks, methodologies, patterns, terminology)
- [ ] Response parsed as JSON: `{concepts: [{name: string, context: string}, ...]}`
- [ ] User can configure LLM model via config.yaml (default: mistral/mistral-large)
- [ ] API key passed via OPENROUTER_API_KEY environment variable
- [ ] Failed extractions logged without blocking sync
- [ ] Tests mock OpenRouter API and validate parsing
- [ ] Cost tracking (log tokens used per video)

## Blocked by

- Issue 4

## User stories

- User story 19: "I want meaningful concepts extracted from transcripts"
```

---

## Issue 6: Vector Embeddings & Chroma Storage

**Title**: `feat: generate embeddings and store in Chroma vector DB`

**Labels**: `ready-for-agent`

**Body**:
```
## What to build

Generate vector embeddings for transcripts using sentence-transformers (local). Store embeddings in Chroma with metadata linking back to videos and timestamps. Enable semantic search on the vector store.

**End-to-end behavior**:
- For each transcript (from Issue 4):
  - Generate embedding using sentence-transformers (all-MiniLM-L6-v2)
  - Store in Chroma with metadata: {video_id, title, url, timestamp, concept}
  - Chroma persists to ~/.yt-rag/chroma_db/
- Search queries are embedded and matched against stored vectors by similarity

## Acceptance criteria

- [ ] sentence-transformers integrated (model: all-MiniLM-L6-v2)
- [ ] Chroma vector database initialized in ~/.yt-rag/chroma_db/
- [ ] Embeddings generated and stored with metadata
- [ ] Metadata includes: video_id, title, url, watch_date, concept
- [ ] Vector search returns results by cosine similarity score (0-1)
- [ ] Chroma persists across syncs
- [ ] Tests cover embedding generation and retrieval

## Blocked by

- Issue 4

## User stories

- User story 4: "I want to search using natural language"
- User story 20: "I want results ranked by relevance score"
```

---

## Issue 7: Neo4j Knowledge Graph Setup

**Title**: `feat: initialize Neo4j and create knowledge graph schema`

**Labels**: `ready-for-agent`

**Body**:
```
## What to build

Initialize Neo4j graph database running in Docker locally. Create the knowledge graph schema with nodes (Video, Concept, Timestamp) and edges (contains, appears_at, co_occurs_with, introduced_in). Implement concept deduplication logic.

**End-to-end behavior**:
- `yt-rag init` starts Neo4j Docker container (volume mounted to ~/.yt-rag/neo4j_data/)
- Graph schema created with node and edge definitions
- Connection pool configured and tested
- Concept deduplication detects near-duplicates using embedding similarity

## Graph Schema

**Nodes**:
- Video (id, title, url, watch_date, duration)
- Concept (name, definition_context)
- Timestamp (video_id, seconds, transcript_snippet)

**Edges**:
- Video --"contains"--> Concept (occurrence_count)
- Concept --"appears_at"--> Timestamp
- Concept --"co_occurs_with"--> Concept (confidence_score)
- Concept --"introduced_in"--> Timestamp

## Acceptance criteria

- [ ] Docker Neo4j container runs and persists to ~/.yt-rag/neo4j_data/
- [ ] Neo4j connection pool established and tested
- [ ] Node labels and properties created (Video, Concept, Timestamp)
- [ ] Relationship types created (contains, appears_at, co_occurs_with, introduced_in)
- [ ] Concept deduplication implemented (embedding similarity matching)
- [ ] Graph queries tested (create/read/update relationships)
- [ ] Tests use testcontainers for Neo4j

## Blocked by

- Issue 1

## User stories

- User story 7: "I want to know concept relationships and first mentions"
- User story 8: "I want to see related concepts in search results"
- User story 22: "I want to understand provenance"
```

---

## Issue 8: Semantic Search on Vectors

**Title**: `feat: semantic search across transcripts`

**Labels**: `ready-for-agent`

**Body**:
```
## What to build

Implement semantic search on the Chroma vector database. User provides a natural language query, system embeds it, finds similar transcripts, and returns results with proper formatting (title, URL, timestamp, snippet, relevance score).

**End-to-end behavior**:
- User runs: `yt-rag search "how do I authenticate users?"`
- System embeds query using sentence-transformers
- System queries Chroma for top-K similar embeddings
- System formats results: Video Title | youtube.com/watch?v=xyz | 12:34 | "...snippet..." | Relevance: 92%
- Results are returned to user

## Acceptance criteria

- [ ] Query embedding generated with sentence-transformers
- [ ] Vector similarity search returns top-K results (default K=5)
- [ ] Results formatted: Title | URL | Timestamp | Snippet | Relevance %
- [ ] Snippet extracted from original transcript (1-2 sentences)
- [ ] Relevance score shown (0-100% scale)
- [ ] Edge case handling: no results, single result, many results
- [ ] Tests cover search quality (relevant vs irrelevant queries)

## Blocked by

- Issue 6

## User stories

- User story 4: "I want to search using natural language"
- User story 5: "I want semantic search across concepts"
- User story 20: "I want results ranked by relevance"
```

---

## Issue 9: Augment Search with Graph Context

**Title**: `feat: add provenance and related concepts to search results`

**Labels**: `ready-for-agent`

**Body**:
```
## What to build

Augment semantic search results (from Issue 8) with graph context from Neo4j. For each result, fetch related concepts, show which video introduced the concept first, and show how many videos discuss it.

**End-to-end behavior**:
- User searches (from Issue 8)
- For each result, query Neo4j for:
  - Concepts that co-occur with matched concept
  - Which video introduced concept first (provenance)
  - How many videos discuss this concept
- Results enhanced with this context

## Acceptance criteria

- [ ] Neo4j queries implemented for related concepts
- [ ] First mention tracking implemented
- [ ] Concept frequency tracking (how many videos discuss it)
- [ ] Results formatted to include related concepts and provenance
- [ ] Graph queries are performant (< 500ms per result)
- [ ] Tests cover graph context retrieval

## Blocked by

- Issue 7 (graph schema)
- Issue 8 (search results)

## User stories

- User story 7: "I want to know concept relationships"
- User story 8: "I want to see related concepts"
- User story 16: "I want to search for complex relationships"
- User story 22: "I want to understand provenance"
```

---

## Issue 10: CLI Interface

**Title**: `feat: CLI commands (init, sync, search, config, status)`

**Labels**: `ready-for-agent`

**Body**:
```
## What to build

Implement CLI interface using Click or Typer. Provide commands for initialization, syncing, searching, configuration, and status reporting.

**Commands**:
- `yt-rag init`: One-time setup (OAuth, directories, databases)
- `yt-rag sync`: Manually trigger sync
- `yt-rag search <query>`: Execute semantic search
- `yt-rag config set <key> <value>`: Modify configuration
- `yt-rag status`: Show sync status and statistics

**End-to-end behavior**:
- User runs CLI commands
- All commands parse arguments correctly
- Output is formatted clearly and consistently
- Errors provide actionable remediation steps

## Acceptance criteria

- [ ] Click or Typer framework integrated
- [ ] All 5 commands implemented
- [ ] Argument parsing working correctly
- [ ] Help text available for all commands
- [ ] Output formatting consistent and clear
- [ ] Error messages guide users to fixes
- [ ] Tests cover command execution and output

## Blocked by

- Issue 2 (auth setup)
- Issue 3 (fetch history)
- Issue 5 (concepts)
- Issue 6 (embeddings)
- Issue 7 (graph)

## User stories

- User story 12: "I want simple one-time setup"
- User story 14: "I want to use the system via CLI"
- User story 15: "I want to see sync status and statistics"
```

---

## Issue 11: Full Sync Orchestration Pipeline

**Title**: `feat: orchestrate full sync pipeline end-to-end`

**Labels**: `ready-for-agent`

**Body**:
```
## What to build

Orchestrate the full sync pipeline (Issues 3-7) into a single cohesive operation. Implement error handling: critical failures (auth, network) abort sync; per-video failures (transcript, concept extraction) are logged and sync continues. Provide status feedback to user.

**Sync Pipeline Steps**:
1. Fetch new videos from YouTube (Issue 3)
2. Extract transcripts (Issue 4)
3. Extract concepts (Issue 5)
4. Generate embeddings (Issue 6)
5. Update knowledge graph (Issue 7)
6. Update sync state

**Error Handling**:
- **Critical**: Auth expired, network down, database unavailable → Abort with clear error
- **Per-video**: Transcript/concept extraction fails → Log and continue
- **Status**: Report final counts (indexed, failed, skipped)

## Acceptance criteria

- [ ] Sync pipeline orchestrates steps 1-6 in sequence
- [ ] Critical errors abort sync with remediation message
- [ ] Per-video failures logged without blocking sync
- [ ] Final status shows: videos indexed, concepts extracted, failed count
- [ ] Sync state persisted (sync_state.json updated)
- [ ] Incremental sync confirmed (only new videos processed)
- [ ] Tests cover full pipeline with various failure scenarios

## Blocked by

- Issue 3, 4, 5, 6, 7, 10

## User stories

- User story 1: "I want to import my watch history"
- User story 9: "I want graceful handling of missing transcripts"
- User story 10: "I want clear error messages"
- User story 23: "I want graceful degradation for per-video failures"
```

---

## Issue 12: Sync Scheduling (Manual + Automatic)

**Title**: `feat: sync scheduling (manual, daily, weekly)`

**Labels**: `ready-for-agent`

**Body**:
```
## What to build

Implement manual and automatic sync scheduling. Users can:
- Manually run `yt-rag sync` anytime
- Configure automatic syncing (manual, daily, weekly) in config.yaml
- Use system cron or APScheduler for scheduled syncs

**End-to-end behavior**:
- User sets sync schedule in config: `sync.schedule: daily`
- System runs sync at scheduled times
- User can also manually trigger `yt-rag sync` anytime
- `yt-rag status` shows last sync time and next scheduled sync

## Acceptance criteria

- [ ] APScheduler integration for scheduling
- [ ] Config supports schedule options: manual, daily, weekly
- [ ] Scheduled syncs run in background without blocking user
- [ ] Manual `yt-rag sync` command always works
- [ ] `yt-rag status` shows last sync time and next scheduled sync
- [ ] Syncs respect rate limits and avoid overwhelming APIs
- [ ] Tests cover scheduling and manual triggers

## Blocked by

- Issue 11 (sync orchestration)
- Issue 10 (CLI interface)

## User stories

- User story 3: "I want to configure when syncing happens"
- User story 13: "I want to trigger syncs manually or automatically"
```

---

## How to Create Issues

You have two options:

### Option A: Use GitHub CLI (if installed)
```bash
gh issue create --title "Project Scaffold & Configuration Management" \
  --body "$(cat issue-1.md)" \
  --label ready-for-agent,epic
```

### Option B: Create Manually on GitHub
1. Go to https://github.com/mueedhussain7/yt-history-rag/issues/new
2. Copy the title and body from each issue above
3. Apply labels: `ready-for-agent` and any others noted
4. Create in order (so issue numbers are sequential)
5. Update "Blocked by" references once you know the issue numbers

### Option C: Use this script (requires GitHub token)
Set `GITHUB_TOKEN` environment variable, then run the provided curl commands to create via API.

---

**Status**: All 12 issues ready for creation. Create in dependency order (1 → 2 → 3 → ... → 12).

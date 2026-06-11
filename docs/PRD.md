# GraphRAG YouTube History — Product Requirements Document

## Problem Statement

Users watch YouTube videos to learn, but cannot later find or revisit specific ideas, explanations, or insights they have seen. They may remember watching something about "authentication patterns" or "caching strategies" but lack a way to search their entire watch history and retrieve the exact segments where information appears. Existing YouTube search only covers metadata and trending content, not personal learning history.

## Solution

Build a personal, self-hosted knowledge system that transforms a user's YouTube watch history into a searchable, structured knowledge base. Users can import their watch history once, configure automatic syncing, and perform natural language semantic searches across all watched videos. Results include video links, timestamps, and matched transcript snippets, grounded entirely in their personal viewing history.

The system uses Graph RAG to understand concept relationships and provenance, enabling both simple fact retrieval and complex semantic understanding across the knowledge base.

## User Stories

1. As a developer, I want to import my YouTube watch history into the system, so that all my previously watched videos become searchable.

2. As a user, I want to authenticate with YouTube once via OAuth, so that I don't have to manually manage credentials.

3. As a user, I want to configure when syncing happens (manual, daily, weekly), so that new videos are automatically added to the index on my preferred schedule.

4. As a user, I want to search across all my watched videos using natural language, so that I can find content even if I don't remember exact keywords.

5. As a developer, I want to search "how do I implement authentication?" and get back videos about JWT, OAuth, session tokens, and related concepts, so that I can discover all related learning material even when using different terminology.

6. As a user, I want each search result to show the video title, a clickable YouTube link, the exact timestamp where the match occurs, and a snippet of the transcript, so that I can jump directly to the relevant segment.

7. As a user, I want to know which concepts I've learned about most deeply (across multiple videos) and which concepts were introduced first, so that I can understand the structure of my learning.

8. As a user, I want to see related concepts when viewing search results, so that I can explore conceptually similar topics and deepen my understanding.

9. As a user, I want the system to skip videos that don't have transcripts available, mark them as unavailable, and continue syncing, so that one missing transcript doesn't block my entire sync process.

10. As a user, I want authentication errors or network failures to be reported clearly with actionable next steps, so that I know what to fix.

11. As a user, I want to run the system entirely on my local machine with no cloud dependencies, so that my watch history stays private and under my control.

12. As a user, I want a simple one-time setup (one command) that handles all infrastructure (database, graph, embeddings), so that I don't need to be an ops expert to use this.

13. As a user, I want to trigger syncs manually via CLI or let them run automatically on a schedule, so that I can choose how frequently my index updates.

14. As a developer, I want to use the system via a simple CLI interface, so that I can integrate it into my workflow without a web browser dependency.

15. As a user, I want the system to track sync status and show me how many videos are indexed, how many concepts were extracted, and which videos failed, so that I understand the state of my knowledge base.

16. As a user, I want to search for complex relationships like "what concepts do I need to understand X?" and "what other videos discuss this concept?", so that I can navigate my learning structurally.

17. As a system administrator, I want to be able to switch between different LLM providers (OpenAI, Anthropic, Mistral, etc.) without changing code, so that I can optimize for cost or quality.

18. As a user, I want transcript extraction to be reliable even if YouTube changes their site structure, so that syncing continues working without manual intervention.

19. As a user, I want the system to extract meaningful concepts (tools, frameworks, methodologies, patterns) from transcripts, so that my knowledge graph reflects what I actually learned.

20. As a user, I want search results ranked by relevance score, so that the most semantically similar content appears first.

21. As a power user, I want to extend concept extraction with custom logic or rules, so that the system can be tailored to my domain.

22. As a user, I want to understand the provenance of search results (which video introduced a concept first, how many videos discuss it, etc.), so that I can trust and verify the results.

23. As a user, I want graceful degradation where individual video failures don't block syncing, but critical failures (auth, network) stop immediately, so that I get reliable partial progress rather than cascading failures.

24. As a developer, I want a clear data model that separates videos, concepts, timestamps, and relationships, so that the system is maintainable and extensible.

## Implementation Decisions

### Data Model & Graph Structure

The system uses a knowledge graph with the following node and edge types:

**Nodes:**
- **Video**: Represents a YouTube video (id, title, url, watch_date, duration)
- **Concept**: Represents an extracted key term or idea (name, definition_context)
- **Timestamp**: Represents a specific point in a video where a concept is mentioned (video_id, seconds, transcript_snippet)

**Edges:**
- **Video --"contains"--> Concept** (with occurrence_count): How many times this concept appears in the video
- **Concept --"appears_at"--> Timestamp**: Links concept to specific timestamps where it's mentioned
- **Concept --"co_occurs_with"--> Concept** (with confidence_score): Concepts appearing together in transcripts
- **Concept --"introduced_in"--> Timestamp**: The first place a concept is mentioned (provenance)

This structure enables both semantic search and graph-based reasoning while maintaining complete provenance.

### Sync Pipeline Architecture

The sync process follows a clearly defined sequence:

1. **Fetch new videos**: Query YouTube Data API (authenticated via OAuth) for new videos in watch history since last sync
2. **Extract transcripts**: For each new video, attempt yt-dlp first, fallback to youtube-transcript-api, mark as failed if both fail
3. **Extract concepts**: Send transcript to OpenRouter LLM with structured prompt requesting JSON output of [name, context] pairs
4. **Generate embeddings**: Use sentence-transformers (local, all-MiniLM-L6-v2) to embed the full transcript and individual concepts
5. **Update vector DB**: Store transcript embeddings in Chroma with metadata (video_id, timestamp, concept)
6. **Update knowledge graph**: Create/update nodes and edges in Neo4j, handle concept deduplication and relationship merging
7. **Update sync state**: Record which videos processed, timestamp of sync, and statistics (extracted, failed)

Sync is **incremental only**—videos already indexed are never re-processed. This ensures consistent cost and performance.

### Transcript Extraction Strategy

Use **yt-dlp as primary method**, **youtube-transcript-api as fallback**, mark as **failed if both fail**. Never silently index videos without transcripts.

**Rationale**: yt-dlp has no API quota limits and is more reliable for bulk extraction. youtube-transcript-api provides insurance if yt-dlp breaks. If both fail, the video is marked as unavailable and not searchable, preventing low-quality results.

### Concept Extraction via LLM

Use **OpenRouter API** for concept extraction. Users configure their preferred model (Mistral, GPT-4, Claude, etc.) via config file without code changes.

**Prompt structure**: "Extract key technical concepts (tools, frameworks, methodologies, patterns, terminology) from this transcript. Return as JSON: {concepts: [{name: string, context: string}, ...]}"

**Extraction happens at sync time**, not search time. Costs are predictable and transparent.

### Vector Search & Semantic Ranking

Use **Chroma for vector storage** and **sentence-transformers for local embeddings**. Search results are ranked by cosine similarity score (0-1).

**Rationale**: Chroma is lightweight, embedded, requires no separate service. sentence-transformers runs locally, no API calls for every search.

**Fallback**: Architecture supports plugging in API-based embeddings (OpenAI, Anthropic) for users prioritizing quality over compute resources.

### Knowledge Graph Storage

Use **Neo4j** running in **Docker locally**. Graph serves two purposes:
1. **Ontology**: Understand concept relationships and structure
2. **Provenance**: Track where every piece of information came from

Graph queries augment vector search results with context (related concepts, first mention, frequency).

### Error Handling Strategy

**Critical failures** (auth expired, network down, database unavailable): **Abort sync**, show clear error message with remediation steps (re-authenticate, check network, restart Neo4j).

**Per-video failures** (transcript extraction fails, concept extraction fails): **Log and continue**. Mark video as failed. Complete sync with partial progress. Show user summary of what succeeded and what failed.

This prevents one bad video from blocking the entire knowledge base update.

### CLI Interface Design

Use **Click or Typer** for CLI. Primary commands:

- `yt-rag init`: One-time setup (YouTube OAuth, Neo4j Docker, Chroma init)
- `yt-rag sync`: Manually trigger sync
- `yt-rag search <query>`: Execute semantic search
- `yt-rag config set <key> <value>`: Modify configuration
- `yt-rag status`: Show sync status and statistics

Configuration stored in `~/.yt-rag/config.yaml` (user-editable YAML, not required for basic operation).

### Configuration Model

**Required at setup:**
- YouTube OAuth token (captured interactively during `yt-rag init`)
- OpenRouter API key (users set via `OPENROUTER_API_KEY` env var or config)

**Optional configuration:**
- Sync schedule (manual, daily, weekly)
- Concept extraction model (default: mistral/mistral-large)
- Embeddings method (default: local, optional: OpenAI/Anthropic)
- Data directory (default: ~/.yt-rag)

### Sync Scheduling

For v1: **Manual sync via CLI** or **cron/APScheduler** for automated scheduling. No built-in daemon.

Users can:
- Run `yt-rag sync` manually whenever they want
- Add to system cron: `0 2 * * * yt-rag sync` (daily at 2 AM)
- Use APScheduler for programmatic scheduling

### Data Storage Location

All data persists in `~/.yt-rag/`:
- `config.yaml`: Configuration and OAuth token
- `chroma_db/`: Chroma vector database (persisted)
- `neo4j_data/`: Neo4j database (Docker volume mount)
- `sync_state.json`: Metadata about indexed videos and sync history

This follows Unix conventions and keeps everything self-contained.

### Incremental Processing Strategy

**Only new videos are processed on sync.** Videos are tracked by ID in sync_state.json. Once a video is indexed, it is never re-processed, even if transcript extraction logic improves.

**Rationale**: Keeps sync costs predictable and performance consistent. Full re-indexing is optional (planned for future).

### Search Result Output Format

Results are simple and scannable:

```
1. Video Title | youtube.com/watch?v=xyz | 12:34
   "...snippet of matched transcript..."
   Relevance: 92%

2. Another Video | youtube.com/watch?v=abc | 05:12
   "...another relevant snippet..."
   Relevance: 88%
```

Each result includes:
- Title (one line)
- YouTube URL (clickable)
- Timestamp (second marker in video)
- Transcript snippet (1-2 sentences showing match)
- Relevance score

### Concept Deduplication

When extracting concepts from multiple videos, the same concept may be named differently ("JWT", "JSON Web Token", "JWT token"). 

**Strategy**: Use embedding similarity on concept definitions to detect near-duplicates. Merge duplicate nodes, tracking all mentions. Update edges accordingly.

**Alternative for future**: Allow manual concept aliasing / merging.

## Testing Decisions

### Testing Philosophy

- **Test external behavior, not implementation details.** Test the CLI interface and the semantic search quality, not internal LlamaIndex pipeline details.
- **Test at the highest seam possible.** Integration tests with actual Chroma and Neo4j (using test instances) are preferred to mocking.
- **Test against realistic data.** Use real transcripts and real concepts, not toy examples.

### Test Modules & Coverage

1. **Sync Pipeline Tests**
   - Test that new videos are detected correctly
   - Test that transcripts are extracted (mock yt-dlp, test fallback behavior)
   - Test that concepts are extracted correctly (mock OpenRouter, validate JSON structure)
   - Test that embeddings are generated (validate vector dimensions)
   - Test that videos are stored in Neo4j and Chroma with correct structure
   - Test that sync state is updated correctly

2. **Search Tests**
   - Test that semantic search returns relevant videos
   - Test that relevance ranking works correctly
   - Test that results include all required fields (title, URL, timestamp, snippet, score)
   - Test that graph context is added (related concepts)
   - Test edge cases (no results, single result, many results)

3. **Error Handling Tests**
   - Test that authentication failures abort sync with clear error
   - Test that network failures are handled
   - Test that per-video transcript failures don't block sync
   - Test that concept extraction failures are logged and handled gracefully

4. **Data Model Tests**
   - Test that the knowledge graph structure is created correctly
   - Test that concept deduplication works
   - Test that provenance is preserved (first mention, co-occurrence)

5. **CLI Tests**
   - Test that commands parse arguments correctly
   - Test that commands execute and produce expected output
   - Test that configuration is read and written correctly

### Test Infrastructure

- Use **pytest** as test framework
- Use **Docker for Neo4j** in tests (testcontainers or similar)
- Use **in-memory or file-based Chroma** for test isolation
- Mock **YouTube API** and **OpenRouter API** to avoid external dependencies
- Create **fixture videos with sample transcripts** for reproducible testing

### Prior Art

Similar test patterns exist in:
- **LlamaIndex test suite**: Testing document ingestion, embedding generation, retrieval
- **Graph database integration tests**: Testing graph creation, querying, relationship handling

## Out of Scope

The following are **not** included in v1 and are planned for future releases:

- **Web UI**: v1 is CLI-only. Web interface for search and knowledge graph exploration is future work.
- **Multi-user/cloud sync**: v1 is single-user, local-only. Cloud sync and multi-user collaboration are out of scope.
- **Fine-tuned embeddings**: v1 uses off-the-shelf sentence-transformers. Domain-specific embedding fine-tuning is future work.
- **Concept aliasing UI**: v1 uses automatic deduplication. Manual concept merging/aliasing UI is future work.
- **Advanced filtering**: v1 supports semantic search only. Date-based, speaker-based, or metadata filtering are future work.
- **Export/visualization**: Graph export (Neo4j dump, GML, etc.) and concept visualization are future work.
- **Local LLM fallback**: v1 requires OpenRouter API. Local LLM (Ollama) support is planned for v2.
- **Video transcript annotation**: Highlighting, notes, or custom annotations on transcripts are out of scope.
- **Re-indexing control**: v1 does not allow manual re-indexing. Users can only trigger new syncs.

## Further Notes

### Architecture Documentation

Comprehensive architecture documentation exists in:
- `CONTEXT.md`: Domain glossary and key terms
- `ARCHITECTURE.md`: System overview, data flows, tech stack
- `docs/adr/`: Architecture decision records with detailed reasoning

These documents should be consulted for detailed rationale on major decisions.

### Technology Stack

- **Language**: Python 3.10+
- **RAG Framework**: LlamaIndex (GraphRAGIndex with Neo4j backend)
- **Vector DB**: Chroma
- **Graph DB**: Neo4j (Docker)
- **Embeddings**: sentence-transformers (local, pluggable for API)
- **LLM for concepts**: OpenRouter API
- **Transcript extraction**: yt-dlp + youtube-transcript-api fallback
- **CLI**: Click or Typer
- **Sync scheduling**: APScheduler or system cron

### Security Considerations

- **YouTube OAuth tokens** are stored locally in config.yaml. Users should protect this file (consider adding file permission checks).
- **OpenRouter API keys** are passed via environment variable, not stored in config.
- **Transcripts and embeddings** are stored locally. No data leaves the user's machine except to OpenRouter for concept extraction.
- Consider adding optional transcript encryption for users with sensitive content.

### Performance Expectations

- **First sync (1000-video library)**: ~30-60 minutes (depends on avg video length and OpenRouter rate limits)
- **Incremental sync (10-50 new videos)**: ~2-5 minutes
- **Search query**: <1 second (vector search) + <500ms (graph context lookup)

### Future Extensibility

The architecture supports:
- **Pluggable LLM providers** (already designed in via OpenRouter)
- **Pluggable embeddings** (local or API-based)
- **Custom concept extraction** (users can replace LLM logic)
- **Graph schema extensions** (add new node/edge types for custom relationships)
- **Local LLM fallback** (when OpenRouter unavailable)

---

**Document Status**: Ready for implementation planning and task breakdown.

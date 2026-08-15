from dotenv import load_dotenv
load_dotenv()

import typer
import os
import re
import time
from pathlib import Path
from typing import Optional, List
from .config import (
    get_config_dir,
    create_config_template,
    save_config,
    load_sync_state,
    update_sync_state,
    save_concepts,
    load_concepts,
    load_timestamps,
    find_timestamps_for_concept,
)
from .oauth import authenticate_youtube, is_authenticated
from .providers import (
    YouTubeAPIProvider,
    GoogleTakeoutProvider,
    BrowserExtensionProvider,
)
from .transcript import TranscriptExtractor
from .concepts import ConceptExtractor
from .embeddings import EmbeddingGenerator
from .search import TranscriptSearcher
from .neo4j_driver import Neo4jDriver
from .knowledge_graph import KnowledgeGraph
from .concept_deduplication import ConceptDeduplicator

# Load environment variables from .env file
load_dotenv()

app = typer.Typer(help="YouTube History RAG - Search your YouTube watch history")


def _process_videos(videos: list, typer_echo=typer.echo) -> None:
    """
    Internal helper function to process a list of videos through the pipeline.
    Shared by sync and import commands.
    """
    if not videos:
        typer_echo("No videos to process!")
        return

    sync_state = load_sync_state()
    already_indexed = set(sync_state.get("indexed_video_ids", []))

    # Filter out already-indexed videos
    new_videos = [
        v for v in videos
        if v["video_id"] not in already_indexed
    ]
    typer_echo(f"New videos to process: {len(new_videos)}")
    typer_echo(f"Skipping: {len(videos) - len(new_videos)} already indexed\n")

    if not new_videos:
        typer_echo("Nothing new to process!")
        return

    # Initialize Neo4j knowledge graph (Phase 1: Connection + Schema)
    typer_echo("Initializing knowledge graph...")
    kg_driver = None
    kg = None
    deduplicator = None

    try:
        kg_driver = Neo4jDriver()
        kg_driver.create_schema()
        kg = KnowledgeGraph(kg_driver)
        deduplicator = ConceptDeduplicator(kg)
        typer_echo("✓ Knowledge graph ready\n")
    except Exception as e:
        typer_echo(f"✗ Knowledge graph unavailable: {str(e)}\n")
        kg_driver = None
        kg = None
        deduplicator = None

    # Phase 2: Create Video nodes in Neo4j
    graph_videos = 0
    graph_failed = 0

    if kg:
        typer_echo("Creating video nodes...")
        for i, video in enumerate(new_videos, 1):
            video_id = video["video_id"]
            typer_echo(f"  [{i}/{len(new_videos)}] {video['title'][:50]}...", nl=False)

            try:
                kg.create_video_node(
                    video_id=video_id,
                    title=video["title"],
                    url=video.get("url", ""),
                    watch_date=video.get("watch_date", ""),
                    duration_seconds=video.get("duration_seconds", 0),
                    provider=video.get("provider", "unknown"),
                )
                graph_videos += 1
                typer_echo(" ✓")
            except Exception as e:
                graph_failed += 1
                typer_echo(f" ✗ ({str(e)[:30]})")

        typer_echo(f"\nVideo nodes created: {graph_videos}/{len(new_videos)}\n")

        # Phase 3: Create Timestamp nodes in Neo4j
        typer_echo("Creating timestamp nodes...")
        timestamps_processed = 0
        timestamps_failed = 0

        for i, video in enumerate(new_videos, 1):
            video_id = video["video_id"]

            try:
                # Load timestamps for this video
                timestamps_data = load_timestamps(video_id)
                if not timestamps_data:
                    continue

                # Create Timestamp node for each entry (uses MERGE for idempotency)
                for ts_entry in timestamps_data:
                    kg.create_timestamp_node(
                        video_id=video_id,
                        timestamp_seconds=ts_entry["timestamp"],
                        text=ts_entry["text"]
                    )
                    timestamps_processed += 1

            except Exception as e:
                timestamps_failed += 1

        typer_echo(f"Timestamp nodes created: {timestamps_processed}\n")

    # Extract transcripts from new videos
    typer_echo("Extracting transcripts...")
    extractor = TranscriptExtractor()
    transcripts_extracted = 0
    transcripts_failed = 0

    for i, video in enumerate(new_videos, 1):
        video_id = video["video_id"]
        typer_echo(f"  [{i}/{len(new_videos)}] {video['title'][:50]}...", nl=False)

        transcript, error = extractor.extract_transcript(video_id)
        if transcript:
            transcripts_extracted += 1
            typer_echo(" ✓")
        else:
            transcripts_failed += 1
            typer_echo(f" ✗ ({error})")

    typer_echo(f"\nTranscripts extracted: {transcripts_extracted}/{len(new_videos)}\n")

    # Extract concepts from transcripts
    typer_echo("Extracting concepts...")
    try:
        concept_extractor = ConceptExtractor()
    except ValueError as e:
        typer_echo(f"Concept extraction skipped: {str(e)}\n")
        concept_extractor = None

    concepts_extracted = 0
    concepts_failed = 0

    if concept_extractor:
        for i, video in enumerate(new_videos, 1):
            video_id = video["video_id"]

            # Only extract concepts if transcript was extracted
            transcript = extractor.get_transcript(video_id)
            if not transcript:
                continue

            typer_echo(f"  [{i}/{len(new_videos)}] {video['title'][:50]}...", nl=False)

            concepts, error = concept_extractor.extract_concepts(transcript)
            if concepts:
                save_concepts(video_id, concepts)
                concepts_extracted += 1
                typer_echo(" ✓")
            else:
                concepts_failed += 1
                typer_echo(f" ✗ ({error})")

        typer_echo(f"\nConcepts extracted: {concepts_extracted}/{len(new_videos)}\n")

    # Phase 4, 5, & 6: Build Neo4j knowledge graph (NOW that concepts exist)
    # REORDERED: Concepts must be extracted BEFORE deduplicating them in Neo4j
    if kg:
        # Phase 4 & 5 (Combined): Deduplicate concepts + create all relationships
        typer_echo("Deduplicating concepts and creating relationships...")
        concepts_deduped = 0
        concepts_created = 0
        contains_relationships = 0
        appears_at_rels = 0
        introduced_in_rels = 0

        for i, video in enumerate(new_videos, 1):
            video_id = video["video_id"]

            try:
                # Load concepts and timestamps for this video
                concepts = load_concepts(video_id)
                timestamps_data = load_timestamps(video_id)

                if not concepts or not timestamps_data:
                    continue

                # Process each concept (SINGLE PASS - dedup runs once)
                for concept in concepts:
                    concepts_deduped += 1

                    # 1. Deduplicate via ConceptDeduplicator (Chroma similarity check)
                    deduped_results = deduplicator.deduplicate_concepts(
                        [concept],
                        video_id=video_id,
                        similarity_threshold=0.85
                    )

                    concept_name_to_use = deduped_results[0][0]
                    is_new = deduped_results[0][1]

                    if is_new:
                        concepts_created += 1

                    # 2. Find matching timestamps for this concept (word-based)
                    matching_ts = find_timestamps_for_concept(
                        concept_name_to_use,
                        timestamps_data
                    )

                    # 3. Create contains relationship with accurate occurrence_count
                    occurrence_count = max(1, len(matching_ts))

                    kg.create_contains_relationship(
                        video_id=video_id,
                        concept_name=concept_name_to_use,
                        occurrence_count=occurrence_count
                    )
                    contains_relationships += 1

                    # 4. Create appears_at for all matching timestamps
                    for ts_seconds in matching_ts:
                        kg.create_appears_at_relationship(
                            concept_name=concept_name_to_use,
                            video_id=video_id,
                            timestamp_seconds=ts_seconds
                        )
                        appears_at_rels += 1

                    # 5. Create introduced_in for first (earliest) timestamp
                    if matching_ts:
                        first_ts = min(matching_ts)
                        kg.create_introduced_in_relationship(
                            concept_name=concept_name_to_use,
                            video_id=video_id,
                            timestamp_seconds=first_ts
                        )
                        introduced_in_rels += 1

            except Exception as e:
                pass

        typer_echo(f"Concepts deduped: {concepts_deduped}")
        typer_echo(f"Concepts created: {concepts_created}")
        typer_echo(f"Contains relationships: {contains_relationships}")
        typer_echo(f"Appears_at relationships: {appears_at_rels}")
        typer_echo(f"Introduced_in relationships: {introduced_in_rels}\n")

        # Phase 6: Create co_occurs_with bidirectional relationships
        typer_echo("Creating co-occurrence relationships...")
        cooccurs_relationships = 0

        for i, video in enumerate(new_videos, 1):
            video_id = video["video_id"]

            try:
                concepts = load_concepts(video_id)
                timestamps_data = load_timestamps(video_id)

                if not concepts or not timestamps_data or len(concepts) < 2:
                    continue

                concept_timestamps = {}

                for concept in concepts:
                    deduped_results = deduplicator.deduplicate_concepts(
                        [concept],
                        video_id=video_id,
                        similarity_threshold=0.85
                    )

                    concept_name = deduped_results[0][0]
                    matching_ts = find_timestamps_for_concept(
                        concept_name,
                        timestamps_data
                    )

                    if matching_ts:
                        concept_timestamps[concept_name] = matching_ts

                concept_names = list(concept_timestamps.keys())

                for i in range(len(concept_names)):
                    for j in range(i + 1, len(concept_names)):
                        concept1 = concept_names[i]
                        concept2 = concept_names[j]

                        ts1_list = concept_timestamps[concept1]
                        ts2_list = concept_timestamps[concept2]

                        score_1_to_2, score_2_to_1 = deduplicator.calculate_co_occurrence_scores(
                            ts1_list,
                            ts2_list,
                            proximity_window=60
                        )

                        kg.create_co_occurs_with_relationship(
                            concept1_name=concept1,
                            concept2_name=concept2,
                            confidence_score_1_to_2=score_1_to_2,
                            confidence_score_2_to_1=score_2_to_1
                        )
                        cooccurs_relationships += 2

            except Exception as e:
                pass

        typer_echo(f"Co-occurrence relationships: {cooccurs_relationships}\n")

    # Generate embeddings for transcripts
    typer_echo("Generating embeddings...")
    try:
        embedding_generator = EmbeddingGenerator()
    except Exception as e:
        typer_echo(f"Embedding generation skipped: {str(e)}\n")
        embedding_generator = None

    embeddings_generated = 0
    embeddings_failed = 0

    if embedding_generator:
        for i, video in enumerate(new_videos, 1):
            video_id = video["video_id"]

            # Only generate embeddings if transcript was extracted
            transcript = extractor.get_transcript(video_id)
            if not transcript:
                continue

            typer_echo(f"  [{i}/{len(new_videos)}] {video['title'][:50]}...", nl=False)

            try:
                # Load timestamps for this video (for chunk-to-timestamp mapping)
                timestamps = load_timestamps(video_id)

                chunks_count = embedding_generator.embed_and_store(
                    video_id,
                    video["title"],
                    transcript,
                    timestamps=timestamps
                )
                embeddings_generated += 1
                typer_echo(f" ✓ ({chunks_count} chunks)")
            except Exception as e:
                embeddings_failed += 1
                typer_echo(f" ✗ ({str(e)})")

        typer_echo(f"\nEmbeddings generated: {embeddings_generated}/{len(new_videos)}\n")

    # Update sync state
    typer_echo("Updating sync state...")
    new_video_ids = [v["video_id"] for v in new_videos]
    try:
        update_sync_state(new_video_ids, failed_count=transcripts_failed)
        typer_echo(f"Saved {len(new_video_ids)} new videos\n")
    except Exception as e:
        typer_echo(f"Error saving sync state: {str(e)}")
        return

    # Cleanup Neo4j connection
    if kg_driver:
        kg_driver.close()

    # Show summary
    typer_echo("Processing complete!")
    typer_echo(f"Transcripts extracted: {transcripts_extracted}")
    typer_echo(f"Transcripts failed: {transcripts_failed}")
    if concept_extractor:
        typer_echo(f"Concepts extracted: {concepts_extracted}")
        typer_echo(f"Concepts failed: {concepts_failed}")
    if embedding_generator:
        typer_echo(f"Embeddings generated: {embeddings_generated}")
        typer_echo(f"Embeddings failed: {embeddings_failed}")


@app.command()
def init() -> None:
    """Initialize the project scaffold and configuration."""
    config_dir = get_config_dir()

    typer.echo("Initializing yt-history-rag...\n")

    #Create directories
    typer.echo("Creating directories...")
    subdirs = [
        config_dir,
        config_dir / "chroma_db",
        config_dir / "neo4j_data",
    ]

    for subdir in subdirs:
        subdir.mkdir(parents=True, exist_ok=True)
        typer.echo(f"Created {subdir}")

    #Create config file
    typer.echo("\n Creating configuration file...")
    config = create_config_template()
    save_config(config)
    typer.echo(f"Created config.yaml at {config_dir / 'config.yaml'}")

    #YouTube OAuth authentication
    typer.echo("\n Setting up YouTube authentication...")

    # Check if credentials are already set
    if not os.getenv("YOUTUBE_CLIENT_ID") or not os.getenv("YOUTUBE_CLIENT_SECRET"):
        typer.echo("   YouTube credentials not found!")
        typer.echo("\n   To authenticate with YouTube, you need to:")
        typer.echo("   1. Get your Client ID and Secret from Google Cloud Console")
        typer.echo("   2. Copy .env.example to .env")
        typer.echo("   3. Add your credentials to .env file")
        typer.echo("   4. Run 'yt-rag init' again")
        typer.echo("\n   See .env.example for instructions")
        return

    # Try to authenticate
    try:
        typer.echo("Opening browser for YouTube authentication...")
        typer.echo("(If browser doesn't open, visit: http://localhost:8080/)")

        creds = authenticate_youtube()
        typer.echo("Successfully authenticated with YouTube!")
    except Exception as e:
        typer.echo(f"Authentication failed: {str(e)}")
        return

    typer.echo("\n✨ Project initialized successfully!")
    typer.echo(f" Configuration directory: {config_dir}")
    typer.echo("\n Next steps:")
    typer.echo("1. Run: yt-rag sync    (to sync your YouTube watch history)")
    typer.echo("2. Run: yt-rag search <query>  (to search your videos)")


@app.command()
def sync(provider: Optional[str] = typer.Option(None, "--provider", help="Provider to use: browser-extension, youtube-api")) -> None:
    """
    Sync videos from a provider and process them.

    Examples:
        yt-rag sync                              (uses YouTube API)
        yt-rag sync --provider browser-extension (uses browser extension data)
    """
    typer.echo("Starting sync...\n")

    # Get videos from provider
    if provider == "browser-extension":
        typer.echo("Loading videos from browser extension...\n")
        try:
            provider_obj = BrowserExtensionProvider()
            all_videos = provider_obj.get_videos()
            typer.echo(f"Found {len(all_videos)} videos from browser extension\n")
        except Exception as e:
            typer.echo(f"Error loading from browser extension: {str(e)}")
            return

    else:
        # Default to YouTube API
        typer.echo("Checking authentication...")
        try:
            provider_obj = YouTubeAPIProvider()
            typer.echo("Authenticated with YouTube\n")
        except Exception as e:
            typer.echo(f"Not authenticated: {str(e)}")
            typer.echo("\nRun 'yt-rag init' first to authenticate")
            return

        typer.echo("Fetching videos from YouTube...")
        try:
            all_videos = provider_obj.get_videos()
            typer.echo(f"Found {len(all_videos)} videos in your history\n")
        except Exception as e:
            typer.echo(f"Error fetching videos: {str(e)}")
            return

    # Process the videos
    _process_videos(all_videos)
    typer.echo("\nNext step: Run 'yt-rag search <query>' to find videos")


@app.command()
def import_videos(
    provider: str = typer.Option(..., "--provider", help="Provider type: takeout"),
    file: str = typer.Option(..., "--file", help="Path to source file (e.g., watch-history.html)")
) -> None:
    """
    Import videos from an external source.

    Example:
        yt-rag import --provider takeout --file ~/Downloads/watch-history.html
    """
    typer.echo("Starting import...\n")

    if provider == "takeout":
        typer.echo(f"Loading videos from Google Takeout file: {file}\n")
        try:
            provider_obj = GoogleTakeoutProvider(file)
            all_videos = provider_obj.get_videos()
            typer.echo(f"Found {len(all_videos)} videos in Takeout export\n")
        except FileNotFoundError as e:
            typer.echo(f"Error: {str(e)}")
            return
        except ValueError as e:
            typer.echo(f"Error: {str(e)}")
            return
        except Exception as e:
            typer.echo(f"Error loading videos: {str(e)}")
            return

    else:
        typer.echo(f"Error: Unknown provider '{provider}'")
        typer.echo("Supported providers: takeout")
        return

    # Process the videos
    _process_videos(all_videos)
    typer.echo("\nNext step: Run 'yt-rag search <query>' to find videos")


def _enrich_search_results(results: List[dict], typer_echo=typer.echo) -> tuple[List[dict], float]:
    """
    Enrich search results with Neo4j knowledge graph data.

    For each search result, fetches related concepts, provenance, and frequency data.
    Returns enriched results and elapsed time.
    """
    if not results:
        return results, 0.0

    start_time = time.time()

    try:
        # Initialize Neo4j connection
        kg_driver = Neo4jDriver()
        kg = KnowledgeGraph(kg_driver)

        # Collect concepts for each result using timestamp-window matching (Tier 1)
        # Falls back to all video concepts if no confident timestamps (Tier 2)
        all_concepts = set()
        result_concepts = {}

        for i, result in enumerate(results):
            video_id = result["video_id"]
            start_sec = result.get("start_seconds")
            end_sec = result.get("end_seconds")

            concepts = kg.get_concepts_for_chunk(video_id, start_sec, end_sec)
            result_concepts[i] = concepts
            all_concepts.update(concepts)

        # If no concepts found, return results as-is
        if not all_concepts:
            kg_driver.close()
            elapsed = time.time() - start_time
            return results, elapsed

        concept_list = list(all_concepts)

        # Batch-query all enrichment data once
        related = kg.get_related_concepts(concept_list)
        provenance = kg.get_concept_provenance(concept_list)
        frequency = kg.get_concept_frequency(concept_list)

        # Attach enriched data to each result
        for i, result in enumerate(results):
            concepts = result_concepts.get(i, [])

            # Build enriched concept data
            enriched_concepts = []
            for concept in concepts:
                concept_data = {
                    "name": concept,
                    "related": related.get(concept, {}),
                    "first_mentioned_in": provenance.get(concept),
                    "discussed_in_videos": frequency.get(concept, 0)
                }
                enriched_concepts.append(concept_data)

            result["enriched_concepts"] = enriched_concepts

        kg_driver.close()
        elapsed = time.time() - start_time
        return results, elapsed

    except Exception as e:
        # Graceful degradation: return results without enrichment
        elapsed = time.time() - start_time
        return results, elapsed


@app.command()
def serve_extension() -> None:
    """
    Start the browser extension receiver server.

    This listens on localhost:8765 for videos recorded by the Chrome extension.
    Keep this running while you watch YouTube videos.

    Example:
        yt-rag serve-extension
    """
    typer.echo("Starting yt-rag browser extension receiver...\n")

    try:
        from .providers.browser_extension_provider import start_extension_server
        start_extension_server()
    except KeyboardInterrupt:
        typer.echo("\n\nShutting down...")
    except Exception as e:
        typer.echo(f"Error: {str(e)}")


@app.command()
def search(query: str) -> None:
    """
    Search your transcript chunks by semantic similarity.

    Example: yt-rag search "machine learning"
    """
    if not query.strip():
        typer.echo("Error: Search query cannot be empty")
        return

    typer.echo(f"Searching for: '{query}'\n")

    try:
        searcher = TranscriptSearcher()
    except Exception as e:
        typer.echo(f"Search failed: {str(e)}")
        return

    results = searcher.search(query, top_k=5)

    if not results:
        typer.echo("No results found. Try running 'yt-rag sync' first.")
        return

    # Enrich results with Neo4j knowledge graph data
    enriched_results, enrichment_time = _enrich_search_results(results)

    typer.echo(f"Found {len(enriched_results)} results:\n")

    for i, result in enumerate(enriched_results, 1):
        typer.echo(f"{i}. Video: {result['video_title']}")
        typer.echo(f"   Relevance: {result['similarity_score']}%")

        # Truncate snippet to first 1-2 sentences for display
        chunk_text = result['chunk_text']
        # Normalize whitespace (newlines → spaces) and split on sentence boundaries
        normalized = re.sub(r'\s+', ' ', chunk_text).strip()
        sentences = re.split(r'(?<=[.!?])\s+', normalized)
        display_snippet = ' '.join(sentences[:2])
        if len(sentences) > 2:
            display_snippet += '...'
        typer.echo(f"   Snippet: {display_snippet}")

        # Show timestamp URL if available
        if "start_seconds" in result:
            start_sec = result["start_seconds"]
            timestamp_url = f"https://youtube.com/watch?v={result['video_id']}&t={start_sec}s"
            typer.echo(f"   Link: {timestamp_url}")
        else:
            typer.echo("   Link: (timestamp not available)")

        # Show enriched concepts if available
        if "enriched_concepts" in result and result["enriched_concepts"]:
            typer.echo(f"   Related concepts:")
            for concept_data in result["enriched_concepts"][:3]:  # Show top 3 concepts
                concept_name = concept_data["name"]
                video_count = concept_data["discussed_in_videos"]
                related_count = len(concept_data["related"])
                typer.echo(f"     • {concept_name} (in {video_count} video{'s' if video_count != 1 else ''}, {related_count} related)")

                # Show first-mention info if available
                if concept_data["first_mentioned_in"]:
                    first_mention = concept_data["first_mentioned_in"]
                    first_ts = first_mention.get("timestamp_seconds", 0)
                    typer.echo(f"       First mentioned at {first_ts}s")

        typer.echo()

    if enrichment_time > 0:
        typer.echo(f"Enrichment completed in {enrichment_time*1000:.1f}ms")


if __name__ == "__main__":
    app()

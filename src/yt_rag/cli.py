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

# Config sub-app for configuration management
config_app = typer.Typer(help="Manage configuration.")


@config_app.command()
def get(key: str = typer.Argument(..., help="Config key (e.g., youtube.client_id)")):
    """Get a configuration value."""
    try:
        from .config import get_config_value
        value = get_config_value(key)
        if value is None:
            typer.echo("(not set)")
        else:
            typer.echo(str(value))
    except KeyError as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)


@config_app.command()
def set(
    key: str = typer.Argument(..., help="Config key (e.g., youtube.client_id)"),
    value: str = typer.Argument(..., help="Value to set")
):
    """Set a configuration value."""
    try:
        from .config import set_config_value
        set_config_value(key, value)
        typer.echo(f"✓ Set {key} = {value}")
    except (KeyError, ValueError) as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)


app.add_typer(config_app, name="config")


@app.command()
def status():
    """Show sync status and statistics."""
    from .config import load_sync_state
    from datetime import datetime

    sync_state = load_sync_state()
    last_sync = sync_state.get("last_sync_time")
    stats = sync_state.get("sync_stats", {})

    typer.echo("\n" + "="*60)
    typer.echo("SYNC STATUS")
    typer.echo("="*60)

    # Format last sync time
    if last_sync:
        try:
            dt = datetime.fromisoformat(last_sync)
            formatted = dt.strftime("%Y-%m-%d %H:%M:%S")
            typer.echo(f"Last sync:       {formatted}")
        except (ValueError, TypeError):
            typer.echo(f"Last sync:       {last_sync}")
    else:
        typer.echo("Last sync:       Never")

    # Display stats
    indexed = stats.get("total_indexed", 0)
    failed = stats.get("total_failed", 0)

    typer.echo(f"Videos indexed:  {indexed}")
    typer.echo(f"Videos failed:   {failed}")

    typer.echo("="*60 + "\n")


def _stage_init_neo4j(typer_echo=typer.echo) -> tuple:
    """
    Stage 1: Initialize Neo4j connection and create schema.

    CRITICAL: If this fails, abort sync with remediation message.
    Returns: (driver, knowledge_graph, deduplicator) or (None, None, None) if failed
    """
    typer_echo("Initializing knowledge graph...")

    try:
        kg_driver = Neo4jDriver()
        kg_driver.create_schema()
        kg = KnowledgeGraph(kg_driver)
        deduplicator = ConceptDeduplicator(kg)
        typer_echo("✓ Knowledge graph ready\n")
        return kg_driver, kg, deduplicator
    except Exception as e:
        typer_echo(f"\n✗ CRITICAL ERROR: Knowledge graph initialization failed")
        typer_echo(f"   {str(e)}\n")
        typer_echo("REMEDIATION:")
        typer_echo("   - Check that Neo4j is running (docker ps | grep neo4j)")
        typer_echo("   - Check connection settings in ~/.yt-rag/config.yaml")
        typer_echo("   - Run: neo4j restart (if using Docker)\n")
        return None, None, None


def _stage_create_neo4j_nodes(kg, new_videos, typer_echo=typer.echo) -> dict:
    """
    Stage 2: Create Video and Timestamp nodes in Neo4j.

    PER-VIDEO: Log failures but continue sync.
    Returns: {"success": bool, "videos_created": int, "timestamps_created": int, "errors": [...]}
    """
    if not kg:
        return {"success": False, "videos_created": 0, "timestamps_created": 0, "errors": ["Neo4j unavailable"]}

    typer_echo("Creating video nodes...")
    videos_created = 0
    timestamps_created = 0
    errors = []

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
            videos_created += 1
            typer_echo(" ✓")
        except Exception as e:
            errors.append(f"Video {video_id}: {str(e)[:60]}")
            typer_echo(f" ✗ ({str(e)[:30]})")

    typer_echo(f"\nVideo nodes created: {videos_created}/{len(new_videos)}\n")

    return {
        "success": videos_created > 0,
        "videos_created": videos_created,
        "timestamps_created": timestamps_created,
        "errors": errors
    }


def _stage_extract_transcripts(new_videos, typer_echo=typer.echo) -> dict:
    """
    Stage 3: Extract transcripts from new videos.

    PER-VIDEO: Log failures but continue sync.
    Returns: {"success": bool, "transcripts_extracted": int, "errors": [...]}
    """
    typer_echo("Extracting transcripts...")
    extractor = TranscriptExtractor()
    transcripts_extracted = 0
    errors = []

    for i, video in enumerate(new_videos, 1):
        video_id = video["video_id"]
        typer_echo(f"  [{i}/{len(new_videos)}] {video['title'][:50]}...", nl=False)

        transcript, error = extractor.extract_transcript(video_id)
        if transcript:
            transcripts_extracted += 1
            typer_echo(" ✓")
        else:
            errors.append(f"Video {video_id}: {error}")
            typer_echo(f" ✗ ({error})")

    typer_echo(f"\nTranscripts extracted: {transcripts_extracted}/{len(new_videos)}\n")

    return {
        "success": transcripts_extracted > 0,
        "transcripts_extracted": transcripts_extracted,
        "errors": errors
    }


def _stage_create_timestamp_nodes(kg, new_videos, typer_echo=typer.echo) -> dict:
    """
    Stage 4: Create Timestamp nodes in Neo4j.

    Runs AFTER transcript extraction, so .timestamps.json files now exist.
    PER-VIDEO: Log failures but continue sync.
    Returns: {"success": bool, "timestamps_created": int, "errors": [...]}
    """
    if not kg:
        return {"success": False, "timestamps_created": 0, "errors": ["Neo4j unavailable"]}

    typer_echo("Creating timestamp nodes...")
    timestamps_created = 0
    errors = []

    for video in new_videos:
        video_id = video["video_id"]

        try:
            timestamps_data = load_timestamps(video_id)
            if not timestamps_data:
                continue

            for ts_entry in timestamps_data:
                kg.create_timestamp_node(
                    video_id=video_id,
                    timestamp_seconds=ts_entry["timestamp"],
                    text=ts_entry["text"]
                )
                timestamps_created += 1

        except Exception as e:
            errors.append(f"Video {video_id}: {str(e)[:60]}")

    typer_echo(f"Timestamp nodes created: {timestamps_created}\n")

    return {
        "success": timestamps_created > 0 or len(new_videos) == 0,
        "timestamps_created": timestamps_created,
        "errors": errors
    }


def _stage_extract_concepts(new_videos, typer_echo=typer.echo) -> dict:
    """
    Stage 5: Extract concepts from transcripts using LLM.

    PER-VIDEO: Log failures but continue sync.
    Returns: {"success": bool, "concepts_extracted": int, "errors": [...]}
    """
    typer_echo("Extracting concepts...")

    # Initialize ConceptExtractor (may fail if API unavailable)
    try:
        concept_extractor = ConceptExtractor()
    except ValueError as e:
        typer_echo(f"Concept extraction skipped: {str(e)}\n")
        return {
            "success": False,
            "concepts_extracted": 0,
            "errors": [str(e)]
        }

    extractor = TranscriptExtractor()
    concepts_extracted = 0
    errors = []

    for i, video in enumerate(new_videos, 1):
        video_id = video["video_id"]
        typer_echo(f"  [{i}/{len(new_videos)}] {video['title'][:50]}...", nl=False)

        # Load transcript (already extracted in Stage 3)
        transcript = extractor.get_transcript(video_id)
        if not transcript:
            typer_echo(" ✗ (no transcript available)")
            continue

        try:
            concepts, error = concept_extractor.extract_concepts(transcript)
            if concepts:
                save_concepts(video_id, concepts)
                concepts_extracted += 1
                typer_echo(" ✓")
            else:
                errors.append(f"Video {video_id}: {error}")
                typer_echo(f" ✗ ({error})")
        except Exception as e:
            errors.append(f"Video {video_id}: {str(e)[:60]}")
            typer_echo(f" ✗ ({str(e)[:30]})")

    typer_echo(f"\nConcepts extracted: {concepts_extracted}/{len(new_videos)}\n")

    return {
        "success": concepts_extracted > 0,
        "concepts_extracted": concepts_extracted,
        "errors": errors
    }


def _stage_build_knowledge_graph(kg, deduplicator, new_videos, typer_echo=typer.echo) -> dict:
    """
    Stage 6: Deduplicate concepts and build Neo4j knowledge graph relationships.

    Combines:
    - Concept deduplication via Chroma similarity (SINGLE PASS per video)
    - Creation of contains, appears_at, introduced_in relationships
    - Creation of co_occurs_with bidirectional relationships

    PER-VIDEO: Log failures but continue sync.
    Returns: {"success": bool, "contains": int, "appears_at": int, "introduced_in": int,
              "cooccurs": int, "concepts_created": int, "errors": [...]}
    """
    if not kg or not deduplicator:
        return {
            "success": False,
            "contains": 0,
            "appears_at": 0,
            "introduced_in": 0,
            "cooccurs": 0,
            "concepts_created": 0,
            "errors": ["Neo4j or deduplicator unavailable"]
        }

    typer_echo("Deduplicating concepts and creating relationships...")
    concepts_deduped = 0
    concepts_created = 0
    contains_count = 0
    appears_at_count = 0
    introduced_in_count = 0
    cooccurs_count = 0
    errors = []

    for i, video in enumerate(new_videos, 1):
        video_id = video["video_id"]

        try:
            concepts = load_concepts(video_id)
            timestamps_data = load_timestamps(video_id)

            if not concepts or not timestamps_data:
                continue

            # SINGLE PASS: Deduplicate all concepts once, store results
            concept_timestamps = {}  # {concept_name: [timestamps]}

            for concept in concepts:
                concepts_deduped += 1

                # Deduplicate via ConceptDeduplicator (ONCE per concept)
                deduped_results = deduplicator.deduplicate_concepts(
                    [concept],
                    video_id=video_id,
                    similarity_threshold=0.85
                )

                concept_name_to_use = deduped_results[0][0]
                is_new = deduped_results[0][1]

                if is_new:
                    concepts_created += 1

                # Find matching timestamps for this concept
                matching_ts = find_timestamps_for_concept(
                    concept_name_to_use,
                    timestamps_data
                )

                if matching_ts:
                    concept_timestamps[concept_name_to_use] = matching_ts

                    # Create contains relationship
                    occurrence_count = max(1, len(matching_ts))
                    kg.create_contains_relationship(
                        video_id=video_id,
                        concept_name=concept_name_to_use,
                        occurrence_count=occurrence_count
                    )
                    contains_count += 1

                    # Create appears_at for all matching timestamps
                    for ts_seconds in matching_ts:
                        kg.create_appears_at_relationship(
                            concept_name=concept_name_to_use,
                            video_id=video_id,
                            timestamp_seconds=ts_seconds
                        )
                        appears_at_count += 1

                    # Create introduced_in for first (earliest) timestamp
                    first_ts = min(matching_ts)
                    kg.create_introduced_in_relationship(
                        concept_name=concept_name_to_use,
                        video_id=video_id,
                        timestamp_seconds=first_ts
                    )
                    introduced_in_count += 1

            # Now use the already-deduplicated concept_timestamps for co-occurrence
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
                    cooccurs_count += 2

        except Exception as e:
            errors.append(f"Video {video_id}: {str(e)[:60]}")

    typer_echo(f"Concepts deduped: {concepts_deduped}")
    typer_echo(f"Concepts created: {concepts_created}")
    typer_echo(f"Contains relationships: {contains_count}")
    typer_echo(f"Appears_at relationships: {appears_at_count}")
    typer_echo(f"Introduced_in relationships: {introduced_in_count}")
    typer_echo(f"Co-occurrence relationships: {cooccurs_count}\n")

    return {
        "success": (contains_count + appears_at_count + introduced_in_count) > 0 or len(new_videos) == 0,
        "contains": contains_count,
        "appears_at": appears_at_count,
        "introduced_in": introduced_in_count,
        "cooccurs": cooccurs_count,
        "concepts_created": concepts_created,
        "errors": errors
    }


def _stage_generate_embeddings(new_videos, typer_echo=typer.echo) -> dict:
    """
    Stage 7: Generate embeddings for transcript chunks using Chroma.

    PER-VIDEO: Log failures but continue sync.
    Returns: {"success": bool, "embeddings_generated": int, "chunks_total": int, "errors": [...]}
    """
    typer_echo("Generating embeddings...")

    # Initialize EmbeddingGenerator (may fail if Chroma unavailable)
    try:
        embedding_generator = EmbeddingGenerator()
    except Exception as e:
        typer_echo(f"Embedding generation skipped: {str(e)}\n")
        return {
            "success": False,
            "embeddings_generated": 0,
            "chunks_total": 0,
            "errors": [str(e)]
        }

    extractor = TranscriptExtractor()
    embeddings_generated = 0
    chunks_total = 0
    errors = []

    for i, video in enumerate(new_videos, 1):
        video_id = video["video_id"]
        typer_echo(f"  [{i}/{len(new_videos)}] {video['title'][:50]}...", nl=False)

        # Load transcript (already extracted in Stage 3)
        transcript = extractor.get_transcript(video_id)
        if not transcript:
            typer_echo(" ✗ (no transcript available)")
            continue

        try:
            # Load timestamps for chunk-to-timestamp mapping
            timestamps = load_timestamps(video_id)

            chunks_count = embedding_generator.embed_and_store(
                video_id,
                video["title"],
                transcript,
                timestamps=timestamps
            )
            embeddings_generated += 1
            chunks_total += chunks_count
            typer_echo(f" ✓ ({chunks_count} chunks)")
        except Exception as e:
            errors.append(f"Video {video_id}: {str(e)[:60]}")
            typer_echo(f" ✗ ({str(e)[:30]})")

    typer_echo(f"\nEmbeddings generated: {embeddings_generated}/{len(new_videos)}, total chunks: {chunks_total}\n")

    return {
        "success": embeddings_generated > 0,
        "embeddings_generated": embeddings_generated,
        "chunks_total": chunks_total,
        "errors": errors
    }


def _stage_update_sync_state(new_video_ids, stats_summary, typer_echo=typer.echo) -> dict:
    """
    Stage 8: Persist sync state to disk.

    CRITICAL: If this fails, sync work is not recorded and will be re-done on next sync.
    If this fails, abort with clear remediation message.

    Args:
        new_video_ids: List of video IDs successfully processed
        stats_summary: Dict with sync statistics (transcripts_failed, etc.)

    Returns: {"success": bool, "videos_persisted": int, "errors": [...]}
    """
    typer_echo("Updating sync state...")

    try:
        # Calculate failed count (transcripts that failed to extract)
        failed_count = stats_summary.get("transcripts_failed", 0)

        # Persist sync state
        update_sync_state(new_video_ids, failed_count=failed_count)
        typer_echo(f"Saved {len(new_video_ids)} new videos\n")

        return {
            "success": True,
            "videos_persisted": len(new_video_ids),
            "errors": []
        }

    except Exception as e:
        typer_echo(f"\n✗ CRITICAL ERROR: Failed to update sync state")
        typer_echo(f"   {str(e)}\n")
        typer_echo("REMEDIATION:")
        typer_echo("   - Check disk space in ~/.yt-rag/")
        typer_echo("   - Verify sync_state.json is writable")
        typer_echo("   - Check file permissions: ls -la ~/.yt-rag/sync_state.json\n")
        typer_echo("⚠️  WARNING: Sync work was completed but NOT persisted.")
        typer_echo("   Videos will be re-processed on next sync.\n")

        return {
            "success": False,
            "videos_persisted": 0,
            "errors": [str(e)]
        }


def _process_videos(videos: list, typer_echo=typer.echo) -> None:
    """
    Orchestrate full sync pipeline (Stages 1-8) with proper error handling.

    CRITICAL stages (1, 8): abort on failure with remediation message
    PER-VIDEO stages (2-7): continue on individual failures, accumulate stats
    """
    if not videos:
        typer_echo("No videos to process!")
        return

    # Filter new videos
    sync_state = load_sync_state()
    already_indexed = set(sync_state.get("indexed_video_ids", []))
    new_videos = [v for v in videos if v["video_id"] not in already_indexed]

    if not new_videos:
        typer_echo("Nothing new to process!")
        return

    typer_echo(f"New videos to process: {len(new_videos)}")
    typer_echo(f"Skipping: {len(videos) - len(new_videos)} already indexed\n")

    # Accumulate stats across all stages
    all_stats = {
        "videos_processed": len(new_videos),
        "videos_indexed": 0,
        "transcripts_extracted": 0,
        "transcripts_failed": 0,
        "concepts_extracted": 0,
        "concepts_created": 0,
        "embeddings_generated": 0,
        "chunks_total": 0,
        "neo4j_contains": 0,
        "neo4j_appears_at": 0,
        "neo4j_introduced_in": 0,
        "neo4j_cooccurs": 0,
        "all_errors": [],
        "critical_error": None,
    }

    # STAGE 1: Init Neo4j (CRITICAL)
    kg_driver, kg, deduplicator = _stage_init_neo4j(typer_echo)

    if not kg:
        all_stats["critical_error"] = "Neo4j initialization failed"
        _print_final_status(all_stats, typer_echo)
        return

    # STAGES 2-7: Run in sequence, accumulate results
    result2 = _stage_create_neo4j_nodes(kg, new_videos, typer_echo)
    all_stats["all_errors"].extend(result2["errors"])

    result3 = _stage_extract_transcripts(new_videos, typer_echo)
    all_stats["transcripts_extracted"] = result3["transcripts_extracted"]
    all_stats["transcripts_failed"] = len(new_videos) - result3["transcripts_extracted"]
    all_stats["all_errors"].extend(result3["errors"])

    result4 = _stage_create_timestamp_nodes(kg, new_videos, typer_echo)
    all_stats["all_errors"].extend(result4["errors"])

    result5 = _stage_extract_concepts(new_videos, typer_echo)
    all_stats["concepts_extracted"] = result5["concepts_extracted"]
    all_stats["all_errors"].extend(result5["errors"])

    result6 = _stage_build_knowledge_graph(kg, deduplicator, new_videos, typer_echo)
    all_stats["concepts_created"] = result6["concepts_created"]
    all_stats["neo4j_contains"] = result6["contains"]
    all_stats["neo4j_appears_at"] = result6["appears_at"]
    all_stats["neo4j_introduced_in"] = result6["introduced_in"]
    all_stats["neo4j_cooccurs"] = result6["cooccurs"]
    all_stats["all_errors"].extend(result6["errors"])

    result7 = _stage_generate_embeddings(new_videos, typer_echo)
    all_stats["embeddings_generated"] = result7["embeddings_generated"]
    all_stats["chunks_total"] = result7["chunks_total"]
    all_stats["all_errors"].extend(result7["errors"])

    # STAGE 8: Update sync state (CRITICAL)
    new_video_ids = [v["video_id"] for v in new_videos]
    result8 = _stage_update_sync_state(new_video_ids, all_stats, typer_echo)
    all_stats["videos_indexed"] = result8["videos_persisted"]

    if not result8["success"]:
        all_stats["critical_error"] = "Failed to persist sync state"
        all_stats["all_errors"].extend(result8["errors"])

    # Cleanup
    if kg_driver:
        kg_driver.close()

    # Print comprehensive final status
    _print_final_status(all_stats, typer_echo)


def _print_final_status(stats, typer_echo=typer.echo) -> None:
    """
    Print comprehensive final status report for sync operation.

    Combines results from all 8 stages per Issue #11 requirements:
    "Final status shows: videos indexed, concepts extracted, failed count"
    """
    typer_echo("=" * 80)
    typer_echo("SYNC PIPELINE COMPLETE")
    typer_echo("=" * 80)

    if stats["critical_error"]:
        typer_echo(f"\n✗ CRITICAL ERROR: {stats['critical_error']}")
        typer_echo("   See remediation messages above.\n")
        return

    typer_echo("\nProcessing Summary:")
    typer_echo(f"  Videos processed: {stats['videos_processed']}")
    typer_echo(f"  Videos indexed: {stats['videos_indexed']}")
    typer_echo(f"  Transcripts extracted: {stats['transcripts_extracted']}/{stats['videos_processed']}")
    if stats['transcripts_failed'] > 0:
        typer_echo(f"  Transcripts failed: {stats['transcripts_failed']}")

    typer_echo(f"\nConcepts:")
    typer_echo(f"  Extracted: {stats['concepts_extracted']}")
    typer_echo(f"  Created (new): {stats['concepts_created']}")

    typer_echo(f"\nKnowledge Graph Relationships:")
    typer_echo(f"  Contains: {stats['neo4j_contains']}")
    typer_echo(f"  Appears_at: {stats['neo4j_appears_at']}")
    typer_echo(f"  Introduced_in: {stats['neo4j_introduced_in']}")
    typer_echo(f"  Co-occurs: {stats['neo4j_cooccurs']}")

    typer_echo(f"\nEmbeddings:")
    typer_echo(f"  Videos with embeddings: {stats['embeddings_generated']}")
    typer_echo(f"  Total chunks: {stats['chunks_total']}")

    if stats["all_errors"]:
        typer_echo(f"\nPer-video failures ({len(stats['all_errors'])}):")
        for error in stats["all_errors"][:5]:
            typer_echo(f"  - {error}")
        if len(stats["all_errors"]) > 5:
            typer_echo(f"  ... and {len(stats['all_errors']) - 5} more")

    typer_echo("\n✓ SYNC COMPLETE")
    typer_echo("=" * 80)


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

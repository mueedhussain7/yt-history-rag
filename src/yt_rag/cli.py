from dotenv import load_dotenv
load_dotenv()

import typer
import os
from pathlib import Path
from typing import Optional
from .config import (
    get_config_dir,
    create_config_template,
    save_config,
    load_sync_state,
    update_sync_state,
    save_concepts,
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
                chunks_count = embedding_generator.embed_and_store(
                    video_id,
                    video["title"],
                    transcript
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

    typer.echo(f"Found {len(results)} results:\n")

    for i, result in enumerate(results, 1):
        typer.echo(f"{i}. Video: {result['video_title']}")
        typer.echo(f"   Similarity: {result['similarity_score']}")
        typer.echo(f"   Chunk: {result['chunk_text'][:100]}...")
        typer.echo()


if __name__ == "__main__":
    app()

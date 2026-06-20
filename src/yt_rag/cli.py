import typer
import os
from pathlib import Path
from dotenv import load_dotenv
from .config import (
    get_config_dir,
    create_config_template,
    save_config,
    load_sync_state,
    update_sync_state,
)
from .oauth import authenticate_youtube, is_authenticated
from .youtube_api import YouTubeAPI

# Load environment variables from .env file
load_dotenv()

app = typer.Typer(help="YouTube History RAG - Search your YouTube watch history")


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
def sync() -> None:
    """
    Sync your YouTube watch history.
    """
    typer.echo("Starting sync...\n")

    #Check if authenticated
    typer.echo("Checking authentication...")
    try:
        youtube_api = YouTubeAPI()
        typer.echo("Authenticated with YouTube\n")
    except Exception as e:
        typer.echo(f"Not authenticated: {str(e)}")
        typer.echo("\n Run 'yt-rag init' first to authenticate")
        return

    #Get current sync state
    typer.echo(" Loading sync state...")
    sync_state = load_sync_state()
    already_indexed = set(sync_state.get("indexed_video_ids", []))
    typer.echo(f"Previously indexed: {len(already_indexed)} videos\n")

    #Fetch videos from YouTube
    typer.echo("Fetching videos from YouTube...")
    try:
        all_videos = youtube_api.fetch_watch_history()
        typer.echo(f"Found {len(all_videos)} videos in your history\n")
    except Exception as e:
        typer.echo(f"Error fetching videos: {str(e)}")
        return

    # Find new videos (not already indexed)
    new_videos = [
        v for v in all_videos
        if v["video_id"] not in already_indexed
    ]
    typer.echo(f"New videos to process: {len(new_videos)}")
    typer.echo(f"Skipping: {len(all_videos) - len(new_videos)} already indexed\n")

    if not new_videos:
        typer.echo("Nothing new to sync!")
        return

    # Step 5: Update sync state
    typer.echo("Updating sync state...")
    new_video_ids = [v["video_id"] for v in new_videos]
    try:
        update_sync_state(new_video_ids)
        typer.echo(f"Saved {len(new_video_ids)} new videos\n")
    except Exception as e:
        typer.echo(f"Error saving sync state: {str(e)}")
        return

    # Step 6: Show summary
    typer.echo("Sync complete!")
    typer.echo(f"Total videos indexed: {len(already_indexed) + len(new_videos)}")
    typer.echo(f"New videos this sync: {len(new_videos)}")
    typer.echo("\n Next step: Run 'yt-rag search <query>' to find videos")


if __name__ == "__main__":
    app()

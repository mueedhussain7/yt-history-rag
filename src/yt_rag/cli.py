import typer
import os
from pathlib import Path
from dotenv import load_dotenv
from .config import get_config_dir, create_config_template, save_config
from .oauth import authenticate_youtube, is_authenticated

# Load environment variables from .env file
load_dotenv()

app = typer.Typer(help="YouTube History RAG - Search your YouTube watch history")


@app.command()
def init() -> None:
    """Initialize the project scaffold and configuration."""
    config_dir = get_config_dir()

    typer.echo("🚀 Initializing yt-history-rag...\n")

    # Step 1: Create directories
    typer.echo("📁 Creating directories...")
    subdirs = [
        config_dir,
        config_dir / "chroma_db",
        config_dir / "neo4j_data",
    ]

    for subdir in subdirs:
        subdir.mkdir(parents=True, exist_ok=True)
        typer.echo(f"   ✓ Created {subdir}")

    # Step 2: Create config file
    typer.echo("\n⚙️  Creating configuration file...")
    config = create_config_template()
    save_config(config)
    typer.echo(f"   ✓ Created config.yaml at {config_dir / 'config.yaml'}")

    # Step 3: YouTube OAuth authentication
    typer.echo("\n🔐 Setting up YouTube authentication...")

    # Check if credentials are already set
    if not os.getenv("YOUTUBE_CLIENT_ID") or not os.getenv("YOUTUBE_CLIENT_SECRET"):
        typer.echo("   ❌ YouTube credentials not found!")
        typer.echo("\n   To authenticate with YouTube, you need to:")
        typer.echo("   1. Get your Client ID and Secret from Google Cloud Console")
        typer.echo("   2. Copy .env.example to .env")
        typer.echo("   3. Add your credentials to .env file")
        typer.echo("   4. Run 'yt-rag init' again")
        typer.echo("\n   📖 See .env.example for instructions")
        return

    # Try to authenticate
    try:
        typer.echo("   Opening browser for YouTube authentication...")
        typer.echo("   (If browser doesn't open, visit: http://localhost:8080/)")

        creds = authenticate_youtube()
        typer.echo("   ✓ Successfully authenticated with YouTube!")
    except Exception as e:
        typer.echo(f"   ❌ Authentication failed: {str(e)}")
        return

    typer.echo("\n✨ Project initialized successfully!")
    typer.echo(f"📍 Configuration directory: {config_dir}")
    typer.echo("\n📝 Next steps:")
    typer.echo("   1. Run: yt-rag sync    (to sync your YouTube watch history)")
    typer.echo("   2. Run: yt-rag search <query>  (to search your videos)")


if __name__ == "__main__":
    app()

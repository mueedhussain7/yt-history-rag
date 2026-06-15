import typer
from pathlib import Path
from .config import get_config_dir, create_config_template, save_config

app = typer.Typer(help="YouTube History RAG - Search your YouTube watch history")


@app.command()
def init() -> None:
    """Initialize the project scaffold and configuration."""
    config_dir = get_config_dir()

    # Create directories
    subdirs = [
        config_dir,
        config_dir / "chroma_db",
        config_dir / "neo4j_data",
    ]

    for subdir in subdirs:
        subdir.mkdir(parents=True, exist_ok=True)
        typer.echo(f"✓ Created {subdir}")

    # Create config file
    config = create_config_template()
    save_config(config)
    typer.echo(f"✓ Created config.yaml at {config_dir / 'config.yaml'}")

    typer.echo("\n✨ Project initialized successfully!")
    typer.echo(f"Configuration directory: {config_dir}")


if __name__ == "__main__":
    app()

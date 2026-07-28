# GraphRAG YouTube History

> GraphRAG knowledge retrieval from your YouTube watch history.

[![CI](https://github.com/mueedhussain7/yt-history-rag/actions/workflows/ci.yml/badge.svg)](https://github.com/mueedhussain7/yt-history-rag/actions/workflows/ci.yml)

## Overview

Users often remember information they learned from a video but cannot easily find the original source again. While YouTube search works well for discovering videos, it is not designed for searching the content of videos a user has already watched.

This project indexes transcripts from a user's watched or saved YouTube videos and enables content-based search across them. Users can search for information they have previously encountered and retrieve the relevant video segments, sources, and timestamps.

### Scope

This project is limited to helping users find and revisit information contained within their own YouTube content history. It is **not** a recommendation system, general-purpose YouTube search engine, or content generation tool.

## Getting Started

### Prerequisites

- List any required tools, runtimes, or accounts here.

### Installation

```sh
# Clone the repo
git clone https://github.com/mueedhussain7/yt-history-rag.git
cd yt-history-rag

# Install dependencies (update for your stack)
# npm install / pip install -r requirements.txt / etc.
```

### Usage

#### Option 1: Browser Extension (Recommended for ongoing tracking)

The Chrome extension automatically records videos as you watch them.

**Step 1: Start the yt-rag server**

```bash
yt-rag serve-extension
```

Keep this terminal open. You should see:
```
✓ yt-rag extension receiver started on http://localhost:8765
  Waiting for videos from Chrome extension...
```

**Step 2: Install the Chrome extension**

1. Open Chrome and go to: `chrome://extensions/`
2. Enable **Developer mode** (toggle in top-right)
3. Click **Load unpacked**
4. Select the `browser_extension/` folder in this repo
5. You should see "yt-rag Watch History Recorder" listed

**Step 3: Watch videos normally**

- Go to YouTube and watch videos
- The extension records them silently in the background
- Check browser console (F12) to see logs

**Step 4: Sync your videos**

```bash
yt-rag sync --provider browser-extension
```

This extracts transcripts, concepts, and generates embeddings.

---

#### Option 2: Google Takeout (One-time bulk import)

Import your watch history from a Google Takeout export.

**Step 1: Download from Google Takeout**

1. Go to [takeout.google.com](https://takeout.google.com)
2. Select only "YouTube and YouTube Music" → "History"
3. Download the ZIP file
4. Extract it and find `Takeout/YouTube and YouTube Music/history/watch-history.html`

**Step 2: Import into yt-rag**

```bash
yt-rag import --provider takeout --file ~/Downloads/watch-history.html
```

This will:
- Parse the HTML file
- Extract all videos and their watch dates
- Process them (extract transcripts, concepts, embeddings)
- Index them in Chroma for search

---

#### Option 3: Search your indexed videos

After syncing videos from either method:

```bash
yt-rag search "machine learning"
```

Returns the top 5 most similar video segments with timestamps.

## Folder Structure

```
src/       # Source code
docs/      # Documentation
tests/     # Tests
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)

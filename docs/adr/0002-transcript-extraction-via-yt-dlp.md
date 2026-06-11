# ADR 0002: Use yt-dlp for Transcript Extraction (Not YouTube Official API)

## Status
Accepted

## Context
The system needs to extract transcripts from YouTube videos for indexing and semantic search. Two approaches were considered:

1. **YouTube Official API** (youtube-data-api): Official, but requires API quota
2. **yt-dlp**: Third-party tool, no API quota, more reliable for bulk extraction

## Decision
Use **yt-dlp as primary**, with **youtube-transcript-api as fallback**.

## Rationale

### 1. No API Quota Limits
YouTube's API enforces daily quota units. A user with 1000+ videos could exhaust quota in a single sync session, blocking further syncs until the next day.

yt-dlp bypasses this by extracting captions directly, allowing unlimited extractions without quota concerns. This is essential for reliable, scalable personal knowledge systems.

### 2. More Reliable for Bulk Operations
yt-dlp is purpose-built for video downloading and extraction. It:
- Handles auto-generated captions when official captions unavailable
- More robust to YouTube frontend changes
- Actively maintained with regular updates
- Widely used in production systems

youtube-transcript-api is a lightweight unofficial scraper—it works, but can break if YouTube changes their frontend.

### 3. Graceful Fallback Strategy
Use yt-dlp first (faster, no API key needed). If extraction fails, fall back to youtube-transcript-api as a secondary attempt. If both fail, mark video as failed and continue.

## Trade-Offs

### Against Official API
yt-dlp depends on YouTube's HTML structure. If YouTube significantly changes their site, extraction could break. However:
- yt-dlp maintainers respond quickly to YouTube changes
- The project has a large user base that catches issues fast
- Fallback to youtube-transcript-api provides additional resilience
- Risk is acceptable for personal use (not production SaaS)

### Complexity
Requires managing two extraction libraries instead of one. However, the fallback pattern is simple and provides insurance against either tool breaking independently.

## Implementation

### Extraction Pipeline
```python
def extract_transcript(video_id):
    # Try yt-dlp first
    try:
        transcript = yt_dlp_extract(video_id)
        return transcript, "yt-dlp"
    except:
        pass
    
    # Fallback to youtube-transcript-api
    try:
        transcript = youtube_transcript_api_extract(video_id)
        return transcript, "youtube-transcript-api"
    except:
        return None, "failed"
```

### Error Handling
- **Both succeed**: Use yt-dlp result
- **Only youtube-transcript-api succeeds**: Use fallback (log as warning)
- **Both fail**: Mark video as failed, continue with next video
- **Critical error** (e.g., network down): Abort sync, show error to user

### Configuration
Users can optionally configure:
- Primary extraction method (default: yt-dlp)
- Whether to use fallback (default: enabled)
- Retry behavior on failure

## Alternatives Considered

### YouTube Official API Only
Simpler, official, but suffers from quota limits and can block users. Rejected for personal knowledge systems with large watch histories.

### Local Speech-to-Text (Whisper)
Download video audio, transcribe locally with OpenAI Whisper. Provides transcript even when captions unavailable. Rejected due to:
- High computational cost (GPU preferred)
- Much slower (minutes per video)
- Requires large model downloads
- Overkill when captions already available

## Consequences

### Positive
- No quota limits—sync at any frequency
- More reliable for bulk operations
- Fallback provides resilience
- Faster extraction than official API
- No API keys needed for yt-dlp

### Negative
- Depends on YouTube not blocking tool usage
- Requires maintaining two extraction libraries
- yt-dlp could break if YouTube redesigns site
- Slightly slower than official API for small batches

## Decision Log
- **2026-06-11**: Grilling session confirmed that rate-limiting and quota limits are blockers for reliable personal syncing. yt-dlp + fallback approved.

# ADR 0003: Use OpenRouter for LLM-Based Concept Extraction

## Status
Accepted

## Context
The system needs to extract key concepts (tools, frameworks, methodologies) from video transcripts to build the knowledge graph. These concepts need to be semantically meaningful and consistent across all indexed videos.

Two main approaches were considered:

1. **Local LLM** (e.g., Ollama + Mistral): Free, offline, no external dependencies
2. **API-Based LLM** (OpenRouter, OpenAI, Anthropic): Better quality, vendor flexibility, requires API keys and costs

## Decision
Use **OpenRouter API** for concept extraction.

## Rationale

### 1. Vendor Independence
OpenRouter abstracts away specific LLM provider APIs. A single configuration can switch between:
- OpenAI (GPT-4, GPT-3.5)
- Anthropic (Claude)
- Open-source models (Mistral, Llama)
- Others (Cohere, etc.)

Users can choose based on cost, quality, and availability. If one provider has issues, switching is one config change.

### 2. Quality Over Local LLM
Concept extraction quality is critical for search accuracy. A larger, more capable model (GPT-4, Claude) will:
- Understand context better
- Extract more semantically meaningful concepts
- Avoid nonsensical or overly general terms
- Recognize domain-specific terminology

Local LLMs (Mistral, Llama) are cheaper but weaker. For a personal knowledge system where accuracy matters, quality is worth the API cost.

### 3. User Choice
Different users have different preferences:
- Some prefer cheap (Mistral on OpenRouter)
- Some prefer quality (GPT-4)
- Some prefer privacy (local LLM fallback)

OpenRouter enables all options without code changes—just config.

### 4. Simplicity
Local LLM requires:
- Downloading and managing large model files
- Running Ollama or similar service
- Managing GPU vs CPU trade-offs
- Ensuring availability during syncs

OpenRouter is a simple API call. No infrastructure overhead.

## Trade-Offs

### Cost
OpenRouter (and underlying LLM providers) charge per token. A 1000-video library with 1-hour average videos = ~120M tokens. Cost depends on model selected (Mistral: ~$2-3, GPT-4: ~$10-15 for full library).

**Mitigation**: 
- Concept extraction happens once per video (on first sync)
- Costs are predictable and transparent
- Users can choose cheaper models
- Optional local LLM fallback for budget users

### External Dependency
System requires internet and a working API. If OpenRouter is down, sync fails.

**Mitigation**:
- OpenRouter is a reputable service with high uptime
- Users can configure fallback to local LLM or batch processing
- Sync is offline (user doesn't wait in real-time)

### No Offline Guarantee
Unlike local LLM, concept extraction requires external API. Privacy-conscious users must accept this or configure local fallback.

**Mitigation**: 
- Configuration supports pluggable concept extraction
- Local LLM fallback can be added later
- For v1, assume users accept this trade-off

## Implementation

### Configuration
```yaml
# ~/.yt-rag/config.yaml
concept_extraction:
  provider: "openrouter"  # or "local_llm"
  model: "mistral/mistral-large"  # or "openai/gpt-4", etc.
  api_key: "${OPENROUTER_API_KEY}"
  
# Alternative: local LLM
# concept_extraction:
#   provider: "local_llm"
#   model: "mistral"
#   base_url: "http://localhost:11434"
```

### Extraction Prompt
```
Extract key technical concepts from this transcript. Include tools, frameworks, 
methodologies, patterns, and terminology. Return as JSON:
{
  "concepts": [
    {"name": "JWT", "context": "...sentence where mentioned..."},
    ...
  ]
}
```

### Cost Tracking
Log concept extraction costs per sync. Users can monitor API usage and adjust model selection if needed.

## Alternatives Considered

### Local LLM Only
Simpler, free, offline. But extraction quality is weaker. Rejected because accuracy of the knowledge graph directly impacts search quality.

### No Concept Extraction (Vector Search Only)
Skip the knowledge graph, stay vector-only. Rejected because user prioritized accuracy and ontology understanding.

### OpenAI or Anthropic Direct
Use a single provider directly. Less flexible than OpenRouter. Rejected in favor of vendor independence.

## Consequences

### Positive
- High-quality concept extraction
- Vendor independence—easy to switch models
- User choice—cheap vs quality trade-offs
- Predictable, transparent costs
- Supports future local LLM fallback without redesign

### Negative
- Requires internet connection for concept extraction
- API costs ($2-15 per 1000-video library, depending on model)
- Depends on external service availability
- Requires API key management
- Potential privacy concerns (transcripts sent to API)

## Decision Log
- **2026-06-11**: Grilling session confirmed user wants flexibility and quality. OpenRouter approved for vendor independence and model choice. Local LLM fallback can be added later if needed.

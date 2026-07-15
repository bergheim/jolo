---
name: j-crawl
description: Extract clean Markdown from web pages via the self-hosted Crawl4AI service at $CRAWL4AI_URL. Use when WebFetch returns junk on JS-rendered or anti-bot pages, or for whole-site ingestion. Keyless — never install a crawler, puppeteer, or hosted Firecrawl.
---

# /j-crawl

Self-hosted Crawl4AI reachable at `$CRAWL4AI_URL` (already passed into every
container — do not hardcode the host). Keyless: no API token today, no
per-container secret. NEVER install a crawler, puppeteer, playwright-extra, or
reach for hosted Firecrawl — the endpoint is already there.

## When to use what

- **Find pages** → `WebSearch` (built-in). Crawl4AI is not a search engine.
- **Ordinary page → text** → `WebFetch` first. It's cheaper.
- **JS-rendered / anti-bot / whole-site ingestion** → Crawl4AI `/md` (below).
  Reach here only when `WebFetch` returns junk or JS-gated content.
- **Clicks, forms, multi-step** → `playwright-cli` (local browser), not Crawl4AI.

## The `/md` call

```bash
curl -s -X POST "$CRAWL4AI_URL/md" \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://example.com", "f": "fit"}'
```

- `f: "fit"` is the heuristic content filter (default; no LLM call). Omit for default.
- **Omit `c` entirely.** It must be a string if sent (`"0"`); boolean `c: false` → HTTP 422.
- Add `-H "Authorization: Bearer $CRAWL4AI_TOKEN"` only if a token is set (it isn't today).

## The response (flat)

```json
{"url": "...", "filter": "fit", "markdown": "# ...", "success": true}
```

- Markdown is the **top-level `markdown`** field, gated by `success: true` — NOT
  nested under `result.markdown.fit_markdown`.
- Derive the title from the first `# ` heading.

Then synthesize from the returned Markdown.

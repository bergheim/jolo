---
name: j-crawl
description: Extract clean Markdown from web pages via the self-hosted Crawl4AI service at $CRAWL4AI_URL. This is the DEFAULT tool for reading any web page - clean markdown, fewer context tokens than WebFetch/curl HTML. The shared API token is preconfigured; never install a crawler, puppeteer, or hosted Firecrawl.
---

# /j-crawl

Self-hosted Crawl4AI reachable at `$CRAWL4AI_URL` (already passed into every
container — do not hardcode the host). `$CRAWL4AI_API_TOKEN` is also injected;
use it without prompting the user. NEVER install a crawler, puppeteer,
playwright-extra, or reach for hosted Firecrawl — the endpoint is already there.

## When to use what

- **Find pages** → `WebSearch` (built-in), or the `h-search` skill (self-hosted SearXNG)
  when no search tool exists. Crawl4AI is not a search engine.
- **Page → text: Crawl4AI is the DEFAULT** (user decision 2026-07-27). It
  returns clean Markdown — better data quality and far fewer context tokens
  than raw HTML or WebFetch output. Cost is ~4s/page (warm) vs ~0.4s for
  plain curl; that's worth it for quality.
- **Bulk sweeps of one server-rendered site** (tens of pages you'll parse
  with a script anyway) → plain `curl -A "Mozilla/5.0"` is the exception
  where speed wins.
- **Clicks, forms, multi-step** → `playwright-cli` (local browser), not Crawl4AI.

## The `/md` call

```bash
# Recommended command to immediately see errors instead of just 'null':
curl -s -X POST "$CRAWL4AI_URL/md" \
  -H "Authorization: Bearer $CRAWL4AI_API_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://example.com", "f": "fit"}' \
  | jq -r 'if .error then "ERROR: \(.error)" elif .success == false then "FAILED" else .markdown end'
```

- `f: "fit"` is the heuristic content filter (default; no LLM call). Omit for default.
- **Omit `c` entirely.** It must be a string if sent (`"0"`); boolean `c: false` → HTTP 422.
- Every endpoint except `/health` requires the bearer token on Crawl4AI 0.9.x.

## The response (flat)

```json
{"url": "...", "filter": "fit", "markdown": "# ...", "success": true}
```
*(On failure, it may return `{"error": "Internal server error"}` or similar.)*

- Markdown is the **top-level `markdown`** field, gated by `success: true` — NOT
  nested under `result.markdown.fit_markdown`.
- Derive the title from the first `# ` heading.
- **If you get an error (e.g., Internal server error) or `null`**, do not keep retrying the same URL via `/md`. Move to the fallback immediately.

Then synthesize from the returned Markdown.

## Cookie/GDPR consent walls

If `/md` returns only cookie-consent text (or ~empty markdown), the site's
consent overlay is blocking the render. Fix: **use `/crawl` with
consent/overlay removal** (the intended API for this, crawl4ai#1005):

```bash
curl -s -X POST "$CRAWL4AI_URL/crawl" \
  -H "Authorization: Bearer $CRAWL4AI_API_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"urls": ["https://example.com"],
       "crawler_config": {"type": "CrawlerRunConfig",
                          "params": {"remove_consent_popups": true,
                                     "remove_overlay_elements": true}}}'
```

- `remove_consent_popups` is CMP-aware (OneTrust, Cookiebot, …);
  `remove_overlay_elements` is the generic fallback. Use both.
- Response shape differs from `/md`: `results[0].markdown` is an object —
  use `.fit_markdown` or `.raw_markdown`. Consent *text* may remain in the
  markdown; the overlay no longer blocks the real content.
- `magic`, `js_code`, `simulate_user` are rejected as
  "not permitted … from an untrusted request". This is hardcoded in the
  server (deliberate RCE boundary) — no server setting unlocks it. Don't
  fight it; use playwright-cli if you truly need clicks.

## If Crawl4AI itself fails

Service down, timeout, render error, or still-junk output after the consent
fix → fall back to `curl -s -A "Mozilla/5.0" <url>` and parse the HTML.
Server-rendered sites (e.g. birk.no) work fine this way; only a true SPA
(empty `<div id="app">` shell) gives curl nothing — then playwright-cli.

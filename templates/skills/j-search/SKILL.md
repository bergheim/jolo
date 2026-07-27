---
name: j-search
description: Web search via the self-hosted SearXNG at https://search.ts.glvortex.net. Use when you need to discover pages, find URLs, or search the web and have no built-in WebSearch tool (pi, local workers, plain bash). Keyless — never scrape Google/DuckDuckGo HTML and never install or sign up for Brave/Tavily/SerpAPI.
---

# /j-search

Self-hosted SearXNG on the tailnet at `https://search.ts.glvortex.net`
(JSON API enabled, no key). NEVER scrape Google/DuckDuckGo HTML with a
spoofed user agent — you get anti-bot junk, not results. The endpoint is
already there.

## When to use what

- **Built-in `WebSearch` tool available** → use that.
- **No search tool** → SearXNG call below.
- **Already have the URL, need content** → `WebFetch`/curl, or j-crawl
  (Crawl4AI) for JS-rendered and anti-bot pages. SearXNG is discovery only.

## The call

```bash
curl -sG 'https://search.ts.glvortex.net/search' \
  --data-urlencode 'q=your query here' \
  -d format=json
```

Optional narrowing: `-d time_range=year` (`day`/`month`/`year`),
`-d categories=it`, `-d pageno=2`, `-d language=en`.

## The response

```json
{"results": [{"title": "...", "url": "...", "content": "snippet"}],
 "answers": [], "infoboxes": []}
```

- Work from `.results[]` — `title`, `url`, `content` (snippet). The first
  ~10 are usually enough; quick scan:
  `jq -r '.results[:8][] | .title + " | " + .url'`
- Before citing a URL, confirm it resolves:
  `curl -s -o /dev/null -w '%{http_code}' <url>`

Then fetch the pages worth reading (j-crawl for anything curl mangles).

---
name: j-browser-verify
description: Verify a local web app is running and provide reproducible evidence using browser-check and optional Playwright screenshot capture.
---

# /j-browser-verify

Use this skill when the user asks to check if the site is running, verify browser tooling, or collect browser evidence.

## Workflow

1. Resolve target URL.
- Prefer `http://127.0.0.1:${PORT:-4000}` unless the user gives a different URL.

2. Verify service is listening.
- Run `ss -ltnp` and confirm a listener on `$PORT`.

3. Verify HTTP response.
- Run `curl -sS -D - -o /tmp/browser_verify_body.txt --max-time 5 "$URL"`.
- Capture status line and key headers.
- Capture first lines of body for page identity.

4. Run browser-level check.
- Run `browser-check "$URL" --describe --console --errors`.

5. Capture screenshot evidence.
- Default: `browser-check "$URL" --screenshot --output scratch/site-screenshot.png`.
- If user asks to verify Playwright specifically, also run:
  - `playwright-cli open "$URL"`
  - `playwright-cli -s=default screenshot --filename scratch/site-screenshot-playwright.png`
  - `playwright-cli -s=default close`
- If `-s=default` fails, run `playwright-cli list` and use the listed session label.

## Report Format

Always include:

- Exact URL
- Exact date/time of check
- Commands run
- Evidence summary (listening port, HTTP status, page title/body marker, console/errors)
- Artifact path(s) under `scratch/`

## Rules

- Keep checks non-destructive and read-only.
- Save artifacts to `scratch/`.
- Prefer concise evidence over long raw output dumps.

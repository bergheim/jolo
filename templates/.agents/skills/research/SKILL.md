---
name: research
description: Web research workflow that collects sources and summarizes findings into an org file. Use when the user asks to research a topic, compare sources, or gather references.
---

# Research

## Overview

Use this skill for web research. Write findings to the file specified in the prompt, or `RESEARCH.org` if none specified.

## Workflow

1. Parse the prompt. If it specifies a target filename (e.g., "Write findings to 2026-02-11-topic.org"), use that file. Otherwise use `RESEARCH.org`.
2. Extract the original research question from the prompt.
3. Gather sources (prefer primary docs, reputable outlets, official sites).
4. Write findings using the standard template below.
5. Save and commit immediately.

## Standard Template

```org
#+TITLE: <research question>
#+DATE: <YYYY-MM-DD>
#+PROPERTY: PROMPT <original prompt text>

* Summary
- <3-6 bullet summary of key findings>

* Findings
- <concise, sourced points; cite URLs inline>

* Links
- [[https://example.com][Example — Title]]

* Open Questions
- <things to verify or follow up>
```

## Sourcing Rules

- Prefer primary sources, official documentation, and reputable outlets.
- Include direct links in the `Links` section; add inline links in `Findings` where helpful.
- Keep quotes short; summarize in your own words.

## Git Hygiene

- Save the file and immediately commit.
- Use a clear commit message, e.g. `research: <topic>`.

## File Locations

- Default output: `RESEARCH.org` at the repo root (for interactive use).
- If the prompt specifies a filename, write to that file at the repo root instead.
- If the file does not exist, create it with the template above.

## Resources

No additional scripts or assets are required for this skill.

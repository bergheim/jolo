---
name: research
description: Web research workflow for multi-agent runs that collect sources and summarize findings into RESEARCH.org. Use when the user asks to research a topic, compare sources, or gather references, especially for parallel agents that need to avoid merge conflicts while writing notes.
---

# Research

## Overview

Use this skill to coordinate parallel web research. Each agent appends its own org heading in `RESEARCH.org`, includes links and source notes, and commits immediately after writing to reduce conflicts.

## Workflow

1. Define the research question or prompt in one sentence.
1. Gather sources (prefer primary docs, reputable outlets, and official sites).
1. Append a new top-level heading in `RESEARCH.org` for the current agent.
1. Write findings under the heading using the standard template.
1. Save the file and commit immediately.

## Standard Template (append-only)

Use a new top-level heading per agent run. Do not edit or reorder other agents’ sections.

```org
* <AgentName> — <YYYY-MM-DD>  :research:
:PROPERTIES:
:DATE: <YYYY-MM-DD>
:PROMPT: <one-line research question>
:END:

** Summary
- <3–6 bullet summary of key findings>

** Findings
- <concise, sourced points; cite URLs inline>

** Links
- <org links, one per line>
  - Example: [[https://example.com][Example — Title]]

** Open Questions
- <things to verify or follow up>
```

## Sourcing Rules

- Prefer primary sources, official documentation, and reputable outlets.
- Include direct links in the `Links` section; add inline links in `Findings` where helpful.
- Keep quotes short; summarize in your own words.

## Git Hygiene

- Save `RESEARCH.org` and immediately commit after each agent section.
- Use a clear commit message, e.g. `research: add <AgentName> notes`.
- If conflicts appear, rebase and resolve by keeping each agent’s section intact and append-only.

## File Locations

- Primary output: `RESEARCH.org` at the repo root.
- If `RESEARCH.org` does not exist, create it with:

```org
#+TITLE: Research Notes
#+STARTUP: overview
```

## Resources

No additional scripts or assets are required for this skill.

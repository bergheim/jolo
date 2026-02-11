---
name: doc-compare
description: Compare two or more document versions and provide a narrative summary of meaningful differences. Use when the user wants a human-readable summary of changes across versions (A/B/C), change impacts, regressions, or missing content, without a line-by-line diff or rewrite.
---

# Doc Compare

## Overview
Summarize differences across multiple document versions in a narrative form, focused on impact and meaning rather than mechanical diffs.

## Workflow
1. Identify baseline and variants. If unclear, ask which version is the reference.
2. Read each version for structure, claims, and intent (not just wording).
3. Summarize changes by impact: added scope, removed content, altered meaning, and tone shifts.
4. Call out regressions and omissions explicitly.
5. Keep the author’s voice and avoid rewrites unless asked.

## Output Format
- Summary: 2-3 sentences on the overall change.
- Key Differences: bullets, ordered by impact.
- Regressions or Omissions: bullets (if any).
- Questions: only if baseline or intent is ambiguous.

## Constraints
- Narrative summary only; no line-by-line diff.
- Preserve the author’s voice; do not rewrite.
- Focus on meaning, scope, and reader impact over minor edits.

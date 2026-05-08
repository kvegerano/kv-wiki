---
name: wiki-query
description: Answer natural-language questions against the project wiki. Returns synthesised answers with citations. Optionally files the answer back as a new wiki page.
---

# wiki-query

Answer questions against the project wiki.

## When to use

- At the start of a new epic session, to load relevant context ("what do we already know about <topic>?").
- Ad-hoc user questions about the project.
- When asked to summarise or cross-reference wiki content.

## Inputs

- **Natural language question.** Example: "how does PocketSmith rate limiting work in this project?"

## Process

1. Grep `docs/wiki/` for terms from the question. Use the helper for consistent ranking.
2. Read the top N (default 5) matching pages in full.
3. Synthesise an answer with citations. Every factual claim must cite `<page path>` (section).
4. If the answer is novel (not already on a page), offer: "File this back as a new wiki page? [y/n]".
   - If yes: create a new markdown draft with frontmatter, call `wiki-ingest` with the draft path.

## Helper

```bash
python ${CLAUDE_PLUGIN_ROOT}/skills/wiki-query/helper.py search --query "<question>" --wiki-root docs/wiki --top-k 5
```

## Output

```
## Answer
<synthesised answer>

## Citations
- docs/wiki/architecture/pocketsmith.md#rate-limits
- docs/wiki/gotchas/pocketsmith-429.md
```

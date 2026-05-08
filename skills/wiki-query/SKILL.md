---
name: wiki-query
description: Answer natural-language questions against the project wiki. Returns synthesised answer from ranked page snippets. Use before starting any task that might be covered by existing wiki knowledge.
---

# wiki-query

Search the wiki and return ranked page snippets for a natural-language query.

## When to use

- Before starting a task: check if the wiki has relevant patterns, gotchas, or decisions
- When you need to recall a past architectural decision
- When a user asks a question that might be answered by project knowledge

## Inputs

| Arg | Required | Description |
|-----|----------|-------------|
| `--query <text>` | Yes | Natural-language query |
| `--wiki-root <path>` | Yes | Path to `docs/wiki/` |
| `--top-k <N>` | No | Max results to return (default: 5) |

## Helper invocation

```bash
python ${CLAUDE_PLUGIN_ROOT}/skills/wiki-query/helper.py search \
  --query "<your question>" \
  --wiki-root docs/wiki \
  --top-k 5
```

## Output

JSON array: `[{path, score, snippet}, ...]`

## Spec

See `docs/superpowers/specs/2026-05-07-kv-wiki-design.md`.

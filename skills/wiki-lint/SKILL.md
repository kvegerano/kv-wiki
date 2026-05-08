---
name: wiki-lint
description: Health-check the wiki. Detects stale pages, orphans, cycles, missing refs, and invalid frontmatter. Run after bulk ingests or before pull requests.
---

# wiki-lint

Check wiki health. Finds: stale pages, orphaned pages, reference cycles, missing refs, invalid frontmatter, contradictions.

## When to use

- After a bulk ingest session
- Before merging a PR that touches wiki pages
- Periodically to catch drift

## Inputs

| Arg | Required | Description |
|-----|----------|-------------|
| `--wiki-root <path>` | Yes | Path to `docs/wiki/` |
| `--project-root <path>` | Yes | Project root |
| `--stale-days <N>` | No | Days before a page is stale (default: 90) |
| `--json` | No | Output structured JSON instead of human text |

## Helper invocation

```bash
python ${CLAUDE_PLUGIN_ROOT}/skills/wiki-lint/helper.py lint \
  --wiki-root docs/wiki \
  --project-root . \
  --stale-days 90
```

## Output

Human-readable report, or with `--json`: `{stale, orphans, cycles, missing_refs, invalid_frontmatter, contradictions, summary}`.
Exit 0 on no issues, 1 on issues found.

## Spec

See `docs/superpowers/specs/2026-05-07-kv-wiki-design.md`.

---
name: wiki-lint
description: Health-check the wiki. Detects stale pages (frontmatter.updated older than threshold), orphan pages (sources that no longer exist), contradictions (pages in same bucket with conflicting claims), and supersedes/superseded_by cycles.
---

# wiki-lint

Wiki health check.

## When to use

- Manually via `/wiki-lint` when the wiki feels out of date.
- On a schedule (deferred — add via `superpowers:schedule` later).
- Before a major epic starts, to ensure prior context is clean.

## Process

1. Walk `docs/wiki/`.
2. For every page, parse frontmatter.
3. Run checks:
   - **Stale**: `frontmatter.updated` older than threshold (default 90 days from `kv-wiki.yaml.wiki.lint.stale_after_days`).
   - **Orphan**: any path in `frontmatter.sources` no longer exists.
   - **Cycle**: `supersedes` / `superseded_by` form a loop.
   - **Missing ref**: `supersedes` or `superseded_by` points to a page that doesn't exist.
   - **Invalid frontmatter**: required fields missing or wrong type.
4. Report findings grouped by severity.
5. Propose fixes but never auto-apply. User must confirm.
6. Append lint run summary to `docs/wiki/log.md`.

## Helper

```bash
python ${CLAUDE_PLUGIN_ROOT}/skills/wiki-lint/helper.py lint --wiki-root docs/wiki --project-root . --stale-days 90
```

JSON output mode:

```bash
python ${CLAUDE_PLUGIN_ROOT}/skills/wiki-lint/helper.py lint --wiki-root docs/wiki --project-root . --stale-days 90 --json
```

## Output

```
wiki-lint report — 2026-04-14

Stale (1):
  - docs/wiki/domain/afsl-boundary.md (updated 95 days ago, threshold 90)

Orphans (0):
  (none)

Contradictions (0):
  (none)

Invalid frontmatter (0):
  (none)

Summary: 1 issue found. No auto-fixes applied.
```

JSON output shape:

```json
{
  "stale": [...],
  "orphans": [...],
  "cycles": [...],
  "missing_refs": [...],
  "invalid_frontmatter": [...],
  "contradictions": [...],
  "summary": {"total_issues": 0}
}
```

# Changelog

## [0.1.0] — 2026-05-08

### Added
- `wiki-ingest` skill — atomic, cross-platform wiki page ingest from specs/plans/lessons. Replaces `fcntl`-based locking with `portalocker`. Supports 6 active buckets + 3 legacy read-only buckets.
- `wiki-query` skill — ranked-grep search over wiki pages, returns JSON `{path, score, snippet}`.
- `wiki-lint` skill — health-check with `--json` output mode. Detects stale, orphan, cycle, missing-ref, invalid-frontmatter, contradiction issues.
- `bootstrap` skill — 3-state (CREATE/SAME/DIFFERS) project config seeding. ~83 lines. Idempotent.
- `feature-changelog` post-commit hook — git hook that appends idempotent changelog entries to feature wiki pages when matched code files change.
- 6 bucket overview templates + `wiki.yaml.tmpl`, `file-watch.json.tmpl`, `.kv-wiki-features.yaml.tmpl`.

---
name: wiki-ingest
description: Update the project wiki from a new or changed raw source file (spec, plan, lessons learned). Call when specs, plans, or docs/wiki-sources/ files change.
---

# wiki-ingest

Distill a source document into a bucketed wiki page in `docs/wiki/`. Atomic write. Cross-platform (Windows + Linux).

## When to use

- A new spec, plan, or lessons file was created or updated
- You want to update a wiki page from a source document
- A code file matched by `.kv-wiki-features.yaml` was just changed (appends changelog entry only)

## Inputs

| Arg | Required | Description |
|-----|----------|-------------|
| `--source <path>` | Yes | Source file to ingest |
| `--wiki-root <path>` | Yes | Path to `docs/wiki/` |
| `--project-root <path>` | No | Project root (for manifest lookup). Defaults to cwd. |
| `--bucket-hint <bucket>` | No | Override bucket selection |
| `--type <type>` | No | Force ingest type (default: auto-detect) |

## Process

1. Reads source file and existing wiki page (if any)
2. Validates bucket and page path (no traversal, no code files unless manifest-matched)
3. Calls LLM to distill content into frontmatter-tagged markdown
4. Writes atomically to `docs/wiki/<bucket>/<slug>.md`
5. Updates `docs/wiki/index.md` and `docs/wiki/log.md`

## Helper invocation

```bash
python ${CLAUDE_PLUGIN_ROOT}/skills/wiki-ingest/helper.py ingest \
  --source <source-file> \
  --wiki-root docs/wiki \
  --project-root .
```

## Output

Exits 0 on success. Exits 1 on error. Exits 2 on invalid input (code file, bad path).

## Spec

See `docs/superpowers/specs/2026-05-07-kv-wiki-design.md`.

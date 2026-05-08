# kv-wiki

Karpathy LLM-wiki skills for Claude Code. Gives any project a persistent, compounding knowledge base that distills specs, plans, and lessons into bucketed wiki pages.

## Install

```bash
claude plugin install https://github.com/kvegerano/kv-wiki
```

## Quickstart

```bash
# 1. Bootstrap the project (writes wiki config once)
/bootstrap

# 2. Ingest a spec or plan
/wiki-ingest docs/superpowers/specs/my-spec.md

# 3. Query the wiki
/wiki-query "how does authentication work?"

# 4. Check wiki health
/wiki-lint
```

## How it works

`kv-wiki` is installed once per machine at `~/.claude/plugins/marketplaces/kv-wiki/`. The skills, hooks, and helpers **stay in the installed plugin** — they are never copied into your project.

Running `/bootstrap` writes only project-specific config files into your repo:
- `wiki.yaml` — wiki configuration
- `docs/wiki/` — starter wiki pages (one per bucket)
- `.claude/hooks/file-watch.json` — hook config that fires wiki-ingest on file changes
- `.kv-wiki-features.yaml` — feature tracking manifest (empty starter)

## Skills

| Skill | Description |
|-------|-------------|
| `/wiki-ingest` | Distill a spec, plan, or lessons file into a wiki page |
| `/wiki-query` | Answer questions from the wiki |
| `/wiki-lint` | Health-check the wiki |
| `/bootstrap` | Write starter config into a new project (run once) |

## Feature tracking

Add entries to `.kv-wiki-features.yaml` to track code changes against wiki feature pages. A git post-commit hook automatically appends changelog entries when matched files change.

## Buckets

| Bucket | Purpose |
|--------|---------|
| `architecture` | System design, ADRs, component decisions |
| `patterns` | Coding patterns, conventions, idioms |
| `gotchas` | Traps, surprises, things that bit us |
| `domain` | Business logic, financial concepts |
| `integrations` | Third-party service specifics |
| `features` | Feature pages with change history |

## Requirements

- Python 3.11+
- `portalocker`, `pyyaml`, `pydantic`
- Git (for provenance checks)

## Spec

`docs/superpowers/specs/2026-05-07-kv-wiki-design.md` (in consumer project)

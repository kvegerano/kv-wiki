---
name: bootstrap
description: Write starter wiki config files into a consumer project. Run once; idempotent.
---

## When to use

Run `bootstrap` once when setting up a new consumer project that uses the kv-wiki plugin. It copies the template files from `templates/` into the target project directory. Safe to re-run — existing files that match the template are silently skipped.

## Inputs

```
python helper.py --templates-dir <path> --target-dir <path> [--dry-run]
```

| Flag | Required | Description |
|---|---|---|
| `--templates-dir` | yes | Directory containing the template files (the `templates/` dir inside the kv-wiki plugin) |
| `--target-dir` | yes | Consumer project root where files get written |
| `--dry-run` | no | Print the plan without writing anything |

## 3-state behaviour

For each file found under `--templates-dir` (walked recursively), the helper computes a target path of `<target-dir>/<relative-path-from-templates-dir>`. If the template file has a `.tmpl` suffix, that suffix is stripped from the target path.

| State | Condition | Action |
|---|---|---|
| CREATE | Target file does not exist | Write file; print `[CREATE] <path>` |
| SAME | Target exists and content is identical | Skip silently |
| DIFFERS | Target exists but content differs | Print warning to stderr; skip (edit manually) |

## Output

- One `[CREATE] <path>` line per file written (or per file that would be written in `--dry-run` mode).
- `[DIFFERS] <path> — file exists and differs from template, edit manually` to stderr for each differed file.
- Summary line: `Bootstrap complete: N created, M skipped, K differed.`

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success (including zero templates) |
| 2 | `--templates-dir` does not exist |

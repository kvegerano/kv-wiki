#!/usr/bin/env python3
"""wiki-lint helper CLI.

Detects:
- stale pages (frontmatter.updated older than threshold)
- orphan pages (sources that no longer exist on disk)
- supersedes/superseded_by cycles and missing refs
- invalid frontmatter

Proposes fixes but never auto-applies.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

# Reuse frontmatter parser from wiki-ingest
sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "wiki-ingest")
)
from frontmatter import InvalidFrontmatterError, parse  # noqa: E402

# mirrors.py lives alongside this helper (no wiki-drift skill in kv-wiki yet)
sys.path.insert(
    0, str(Path(__file__).resolve().parent)
)
from mirrors import (  # noqa: E402
    DEFAULT_MAPPING_PATH,
    InvalidMirrorMapError,
    compute_hash as _mirror_compute_hash,
    load as _mirror_load,
)


@dataclass
class StaleFinding:
    path: str
    days_old: int
    threshold: int


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def find_stale(wiki_root: Path, stale_days: int) -> list[StaleFinding]:
    today = date.today()
    findings: list[StaleFinding] = []
    for page in wiki_root.rglob("*.md"):
        if page.name in {"index.md", "log.md"}:
            continue
        try:
            content = page.read_text(encoding="utf-8").lstrip("﻿")
            fm, _ = parse(content)
        except InvalidFrontmatterError:
            continue
        updated_val = fm["updated"]
        if isinstance(updated_val, date):
            updated = updated_val
        else:
            updated = _parse_date(str(updated_val))
        days_old = (today - updated).days
        if days_old > stale_days:
            findings.append(
                StaleFinding(path=str(page), days_old=days_old, threshold=stale_days)
            )
    return findings


@dataclass
class OrphanFinding:
    page_path: str
    missing_source: str


def find_orphans(wiki_root: Path, project_root: Path) -> list[OrphanFinding]:
    findings: list[OrphanFinding] = []
    for page in wiki_root.rglob("*.md"):
        if page.name in {"index.md", "log.md"}:
            continue
        try:
            content = page.read_text(encoding="utf-8").lstrip("﻿")
            fm, _ = parse(content)
        except InvalidFrontmatterError:
            continue
        for src in fm.get("sources", []):
            if not isinstance(src, str):
                continue
            if src.startswith("git:"):
                continue
            src_path = project_root / src
            if not src_path.exists():
                findings.append(OrphanFinding(page_path=str(page), missing_source=src))
    return findings


@dataclass
class AbsoluteSourceFinding:
    page_path: str
    offending_source: str


def find_absolute_sources(wiki_root: Path) -> list[AbsoluteSourceFinding]:
    """Find wiki pages whose sources: entries start with / or contain .. segments."""
    findings: list[AbsoluteSourceFinding] = []
    for page in wiki_root.rglob("*.md"):
        if page.name in {"index.md", "log.md"}:
            continue
        try:
            content = page.read_text(encoding="utf-8").lstrip("﻿")
            fm, _ = parse(content)
        except InvalidFrontmatterError:
            continue
        for src in fm.get("sources", []):
            if not isinstance(src, str):
                continue
            # Reject absolute paths or paths containing .. components
            if src.startswith("/") or any(seg == ".." for seg in src.split("/")):
                findings.append(AbsoluteSourceFinding(
                    page_path=str(page),
                    offending_source=src,
                ))
    return findings


@dataclass
class ContradictionFinding:
    kind: str  # "cycle" | "missing-ref"
    detail: str


def _page_slug(page: Path) -> str:
    return page.stem


def find_contradictions(wiki_root: Path) -> list[ContradictionFinding]:
    """Detect supersedes/superseded_by cycles and missing refs."""
    pages: dict[str, dict] = {}
    for page in wiki_root.rglob("*.md"):
        if page.name in {"index.md", "log.md"}:
            continue
        try:
            content = page.read_text(encoding="utf-8").lstrip("﻿")
            fm, _ = parse(content)
        except InvalidFrontmatterError:
            continue
        pages[_page_slug(page)] = fm

    findings: list[ContradictionFinding] = []

    # Check missing refs
    all_slugs = set(pages.keys())
    for slug, fm in pages.items():
        for target in fm.get("supersedes", []) or []:
            if target not in all_slugs:
                findings.append(
                    ContradictionFinding(
                        kind="missing-ref",
                        detail=f"{slug} supersedes {target} (not found)",
                    )
                )
        sb = fm.get("superseded_by")
        if sb is not None and sb not in all_slugs:
            findings.append(
                ContradictionFinding(
                    kind="missing-ref",
                    detail=f"{slug} superseded_by {sb} (not found)",
                )
            )

    # Detect cycles through supersedes chain
    def walk(start: str, visited: set[str]) -> bool:
        if start in visited:
            return True
        visited.add(start)
        fm = pages.get(start, {})
        sb = fm.get("superseded_by")
        if sb and sb in pages:
            return walk(sb, visited)
        return False

    for slug in pages:
        if walk(slug, set()):
            findings.append(
                ContradictionFinding(kind="cycle", detail=f"cycle involving {slug}")
            )
            break  # one cycle report is enough; user fixes it

    return findings


@dataclass
class SourceDriftFinding:
    page_path: str
    mirrors: list[str]
    locked_hash: str
    current_hash: str


def find_source_drift(
    project_root: Path, mapping_path: Path | None = None
) -> list[SourceDriftFinding]:
    """Detect wiki sources whose mirrored code files have changed since the last lock.

    Missing mapping file -> zero findings (opt-in feature).
    Malformed mapping file -> zero findings, not an exception (keeps lint advisory).
    """
    path = mapping_path if mapping_path is not None else project_root / DEFAULT_MAPPING_PATH
    if not path.exists():
        return []
    try:
        m = _mirror_load(path)
    except InvalidMirrorMapError:
        return []
    findings: list[SourceDriftFinding] = []
    for key, entry in m.entries.items():
        current = _mirror_compute_hash(project_root, entry.mirrors)
        if current != entry.hash:
            findings.append(
                SourceDriftFinding(
                    page_path=key,
                    mirrors=list(entry.mirrors),
                    locked_hash=entry.hash,
                    current_hash=current,
                )
            )
    return findings


@dataclass
class InvalidFrontmatterFinding:
    page_path: str
    error: str


def find_invalid_frontmatter(wiki_root: Path) -> list[InvalidFrontmatterFinding]:
    findings: list[InvalidFrontmatterFinding] = []
    for page in wiki_root.rglob("*.md"):
        if page.name in {"index.md", "log.md"}:
            continue
        try:
            content = page.read_text(encoding="utf-8").lstrip("﻿")
            parse(content)
        except InvalidFrontmatterError as err:
            findings.append(
                InvalidFrontmatterFinding(page_path=str(page), error=str(err))
            )
    return findings


def cmd_lint(args: argparse.Namespace) -> int:
    wiki_root = Path(args.wiki_root)
    if not wiki_root.is_dir():
        print(f"error: wiki root not found: {wiki_root}", file=sys.stderr)
        return 2

    stale = find_stale(wiki_root, stale_days=args.stale_days)
    project_root = Path(args.project_root)
    orphans = find_orphans(wiki_root, project_root=project_root)
    abs_sources = find_absolute_sources(wiki_root)
    contradictions = find_contradictions(wiki_root)
    invalid = find_invalid_frontmatter(wiki_root)
    drift = find_source_drift(project_root)

    total = (
        len(stale)
        + len(orphans)
        + len(abs_sources)
        + len(contradictions)
        + len(invalid)
        + len(drift)
    )

    if args.json:
        result = {
            "stale": [
                {"path": s.path, "days_old": s.days_old, "threshold": s.threshold}
                for s in stale
            ],
            "orphans": [
                {"page_path": o.page_path, "missing_source": o.missing_source}
                for o in orphans
            ],
            "cycles": [
                {"kind": c.kind, "detail": c.detail}
                for c in contradictions
                if c.kind == "cycle"
            ],
            "missing_refs": [
                {"kind": c.kind, "detail": c.detail}
                for c in contradictions
                if c.kind == "missing-ref"
            ],
            "invalid_frontmatter": [
                {"page_path": i.page_path, "error": i.error}
                for i in invalid
            ],
            "contradictions": [
                {"kind": c.kind, "detail": c.detail}
                for c in contradictions
            ],
            "summary": {"total_issues": total},
        }
        print(json.dumps(result))
        return 0 if total == 0 else 1

    print(f"wiki-lint report — {date.today().isoformat()}")
    print()
    print(f"Stale ({len(stale)}):")
    if stale:
        for s in stale:
            print(f"  - {s.path} (updated {s.days_old} days ago, threshold {s.threshold})")
    else:
        print("  (none)")
    print()

    print(f"Orphans ({len(orphans)}):")
    if orphans:
        for o in orphans:
            print(f"  - {o.page_path} -> missing source: {o.missing_source}")
    else:
        print("  (none)")
    print()

    print(f"Absolute or traversal paths in sources ({len(abs_sources)}):")
    if abs_sources:
        for a in abs_sources:
            print(f"  - absolute or traversal path in sources: {a.page_path} -> {a.offending_source}")
    else:
        print("  (none)")
    print()

    print(f"Contradictions ({len(contradictions)}):")
    if contradictions:
        for c in contradictions:
            print(f"  - [{c.kind}] {c.detail}")
    else:
        print("  (none)")
    print()

    print(f"Invalid frontmatter ({len(invalid)}):")
    if invalid:
        for i in invalid:
            print(f"  - {i.page_path}: {i.error}")
    else:
        print("  (none)")
    print()

    print(f"Source drift ({len(drift)}):")
    if drift:
        for d in drift:
            print(f"  - {d.page_path}")
            for mp in d.mirrors:
                print(f"      mirrors: {mp}")
    else:
        print("  (none)")
    print()

    print("Summary:", total, "issue(s) found. No auto-fixes applied.")
    return 0 if total == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wiki-lint-helper")
    sub = parser.add_subparsers(dest="command", required=True)

    lint = sub.add_parser("lint", help="Run the wiki health check")
    lint.add_argument("--wiki-root", required=True)
    lint.add_argument("--stale-days", type=int, default=90)
    lint.add_argument("--project-root", required=True, help="Root directory used to resolve relative sources in page frontmatter")
    lint.add_argument("--json", action="store_true", help="Output results as a single JSON object")
    lint.set_defaults(func=cmd_lint)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

"""Build docs/wiki/index.md from filesystem state."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from frontmatter import BUCKETS, BUCKET_TITLES, parse

__all__ = ["BUCKETS", "BUCKET_TITLES", "build_index"]


def _first_nonempty_line(body: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return ""


def build_index(wiki_root: Path) -> str:
    """Walk the wiki and render a fresh index.md string."""
    lines: list[str] = [
        "# Wiki Index",
        "",
        "Auto-maintained by wiki-ingest. Do not hand-edit.",
        "",
    ]
    total = 0

    for bucket in BUCKETS:
        bucket_dir = wiki_root / bucket
        if not bucket_dir.is_dir():
            continue
        pages = sorted(p for p in bucket_dir.glob("*.md") if p.name != "overview.md")
        if not pages:
            continue
        lines.append(f"## {BUCKET_TITLES[bucket]}")
        for page in pages:
            try:
                fm, body = parse(page.read_text())
            except Exception:
                continue
            summary = _first_nonempty_line(body) or fm["title"]
            rel = f"{bucket}/{page.name}"
            lines.append(
                f"- [{fm['title']}]({rel}) — {summary} {fm['status'].capitalize()}."
            )
            total += 1
        lines.append("")

    lines.append("---")
    lines.append(f"Total pages: {total}. Last ingest: {date.today().isoformat()}.")
    lines.append("")
    return "\n".join(lines)

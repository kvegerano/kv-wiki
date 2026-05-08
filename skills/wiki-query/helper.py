#!/usr/bin/env python3
"""wiki-query helper CLI.

Offers one subcommand:
- `search` — rank wiki pages by keyword match count for a given query

The heavy lifting (synthesising an answer from the top pages) is done by the
model reading the SKILL.md instructions. This helper is retrieval-only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Hit:
    path: str
    score: int
    title: str
    snippet: str


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def _extract_snippet(content: str, query_tokens: set[str]) -> str:
    """Return the first line that contains a query token (trimmed to 120 chars)."""
    for line in content.splitlines():
        if any(t in _tokenize(line) for t in query_tokens):
            return line.strip()[:120]
    return ""


def search(wiki_root: Path, query: str, top_k: int = 5) -> list[Hit]:
    """Rank wiki pages by count of query-token occurrences in page body.

    Simple term-frequency ranking. No IDF, no stemming.
    """
    query_tokens = set(_tokenize(query))
    if not query_tokens:
        return []

    hits: list[Hit] = []
    for page in wiki_root.rglob("*.md"):
        if page.name in {"index.md", "log.md"}:
            continue
        content = page.read_text(encoding="utf-8")
        tokens = _tokenize(content)
        score = sum(1 for t in tokens if t in query_tokens)
        if score == 0:
            continue
        # Pull the title from frontmatter if present; otherwise filename.
        title = page.stem
        content = content.lstrip("﻿")
        if content.startswith("---"):
            end = content.find("\n---\n", 4)
            if end != -1:
                for line in content[4:end].splitlines():
                    if line.startswith("title:"):
                        title = line.split(":", 1)[1].strip()
                        break
        snippet = _extract_snippet(content, query_tokens)
        hits.append(Hit(path=str(page), score=score, title=title, snippet=snippet))

    hits.sort(key=lambda h: (-h.score, h.path))
    return hits[:top_k]


def cmd_search(args: argparse.Namespace) -> int:
    wiki_root = Path(args.wiki_root)
    if not wiki_root.is_dir():
        print(f"error: wiki root not found: {wiki_root}", file=sys.stderr)
        return 2
    hits = search(wiki_root, args.query, top_k=args.top_k)
    output = [{"path": h.path, "score": h.score, "snippet": h.snippet} for h in hits]
    print(json.dumps(output))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wiki-query-helper")
    sub = parser.add_subparsers(dest="command", required=True)

    search_cmd = sub.add_parser("search", help="Rank wiki pages by keyword")
    search_cmd.add_argument("--wiki-root", required=True)
    search_cmd.add_argument("--query", required=True)
    search_cmd.add_argument("--top-k", type=int, default=5)
    search_cmd.set_defaults(func=cmd_search)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

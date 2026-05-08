#!/usr/bin/env python3
"""wiki-ingest helper CLI.

Invoked by the wiki-ingest SKILL.md. Takes a raw source file and a set of
metadata hints (bucket, slug, title, summary) and updates the wiki.

In practice the SKILL.md tells Claude to read the source, choose bucket/slug/
title/summary, then invoke this helper with those arguments. The helper is a
pure file-manipulator; it never reads model output or calls external services.
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import re
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import yaml

import portalocker

# Local imports — these files live next to helper.py
sys.path.insert(0, str(Path(__file__).resolve().parent))
from frontmatter import (  # noqa: E402
    ACTIVE_BUCKETS,
    VALID_BUCKETS,
    VALID_TYPES,
    InvalidFrontmatterError,
    parse,
    serialize,
)
from index_generator import build_index  # noqa: E402
from log_appender import append_entry  # noqa: E402

CODE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".svelte", ".go", ".rs", ".java", ".rb", ".php", ".c", ".cpp", ".h"}
DEFAULT_TYPE = "decision"

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

MANIFEST_FILENAME = ".kv-wiki-features.yaml"


def _load_manifest(project_root: Path) -> dict | None:
    """Return parsed manifest dict, or None if absent."""
    manifest_path = project_root / MANIFEST_FILENAME
    if not manifest_path.exists():
        return None
    with open(manifest_path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _file_matches_manifest(rel_source: str, manifest: dict) -> str | None:
    """Return the slug of the first matching feature, or None."""
    for entry in manifest.get("features", []):
        for glob in entry.get("globs", []):
            if fnmatch.fnmatch(rel_source, glob):
                return entry.get("slug")
    return None


def _validate_and_resolve_page_path(
    wiki_root: Path, bucket: str, slug: str
) -> Path:
    if bucket not in VALID_BUCKETS:
        raise ValueError(
            f"invalid bucket: {bucket!r}, must be one of {sorted(VALID_BUCKETS)}"
        )
    if not SLUG_RE.fullmatch(slug):
        raise ValueError(
            f"invalid slug: {slug!r}, must match {SLUG_RE.pattern}"
        )
    wiki_root_resolved = wiki_root.resolve()
    bucket_dir = (wiki_root_resolved / bucket).resolve()
    try:
        bucket_dir.relative_to(wiki_root_resolved)
    except ValueError as exc:
        raise ValueError(
            f"bucket directory escapes wiki root: {bucket_dir}"
        ) from exc
    candidate = (bucket_dir / f"{slug}.md").resolve()
    try:
        candidate.relative_to(wiki_root_resolved)
    except ValueError as exc:
        raise ValueError(
            f"resolved path escapes wiki root: {candidate}"
        ) from exc
    return candidate


def _atomic_write(target_path: Path, content: bytes) -> None:
    """Write content to target_path atomically via tempfile + os.replace()."""
    tmp = tempfile.NamedTemporaryFile(
        mode='wb',
        dir=str(target_path.parent),
        suffix='.tmp',
        delete=False,
    )
    try:
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp.close()
        os.replace(tmp.name, str(target_path))
    except BaseException:
        tmp.close()
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise


def _atomic_write_text(target_path: Path, content: str) -> None:
    """Write text content atomically via tempfile + os.replace()."""
    _atomic_write(target_path, content.encode("utf-8"))


def _find_changelog_section(lines: list[str]) -> int:
    """Return the index of the line after '## Changelog', or -1."""
    for i, line in enumerate(lines):
        if line.strip() == "## Changelog":
            return i + 1
    return -1


def _append_changelog_entry_ingest(
    feature_page: Path,
    source_path: Path,
) -> None:
    """Append a changelog entry for a manual wiki-ingest invocation on a code file."""
    content = feature_page.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    stripped = [l.rstrip("\n").rstrip("\r") for l in lines]

    entry = (
        f"- manual ingest {date.today().isoformat()} — source: {source_path.as_posix()}\n"
    )

    changelog_start = _find_changelog_section(stripped)
    if changelog_start != -1:
        insert_at = changelog_start
        if insert_at < len(stripped) and stripped[insert_at] == "":
            insert_at += 1
        lines.insert(insert_at, entry)
    else:
        if lines and not lines[-1].endswith("\n"):
            lines.append("\n")
        lines.append("\n## Changelog\n")
        lines.append(entry)

    _atomic_write_text(feature_page, "".join(lines))


def _write_page_atomic(
    page_path: Path,
    content: bytes,
    create: bool,
) -> None:
    """Write page_path atomically.

    Uses tempfile.NamedTemporaryFile in the same directory + os.replace().
    If create=True and the file already exists, raises FileExistsError.
    """
    if create and page_path.exists():
        raise FileExistsError(f"page already exists: {page_path}")
    _atomic_write(page_path, content)


def _canonicalize_source(source: Path, project_root: Path) -> str:
    resolved = source.resolve()
    project_resolved = project_root.resolve()
    try:
        rel = resolved.relative_to(project_resolved)
    except ValueError as exc:
        raise ValueError(
            f"source path {source} resolves outside project root {project_root}; "
            "wiki-ingest requires sources tracked within the repository"
        ) from exc
    rel_posix = rel.as_posix()
    tracked = subprocess.run(
        [
            "git",
            "-C",
            str(project_resolved),
            "ls-files",
            "--error-unmatch",
            "--",
            rel_posix,
        ],
        capture_output=True,
        text=True,
    )
    if tracked.returncode != 0:
        raise ValueError(
            f"source path {rel_posix} is not tracked in git "
            f"(project root {project_root}); wiki-ingest requires sources "
            "committed to the repository"
        )
    return rel_posix


def _refuse_if_code(source: Path) -> None:
    if source.suffix in CODE_EXTENSIONS:
        print(
            f"error: refusing to ingest code file {source}. "
            "wiki-ingest only runs on markdown raw sources.",
            file=sys.stderr,
        )
        sys.exit(2)


def _create_page(
    page_path: Path,
    bucket: str,
    title: str,
    summary: str,
    rel_source: str,
    page_type: str = DEFAULT_TYPE,
) -> None:
    today = date.today().isoformat()
    fm = {
        "title": title,
        "type": page_type,
        "bucket": bucket,
        "status": "active",
        "created": today,
        "updated": today,
        "sources": [rel_source],
        "tags": [],
        "supersedes": [],
        "superseded_by": None,
    }
    body = f"\n{summary}\n"
    content = serialize(fm, body).encode("utf-8")
    _write_page_atomic(page_path, content, create=True)


def _update_page(page_path: Path, rel_source: str, summary: str) -> None:
    fm, body = parse(page_path.read_text())
    if rel_source not in fm["sources"]:
        fm["sources"].append(rel_source)
    fm["updated"] = date.today().isoformat()
    new_body = body.rstrip() + f"\n\n- {date.today().isoformat()}: {summary}\n"
    content = serialize(fm, new_body).encode("utf-8")
    _write_page_atomic(page_path, content, create=False)


@contextmanager
def _wiki_lock(wiki_root: Path):
    """Serialize wiki-ingest operations via an exclusive lock on <wiki_root>/.wiki.lock."""
    lock_path = wiki_root / ".wiki.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w") as fh:
        portalocker.lock(fh, portalocker.LOCK_EX)
        try:
            yield
        finally:
            portalocker.unlock(fh)


def cmd_ingest(args: argparse.Namespace) -> int:
    source = Path(args.source)
    wiki_root = Path(args.wiki_root)
    project_root = Path(args.project_root) if getattr(args, "project_root", None) else None

    if not source.exists():
        print(f"error: source not found: {source}", file=sys.stderr)
        return 2

    # Check manifest before code-file guard: if the source matches a manifest
    # entry, append a changelog entry to the feature page and exit 0.
    if source.suffix in CODE_EXTENSIONS and project_root is not None:
        manifest = _load_manifest(project_root)
        if manifest is not None:
            # Compute relative path for glob matching.
            try:
                rel = source.resolve().relative_to(project_root.resolve()).as_posix()
            except ValueError:
                rel = None
            if rel is not None:
                matched_slug = _file_matches_manifest(rel, manifest)
                if matched_slug is not None:
                    feature_page = wiki_root / "features" / f"{matched_slug}.md"
                    if not feature_page.exists():
                        print(
                            f"error: no feature page for slug {matched_slug!r} ({feature_page})",
                            file=sys.stderr,
                        )
                        return 2
                    _append_changelog_entry_ingest(feature_page, source)
                    print(f"wiki-ingest: appended changelog entry to features/{matched_slug}.md")
                    return 0

    _refuse_if_code(source)

    missing = [name for name, val in [
        ("--bucket-hint", args.bucket_hint),
        ("--slug", args.slug),
        ("--title", args.title),
        ("--summary", args.summary),
    ] if val is None]
    if missing:
        print(f"error: missing required argument(s): {', '.join(missing)}", file=sys.stderr)
        return 2

    try:
        page_path = _validate_and_resolve_page_path(wiki_root, args.bucket_hint, args.slug)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    page_path.parent.mkdir(parents=False, exist_ok=True)

    page_type = getattr(args, "type", DEFAULT_TYPE) or DEFAULT_TYPE
    if page_type not in VALID_TYPES:
        print(
            f"error: invalid type: {page_type!r}, must be one of {sorted(VALID_TYPES)}",
            file=sys.stderr,
        )
        return 2

    if project_root is not None:
        try:
            rel_source = _canonicalize_source(source, project_root)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    else:
        rel_source = str(source)

    changes: list[str] = []

    with _wiki_lock(wiki_root):
        bucket = args.bucket_hint
        slug = args.slug

        try:
            if page_path.exists():
                try:
                    parse(page_path.read_text())
                except InvalidFrontmatterError as exc:
                    print(
                        f"error: existing page has invalid frontmatter: {exc}",
                        file=sys.stderr,
                    )
                    return 2

                _update_page(page_path, rel_source, args.summary)
                changes.append(f"Updated: {bucket}/{slug}.md")
            else:
                _create_page(
                    page_path,
                    bucket,
                    args.title,
                    args.summary,
                    rel_source,
                    page_type=page_type,
                )
                changes.append(f"Created: {bucket}/{slug}.md")

        except OSError as exc:
            print(f"error: I/O failure during ingest: {exc}", file=sys.stderr)
            return 1

        try:
            index_path = wiki_root / "index.md"
            new_index_content = build_index(wiki_root)
            _atomic_write_text(index_path, new_index_content)
            changes.append("Updated: index.md")

            log_path = wiki_root / "log.md"
            append_entry(log_path, op="wiki-ingest", source=rel_source, changes=changes)

        except OSError as exc:
            print(f"error: post-publish bookkeeping failed: {exc}", file=sys.stderr)
            return 1

    print("wiki-ingest complete.")
    for change in changes:
        print(f"  {change}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wiki-ingest-helper")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="Ingest a raw source into the wiki")
    ingest.add_argument("--source", required=True)
    ingest.add_argument("--wiki-root", required=True)
    ingest.add_argument("--project-root", required=False, default=None)
    ingest.add_argument("--bucket-hint", default=None)
    ingest.add_argument("--slug", default=None)
    ingest.add_argument("--title", default=None)
    ingest.add_argument("--summary", default=None)
    ingest.add_argument(
        "--type",
        default=DEFAULT_TYPE,
        choices=sorted(VALID_TYPES),
        help=(
            "Karpathy page kind written into frontmatter `type:`. "
            f"Default: {DEFAULT_TYPE}."
        ),
    )
    ingest.set_defaults(func=cmd_ingest)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Git post-commit hook: append changelog entries to feature wiki pages.

Usage (from the consumer project's .git/hooks/post-commit):
    python <plugin_root>/hooks/feature-changelog.py \
        --project-root <path> \
        --plugin-root <path>
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import re
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

import yaml

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

MANIFEST_FILENAME = ".kv-wiki-features.yaml"
FEATURES_BUCKET = "features"
WIKI_SUBDIR = "docs/wiki"


def _load_manifest(project_root: Path) -> dict | None:
    """Return parsed manifest dict, or None if the manifest file is absent."""
    manifest_path = project_root / MANIFEST_FILENAME
    if not manifest_path.exists():
        return None
    with open(manifest_path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def validate_manifest(manifest: dict) -> None:
    """Raise ValueError if any entry has an invalid slug or unsafe glob."""
    for entry in manifest.get("features", []):
        slug = entry.get("slug", "")
        if not SLUG_RE.match(slug):
            raise ValueError(f"Invalid slug: {slug!r}")
        for glob in entry.get("globs", []):
            if ".." in glob:
                raise ValueError(f"Glob contains '..': {glob!r}")
            if glob.startswith("/"):
                raise ValueError(f"Glob has leading '/': {glob!r}")


def _git_changed_files(project_root: Path) -> list[str]:
    """Return list of files changed in HEAD relative to HEAD~1."""
    result = subprocess.run(
        ["git", "-C", str(project_root), "diff", "--name-only", "HEAD~1", "HEAD"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line]


def _git_short_sha(project_root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(project_root), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _matches_any_glob(file_path: str, globs: list[str]) -> bool:
    for glob in globs:
        if fnmatch.fnmatch(file_path, glob):
            return True
    return False


def _file_matches_manifest(rel_source: str, manifest: dict) -> str | None:
    """Return the slug of the first matching feature entry, or None."""
    for entry in manifest.get("features", []):
        if _matches_any_glob(rel_source, entry.get("globs", [])):
            return entry.get("slug")
    return None


def _find_changelog_section(lines: list[str]) -> int:
    """Return the index of the line after the '## Changelog' heading, or -1."""
    for i, line in enumerate(lines):
        if line.strip() == "## Changelog":
            return i + 1
    return -1


def _atomic_write_text(target_path: Path, content: str) -> None:
    tmp = tempfile.NamedTemporaryFile(
        mode="wb",
        dir=str(target_path.parent),
        suffix=".tmp",
        delete=False,
    )
    try:
        tmp.write(content.encode("utf-8"))
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


def _append_changelog_entry(
    feature_page: Path,
    sha: str,
    matched_files: list[str],
) -> None:
    """Append a changelog entry to the feature page. Idempotent by SHA."""
    content = feature_page.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)

    # Idempotency check: skip if this SHA is already in the Changelog section.
    changelog_start = _find_changelog_section([l.rstrip("\n").rstrip("\r") for l in lines])
    if changelog_start != -1:
        section_text = "".join(lines[changelog_start:])
        if f"`{sha}`" in section_text:
            return

    entry = (
        f"- `{sha}` {date.today().isoformat()} — "
        f"{len(matched_files)} file(s) changed: {', '.join(matched_files)}\n"
    )

    if changelog_start != -1:
        # Insert immediately after the ## Changelog heading line.
        # Keep any blank line that may follow the heading.
        insert_at = changelog_start
        # If the next line is blank, insert after it so the entry follows the gap.
        stripped_lines = [l.rstrip("\n").rstrip("\r") for l in lines]
        if insert_at < len(stripped_lines) and stripped_lines[insert_at] == "":
            insert_at += 1
        lines.insert(insert_at, entry)
    else:
        # No ## Changelog section — append one at the end.
        if lines and not lines[-1].endswith("\n"):
            lines.append("\n")
        lines.append("\n## Changelog\n")
        lines.append(entry)

    _atomic_write_text(feature_page, "".join(lines))


def run(project_root: Path, wiki_root: Path) -> int:
    manifest = _load_manifest(project_root)
    if manifest is None:
        return 0

    try:
        validate_manifest(manifest)
    except ValueError as exc:
        print(f"feature-changelog: manifest validation error: {exc}", file=sys.stderr)
        return 1

    changed_files = _git_changed_files(project_root)
    sha = _git_short_sha(project_root)

    for entry in manifest.get("features", []):
        slug = entry.get("slug", "")
        globs = entry.get("globs", [])
        matched = [f for f in changed_files if _matches_any_glob(f, globs)]
        if not matched:
            continue

        feature_page = wiki_root / FEATURES_BUCKET / f"{slug}.md"
        if not feature_page.exists():
            print(
                f"feature-changelog: warning: no feature page for slug {slug!r} "
                f"({feature_page}); skipping",
                file=sys.stderr,
            )
            continue

        _append_changelog_entry(feature_page, sha, matched)

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="feature-changelog")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--plugin-root", required=True)
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    wiki_root = project_root / WIKI_SUBDIR

    return run(project_root, wiki_root)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""bootstrap helper CLI.

Writes starter wiki config files from a templates directory into a consumer
project. Three states per file: CREATE (absent), SAME (identical), DIFFERS
(exists but different content).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _enumerate_templates(templates_dir: Path) -> list[tuple[Path, str]]:
    """Return (abs_src, target_rel_str) for every file under templates_dir."""
    results: list[tuple[Path, str]] = []
    for src in sorted(templates_dir.rglob("*")):
        if not src.is_file():
            continue
        if src.name.startswith("."):
            continue
        rel = src.relative_to(templates_dir)
        rel_str = str(rel).replace("\\", "/")
        if rel_str.endswith(".tmpl"):
            rel_str = rel_str[:-5]
        results.append((src, rel_str))
    return results


def _classify(src: Path, target: Path) -> str:
    """Return 'CREATE', 'SAME', or 'DIFFERS'."""
    if not target.exists():
        return "CREATE"
    if src.read_bytes() == target.read_bytes():
        return "SAME"
    return "DIFFERS"


def run(templates_dir: Path, target_dir: Path, dry_run: bool) -> int:
    if not templates_dir.is_dir():
        print(f"error: templates directory not found: {templates_dir}", file=sys.stderr)
        return 2

    entries = _enumerate_templates(templates_dir)

    created = 0
    skipped = 0
    differed = 0

    for src, rel_str in entries:
        target = target_dir / rel_str
        state = _classify(src, target)

        if state == "CREATE":
            if dry_run:
                print(f"[CREATE] {rel_str}")
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(src.read_bytes())
                print(f"[CREATE] {rel_str}")
            created += 1
        elif state == "SAME":
            skipped += 1
        else:  # DIFFERS
            print(
                f"[DIFFERS] {rel_str} — file exists and differs from template, edit manually",
                file=sys.stderr,
            )
            differed += 1

    verb = "would create" if dry_run else "created"
    print(f"Bootstrap complete: {created} {verb}, {skipped} skipped, {differed} differed.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bootstrap-helper",
        description="Write starter wiki config files into a consumer project.",
    )
    parser.add_argument("--templates-dir", required=True, help="Path to the templates directory")
    parser.add_argument("--target-dir", required=True, help="Path to the consumer project root")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen without writing any files",
    )
    args = parser.parse_args(argv)
    return run(
        templates_dir=Path(args.templates_dir),
        target_dir=Path(args.target_dir),
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())

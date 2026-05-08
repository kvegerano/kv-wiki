"""Schema for `_code_mirrors.json`: maps wiki-source pages to code files.

Shared by `wiki-drift` (write: scaffold/lock/check) and `wiki-lint`
(read: source-drift finding category).

Schema version 1:
    {
      "version": 1,
      "mirrors": {
        "docs/wiki-sources/backend-config-py.md": {
          "mirrors": ["backend/app/core/config.py"],
          "hash": "sha256:abc123..."
        }
      }
    }

Hash algorithm: SHA-256 over the concatenated bytes of all mirror files,
with per-file sentinels so reordering or file addition/removal changes the
hash deterministically. Algorithm is stored in the hash prefix so it can be
upgraded without breaking existing locks.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MAPPING_PATH = "docs/wiki-sources/_code_mirrors.json"
HASH_ALGO = "sha256"
HASH_PREFIX = f"{HASH_ALGO}:"
SCHEMA_VERSION = 1


class InvalidMirrorMapError(ValueError):
    """Raised when `_code_mirrors.json` is malformed or an unknown version."""


@dataclass
class MirrorEntry:
    mirrors: list[str]
    hash: str


@dataclass
class MirrorMap:
    version: int = SCHEMA_VERSION
    entries: dict[str, MirrorEntry] = field(default_factory=dict)


def load(path: Path) -> MirrorMap:
    """Load and validate a mapping file. Missing file → empty map (not error)."""
    if not path.exists():
        return MirrorMap()
    try:
        raw = json.loads(path.read_text(encoding="utf-8").lstrip("﻿"))
    except json.JSONDecodeError as e:
        raise InvalidMirrorMapError(f"{path}: invalid JSON — {e}") from e
    if not isinstance(raw, dict):
        raise InvalidMirrorMapError(f"{path}: top-level must be an object")
    version = raw.get("version")
    if version != SCHEMA_VERSION:
        raise InvalidMirrorMapError(
            f"{path}: unsupported schema version {version!r}, expected {SCHEMA_VERSION}"
        )
    mirrors_raw = raw.get("mirrors", {})
    if not isinstance(mirrors_raw, dict):
        raise InvalidMirrorMapError(f"{path}: 'mirrors' must be an object")
    entries: dict[str, MirrorEntry] = {}
    for key, entry_raw in mirrors_raw.items():
        if not isinstance(entry_raw, dict):
            raise InvalidMirrorMapError(f"{path}: entry {key!r} must be an object")
        codes = entry_raw.get("mirrors")
        if not isinstance(codes, list) or not all(isinstance(c, str) for c in codes):
            raise InvalidMirrorMapError(
                f"{path}: entry {key!r}: 'mirrors' must be a list of strings"
            )
        hash_s = entry_raw.get("hash", "")
        if not isinstance(hash_s, str):
            raise InvalidMirrorMapError(f"{path}: entry {key!r}: 'hash' must be a string")
        entries[key] = MirrorEntry(mirrors=list(codes), hash=hash_s)
    return MirrorMap(version=version, entries=entries)


def save(path: Path, m: MirrorMap) -> None:
    """Write mapping file with deterministic key ordering and trailing newline."""
    data = {
        "version": m.version,
        "mirrors": {
            key: {"mirrors": list(entry.mirrors), "hash": entry.hash}
            for key, entry in sorted(m.entries.items())
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def compute_hash(project_root: Path, mirror_paths: list[str]) -> str:
    """SHA-256 over concatenated mirror file contents with per-file sentinels.

    Missing files are hashed as a MISSING sentinel rather than ignored, so
    removal of a mirrored file shows up as drift.
    """
    h = hashlib.sha256()
    for mp in sorted(mirror_paths):
        fp = project_root / mp
        if not fp.exists():
            h.update(f"\x00MISSING:{mp}\x00".encode())
            continue
        h.update(f"\x00FILE:{mp}\x00".encode())
        h.update(fp.read_bytes())
    return f"{HASH_PREFIX}{h.hexdigest()}"

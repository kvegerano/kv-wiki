"""Frontmatter read/write for wiki pages.

Enforces the mandatory schema defined in the framework design spec.
"""
from __future__ import annotations

from typing import Any

import yaml

REQUIRED_FIELDS = {
    "title",
    "type",
    "bucket",
    "status",
    "created",
    "updated",
    "sources",
    "tags",
    "supersedes",
    "superseded_by",
}

ACTIVE_BUCKETS = frozenset({
    "architecture",
    "patterns",
    "gotchas",
    "domain",
    "integrations",
    "features",
})

LEGACY_BUCKETS = frozenset({
    "entities",
    "operations",
    "testing",
})

VALID_BUCKETS = ACTIVE_BUCKETS | LEGACY_BUCKETS

# Ordered list used by index_generator to control rendering order.
BUCKETS = [
    "architecture",
    "patterns",
    "gotchas",
    "domain",
    "integrations",
    "features",
    "entities",
    "operations",
    "testing",
]
BUCKET_TITLES = {
    "architecture": "Architecture",
    "patterns": "Patterns",
    "gotchas": "Gotchas",
    "domain": "Domain",
    "integrations": "Integrations",
    "features": "Features",
    "entities": "Entities",
    "operations": "Operations",
    "testing": "Testing",
}

VALID_TYPES = frozenset({
    "entity",
    "concept",
    "source",
    "synthesis",
    "decision",
    "gotcha",
    "pattern",
    "overview",
    "domain",
})
VALID_STATUSES = {"draft", "active", "stale", "superseded"}


class InvalidFrontmatterError(ValueError):
    """Raised when a wiki page has missing or invalid frontmatter."""


def parse(content: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter + body from a markdown string.

    Returns (frontmatter_dict, body_str). Raises InvalidFrontmatterError on
    any schema violation.
    """
    content = content.replace('\r\n', '\n').replace('\r', '\n')
    if not content.startswith("---\n"):
        raise InvalidFrontmatterError("missing frontmatter: content must start with '---'")
    end = content.find("\n---\n", 4)
    if end == -1:
        raise InvalidFrontmatterError("frontmatter not terminated with '---'")
    raw = content[4:end]
    body = content[end + 5:]

    try:
        fm = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise InvalidFrontmatterError(f"invalid YAML in frontmatter: {exc}") from exc

    if not isinstance(fm, dict):
        raise InvalidFrontmatterError("frontmatter must be a YAML mapping")

    missing = REQUIRED_FIELDS - set(fm)
    if missing:
        raise InvalidFrontmatterError(f"missing required field(s): {sorted(missing)}")

    if fm["bucket"] not in VALID_BUCKETS:
        raise InvalidFrontmatterError(
            f"invalid bucket {fm['bucket']!r}, must be one of {sorted(VALID_BUCKETS)}"
        )
    if fm["type"] not in VALID_TYPES:
        raise InvalidFrontmatterError(
            f"invalid type {fm['type']!r}, must be one of {sorted(VALID_TYPES)}"
        )
    if fm["status"] not in VALID_STATUSES:
        raise InvalidFrontmatterError(
            f"invalid status {fm['status']!r}, must be one of {sorted(VALID_STATUSES)}"
        )
    if not isinstance(fm["sources"], list):
        raise InvalidFrontmatterError("sources must be a list")
    if not isinstance(fm["tags"], list):
        raise InvalidFrontmatterError("tags must be a list")
    if not isinstance(fm["supersedes"], list):
        raise InvalidFrontmatterError("supersedes must be a list")

    return fm, body


def serialize(fm: dict[str, Any], body: str) -> str:
    """Serialize frontmatter + body back to markdown string."""
    yaml_str = yaml.safe_dump(fm, sort_keys=False, default_flow_style=False)
    return f"---\n{yaml_str}---\n{body}"

"""Tests for feature tracking: hooks/feature-changelog.py and manifest support
in skills/wiki-ingest/helper.py.
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Path setup so we can import from hooks/ and skills/wiki-ingest/ directly.
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "hooks"))
sys.path.insert(0, str(REPO_ROOT / "skills" / "wiki-ingest"))

from feature_changelog import (  # noqa: E402
    _append_changelog_entry,
    _file_matches_manifest,
    _matches_any_glob,
    run,
    validate_manifest,
)

# ---------------------------------------------------------------------------
# 1. Manifest validation
# ---------------------------------------------------------------------------


def test_valid_manifest_passes():
    manifest = {
        "features": [
            {"slug": "stripe-integration", "globs": ["backend/app/stripe/**"]},
            {"slug": "abc123", "globs": ["src/foo.py"]},
        ]
    }
    validate_manifest(manifest)  # must not raise


def test_invalid_slug_too_short():
    with pytest.raises(ValueError, match="Invalid slug"):
        validate_manifest({"features": [{"slug": "", "globs": []}]})


def test_invalid_slug_uppercase():
    with pytest.raises(ValueError, match="Invalid slug"):
        validate_manifest({"features": [{"slug": "My-Feature", "globs": []}]})


def test_invalid_slug_leading_hyphen():
    with pytest.raises(ValueError, match="Invalid slug"):
        validate_manifest({"features": [{"slug": "-bad", "globs": []}]})


def test_glob_with_dotdot_fails():
    with pytest.raises(ValueError, match=r"Glob contains '\.\.'"):
        validate_manifest(
            {"features": [{"slug": "ok-slug", "globs": ["../secrets/key.pem"]}]}
        )


def test_glob_with_leading_slash_fails():
    with pytest.raises(ValueError, match="Glob has leading '/'"):
        validate_manifest(
            {"features": [{"slug": "ok-slug", "globs": ["/etc/passwd"]}]}
        )


def test_empty_features_list_passes():
    validate_manifest({"features": []})


# ---------------------------------------------------------------------------
# 2. Glob matching
# ---------------------------------------------------------------------------


def test_glob_matches_file_under_wildcard():
    assert _matches_any_glob("backend/app/stripe/charge.py", ["backend/app/stripe/**"])


def test_glob_matches_exact_path():
    assert _matches_any_glob("src/foo.py", ["src/foo.py"])


def test_glob_no_match():
    assert not _matches_any_glob("backend/app/other/charge.py", ["backend/app/stripe/**"])


def test_glob_multi_segment_wildcard():
    assert _matches_any_glob("frontend/src/routes/latte-pour/index.ts", ["frontend/src/routes/latte-pour/**"])


# ---------------------------------------------------------------------------
# 3. _file_matches_manifest helper
# ---------------------------------------------------------------------------


def test_file_matches_manifest_returns_slug():
    manifest = {
        "features": [
            {"slug": "stripe-integration", "globs": ["backend/app/stripe/**"]},
        ]
    }
    assert _file_matches_manifest("backend/app/stripe/charge.py", manifest) == "stripe-integration"


def test_file_matches_manifest_no_match():
    manifest = {
        "features": [
            {"slug": "stripe-integration", "globs": ["backend/app/stripe/**"]},
        ]
    }
    assert _file_matches_manifest("backend/app/auth/login.py", manifest) is None


# ---------------------------------------------------------------------------
# 4. Hook: append entry when file matches manifest
# ---------------------------------------------------------------------------

FEATURE_PAGE_CONTENT = textwrap.dedent("""\
    ---
    title: Stripe Integration
    type: concept
    bucket: features
    status: active
    created: 2025-01-01
    updated: 2025-01-01
    sources: []
    tags: []
    supersedes: []
    superseded_by: null
    ---

    Overview of the Stripe integration.

    ## Changelog
""")


def _make_feature_page(tmp_path: Path, slug: str, content: str) -> Path:
    features_dir = tmp_path / "docs" / "wiki" / "features"
    features_dir.mkdir(parents=True)
    page = features_dir / f"{slug}.md"
    page.write_text(content, encoding="utf-8")
    return page


def _make_manifest(tmp_path: Path, features: list[dict]) -> None:
    import yaml
    manifest = {"features": features}
    (tmp_path / ".kv-wiki-features.yaml").write_text(
        yaml.safe_dump(manifest), encoding="utf-8"
    )


def test_hook_appends_entry_for_matched_file(tmp_path):
    _make_manifest(
        tmp_path,
        [{"slug": "stripe-integration", "globs": ["backend/app/stripe/**"]}],
    )
    page = _make_feature_page(tmp_path, "stripe-integration", FEATURE_PAGE_CONTENT)
    wiki_root = tmp_path / "docs" / "wiki"

    with (
        patch(
            "feature_changelog._git_changed_files",
            return_value=["backend/app/stripe/charge.py"],
        ),
        patch("feature_changelog._git_short_sha", return_value="abc1234"),
    ):
        rc = run(tmp_path, wiki_root)

    assert rc == 0
    text = page.read_text(encoding="utf-8")
    assert "`abc1234`" in text
    assert "backend/app/stripe/charge.py" in text


# ---------------------------------------------------------------------------
# 5. Idempotency: same SHA produces one entry, not two
# ---------------------------------------------------------------------------


def test_hook_idempotent(tmp_path):
    _make_manifest(
        tmp_path,
        [{"slug": "stripe-integration", "globs": ["backend/app/stripe/**"]}],
    )
    page = _make_feature_page(tmp_path, "stripe-integration", FEATURE_PAGE_CONTENT)
    wiki_root = tmp_path / "docs" / "wiki"

    with (
        patch(
            "feature_changelog._git_changed_files",
            return_value=["backend/app/stripe/charge.py"],
        ),
        patch("feature_changelog._git_short_sha", return_value="deadbeef"),
    ):
        run(tmp_path, wiki_root)
        run(tmp_path, wiki_root)

    text = page.read_text(encoding="utf-8")
    # Count occurrences of the SHA — must be exactly 1.
    assert text.count("`deadbeef`") == 1


# ---------------------------------------------------------------------------
# 6. Missing feature page: log warning, no crash
# ---------------------------------------------------------------------------


def test_hook_missing_feature_page_warns_and_skips(tmp_path, capsys):
    _make_manifest(
        tmp_path,
        [{"slug": "no-such-feature", "globs": ["backend/app/stripe/**"]}],
    )
    wiki_root = tmp_path / "docs" / "wiki"
    (wiki_root / "features").mkdir(parents=True)  # dir exists but no page

    with (
        patch(
            "feature_changelog._git_changed_files",
            return_value=["backend/app/stripe/charge.py"],
        ),
        patch("feature_changelog._git_short_sha", return_value="abc1234"),
    ):
        rc = run(tmp_path, wiki_root)

    assert rc == 0
    captured = capsys.readouterr()
    assert "warning" in captured.err.lower()
    assert "no-such-feature" in captured.err


# ---------------------------------------------------------------------------
# 7. No manifest: hook exits 0 silently
# ---------------------------------------------------------------------------


def test_hook_no_manifest_exits_zero(tmp_path):
    wiki_root = tmp_path / "docs" / "wiki"
    rc = run(tmp_path, wiki_root)
    assert rc == 0


# ---------------------------------------------------------------------------
# 8. wiki-ingest helper: manifest-matched code file appends changelog entry
# ---------------------------------------------------------------------------


def test_ingest_code_file_matched_by_manifest(tmp_path):
    """If --source is a code file that matches a manifest entry, ingest appends
    a changelog entry to the feature page instead of refusing."""
    import yaml
    from helper import cmd_ingest

    import argparse

    # Create project layout
    project_root = tmp_path / "project"
    project_root.mkdir()
    wiki_root = project_root / "docs" / "wiki"
    features_dir = wiki_root / "features"
    features_dir.mkdir(parents=True)

    # Manifest
    (project_root / ".kv-wiki-features.yaml").write_text(
        yaml.safe_dump(
            {"features": [{"slug": "my-feature", "globs": ["src/foo.py"]}]}
        ),
        encoding="utf-8",
    )

    # Feature page
    page = features_dir / "my-feature.md"
    page.write_text(FEATURE_PAGE_CONTENT, encoding="utf-8")

    # Source code file
    src_dir = project_root / "src"
    src_dir.mkdir()
    code_file = src_dir / "foo.py"
    code_file.write_text("# hello\n", encoding="utf-8")

    args = argparse.Namespace(
        source=str(code_file),
        wiki_root=str(wiki_root),
        project_root=str(project_root),
        bucket_hint="features",
        slug="my-feature",
        title="My Feature",
        summary="some summary",
        type="concept",
        func=None,
    )

    rc = cmd_ingest(args)
    assert rc == 0
    text = page.read_text(encoding="utf-8")
    assert "manual ingest" in text
    assert "src/foo.py" in text


def test_ingest_code_file_not_in_manifest_refused(tmp_path):
    """A code file NOT in the manifest still triggers exit 2."""
    import yaml
    from helper import cmd_ingest

    import argparse

    project_root = tmp_path / "project"
    project_root.mkdir()
    wiki_root = project_root / "docs" / "wiki"
    wiki_root.mkdir(parents=True)

    # Manifest with a different glob
    (project_root / ".kv-wiki-features.yaml").write_text(
        yaml.safe_dump(
            {"features": [{"slug": "other-feature", "globs": ["src/other.py"]}]}
        ),
        encoding="utf-8",
    )

    src_dir = project_root / "src"
    src_dir.mkdir()
    code_file = src_dir / "foo.py"
    code_file.write_text("# hello\n", encoding="utf-8")

    args = argparse.Namespace(
        source=str(code_file),
        wiki_root=str(wiki_root),
        project_root=str(project_root),
        bucket_hint=None,
        slug=None,
        title=None,
        summary=None,
        type="concept",
        func=None,
    )

    with pytest.raises(SystemExit) as exc_info:
        cmd_ingest(args)
    assert exc_info.value.code == 2


# ---------------------------------------------------------------------------
# 9. _append_changelog_entry_ingest: creates ## Changelog section if missing
# ---------------------------------------------------------------------------


def test_append_creates_changelog_section_if_missing(tmp_path):
    """Feature page with no ## Changelog section gets one created."""
    from helper import _append_changelog_entry_ingest

    page = tmp_path / "my-feature.md"
    page.write_text("---\ntitle: My Feature\n---\n\n# Body\n", encoding="utf-8")

    source = tmp_path / "foo.py"
    source.write_text("# src\n", encoding="utf-8")

    _append_changelog_entry_ingest(page, source)

    text = page.read_text(encoding="utf-8")
    assert "## Changelog" in text
    assert "manual ingest" in text


# ---------------------------------------------------------------------------
# 10. validate_manifest: invalid slug causes run() to return 1
# ---------------------------------------------------------------------------


def test_hook_invalid_manifest_returns_error(tmp_path):
    """run() with a bad slug returns exit code 1."""
    manifest = tmp_path / ".kv-wiki-features.yaml"
    manifest.write_text("features:\n  - slug: INVALID_SLUG\n    globs: []\n", encoding="utf-8")
    wiki_root = tmp_path / "docs" / "wiki"

    with pytest.raises(ValueError, match="Invalid slug"):
        validate_manifest({"features": [{"slug": "INVALID_SLUG", "globs": []}]})

    rc = run(tmp_path, wiki_root)
    assert rc == 1

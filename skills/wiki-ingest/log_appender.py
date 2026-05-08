"""Append entries to docs/wiki/log.md."""
from __future__ import annotations

import os
import tempfile
from datetime import date
from pathlib import Path


def _atomic_write(path: Path, text: str) -> None:
    tmp = tempfile.NamedTemporaryFile(
        mode='w', dir=str(path.parent), suffix='.tmp',
        delete=False, encoding='utf-8',
    )
    try:
        tmp.write(text)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp.close()
        os.replace(tmp.name, str(path))
    except Exception:
        tmp.close()
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise


def append_entry(
    log_path: Path,
    op: str,
    source: str | None,
    changes: list[str],
) -> None:
    """Append an entry to the wiki log under today's date heading.

    If today's heading does not exist, insert it at the top (after the
    '# Wiki Log' header). If it exists, append to it.
    """
    today = date.today().isoformat()
    header_line = f"## {today}"

    if source is not None:
        entry_lines = [f"- `{op}` ← {source}"]
    else:
        entry_lines = [f"- `{op}`"]
    for change in changes:
        entry_lines.append(f"  - {change}")
    entry_block = "\n".join(entry_lines)

    if not log_path.exists():
        _atomic_write(log_path, f"# Wiki Log\n\n{header_line}\n{entry_block}\n")
        return

    content = log_path.read_text(encoding='utf-8')

    if header_line in content:
        start = content.index(header_line) + len(header_line) + 1
        next_heading = content.find("\n## ", start)
        if next_heading == -1:
            new = content.rstrip() + f"\n{entry_block}\n"
        else:
            new = content[:next_heading] + f"{entry_block}\n\n" + content[next_heading + 1:]
        _atomic_write(log_path, new)
        return

    lines = content.splitlines()
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("# Wiki Log"):
            insert_at = i + 1
            if insert_at < len(lines) and lines[insert_at].strip() == "":
                insert_at += 1
            break
    new_block = [header_line, entry_block, ""]
    lines[insert_at:insert_at] = new_block
    _atomic_write(log_path, "\n".join(lines) + "\n")

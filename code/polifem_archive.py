#!/usr/bin/env python3
"""Polifem Archive — Move old buffer entries to Obsidian vault."""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BUFFER_PATH = Path.home() / ".openclaw" / "proiecte" / "polifem" / "data" / "buffer.json"
OBSIDIAN_PATH = Path.home() / ".openclaw" / "Obsidian" / "Atlas" / "Polifem"
MAX_CONTENT_LEN = {
    "user": 1000,
    "assistant": 500,
    "toolResult": 300,
}
DEFAULT_MAX_CONTENT = 400
ARCHIVE_AGE_DAYS = 3


def parse_timestamp(ts):
    """Parse timestamp from entry (ms epoch or ISO string)."""
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts / 1000 if ts > 1e12 else ts, tz=timezone.utc)
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def slugify_session(session_key):
    """Create filesystem-safe slug from session key."""
    s = session_key.replace("agent:", "").replace(":", "-")
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in s)


def archive_old_entries(dry_run=False):
    """Archive entries older than ARCHIVE_AGE_DAYS, return archive report."""
    if not BUFFER_PATH.exists():
        print("No buffer file found.", file=sys.stderr)
        return {"archived": 0, "files": [], "remaining": 0}

    with open(BUFFER_PATH, "r", encoding="utf-8") as f:
        buffer = json.load(f)

    entries = buffer.get("entries", [])
    if not entries:
        print("Buffer is empty.", file=sys.stderr)
        return {"archived": 0, "files": [], "remaining": 0}

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=ARCHIVE_AGE_DAYS)

    old_entries = []
    current_entries = []
    for entry in entries:
        ts = parse_timestamp(entry.get("timestamp", ""))
        if ts and ts < cutoff:
            old_entries.append(entry)
        else:
            current_entries.append(entry)

    if not old_entries:
        print(f"No entries older than {ARCHIVE_AGE_DAYS} days to archive.")
        return {"archived": 0, "files": [], "remaining": len(entries)}

    # Group old entries by (date, session_key)
    groups = {}
    for entry in old_entries:
        ts = parse_timestamp(entry.get("timestamp", ""))
        if not ts:
            continue
        date_str = ts.strftime("%Y-%m-%d")
        session_key = entry.get("sessionKey", "unknown")
        key = (date_str, session_key)
        groups.setdefault(key, []).append(entry)

    # Write archive files
    OBSIDIAN_PATH.mkdir(parents=True, exist_ok=True)
    archived_files = []

    for (date_str, session_key), group_entries in sorted(groups.items()):
        slug = slugify_session(session_key)
        filename = f"{date_str}--{slug}.md"
        filepath = OBSIDIAN_PATH / filename

        role_counts = {}
        for e in group_entries:
            r = e.get("role", "unknown")
            role_counts[r] = role_counts.get(r, 0) + 1

        timestamps = [parse_timestamp(e.get("timestamp", "")) for e in group_entries]
        timestamps = [t for t in timestamps if t]
        time_min = min(timestamps).strftime("%H:%M") if timestamps else "?"
        time_max = max(timestamps).strftime("%H:%M") if timestamps else "?"

        lines = [
            f"# Polifem Archive: {date_str} ({slug})",
            "",
            f"> Auto-archived from Polifem buffer on {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "## Summary",
            f"- Entries: {len(group_entries)} ({', '.join(f'{k}: {v}' for k, v in sorted(role_counts.items()))})",
            f"- Date range: {time_min} — {time_max}",
            "",
            "## Messages",
            "",
        ]

        for entry in group_entries:
            ts = parse_timestamp(entry.get("timestamp", ""))
            time_str = ts.strftime("%H:%M") if ts else "?"
            role = entry.get("role", "unknown")
            content = entry.get("content", "")
            max_len = MAX_CONTENT_LEN.get(role, DEFAULT_MAX_CONTENT)
            truncated = len(content) > max_len
            content_preview = content[:max_len]
            if truncated:
                content_preview += "... (truncated, full content in buffer)"

            lines.append(f"### [{time_str}] {role}")
            lines.append(content_preview)
            lines.append("")

        content = "\n".join(lines)

        if not dry_run:
            tmp = filepath.with_suffix(".tmp")
            tmp.write_text(content, encoding="utf-8")
            tmp.rename(filepath)

        archived_files.append(filename)

    # Update buffer — remove archived entries
    if not dry_run:
        buffer["entries"] = current_entries
        tmp = BUFFER_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(buffer, indent=2), encoding="utf-8")
        tmp.rename(BUFFER_PATH)

    report = {
        "archived": len(old_entries),
        "files": archived_files,
        "remaining": len(current_entries),
        "dry_run": dry_run,
    }

    print(f"Archived {len(old_entries)} entries into {len(archived_files)} files.")
    print(f"Remaining in buffer: {len(current_entries)} entries.")
    for f in archived_files:
        print(f"  → {f}")

    return report


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    archive_old_entries(dry_run=dry_run)
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
ARCHIVE_AGE_DAYS = 7


def parse_timestamp(ts):
    """Parse timestamp from entry (ms epoch or ISO string).

    P1-3: always return a timezone-aware datetime so naive/aware comparisons
    (e.g. `ts < cutoff`) never raise TypeError. ISO strings without an offset
    are assumed UTC.
    """
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts / 1000 if ts > 1e12 else ts, tz=timezone.utc)
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def slugify_session(session_key):
    """Create filesystem-safe slug from session key."""
    s = session_key.replace("agent:", "").replace(":", "-")
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in s)


def _looks_like_session_link(link):
    """Heuristic: a session link looks like `YYYY-MM-DD--<slug>`.
    Matches the format produced by handler.js generateLinks()."""
    parts = link.split("--", 1)
    if len(parts) != 2:
        return False
    date_part = parts[0]
    if len(date_part) != 10 or date_part[4] != "-" or date_part[7] != "-":
        return False
    try:
        datetime.strptime(date_part, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _find_same_day_sessions(obsidian_dir, date_str, self_slug):
    """Find other archive files from the same day, returning their link slugs.
    Excludes the current file (self_slug) to avoid auto-references."""
    results = []
    prefix = f"{date_str}--"
    try:
        for f in obsidian_dir.iterdir():
            if not f.is_file() or f.suffix != ".md":
                continue
            name = f.stem  # filename without .md
            if not name.startswith(prefix):
                continue
            # Strip any `--<suffix>` collision counter to get the base slug.
            base = name
            # A collision suffix looks like `--2`, `--3`, etc. after the base slug.
            # We keep the full stem as the link target (Obsidian resolves by filename).
            if base == self_slug:
                continue
            results.append(base)
    except OSError:
        pass
    return results


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
        base_filename = f"{date_str}--{slug}"
        filename = f"{base_filename}.md"
        filepath = OBSIDIAN_PATH / filename

        # Avoid silently overwriting an existing archive for the same (date, session)
        suffix = 2
        while filepath.exists():
            filename = f"{base_filename}--{suffix}.md"
            filepath = OBSIDIAN_PATH / filename
            suffix += 1

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

        # BUG-2: compute self_slug BEFORE the per-message loop so each entry's
        # own session link is excluded (not just in the aggregated section).
        self_slug = f"{date_str}--{slug}"

        for entry in group_entries:
            ts = parse_timestamp(entry.get("timestamp", ""))
            time_str = ts.strftime("%H:%M") if ts else "?"
            role = entry.get("role", "unknown")
            # BUG-7: null-hardening — `content` may be null, tags/links may be null.
            content = entry.get("content") or ""
            max_len = MAX_CONTENT_LEN.get(role, DEFAULT_MAX_CONTENT)
            truncated = len(content) > max_len
            content_preview = content[:max_len]
            if truncated:
                content_preview += "... (truncated, full content in buffer)"

            lines.append(f"### [{time_str}] {role}")
            tags = entry.get("tags") or []
            # BUG-2: filter out the entry's own session link (self-reference).
            links = [l for l in (entry.get("links") or []) if l != self_slug]
            if tags:
                lines.append(f"Tags: {' '.join('#' + t for t in tags)}")
            if links:
                lines.append(f"Links: {' '.join('[[' + l + ']]' for l in links)}")
            lines.append(content_preview)
            lines.append("")

        # Aggregate tags/links across the group for the backlinks section.
        all_tags = []
        all_links = []
        for entry in group_entries:
            for t in (entry.get("tags") or []):
                if t not in all_tags:
                    all_tags.append(t)
            for l in (entry.get("links") or []):
                if l not in all_links:
                    all_links.append(l)

        # Categorize links: projects vs sessions vs topics/decisions.
        # - Projects: match against the project directory names (same source as handler.js).
        # - Sessions: look like `YYYY-MM-DD--<slug>` (same-day session links).
        # - Topics/Decisions: `decizie-<topic>` or `#tag`-style topics.
        project_links = []
        session_links = []
        topic_links = []
        for l in all_links:
            if l.startswith("decizie-"):
                topic_links.append(l)
            elif _looks_like_session_link(l):
                session_links.append(l)
            else:
                project_links.append(l)

        # BUG-4: compute same-day sessions from in-memory `groups` (bidirectional)
        # plus a disk scan, so files written earlier in this run also link back.
        self_slug = f"{date_str}--{slug}"
        session_links = [l for l in session_links if l != self_slug]
        same_day_sessions = _find_same_day_sessions(OBSIDIAN_PATH, date_str, self_slug)
        # In-memory: other groups from the same date (not yet on disk or already written).
        for (g_date, g_session), _g_entries in groups.items():
            if g_date == date_str and g_session != session_key:
                g_slug = f"{date_str}--{slugify_session(g_session)}"
                if g_slug not in same_day_sessions:
                    same_day_sessions.append(g_slug)
        for s in same_day_sessions:
            if s not in session_links:
                session_links.append(s)

        if all_tags or project_links or session_links or topic_links:
            lines.append("## Links")
            if project_links:
                lines.append(f"- Projects: {' '.join('[[' + l + ']]' for l in project_links)}")
            if session_links:
                lines.append(f"- Sessions: {' '.join('[[' + l + ']]' for l in session_links)}")
            if topic_links:
                lines.append(f"- Topics: {' '.join('[[' + l + ']]' for l in topic_links)}")
            if all_tags:
                lines.append(f"- Tags: {' '.join('#' + t for t in all_tags)}")
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
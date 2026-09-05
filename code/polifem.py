#!/usr/bin/env python3
"""Polifem CLI — Lossless context search and recall."""

import json
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

BUFFER_PATH = Path.home() / ".openclaw" / "proiecte" / "polifem" / "data" / "buffer.json"
OBSIDIAN_PATH = Path.home() / ".openclaw" / "Obsidian" / "Atlas" / "Polifem"


def _print_entry(entry):
    """Print a single buffer entry in the standard [ts] [role] session + preview format."""
    ts = entry.get("timestamp", "?")
    role = entry.get("role", "?")
    session = entry.get("sessionKey", "?")[:40]
    preview = _get_str(entry, "content")[:200]
    print(f"[{ts}] [{role}] {session}")
    print(f"  {preview}...")
    print()


def _freq(items):
    """Return a frequency dict for a list of items."""
    freq = {}
    for i in items:
        freq[i] = freq.get(i, 0) + 1
    return freq


def _get_list(entry, key):
    """P1-2: null-hardening — return `entry.get(key) or []` so a `null` value
    (e.g. `"tags": null`) never reaches `" ".join(None)` / iteration."""
    return entry.get(key) or []


def _get_str(entry, key):
    """P1-2: null-hardening — return `entry.get(key) or ""` so a `null` content
    never reaches `.lower()` / slicing."""
    return entry.get(key) or ""


def load_buffer():
    """Load the Polifem buffer from disk."""
    if not BUFFER_PATH.exists():
        print("No buffer found. Run some conversations first.", file=sys.stderr)
        return {"version": 1, "entries": []}
    try:
        with open(BUFFER_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading buffer: {e}", file=sys.stderr)
        return {"version": 1, "entries": []}


def search(query: str, limit: int = 20, field: str = "all"):
    """Search buffer entries matching query (case-insensitive keyword).

    field: 'all' (content+tags+links), 'tags', or 'links'.
    """
    buffer = load_buffer()
    query_lower = query.lower()
    matches = []
    for entry in buffer.get("entries", []):
        content = _get_str(entry, "content").lower()
        tags = " ".join(_get_list(entry, "tags")).lower()
        links = " ".join(_get_list(entry, "links")).lower()
        if field == "tags":
            hit = query_lower in tags
        elif field == "links":
            hit = query_lower in links
        else:
            hit = query_lower in content or query_lower in tags or query_lower in links
        if hit:
            matches.append(entry)
        if len(matches) >= limit:
            break

    if not matches:
        print(f"No matches for '{query}'")
        return

    for m in matches:
        _print_entry(m)


def recall(session_filter: str = "", days: int = 1, limit: int = 50):
    """Recall full conversation entries, optionally filtered by session or date."""
    buffer = load_buffer()
    cutoff = datetime.now() - timedelta(days=days)
    matches = []

    for entry in buffer.get("entries", []):
        # Date filter
        ts = entry.get("timestamp", "")
        try:
            if isinstance(ts, (int, float)):
                entry_dt = datetime.fromtimestamp(ts / 1000 if ts > 1e12 else ts)
            else:
                entry_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if entry_dt < cutoff:
                continue
        except (ValueError, TypeError):
            pass

        # Session filter
        if session_filter and session_filter.lower() not in entry.get("sessionKey", "").lower():
            continue

        matches.append(entry)
        if len(matches) >= limit:
            break

    if not matches:
        print(f"No entries found (days={days}, session={session_filter or '*'})")
        return

    for m in matches:
        ts = m.get("timestamp", "?")
        role = m.get("role", "?")
        content = m.get("content", "") or ""
        print(f"--- [{ts}] [{role}] ---")
        print(content[:500])
        print()


def context_topic(topic: str, limit: int = 10):
    """Reconstruct context relevant to a topic."""
    buffer = load_buffer()
    topic_lower = topic.lower()
    # Score entries by topic relevance with weighted fields:
    #   content match = 1x, tag match = 3x, link match = 5x
    scored = []
    for entry in buffer.get("entries", []):
        content = _get_str(entry, "content").lower()
        tags = " ".join(_get_list(entry, "tags")).lower()
        links = " ".join(_get_list(entry, "links")).lower()
        score = (
            content.count(topic_lower)
            + 3 * tags.count(topic_lower)
            + 5 * links.count(topic_lower)
        )
        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)

    if not scored:
        print(f"No context found for topic '{topic}'")
        return

    print(f"Context for '{topic}' (top {min(limit, len(scored))} entries):\n")
    for score, entry in scored[:limit]:
        ts = entry.get("timestamp", "?")
        role = entry.get("role", "?")
        content = _get_str(entry, "content")[:300]
        print(f"[{ts}] [{role}] (relevance: {score})")
        print(f"  {content}...")
        print()


def stats():
    """Show buffer statistics."""
    buffer = load_buffer()
    entries = buffer.get("entries", [])

    if not entries:
        print("Buffer is empty.")
        return

    total = len(entries)
    by_role = {}
    by_session = {}
    oldest = None
    newest = None

    for entry in entries:
        role = entry.get("role", "unknown")
        by_role[role] = by_role.get(role, 0) + 1

        sk = entry.get("sessionKey", "unknown")
        if len(sk) > 50:
            sk = sk[:50] + "..."
        by_session[sk] = by_session.get(sk, 0) + 1

        ts = entry.get("timestamp", "")
        try:
            if isinstance(ts, (int, float)):
                dt = datetime.fromtimestamp(ts / 1000 if ts > 1e12 else ts)
            else:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if oldest is None or dt < oldest:
                oldest = dt
            if newest is None or dt > newest:
                newest = dt
        except (ValueError, TypeError):
            pass

    print(f"Polifem Buffer Statistics")
    print(f"  Total entries: {total}")
    if oldest and newest:
        print(f"  Date range: {oldest.strftime('%Y-%m-%d %H:%M')} — {newest.strftime('%Y-%m-%d %H:%M')}")
    print(f"  By role:")
    for role, count in sorted(by_role.items(), key=lambda x: x[1], reverse=True):
        print(f"    {role}: {count}")
    print(f"  By session:")
    for sk, count in sorted(by_session.items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"    {sk}: {count}")

    # Tags and links statistics
    tag_freq = _freq(t for entry in entries for t in _get_list(entry, "tags"))
    link_freq = _freq(l for entry in entries for l in _get_list(entry, "links"))

    print(f"  Distinct tags: {len(tag_freq)}")
    print(f"  Distinct links: {len(link_freq)}")
    if tag_freq:
        print(f"  Top tags:")
        for t, c in sorted(tag_freq.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"    {t}: {c}")
    if link_freq:
        print(f"  Top links:")
        for l, c in sorted(link_freq.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"    {l}: {c}")

    file_size = BUFFER_PATH.stat().st_size if BUFFER_PATH.exists() else 0
    print(f"  File size: {file_size / 1024:.1f} KB")


def tags_search(tags: list, use_and: bool = False, list_only: bool = False, limit: int = 20):
    """Search buffer entries by tags (OR/UNION by default, AND/INTERSECTION with --and)."""
    buffer = load_buffer()
    entries = buffer.get("entries", [])

    if list_only:
        tag_freq = _freq(t for entry in entries for t in _get_list(entry, "tags"))
        if not tag_freq:
            print("No tags in buffer.")
            return
        # P4: respect --limit in --list mode.
        for t, c in sorted(tag_freq.items(), key=lambda x: x[1], reverse=True)[:limit]:
            print(f"{t}: {c}")
        return

    if not tags:
        print("Usage: polifem tags <tag> [tag...] [--and] [--list] [--limit N]", file=sys.stderr)
        sys.exit(1)

    tags_lower = [t.lower() for t in tags]
    matches = []
    for entry in entries:
        entry_tags = [t.lower() for t in _get_list(entry, "tags")]
        if use_and:
            matched = all(t in entry_tags for t in tags_lower)
        else:
            matched = any(t in entry_tags for t in tags_lower)
        if matched:
            matched_tags = [t for t in _get_list(entry, "tags") if t.lower() in tags_lower]
            matches.append((entry, matched_tags))
        if len(matches) >= limit:
            break

    if not matches:
        print(f"No entries with tags: {', '.join(tags)}")
        return

    for entry, matched_tags in matches:
        ts = entry.get("timestamp", "?")
        role = entry.get("role", "?")
        session = entry.get("sessionKey", "?")[:40]
        preview = _get_str(entry, "content")[:200]
        print(f"[{ts}] [{role}] {session}")
        print(f"  tags: {', '.join(matched_tags)}")
        print(f"  {preview}...")
        print()


def parse_archive_links(filepath: Path):
    """Parse the '## Links' section of an archive .md file.

    Returns a dict of category -> list of link strings.
    Categories: Projects, Sessions, Topics, Tags.
    Links are space-separated [[wiki-links]] / #tags.
    """
    try:
        text = filepath.read_text(encoding="utf-8")
    except (IOError, OSError):
        return {}

    in_links = False
    links = {}
    current_cat = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## Links"):
            in_links = True
            continue
        if in_links and stripped.startswith("## ") and stripped != "## Links":
            break
        if not in_links:
            continue
        if stripped.startswith("- "):
            # Category line: "- Projects:" or "- Projects: [[a]] [[b]] #tag"
            body = stripped[2:]
            if ":" in body:
                cat, _, rest = body.partition(":")
                cat = cat.strip()
                current_cat = cat
                # BUG-1: split on whitespace, strip [[ ]] / # prefixes
                items = [i.strip("[]#") for i in rest.split() if i.strip("[]#")]
                links.setdefault(cat, []).extend(items)
            else:
                # bare item under current category
                if current_cat:
                    links.setdefault(current_cat, []).append(body.strip())
    return links


def links_search(query: str, mode: str = "buffer", list_only: bool = False, limit: int = 20):
    """Search buffer and/or Obsidian archives by links.

    mode: 'buffer', 'archive', or 'all'.
    """
    buffer = load_buffer()
    entries = buffer.get("entries", [])

    if list_only:
        # MINOR-1: support --list combined with --archive/--all
        link_freq = _freq(l for entry in entries for l in _get_list(entry, "links"))
        if mode in ("archive", "all") and OBSIDIAN_PATH.exists():
            for md in sorted(OBSIDIAN_PATH.glob("*.md")):
                for items in parse_archive_links(md).values():
                    for item in items:
                        link_freq[item] = link_freq.get(item, 0) + 1
        if not link_freq:
            print("No links in buffer.")
            return
        # P4: respect --limit in --list mode.
        for l, c in sorted(link_freq.items(), key=lambda x: x[1], reverse=True)[:limit]:
            print(f"{l}: {c}")
        return

    if not query:
        print("Usage: polifem links <link> [--archive|--all] [--list] [--backlinks S] [--limit N]", file=sys.stderr)
        sys.exit(1)

    query_lower = query.lower()

    # Buffer search
    if mode in ("buffer", "all"):
        matches = []
        for entry in entries:
            entry_links = [l.lower() for l in _get_list(entry, "links")]
            if any(query_lower in l for l in entry_links):
                matches.append(entry)
            if len(matches) >= limit:
                break
        if matches:
            print(f"=== Buffer matches for '{query}' ===")
            for entry in matches:
                _print_entry(entry)
        else:
            # BUG-2: print no-match message in all modes
            print(f"No buffer entries with link '{query}'")

    # Archive search
    if mode in ("archive", "all"):
        if not OBSIDIAN_PATH.exists():
            # BUG-2: always print an informative message, regardless of mode
            print("No Obsidian archive directory found.")
            return
        archive_matches = []
        for md in sorted(OBSIDIAN_PATH.glob("*.md")):
            links = parse_archive_links(md)
            for cat, items in links.items():
                for item in items:
                    if query_lower in item.lower():
                        archive_matches.append((md.name, cat, item))
                        break
            if len(archive_matches) >= limit:
                break
        # BUG-3: truncate to limit before printing
        archive_matches = archive_matches[:limit]
        if archive_matches:
            print(f"=== Archive matches for '{query}' ===")
            for fname, cat, item in archive_matches:
                print(f"[{fname}] [{cat}]")
                print(f"  {item}")
                print()
        else:
            print(f"No archive links matching '{query}'")


def backlinks(session_key: str, limit: int = 20):
    """Find entries/archives that link to a given session key."""
    buffer = load_buffer()
    entries = buffer.get("entries", [])
    sk_lower = session_key.lower()

    matches = []
    for entry in entries:
        entry_links = [l.lower() for l in _get_list(entry, "links")]
        if any(sk_lower in l for l in entry_links):
            matches.append(entry)
        if len(matches) >= limit:
            break

    if matches:
        print(f"=== Buffer backlinks to '{session_key}' ===")
        for entry in matches:
            _print_entry(entry)
    else:
        print(f"No buffer backlinks to '{session_key}'")

    # Archive backlinks
    if OBSIDIAN_PATH.exists():
        archive_matches = []
        for md in sorted(OBSIDIAN_PATH.glob("*.md")):
            links = parse_archive_links(md)
            for cat, items in links.items():
                for item in items:
                    if sk_lower in item.lower():
                        archive_matches.append((md.name, cat, item))
                        break
            if len(archive_matches) >= limit:
                break
        # BUG-3: truncate to limit before printing
        archive_matches = archive_matches[:limit]
        if archive_matches:
            print(f"=== Archive backlinks to '{session_key}' ===")
            for fname, cat, item in archive_matches:
                print(f"[{fname}] [{cat}]")
                print(f"  {item}")
                print()
        else:
            # P4: no-match message for archive backlinks (was silent).
            print(f"No archive backlinks found for '{session_key}'")


def main():
    if len(sys.argv) < 2:
        print("Polifem CLI — Lossless context preservation")
        print()
        print("Usage:")
        print("  polifem search <query> [--tags|--links|--all] [--limit N]  Search entries")
        print("  polifem recall [--days N] [--session S] [--limit N]  Recall recent entries")
        print("  polifem context <topic> [--limit N]  Reconstruct context for a topic")
        print("  polifem tags <tag> [tag...] [--and] [--list] [--limit N]  Search by tags")
        print("  polifem links <link> [--archive|--all] [--list] [--backlinks S] [--limit N]  Search by links")
        print("  polifem stats              Show buffer statistics")
        sys.exit(1)

    command = sys.argv[1]

    if command == "search":
        import argparse
        parser = argparse.ArgumentParser(prog="polifem search", add_help=False)
        parser.add_argument("--tags", action="store_true")
        parser.add_argument("--links", action="store_true")
        parser.add_argument("--all", action="store_true")
        parser.add_argument("--limit", type=int, default=20)
        args, remaining = parser.parse_known_args(sys.argv[2:])
        query = " ".join(remaining) if remaining else ""
        if not query:
            print("Usage: polifem search <query> [--tags|--links|--all] [--limit N]", file=sys.stderr)
            sys.exit(1)
        field = "all"
        if args.tags:
            field = "tags"
        elif args.links:
            field = "links"
        search(query, limit=args.limit, field=field)
    elif command == "recall":
        import argparse
        parser = argparse.ArgumentParser(prog="polifem recall", add_help=False)
        parser.add_argument("--days", type=int, default=1)
        parser.add_argument("--limit", type=int, default=50)
        parser.add_argument("--session", type=str, default="")
        args, remaining = parser.parse_known_args(sys.argv[2:])
        session = args.session or (" ".join(remaining) if remaining else "")
        recall(session_filter=session, days=args.days, limit=args.limit)
    elif command == "context":
        import argparse
        parser = argparse.ArgumentParser(prog="polifem context", add_help=False)
        parser.add_argument("--limit", type=int, default=10)
        args, remaining = parser.parse_known_args(sys.argv[2:])
        topic = " ".join(remaining) if remaining else ""
        if not topic:
            print("Usage: polifem context <topic> [--limit N]", file=sys.stderr)
            sys.exit(1)
        context_topic(topic, limit=args.limit)
    elif command == "tags":
        import argparse
        parser = argparse.ArgumentParser(prog="polifem tags", add_help=False)
        parser.add_argument("--and", dest="use_and", action="store_true")
        parser.add_argument("--list", dest="list_only", action="store_true")
        parser.add_argument("--limit", type=int, default=20)
        args, remaining = parser.parse_known_args(sys.argv[2:])
        tags_search(tags=remaining, use_and=args.use_and, list_only=args.list_only, limit=args.limit)
    elif command == "links":
        import argparse
        parser = argparse.ArgumentParser(prog="polifem links", add_help=False)
        parser.add_argument("--archive", action="store_true")
        parser.add_argument("--all", action="store_true")
        parser.add_argument("--list", dest="list_only", action="store_true")
        parser.add_argument("--backlinks", type=str, default="")
        parser.add_argument("--limit", type=int, default=20)
        args, remaining = parser.parse_known_args(sys.argv[2:])
        if args.backlinks:
            backlinks(args.backlinks, limit=args.limit)
        else:
            mode = "archive" if args.archive else ("all" if args.all else "buffer")
            query = " ".join(remaining) if remaining else ""
            links_search(query, mode=mode, list_only=args.list_only, limit=args.limit)
    elif command == "stats":
        stats()
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
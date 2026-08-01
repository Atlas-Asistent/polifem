#!/usr/bin/env python3
"""Polifem CLI — Lossless context search and recall."""

import json
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

BUFFER_PATH = Path.home() / ".openclaw" / "proiecte" / "polifem" / "data" / "buffer.json"
OBSIDIAN_PATH = Path.home() / ".openclaw" / "Obsidian" / "Atlas" / "Polifem"


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


def search(query: str, limit: int = 20):
    """Search buffer entries matching query (case-insensitive keyword)."""
    buffer = load_buffer()
    query_lower = query.lower()
    matches = []
    for entry in buffer.get("entries", []):
        content = entry.get("content", "").lower()
        if query_lower in content:
            matches.append(entry)
        if len(matches) >= limit:
            break

    if not matches:
        print(f"No matches for '{query}'")
        return

    for m in matches:
        ts = m.get("timestamp", "?")
        role = m.get("role", "?")
        content_preview = m.get("content", "")[:200]
        session = m.get("sessionKey", "?")[:40]
        print(f"[{ts}] [{role}] {session}")
        print(f"  {content_preview}...")
        print()


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
        content = m.get("content", "")
        print(f"--- [{ts}] [{role}] ---")
        print(content[:500])
        print()


def context_topic(topic: str, limit: int = 10):
    """Reconstruct context relevant to a topic."""
    buffer = load_buffer()
    topic_lower = topic.lower()
    # Score entries by topic relevance
    scored = []
    for entry in buffer.get("entries", []):
        content = entry.get("content", "").lower()
        # Simple relevance: count topic keyword occurrences
        score = content.count(topic_lower)
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
        content = entry.get("content", "")[:300]
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

    file_size = BUFFER_PATH.stat().st_size if BUFFER_PATH.exists() else 0
    print(f"  File size: {file_size / 1024:.1f} KB")


def main():
    if len(sys.argv) < 2:
        print("Polifem CLI — Lossless context preservation")
        print()
        print("Usage:")
        print("  polifem search <query>     Search entries matching keyword")
        print("  polifem recall [--days N] [--session S] [--limit N]  Recall recent entries")
        print("  polifem context <topic>    Reconstruct context for a topic")
        print("  polifem stats              Show buffer statistics")
        sys.exit(1)

    command = sys.argv[1]

    if command == "search":
        query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        if not query:
            print("Usage: polifem search <query>", file=sys.stderr)
            sys.exit(1)
        search(query)
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
        topic = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        if not topic:
            print("Usage: polifem context <topic>", file=sys.stderr)
            sys.exit(1)
        context_topic(topic)
    elif command == "stats":
        stats()
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
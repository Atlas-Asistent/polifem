# Polifem 👁️

**Lossless context preservation for OpenClaw** — saves messages before compaction so nothing is truly lost.

When OpenClaw compacts a conversation, older messages are summarized and discarded. Polifem intercepts the `session:compact:before` event and saves the original messages to a local buffer, giving you full-text search and recall of everything that was "forgotten."

## How It Works

```
[OpenClaw compaction] → [Polifem Hook] → [buffer.json]
                                              │
[CLI: polifem search/recall/context/stats] ←──┘
```

1. **Hook** (`handler.js`) — Listens for `session:compact:before`, reads the session transcript, and appends compacted messages to `buffer.json`
2. **CLI** (`polifem.py`) — Search, recall, and reconstruct context from the buffer
3. **Archive** (`polifem_archive.py`) — Move old entries (3+ days) to Obsidian or Markdown files

## Features

- 🔒 **Lossless** — full message content preserved, not summaries
- 🔍 **Search** — keyword search across all saved messages
- 📜 **Recall** — retrieve recent entries by session or date
- 🧠 **Context** — reconstruct topic-relevant context from saved messages
- 📊 **Stats** — buffer statistics at a glance
- 🔄 **Deduplication** — automatic duplicate detection on save
- ⚡ **Non-blocking** — compaction proceeds regardless of hook outcome
- 🔬 **Atomic writes** — temp file + rename to prevent corruption

## Installation

### 1. Copy files

```bash
# Hook (OpenClaw will look for this path)
mkdir -p ~/.openclaw/hooks/polifem
cp code/hooks/handler.js code/hooks/HOOK.md ~/.openclaw/hooks/polifem/

# CLI
mkdir -p ~/.openclaw/polifem
cp code/polifem.py ~/.openclaw/polifem/polifem.py

# Archive script
cp code/polifem_archive.py ~/.openclaw/polifem/polifem_archive.py

# Data directory
mkdir -p ~/.openclaw/proiecte/polifem/data
```

### 2. Enable the hook in OpenClaw

The hook is auto-detected from `~/.openclaw/hooks/polifem/`. No additional configuration needed.

### 3. Use the CLI

```bash
# Search for a keyword
python3 ~/.openclaw/polifem/polifem.py search "nomos"

# Recall recent entries (last 1 day)
python3 ~/.openclaw/polifem/polifem.py recall --days 1

# Reconstruct context for a topic
python3 ~/.openclaw/polifem/polifem.py context "trading strategy"

# Buffer statistics
python3 ~/.openclaw/polifem/polifem.py stats

# Archive old entries (3+ days) to Markdown
python3 ~/.openclaw/polifem/polifem_archive.py           # live run
python3 ~/.openclaw/polifem/polifem_archive.py --dry-run # preview only
```

## Buffer Format

```json
{
  "version": 1,
  "entries": [
    {
      "id": "msg-uuid",
      "parentId": "uuid|null",
      "sessionKey": "agent:main:telegram:direct:...",
      "timestamp": 1782818842941,
      "role": "user|assistant",
      "content": "...",
      "savedAt": "2026-06-30T15:45:00Z",
      "compactionBatch": 1782818842941
    }
  ]
}
```

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `MAX_ENTRIES` | 50,000 | Maximum entries in buffer (oldest trimmed) |
| `ARCHIVE_AGE_DAYS` | 3 | Days before entries are archived |
| `MAX_CONTENT_LEN` | 1000/500/300 | Truncation by role (user/assistant/toolResult) |

## Requirements

- **Node.js** — for the hook handler
- **Python 3.8+** — for the CLI and archive scripts
- **OpenClaw** — with hook support (`session:compact:before` event)

## License

MIT
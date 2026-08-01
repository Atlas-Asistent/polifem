---
name: polifem
description: "Lossless context preservation: saves compacted messages before OpenClaw discards them."
metadata:
  {
    "openclaw":
      {
        "emoji": "👁️",
        "events": ["session:compact:before"],
        "requires": { "bins": ["node"] },
      },
  }
---

# Polifem 👁️

Saves messages about to be compacted by OpenClaw into a local JSON buffer, preserving full context that would otherwise be lost. After 3 days, Hefaistos archives them to Obsidian and clears the buffer.

- Listens to `session:compact:before` events
- Reads the session transcript JSONL to extract messages being compacted
- Appends them to `~/.openclaw/polifem/data/buffer.json`
- Non-blocking: compaction proceeds normally regardless of hook outcome
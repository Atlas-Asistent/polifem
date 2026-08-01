import { readFileSync, writeFileSync, existsSync, mkdirSync, renameSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";

//#region Polifem — Lossless Context Preservation Hook
const POLIFEM_DIR = join(homedir(), ".openclaw", "proiecte", "polifem", "data");
const BUFFER_PATH = join(POLIFEM_DIR, "buffer.json");
const DEBUG_LOG_PATH = join(POLIFEM_DIR, "hook-debug.log");
const MAX_ENTRIES = 50000;

function readOptionalNumber(context, key) {
  const value = context[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const n = Number(value);
    if (Number.isFinite(n)) return n;
  }
  return undefined;
}

function debugLog(message) {
  try {
    if (!existsSync(POLIFEM_DIR)) mkdirSync(POLIFEM_DIR, { recursive: true });
    const line = `[${new Date().toISOString()}] ${message}\n`;
    writeFileSync(DEBUG_LOG_PATH, line, { flag: "a", encoding: "utf-8" });
  } catch {
    // Best-effort debug logging
  }
}

function loadBuffer() {
  if (!existsSync(BUFFER_PATH)) {
    debugLog(`loadBuffer: file does not exist at ${BUFFER_PATH}`);
    return { version: 1, entries: [] };
  }
  try {
    const raw = readFileSync(BUFFER_PATH, "utf-8");
    const parsed = JSON.parse(raw);
    debugLog(`loadBuffer: loaded ${parsed.entries?.length ?? 0} entries from ${BUFFER_PATH}`);
    return parsed;
  } catch (err) {
    debugLog(`loadBuffer: ERROR parsing ${BUFFER_PATH}: ${err instanceof Error ? err.message : String(err)}`);
    return { version: 1, entries: [] };
  }
}

function saveBuffer(buffer) {
  if (!existsSync(POLIFEM_DIR)) {
    mkdirSync(POLIFEM_DIR, { recursive: true });
  }
  // Atomic write: write to temp file then rename
  const tmpPath = BUFFER_PATH + ".tmp";
  writeFileSync(tmpPath, JSON.stringify(buffer, null, 2), "utf-8");
  renameSync(tmpPath, BUFFER_PATH);
  debugLog(`saveBuffer: saved ${buffer.entries.length} entries to ${BUFFER_PATH}`);
}

function findTranscriptPath(sessionKey, sessionId) {
  const agentsDir = join(homedir(), ".openclaw", "agents");
  const agentMatch = sessionKey && sessionKey.match(/^agent:([^:]+):/);
  const agentId = agentMatch ? agentMatch[1] : "main";

  // If sessionId provided directly, use it
  if (sessionId) {
    const transcriptPath = join(agentsDir, agentId, "sessions", `${sessionId}.jsonl`);
    if (existsSync(transcriptPath)) {
      debugLog(`findTranscriptPath: found via sessionId: ${transcriptPath}`);
      return transcriptPath;
    }
    debugLog(`findTranscriptPath: sessionId path not found: ${transcriptPath}`);
  }

  // Fallback: look up sessionKey in sessions.json
  const sessionsPath = join(agentsDir, agentId, "sessions", "sessions.json");
  if (!existsSync(sessionsPath)) {
    debugLog(`findTranscriptPath: sessions.json not found at ${sessionsPath}`);
    return null;
  }

  try {
    const sessionsRaw = readFileSync(sessionsPath, "utf-8");
    const sessions = JSON.parse(sessionsRaw);
    const entry = sessions[sessionKey];
    if (entry && entry.sessionId) {
      const transcriptPath = join(agentsDir, agentId, "sessions", `${entry.sessionId}.jsonl`);
      if (existsSync(transcriptPath)) {
        debugLog(`findTranscriptPath: found via sessions.json: ${transcriptPath}`);
        return transcriptPath;
      }
      if (entry.sessionFile) {
        const altPath = join(agentsDir, agentId, "sessions", entry.sessionFile);
        if (existsSync(altPath)) {
          debugLog(`findTranscriptPath: found via sessionFile: ${altPath}`);
          return altPath;
        }
      }
    }
    debugLog(`findTranscriptPath: sessionKey not found in sessions.json: ${sessionKey}`);
  } catch (err) {
    debugLog(`findTranscriptPath: error reading sessions.json: ${err instanceof Error ? err.message : String(err)}`);
  }
  return null;
}

function extractCompactedMessages(transcriptPath, messageCount, sessionKey) {
  if (!messageCount || messageCount <= 0) return [];
  if (!transcriptPath || !existsSync(transcriptPath)) return [];

  const entries = [];
  let messageIndex = 0;

  try {
    const raw = readFileSync(transcriptPath, "utf-8");
    const lines = raw.split("\n").filter(Boolean);
    debugLog(`extractCompactedMessages: transcript has ${lines.length} lines, extracting up to ${messageCount} messages`);

    for (const line of lines) {
      try {
        const entry = JSON.parse(line);
        if (entry.type === "message") {
          if (messageIndex >= messageCount) break;
          const msg = entry.message || {};
          let content;
          if (typeof msg.content === "string") {
            content = msg.content;
          } else if (Array.isArray(msg.content)) {
            content = msg.content
              .map(c => c.text || c.type || "")
              .filter(Boolean)
              .join("\n");
          } else {
            content = JSON.stringify(msg.content);
          }

          entries.push({
            id: entry.id || `msg-${messageIndex}`,
            parentId: entry.parentId || null,
            sessionKey: sessionKey || "",
            timestamp: msg.timestamp || entry.timestamp || Date.now(),
            role: msg.role || "unknown",
            content: content,
            savedAt: new Date().toISOString(),
            compactionBatch: Date.now(),
          });
          messageIndex++;
        }
      } catch {
        // Skip malformed lines
      }
    }
  } catch (err) {
    debugLog(`extractCompactedMessages: error reading transcript: ${err instanceof Error ? err.message : String(err)}`);
    return [];
  }

  debugLog(`extractCompactedMessages: extracted ${entries.length} messages`);
  return entries;
}

function deduplicateEntries(existingEntries, newEntries) {
  const existingIds = new Set(existingEntries.map(e => `${e.id}:${e.sessionKey}`));
  const deduped = newEntries.filter(e => {
    const key = `${e.id}:${e.sessionKey}`;
    if (existingIds.has(key)) {
      debugLog(`deduplicateEntries: skipping duplicate id=${e.id} session=${e.sessionKey}`);
      return false;
    }
    return true;
  });
  return deduped;
}

const handler = async (event) => {
  // Log the full event for debugging
  const eventSummary = {
    type: event.type,
    action: event.action,
    sessionKey: event.sessionKey,
    context: event.context,
    timestamp: event.timestamp,
    messagesLength: event.messages?.length ?? 0,
  };
  debugLog(`handler invoked: ${JSON.stringify(eventSummary)}`);

  if (event.type !== "session" || event.action !== "compact:before") {
    debugLog(`handler: skipping event (type=${event.type}, action=${event.action})`);
    return;
  }

  try {
    const sessionKey = event.sessionKey || "";
    const context = event.context || {};
    const sessionId = context.sessionId || "";
    const messageCount = readOptionalNumber(context, "messageCount");
    const tokenCount = readOptionalNumber(context, "tokenCount");

    console.log(`[polifem] Compact:before: sessionKey=${sessionKey}, sessionId=${sessionId}, messageCount=${messageCount}, tokenCount=${tokenCount}`);
    debugLog(`Compact:before: sessionKey=${sessionKey}, sessionId=${sessionId}, messageCount=${messageCount}, tokenCount=${tokenCount}, BUFFER_PATH=${BUFFER_PATH}`);

    if (!messageCount || messageCount <= 0) {
      console.log("[polifem] No messages to save (messageCount=0 or undefined)");
      debugLog("No messages to save (messageCount=0 or undefined)");
      return;
    }

    const transcriptPath = findTranscriptPath(sessionKey, sessionId);
    if (!transcriptPath) {
      console.warn(`[polifem] Could not find transcript for session: ${sessionKey}`);
      debugLog(`Could not find transcript for session: ${sessionKey}`);
      return;
    }

    const compactedMessages = extractCompactedMessages(transcriptPath, messageCount, sessionKey);

    if (compactedMessages.length === 0) {
      console.log("[polifem] No messages extracted from transcript");
      debugLog("No messages extracted from transcript");
      return;
    }

    console.log(`[polifem] Extracted ${compactedMessages.length} messages, saving to buffer`);

    const buffer = loadBuffer();
    const existingCount = buffer.entries.length;

    // Deduplicate against existing entries
    const deduped = deduplicateEntries(buffer.entries, compactedMessages);
    buffer.entries.push(...deduped);

    if (buffer.entries.length > MAX_ENTRIES) {
      buffer.entries = buffer.entries.slice(-MAX_ENTRIES);
    }

    saveBuffer(buffer);
    console.log(`[polifem] Buffer: ${existingCount} + ${deduped.length} (skipped ${compactedMessages.length - deduped.length} dups) = ${buffer.entries.length} entries`);
    debugLog(`Buffer: ${existingCount} + ${deduped.length} (skipped ${compactedMessages.length - deduped.length} dups) = ${buffer.entries.length} entries`);
  } catch (error) {
    const errMsg = error instanceof Error ? error.message : String(error);
    console.error(`[polifem] Error: ${errMsg}`);
    debugLog(`Error: ${errMsg}`);
    if (error instanceof Error && error.stack) {
      debugLog(`Stack: ${error.stack}`);
    }
  }
};

export default handler;
//#endregion
/**
 * Per-session context state the Selector needs (3.6): Runtime pointers created in this session (newest
 * first, the current_task candidates), ranges whose raw text already reached the model (inserted
 * fragments and bounded reads: history_refs, so the next run never re-inserts them), and the message
 * list of the last outbound provider request (history cost). Memory only; a host restart starts fresh
 * SDK sessions, so nothing here outlives the history it describes.
 */
import type { ContextRef, ExplicitContextRef } from "@securecode/contracts";

const MAX_POINTERS = 64;
const MAX_HISTORY = 256;

interface SessionEntry {
    runtimePointers: string[];
    history: ExplicitContextRef[];
    lastMessages: string[];
}

function refKey(ref: ContextRef): string {
    return JSON.stringify(ref);
}

export class SessionContextStore {
    private readonly sessions = new Map<string, SessionEntry>();

    private entry(sessionId: string): SessionEntry {
        let entry = this.sessions.get(sessionId);
        if (!entry) {
            entry = { runtimePointers: [], history: [], lastMessages: [] };
            this.sessions.set(sessionId, entry);
        }
        return entry;
    }

    /** A tool output stored as a Runtime Pointer in this session. */
    pointerCreated(sessionId: string, pointer: string): void {
        const entry = this.entry(sessionId);
        entry.runtimePointers = [pointer, ...entry.runtimePointers.filter((item) => item !== pointer)].slice(
            0,
            MAX_POINTERS,
        );
    }

    /** A range whose raw text is now in the model's history (fragment or bounded read with a selection). */
    shown(sessionId: string, ref: ExplicitContextRef): void {
        const entry = this.entry(sessionId);
        const key = refKey(ref);
        if (entry.history.some((item) => refKey(item) === key)) return;
        entry.history = [...entry.history, ref].slice(-MAX_HISTORY);
    }

    /** Records the messages of the request that just left for the provider (history cost source). */
    outbound(sessionId: string, body: string): void {
        try {
            const parsed = JSON.parse(body) as { messages?: unknown };
            if (Array.isArray(parsed.messages)) {
                // The system prompt is counted separately (OpenAI framing carries it as a message).
                this.entry(sessionId).lastMessages = parsed.messages
                    .filter((message) => (message as { role?: unknown }).role !== "system")
                    .map((message) => JSON.stringify(message));
            }
        } catch {
            // A body the gate could not parse was already refused there.
        }
    }

    view(sessionId: string): { runtimePointers: string[]; history: ExplicitContextRef[]; lastMessages: string[] } {
        const entry = this.entry(sessionId);
        return {
            runtimePointers: [...entry.runtimePointers],
            history: [...entry.history],
            lastMessages: [...entry.lastMessages],
        };
    }

    forget(sessionId: string): void {
        this.sessions.delete(sessionId);
    }
}

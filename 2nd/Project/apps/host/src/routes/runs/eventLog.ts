/**
 * Run-scoped AppEvent log (EVENTS.md 2/5): sequence starts at 1 and grows by
 * one, the latest 1,000 events are kept for Last-Event-ID replay, and after the
 * terminal event the log is closed and dropped 10 minutes later. Subscribers
 * see every appended event; nothing is appended after the terminal event.
 */
import type { AppEvent, ReplayWindow } from "@securecode/contracts";
import { isoTime, newId, type Clock } from "../../security/ids.js";

export const REPLAY_MAX_EVENTS = 1000;
export const REPLAY_RETENTION_AFTER_END_MS = 10 * 60 * 1000;

export interface RunScope {
    workspace_id: string;
    session_id: string;
    run_id: string;
}

type StoredEventType = Exclude<AppEvent["type"], "stream.replay_unavailable">;
type PayloadOf<T extends AppEvent["type"]> = Extract<AppEvent, { type: T }>["payload"];
export type EventSubscriber = (event: AppEvent | null) => void;

export type ReplayResult = { kind: "events"; events: AppEvent[] } | { kind: "gap"; oldest: number };

export class RunEventLog {
    private readonly events: AppEvent[] = [];
    private readonly subscribers = new Set<EventSubscriber>();
    private sequence: number;
    private closedFlag = false;

    constructor(
        private readonly scope: RunScope,
        private readonly clock: Clock,
        lastSequence = 0,
        closed = false,
    ) {
        this.sequence = lastSequence;
        this.closedFlag = closed;
    }

    get lastSequence(): number {
        return this.sequence;
    }

    get closed(): boolean {
        return this.closedFlag;
    }

    append<T extends StoredEventType>(type: T, payload: PayloadOf<T>): AppEvent | null {
        if (this.closedFlag) return null;
        this.sequence += 1;
        const event = {
            schema_version: "1",
            event_id: newId("evt"),
            sequence: this.sequence,
            ...this.scope,
            type,
            timestamp: isoTime(this.clock()),
            payload,
        } as AppEvent;
        this.events.push(event);
        if (this.events.length > REPLAY_MAX_EVENTS) this.events.shift();
        for (const subscriber of this.subscribers) subscriber(event);
        return event;
    }

    /** Marks the terminal event as the last one and drops the replay buffer later. */
    close(): void {
        if (this.closedFlag) return;
        this.closedFlag = true;
        for (const subscriber of this.subscribers) subscriber(null);
        this.subscribers.clear();
        const timer = setTimeout(() => this.events.splice(0), REPLAY_RETENTION_AFTER_END_MS);
        timer.unref();
    }

    window(): ReplayWindow {
        return { oldest_sequence: this.events[0]?.sequence ?? this.sequence + 1, last_sequence: this.sequence };
    }

    replayAfter(afterSequence: number): ReplayResult {
        if (afterSequence >= this.sequence) return { kind: "events", events: [] };
        const oldest = this.window().oldest_sequence;
        if (afterSequence + 1 < oldest) return { kind: "gap", oldest };
        return { kind: "events", events: this.events.filter((event) => event.sequence > afterSequence) };
    }

    replayUnavailable(requestedAfter: number, oldest: number): AppEvent {
        return {
            schema_version: "1",
            event_id: newId("evt"),
            sequence: this.sequence,
            ...this.scope,
            type: "stream.replay_unavailable",
            timestamp: isoTime(this.clock()),
            payload: { requested_after_sequence: requestedAfter, oldest_available_sequence: oldest },
        };
    }

    /** null is delivered once when the log closes, so streams can end. */
    subscribe(subscriber: EventSubscriber): () => void {
        if (this.closedFlag) {
            subscriber(null);
            return () => undefined;
        }
        this.subscribers.add(subscriber);
        return () => this.subscribers.delete(subscriber);
    }
}

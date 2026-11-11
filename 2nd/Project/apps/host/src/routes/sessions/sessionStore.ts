/**
 * App sessions (one SDK session each, created lazily on the first run).
 * active_run_id is non-null while a run is not terminal; it is cleared on the
 * terminal transition and after a host restart.
 */
import type { Session } from "@securecode/contracts";
import { isoTime, newId, type Clock } from "../../security/ids.js";
import { JsonFileStore } from "../shared/jsonFileStore.js";
import { RouteFailure } from "../shared/routeFailure.js";

type SessionRecord = Omit<Session, "schema_version"> & { deleted_at?: string };

export class SessionStore {
    private readonly records = new Map<string, SessionRecord>();
    private readonly store: JsonFileStore<SessionRecord>;

    constructor(
        directory: string,
        private readonly clock: Clock,
    ) {
        this.store = new JsonFileStore<SessionRecord>(directory);
        for (const record of this.store.loadAll()) {
            // A run cannot survive a host restart; recovery marks it terminal (RunService.recover).
            this.records.set(record.session_id, { ...record, active_run_id: null });
        }
    }

    create(workspaceId: string): Session {
        const record: SessionRecord = {
            session_id: newId("ses"),
            workspace_id: workspaceId,
            status: "active",
            active_run_id: null,
            last_run_id: null,
            created_at: isoTime(this.clock()),
        };
        this.save(record);
        return this.toWire(record);
    }

    get(sessionId: string): Session {
        const record = this.records.get(sessionId);
        if (!record || record.deleted_at) throw new RouteFailure("NOT_FOUND", "session not found");
        return this.toWire(record);
    }

    listForWorkspace(workspaceId: string): Session[] {
        return [...this.records.values()]
            .filter((record) => record.workspace_id === workspaceId && !record.deleted_at)
            .sort((left, right) => right.created_at.localeCompare(left.created_at))
            .map((record) => this.toWire(record));
    }

    /** Server-only lookup used to validate a parent workspace before restoring a conversation. */
    workspaceFor(sessionId: string): string {
        return this.requireStored(sessionId).workspace_id;
    }

    remove(sessionId: string): Session {
        const record = this.requireStored(sessionId);
        if (!record.deleted_at) this.save({ ...record, deleted_at: isoTime(this.clock()) });
        return this.toWire(record);
    }

    restore(sessionId: string): Session {
        const record = { ...this.requireStored(sessionId) };
        delete record.deleted_at;
        this.save(record);
        return this.toWire(record);
    }

    setActiveRun(sessionId: string, runId: string | null): void {
        const record = this.records.get(sessionId);
        if (!record) return;
        record.active_run_id = runId;
        if (runId) record.last_run_id = runId;
        this.save(record);
    }

    private save(record: SessionRecord): void {
        this.records.set(record.session_id, record);
        this.store.write(record.session_id, record);
    }

    private requireStored(sessionId: string): SessionRecord {
        const record = this.records.get(sessionId);
        if (!record) throw new RouteFailure("NOT_FOUND", "session not found");
        return record;
    }

    private toWire(record: SessionRecord): Session {
        const session = { ...record };
        delete session.deleted_at;
        return { schema_version: "1", ...session };
    }
}

/**
 * idempotency_key bookkeeping (API.md 2.3). The same key and body returns the
 * first result; the same key with another body is IDEMPOTENCY_CONFLICT. Keys
 * are scoped (e.g. per session) and kept for at least 24 hours on disk.
 */
import { canonicalJson, sha256Hex, type Clock } from "../../security/ids.js";
import { JsonFileStore } from "./jsonFileStore.js";
import { RouteFailure } from "./routeFailure.js";

export const IDEMPOTENCY_RETENTION_MS = 24 * 60 * 60 * 1000;

interface IdempotencyRecord {
    scope: string;
    key: string;
    body_digest: string;
    result_id: string;
    created_at_ms: number;
}

export type IdempotencyLookup = { kind: "new"; bodyDigest: string } | { kind: "replay"; resultId: string };

export class IdempotencyStore {
    private readonly records = new Map<string, IdempotencyRecord>();
    private readonly store: JsonFileStore<IdempotencyRecord>;
    private readonly clock: Clock;

    constructor(directory: string, clock: Clock) {
        this.store = new JsonFileStore<IdempotencyRecord>(directory);
        this.clock = clock;
        for (const record of this.store.loadAll()) {
            this.records.set(this.recordId(record.scope, record.key), record);
        }
        this.purgeExpired();
    }

    /** Checks a key before a create; `body` excludes nothing, so any field change is a conflict. */
    lookup(scope: string, key: string, body: unknown): IdempotencyLookup {
        this.purgeExpired();
        const bodyDigest = sha256Hex(canonicalJson(body));
        const record = this.records.get(this.recordId(scope, key));
        if (!record) return { kind: "new", bodyDigest };
        if (record.body_digest !== bodyDigest) {
            throw new RouteFailure("IDEMPOTENCY_CONFLICT", "idempotency_key was already used with a different body");
        }
        return { kind: "replay", resultId: record.result_id };
    }

    remember(scope: string, key: string, bodyDigest: string, resultId: string): void {
        const record: IdempotencyRecord = {
            scope,
            key,
            body_digest: bodyDigest,
            result_id: resultId,
            created_at_ms: this.clock(),
        };
        const id = this.recordId(scope, key);
        this.records.set(id, record);
        this.store.write(id, record);
    }

    private purgeExpired(): void {
        const cutoff = this.clock() - IDEMPOTENCY_RETENTION_MS;
        for (const [id, record] of this.records) {
            if (record.created_at_ms < cutoff) {
                this.records.delete(id);
                this.store.remove(id);
            }
        }
    }

    private recordId(scope: string, key: string): string {
        return `idem_${sha256Hex(`${scope}\u0000${key}`).slice(0, 48)}`;
    }
}

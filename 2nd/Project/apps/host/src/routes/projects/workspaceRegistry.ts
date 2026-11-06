/**
 * Registered workspaces. The absolute root stays inside the host (3.6 hands it
 * to the symbol/source services); the wire Workspace never contains it.
 * Index state is reported as not_indexed until 3.6 connects the index API.
 */
import type { SupportedLanguage, Workspace, WorkspaceCreateRequest } from "@securecode/contracts";
import { isoTime, newId, type Clock } from "../../security/ids.js";
import type { IdempotencyStore } from "../shared/idempotency.js";
import { JsonFileStore } from "../shared/jsonFileStore.js";
import { RouteFailure } from "../shared/routeFailure.js";
import { resolveWorkspaceRoot } from "./workspaceRoots.js";

export const SUPPORTED_LANGUAGES: [SupportedLanguage, ...SupportedLanguage[]] = [
    "python",
    "c",
    "cpp",
    "java",
    "javascript",
];

interface WorkspaceRecord {
    workspace_id: string;
    display_name: string;
    root: string;
    created_at: string;
}

export class WorkspaceRegistry {
    private readonly records = new Map<string, WorkspaceRecord>();
    private readonly store: JsonFileStore<WorkspaceRecord>;

    constructor(
        directory: string,
        private readonly allowedRoots: readonly string[],
        private readonly idempotency: IdempotencyStore,
        private readonly clock: Clock,
    ) {
        this.store = new JsonFileStore<WorkspaceRecord>(directory);
        for (const record of this.store.loadAll()) this.records.set(record.workspace_id, record);
    }

    /** Returns [workspace, created]; the same root or the same key returns the first registration. */
    create(request: WorkspaceCreateRequest): [Workspace, boolean] {
        const lookup = this.idempotency.lookup("workspaces", request.idempotency_key, request);
        if (lookup.kind === "replay") return [this.get(lookup.resultId), false];
        const root = resolveWorkspaceRoot(request.root_path, this.allowedRoots);
        const existing = [...this.records.values()].find((record) => record.root === root);
        if (existing) {
            this.idempotency.remember("workspaces", request.idempotency_key, lookup.bodyDigest, existing.workspace_id);
            return [this.toWire(existing), false];
        }
        const record: WorkspaceRecord = {
            workspace_id: newId("ws"),
            display_name: request.display_name,
            root,
            created_at: isoTime(this.clock()),
        };
        this.store.write(record.workspace_id, record);
        this.records.set(record.workspace_id, record);
        this.idempotency.remember("workspaces", request.idempotency_key, lookup.bodyDigest, record.workspace_id);
        return [this.toWire(record), true];
    }

    get(workspaceId: string): Workspace {
        return this.toWire(this.requireRecord(workspaceId));
    }

    list(): Workspace[] {
        return [...this.records.values()]
            .sort((left, right) => left.created_at.localeCompare(right.created_at))
            .map((record) => this.toWire(record));
    }

    /** Server-only root lookup for the SDK adapter and 3.6 services. */
    rootFor(workspaceId: string): string {
        return this.requireRecord(workspaceId).root;
    }

    private requireRecord(workspaceId: string): WorkspaceRecord {
        const record = this.records.get(workspaceId);
        if (!record) throw new RouteFailure("NOT_FOUND", "workspace not found");
        return record;
    }

    private toWire(record: WorkspaceRecord): Workspace {
        return {
            schema_version: "1",
            workspace_id: record.workspace_id,
            display_name: record.display_name,
            index_revision: null,
            index_status: "not_indexed",
            supported_languages: SUPPORTED_LANGUAGES,
            created_at: record.created_at,
        };
    }
}

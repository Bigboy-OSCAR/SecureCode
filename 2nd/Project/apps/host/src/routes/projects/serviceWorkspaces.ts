/**
 * Keeps the context-service's workspace root table in step with the host registry (3.6). The host
 * validates roots first (workspaceRoots.ts); the service re-checks them. Registration is idempotent and
 * retried lazily before any call that needs it, so a service restart or a late start heals itself.
 */
import type { WorkspaceService } from "../../context-client/workspaceServices.js";
import type { WorkspaceRegistry } from "./workspaceRegistry.js";

export class ServiceWorkspaces {
    private readonly registered = new Set<string>();

    constructor(
        private readonly registry: WorkspaceRegistry,
        private readonly service: WorkspaceService,
    ) {}

    /** Registers the workspace root with the service once per host process. */
    async ensure(workspaceId: string): Promise<void> {
        if (this.registered.has(workspaceId)) return;
        await this.service.register(workspaceId, this.registry.rootFor(workspaceId));
        this.registered.add(workspaceId);
    }

    /** Best effort: a failure here is retried by the next ensure(). */
    async tryEnsure(workspaceId: string): Promise<void> {
        await this.ensure(workspaceId).catch(() => undefined);
    }
}

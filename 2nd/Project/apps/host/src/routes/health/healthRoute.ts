/**
 * GET /api/v1/health (H-01). Before bootstrap only schema_version and status
 * are public; component details are added for authenticated sessions in 3.5.
 */
import type { HealthResponse, HealthStatus } from "@securecode/contracts";
import type { ContextServiceClient } from "../../context-client/ports.js";
import { sendJson } from "../responses.js";
import type { RouteHandler } from "../router.js";

const HEALTH_PROBE_TIMEOUT_MS = 2000;

export async function computeHostHealth(contextClient: ContextServiceClient): Promise<HealthStatus> {
    try {
        const serviceHealth = await contextClient.health(AbortSignal.timeout(HEALTH_PROBE_TIMEOUT_MS));
        return serviceHealth.status === "ok" ? "ok" : "degraded";
    } catch {
        return "degraded";
    }
}

export function createHealthRoute(contextClient: ContextServiceClient): RouteHandler {
    return async ({ response }) => {
        const body: HealthResponse = { schema_version: "1", status: await computeHostHealth(contextClient) };
        sendJson(response, 200, body);
    };
}

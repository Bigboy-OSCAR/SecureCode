/**
 * GET /api/v1/health (H-01). Before bootstrap only schema_version and status
 * are public; an authenticated browser also sees component states. Feature
 * components (symbols, pointers, selector, PDF) are the context-service's own report.
 */
import type { ComponentHealth, HealthResponse, HealthStatus, ServiceHealthResponse } from "@securecode/contracts";
import type { ContextServiceClient } from "../../context-client/ports.js";
import { sendJson } from "../responses.js";
import type { RouteHandler } from "../router.js";

const HEALTH_PROBE_TIMEOUT_MS = 2000;

export interface HealthDependencies {
    contextClient: ContextServiceClient;
    isAuthenticated: (cookieHeader: string | undefined) => boolean;
    providerConfigured: () => boolean;
}

async function probeService(contextClient: ContextServiceClient): Promise<ServiceHealthResponse | null> {
    try {
        return await contextClient.health(AbortSignal.timeout(HEALTH_PROBE_TIMEOUT_MS));
    } catch {
        return null;
    }
}

export async function computeHostHealth(contextClient: ContextServiceClient): Promise<HealthStatus> {
    const service = await probeService(contextClient);
    return service?.status === "ok" ? "ok" : "degraded";
}

function components(service: ServiceHealthResponse | null, providerConfigured: boolean): ComponentHealth[] {
    const fromService = (name: ComponentHealth["name"]): ComponentHealth =>
        service?.components.find((component) => component.name === name) ?? {
            name,
            status: "unavailable",
            reason_code: "SERVICE_UNAVAILABLE",
        };
    return [
        { name: "host", status: "ok" },
        service
            ? { name: "context_service", status: service.status === "ok" ? "ok" : "degraded" }
            : { name: "context_service", status: "unavailable", reason_code: "SERVICE_UNAVAILABLE" },
        { name: "cline_sdk", status: "ok" },
        providerConfigured
            ? { name: "model_provider", status: "ok" }
            : { name: "model_provider", status: "not_configured", reason_code: "PROVIDER_ERROR" },
        fromService("token_counter"),
        fromService("data_dir"),
        fromService("symbols"),
        fromService("pointers"),
        fromService("context_selector"),
        fromService("pdf"),
    ];
}

export function createHealthRoute(dependencies: HealthDependencies): RouteHandler {
    return async ({ request, response }) => {
        const service = await probeService(dependencies.contextClient);
        const status: HealthStatus = service?.status === "ok" ? "ok" : "degraded";
        const body: HealthResponse = dependencies.isAuthenticated(request.headers.cookie)
            ? { schema_version: "1", status, components: components(service, dependencies.providerConfigured()) }
            : { schema_version: "1", status };
        sendJson(response, 200, body);
    };
}

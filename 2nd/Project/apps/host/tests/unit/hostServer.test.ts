/**
 * The assembled host server answers health, rejects foreign origins and reports
 * contracted-but-missing routes as 501 NOT_IMPLEMENTED, all matching the contracts.
 */
import assert from "node:assert/strict";
import type { AddressInfo } from "node:net";
import { after, before, describe, it } from "node:test";
import { ContractValidator, SCHEMA_REFS, type ServiceHealthResponse } from "@securecode/contracts";
import { createHostServer } from "../../src/app/server.js";
import type { ContextServiceClient } from "../../src/context-client/ports.js";
import { createLogger } from "../../src/logging/logger.js";
import { Redactor } from "../../src/logging/redaction.js";
import { PENDING_ROUTES } from "../../src/routes/pendingRoutes.js";

const validator = ContractValidator.load();
let serviceStatus: ServiceHealthResponse["status"] | "down" = "ok";

const fakeClient = {
    health: () =>
        serviceStatus === "down"
            ? Promise.reject(new Error("down"))
            : Promise.resolve<ServiceHealthResponse>({
                  schema_version: "1",
                  service: "context-service",
                  status: serviceStatus,
                  version: "0.1.0",
                  components: [],
              }),
} as unknown as ContextServiceClient;

describe("host server", () => {
    let baseUrl = "";
    // Filled after listen(0) picks a port; the guard reads these same arrays.
    const originPolicy = { allowedOrigins: [] as string[], allowedHosts: [] as string[] };
    const server = createHostServer({
        contextClient: fakeClient,
        originPolicy,
        logger: createLogger("error", new Redactor(), () => undefined),
    });

    before(async () => {
        await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
        const port = (server.address() as AddressInfo).port;
        baseUrl = `http://127.0.0.1:${port}`;
        originPolicy.allowedOrigins.push(baseUrl);
        originPolicy.allowedHosts.push(`127.0.0.1:${port}`);
    });

    after(() => {
        server.close();
    });

    it("reports ok, then degraded when the context-service is down", async () => {
        serviceStatus = "ok";
        const okBody: unknown = await (await fetch(`${baseUrl}/api/v1/health`)).json();
        assert.deepEqual(okBody, { schema_version: "1", status: "ok" });
        assert.ok(validator.validate(SCHEMA_REFS.healthResponse, okBody).valid);

        serviceStatus = "down";
        const degraded: unknown = await (await fetch(`${baseUrl}/api/v1/health`)).json();
        assert.deepEqual(degraded, { schema_version: "1", status: "degraded" });
    });

    it("answers every pending route with a contract 501 that names the owner task", async () => {
        for (const route of PENDING_ROUTES) {
            const path = route.path.replace(/:[a-z_]+/g, "x");
            const response = await fetch(`${baseUrl}${path}`, { method: route.method, headers: { origin: baseUrl } });
            const body = (await response.json()) as { error: { code: string; details: { owner_task: string } } };
            assert.equal(response.status, 501, path);
            assert.ok(validator.validate(SCHEMA_REFS.errorResponse, body).valid, path);
            assert.equal(body.error.details.owner_task, route.ownerTask);
        }
    });

    it("rejects a foreign Origin with ORIGIN_REJECTED", async () => {
        const response = await fetch(`${baseUrl}/api/v1/sessions`, {
            method: "POST",
            headers: { origin: "http://attacker.example" },
        });
        const body = (await response.json()) as { error: { code: string } };
        assert.equal(response.status, 403);
        assert.equal(body.error.code, "ORIGIN_REJECTED");
    });

    it("returns NOT_FOUND for unknown paths", async () => {
        const response = await fetch(`${baseUrl}/api/v1/unknown`);
        assert.equal(response.status, 404);
        assert.ok(validator.validate(SCHEMA_REFS.errorResponse, await response.json()).valid);
    });
});

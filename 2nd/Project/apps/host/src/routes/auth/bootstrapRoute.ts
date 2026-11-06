/**
 * POST /api/v1/auth/bootstrap: exchanges the launcher's one-time code for an
 * HttpOnly, SameSite=Strict, Path=/api session cookie (roadmap 0.3).
 */
import { SCHEMA_REFS, type BootstrapRequest, type BootstrapResponse } from "@securecode/contracts";
import { isoTime } from "../../security/ids.js";
import { sessionCookie } from "../../security/browserAuth.js";
import type { RouteServices } from "../routeServices.js";
import { sendJson } from "../responses.js";
import type { RouteHandler } from "../router.js";
import { readContractBody } from "../shared/requestBody.js";
import { RouteFailure } from "../shared/routeFailure.js";

export function createBootstrapRoute(services: RouteServices): RouteHandler {
    return async ({ request, response }) => {
        const body = await readContractBody<BootstrapRequest>(
            request,
            services.validator,
            SCHEMA_REFS.bootstrapRequest,
            1024,
        );
        const outcome = services.auth.exchange(body.code);
        switch (outcome.kind) {
            case "invalid":
                throw new RouteFailure("BOOTSTRAP_CODE_INVALID", "the launch code is not valid");
            case "expired":
                throw new RouteFailure(
                    "BOOTSTRAP_CODE_EXPIRED",
                    "the launch code expired; restart SecureCode for a new one",
                );
            case "locked":
                throw new RouteFailure("RATE_LIMITED", "too many invalid launch codes; restart SecureCode");
            case "ok": {
                response.setHeader("set-cookie", sessionCookie(outcome.token, outcome.expiresAtMs, services.clock()));
                const result: BootstrapResponse = {
                    schema_version: "1",
                    authenticated: true,
                    session_expires_at: isoTime(outcome.expiresAtMs),
                };
                sendJson(response, 200, result);
            }
        }
    };
}

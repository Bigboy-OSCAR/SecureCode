/** The native launcher can renew authentication without restarting an active run. */
import { timingSafeEqual } from "node:crypto";
import type { RouteServices } from "../routeServices.js";
import type { RouteHandler } from "../router.js";
import { sendJson } from "../responses.js";
import { RouteFailure } from "../shared/routeFailure.js";

export function createLaunchCodeRoute(services: RouteServices): RouteHandler {
    return async ({ request, response }) => {
        const expected = services.launcherToken;
        const supplied = request.headers.authorization?.replace(/^Bearer /, "") ?? "";
        if (
            !expected ||
            Buffer.byteLength(supplied) !== Buffer.byteLength(expected) ||
            !timingSafeEqual(Buffer.from(supplied), Buffer.from(expected))
        ) {
            throw new RouteFailure("UNAUTHENTICATED", "only the local launcher can renew authentication");
        }
        response.setHeader("cache-control", "no-store");
        sendJson(response, 200, { code: services.auth.reissueCode() });
    };
}

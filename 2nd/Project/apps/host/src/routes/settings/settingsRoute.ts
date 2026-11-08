/** GET /api/v1/settings (H-10): read-only provider, budget, limits and protections without secrets or paths. */
import type { RouteServices } from "../routeServices.js";
import { sendJson } from "../responses.js";
import type { RouteHandler } from "../router.js";

export function createSettingsRoute(services: RouteServices): RouteHandler {
    return async ({ response }) => {
        sendJson(response, 200, services.settings());
    };
}

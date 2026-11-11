/**
 * Allowed-workspace policy for POST /workspaces. The root must be an existing
 * absolute directory, not a link/junction and not a filesystem root, and must
 * sit under SECURECODE_ALLOWED_WORKSPACE_ROOTS when that list is configured.
 * Errors never echo the submitted path.
 */
import { existsSync, lstatSync, realpathSync } from "node:fs";
import { isAbsolute, parse, relative, resolve, sep } from "node:path";
import { RouteFailure } from "../shared/routeFailure.js";

function reject(reason: string): RouteFailure {
    return new RouteFailure("FORBIDDEN", "허용되지 않은 경로입니다.", { reason });
}

function isInside(parent: string, child: string): boolean {
    const offset = relative(parent, child);
    return offset === "" || (!offset.startsWith("..") && !isAbsolute(offset) && !offset.split(sep).includes(".."));
}

export function resolveWorkspaceRoot(
    rootPath: string,
    allowedRoots: readonly string[],
    forbiddenRoots: readonly string[] = [],
): string {
    if (!isAbsolute(rootPath) || rootPath.includes("\u0000")) throw reject("root_not_absolute");
    const requested = resolve(rootPath);
    let info;
    try {
        info = lstatSync(requested);
    } catch {
        throw reject("root_not_found");
    }
    if (info.isSymbolicLink()) throw reject("root_is_link");
    if (!info.isDirectory()) throw reject("root_not_directory");
    const real = realpathSync(requested);
    if (parse(real).root === real) throw reject("root_is_filesystem_root");
    if (
        forbiddenRoots.some((path) => {
            const owned = existsSync(path) ? realpathSync(path) : resolve(path);
            return isInside(owned, real) || isInside(real, owned);
        })
    )
        throw reject("root_overlaps_service_data");
    if (allowedRoots.length > 0 && !allowedRoots.some((allowed) => isInside(realpathSync(allowed), real))) {
        throw reject("path_outside_allowed_roots");
    }
    return real;
}

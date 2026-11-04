/**
 * Small method + path router with `:param` segments. No framework: the host
 * only needs JSON routes and SSE, and 3.5 adds handlers here.
 */
import type { IncomingMessage, ServerResponse } from "node:http";

export interface RouteContext {
    request: IncomingMessage;
    response: ServerResponse;
    params: Readonly<Record<string, string>>;
    requestId: string;
}

export type RouteHandler = (context: RouteContext) => Promise<void>;

interface RouteEntry {
    method: string;
    segments: string[];
    handler: RouteHandler;
}

export type RouteMatch =
    | { kind: "found"; handler: RouteHandler; params: Record<string, string> }
    | { kind: "method_not_allowed" }
    | { kind: "not_found" };

function splitPath(path: string): string[] {
    return path.split("/").filter(Boolean);
}

function matchSegments(pattern: string[], actual: string[]): Record<string, string> | null {
    if (pattern.length !== actual.length) {
        return null;
    }
    const params: Record<string, string> = {};
    for (const [index, segment] of pattern.entries()) {
        const value = actual[index] ?? "";
        if (segment.startsWith(":")) {
            params[segment.slice(1)] = decodeURIComponent(value);
        } else if (segment !== value) {
            return null;
        }
    }
    return params;
}

export class Router {
    private readonly routes: RouteEntry[] = [];

    add(method: string, path: string, handler: RouteHandler): this {
        this.routes.push({ method: method.toUpperCase(), segments: splitPath(path), handler });
        return this;
    }

    match(method: string, path: string): RouteMatch {
        const actual = splitPath(path);
        let pathMatched = false;
        for (const route of this.routes) {
            const params = matchSegments(route.segments, actual);
            if (!params) {
                continue;
            }
            pathMatched = true;
            if (route.method === method.toUpperCase()) {
                return { kind: "found", handler: route.handler, params };
            }
        }
        return pathMatched ? { kind: "method_not_allowed" } : { kind: "not_found" };
    }

    list(): { method: string; path: string }[] {
        return this.routes.map((route) => ({ method: route.method, path: `/${route.segments.join("/")}` }));
    }
}

/** Polls one server's readiness URL until it answers as expected, its process exits, or time runs out. */
import { setTimeout as delay } from "node:timers/promises";
import type { LaunchedChild } from "./childProcess.js";

export interface ReadinessProbe {
    name: string;
    url: string;
    headers?: Record<string, string>;
    /** True when the response means "ready" (e.g. health status ok, or the UI index page). */
    ready(response: Response): Promise<boolean>;
}

export const jsonStatusOk = async (response: Response): Promise<boolean> => {
    if (!response.ok) return false;
    const body: unknown = await response.json();
    return Boolean(body && typeof body === "object" && "status" in body && body.status === "ok");
};

export async function waitReady(
    probe: ReadinessProbe,
    child: LaunchedChild,
    timeoutMs: number,
    signal?: AbortSignal,
): Promise<void> {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        signal?.throwIfAborted();
        if (child.exited()) throw new Error(`${probe.name} exited during startup (see its output above)`);
        try {
            const response = await fetch(probe.url, {
                headers: probe.headers,
                signal: AbortSignal.timeout(1000),
                redirect: "error",
            });
            if (await probe.ready(response)) return;
        } catch {
            /* Not listening yet: retried until the deadline. */
        }
        await delay(100);
    }
    throw new Error(`${probe.name} did not become ready within ${Math.round(timeoutMs / 1000)} seconds`);
}

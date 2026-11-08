/**
 * GET /api/v1/runs/:run_id/events (EVENTS.md 4/5). Replays retained events
 * after Last-Event-ID, then streams live ones; a gap sends one
 * stream.replay_unavailable (no id line) and ends the stream so the client
 * reloads the snapshot. A closed connection never cancels the run.
 */
import type { ServerResponse } from "node:http";
import type { AppEvent } from "@securecode/contracts";
import type { RouteServices } from "../routeServices.js";
import type { RouteHandler, Router } from "../router.js";
import { RouteFailure } from "../shared/routeFailure.js";

function readLastEventId(header: string | string[] | undefined): number {
    const value = Array.isArray(header) ? header[0] : header;
    if (value === undefined || value === "") return 0;
    if (!/^\d{1,15}$/.test(value)) {
        throw new RouteFailure("VALIDATION_FAILED", "Last-Event-ID must be a sequence number", {
            reason: "last_event_id",
        });
    }
    return Number(value);
}

function writeEvent(response: ServerResponse, event: AppEvent, withId: boolean): void {
    const idLine = withId ? `id: ${event.sequence}\n` : "";
    response.write(`${idLine}event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`);
}

export function registerRunEventsRoute(router: Router, services: RouteServices): void {
    const stream: RouteHandler = async ({ request, response, params }) => {
        const log = services.runs.eventLog(params.run_id ?? "");
        const after = readLastEventId(request.headers["last-event-id"]);
        response.writeHead(200, {
            "content-type": "text/event-stream; charset=utf-8",
            "cache-control": "no-store",
            connection: "keep-alive",
            "x-content-type-options": "nosniff",
            "x-accel-buffering": "no",
        });
        let delivered = after;
        let ended = false;
        let unsubscribe = (): void => undefined;
        let keepAlive: NodeJS.Timeout | undefined;
        const end = (): void => {
            if (ended) return;
            ended = true;
            clearInterval(keepAlive);
            unsubscribe();
            response.end();
        };
        const deliver = (event: AppEvent): void => {
            if (event.sequence > delivered) {
                delivered = event.sequence;
                writeEvent(response, event, true);
            }
        };
        if (!log.closed) {
            // Subscribe before replaying so nothing appended in between is lost; sequence dedupes.
            unsubscribe = log.subscribe((event) => (event === null ? end() : deliver(event)));
            keepAlive = setInterval(() => response.write(": keep-alive\n\n"), services.sseKeepAliveMs);
            request.once("close", end);
        }
        const replay = log.replayAfter(after);
        if (replay.kind === "gap") {
            writeEvent(response, log.replayUnavailable(after, replay.oldest), false);
            end();
            return;
        }
        for (const event of replay.events) deliver(event);
        if (log.closed) end();
    };
    router.add("GET", "/api/v1/runs/:run_id/events", stream);
}

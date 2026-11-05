/**
 * Owns one ClineCore + scripted provider + fixture workspace for a scenario and
 * always disposes the core, so scenarios only describe turns and checks.
 */
import type { ClineCore, CoreSessionEvent } from "@cline/sdk";
import type { ScriptedTurn } from "../fixtures/anthropic-sse.js";
import { type OutboundGate, ScriptedProviderFetch } from "../fixtures/scripted-fetch.js";
import { createFixtureWorkspace } from "../support/fixture-workspace.js";
import { type ApprovalHandler, createProbeCore, type ProbeToolExecutors } from "./core-factory.js";

export interface ProbeRun {
    core: ClineCore;
    scriptedFetch: ScriptedProviderFetch;
    workspaceDir: string;
    coreEvents: CoreSessionEvent[];
}

export interface ProbeRunOptions {
    name: string;
    turns: ScriptedTurn[];
    outboundGate?: OutboundGate;
    requestToolApproval?: ApprovalHandler;
    toolExecutors?: ProbeToolExecutors;
}

export async function withProbeRun(options: ProbeRunOptions, body: (run: ProbeRun) => Promise<void>): Promise<void> {
    const scriptedFetch = new ScriptedProviderFetch(options.turns, options.outboundGate);
    const core = await createProbeCore({
        fetch: scriptedFetch.fetch,
        ...(options.requestToolApproval ? { requestToolApproval: options.requestToolApproval } : {}),
        ...(options.toolExecutors ? { toolExecutors: options.toolExecutors } : {}),
    });
    const coreEvents: CoreSessionEvent[] = [];
    const unsubscribe = core.subscribe((event) => coreEvents.push(event));

    try {
        await body({ core, scriptedFetch, workspaceDir: createFixtureWorkspace(options.name), coreEvents });
    } finally {
        unsubscribe();
        await core.dispose(`probe ${options.name} finished`);
    }
}

export function errorMessage(error: unknown): string {
    return error instanceof Error ? error.message : String(error);
}

/** Rejects when `work` does not settle in time, so a hung SDK call cannot stall the probe. */
export function settleWithin<T>(work: Promise<T>, timeoutMs: number, label: string): Promise<T> {
    return new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error(`${label} did not settle within ${timeoutMs}ms`)), timeoutMs);
        work.then(
            (value) => {
                clearTimeout(timer);
                resolve(value);
            },
            (error: unknown) => {
                clearTimeout(timer);
                reject(error instanceof Error ? error : new Error(String(error)));
            },
        );
    });
}

/** Stop waiting when the run ends early or never reaches the expected SDK event. */
export async function waitForProbeEvent(
    predicate: () => boolean,
    started: Promise<unknown>,
    label: string,
    timeoutMs = 10000,
): Promise<void> {
    let finished = false;
    const onFinish = (): void => {
        finished = true;
    };
    void started.then(onFinish, onFinish);
    const deadline = Date.now() + timeoutMs;
    while (!predicate()) {
        if (finished || Date.now() >= deadline) {
            throw new Error(`SDK did not reach ${label}`);
        }
        await new Promise<void>((resolve) => setTimeout(resolve, 20));
    }
}

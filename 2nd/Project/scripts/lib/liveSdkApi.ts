/** Browser-like API client and run helpers for the live SDK smoke (scripts/lib/liveSdkSmoke.ts). */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

export interface Api {
    send(method: string, path: string, body?: unknown): Promise<{ status: number; body: Record<string, unknown> }>;
}

export async function login(hostUrl: string, code: string): Promise<Api> {
    const headers = { origin: hostUrl, "content-type": "application/json" };
    const response = await fetch(`${hostUrl}/api/v1/auth/bootstrap`, {
        method: "POST",
        headers,
        body: JSON.stringify({ code }),
    });
    const cookie = (response.headers.get("set-cookie") ?? "").split(";", 1)[0] ?? "";
    return {
        async send(method, path, body) {
            const reply = await fetch(hostUrl + path, {
                method,
                headers: { ...headers, cookie },
                ...(body === undefined ? {} : { body: JSON.stringify(body) }),
            });
            const text = await reply.text();
            return { status: reply.status, body: (text ? JSON.parse(text) : {}) as Record<string, unknown> };
        },
    };
}

export async function until<T>(read: () => Promise<T>, done: (value: T) => boolean, seconds: number): Promise<T> {
    let value = await read();
    const deadline = Date.now() + seconds * 1000;
    while (!done(value) && Date.now() < deadline) {
        await new Promise((resolve) => setTimeout(resolve, 500));
        value = await read();
    }
    return value;
}

export type Run = Record<string, unknown> & {
    status: string;
    answer: { text: string };
    tool_calls: { tool_name: string; output_pointer?: string; phase?: string; summary?: string }[];
    pending_approvals: { approval_id: string; input_digest: string }[];
    terminal: { reason_code?: string } | null;
};

/** Runs one prompt; approves (or rejects) every approval request until the run ends. */
export async function run(api: Api, sessionId: string, prompt: string, key: string, approve = true): Promise<Run> {
    const created = await api.send("POST", `/api/v1/sessions/${sessionId}/runs`, { prompt, idempotency_key: key });
    if (created.status !== 201)
        return {
            status: "refused",
            answer: { text: JSON.stringify(created.body) },
            tool_calls: [],
            pending_approvals: [],
            terminal: null,
        };
    const runId = created.body.run_id as string;
    for (;;) {
        const snapshot = await until<Run>(
            async () => (await api.send("GET", `/api/v1/runs/${runId}`)).body as Run,
            (s) => s.terminal !== null || s.pending_approvals.length > 0,
            300,
        );
        if (snapshot.terminal) return snapshot;
        const approval = snapshot.pending_approvals[0];
        if (!approval) {
            // Still generating after the time limit (slow local model): cancel so later steps can run.
            await api.send("POST", `/api/v1/runs/${runId}/cancel`);
            const ended = await until<Run>(
                async () => (await api.send("GET", `/api/v1/runs/${runId}`)).body as Run,
                (s) => s.terminal !== null,
                120,
            );
            return { ...ended, status: `timed out (${ended.status})` };
        }
        await api.send("POST", `/api/v1/runs/${runId}/approvals/${approval.approval_id}`, {
            decision: approve ? "approve" : "reject",
            input_digest: approval.input_digest,
        });
    }
}

/** Model-dependent step: up to two attempts (a 7B local model is not deterministic); both are reported. */
export async function twice(
    attempt: (index: number) => Promise<Run>,
    ok: (run: Run) => boolean,
): Promise<[Run, string]> {
    const first = await attempt(1);
    if (ok(first)) return [first, "attempt 1/2"];
    const second = await attempt(2);
    return [
        second,
        `attempt 2/2 (first: ${first.status}, tools=${first.tool_calls.map((c) => c.tool_name).join(",")})`,
    ];
}

export function scan(dir: string): string {
    let text = "";
    const walk = (path: string): void => {
        for (const name of readdirSync(path)) {
            const full = join(path, name);
            if (statSync(full).isDirectory()) walk(full);
            else if (statSync(full).size < 50 * 1024 * 1024) text += readFileSync(full).toString("latin1");
        }
    };
    walk(dir);
    return text;
}

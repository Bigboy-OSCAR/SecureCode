/** Captures real SDK requests and counts a raw-input counterfactual with the same local tokenizer. */
import { execFileSync } from "node:child_process";
import { createServer, request } from "node:http";
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { liveSdkSmokeSteps } from "../lib/liveSdkSmoke.js";
import { liveLlamaCppSteps } from "../lib/liveLlamaCpp.js";
import { WORK_ROOT, SERVICE_DIR } from "../lib/processes.js";

const envFile = join(WORK_ROOT, ".env");
if (existsSync(envFile)) process.loadEnvFile(envFile);
if (process.env.SECURECODE_LIVE_SMOKE !== "1") throw new Error("Set SECURECODE_LIVE_SMOKE=1 explicitly.");
if (process.env.SECURECODE_TOKEN_COUNTER !== "llama-cpp") throw new Error("This measurement uses llama.cpp.");
const upstream = new URL(process.env.SECURECODE_PROVIDER_BASE_URL ?? "http://127.0.0.1:8080/v1");
const captured: Record<string, unknown>[] = [];
let sourceText = "";
let logText = "";
let pdfText = "";

function captureFixture(root: string): void {
    const files = readdirSync(root, { recursive: true, withFileTypes: true });
    sourceText = files
        .filter((file) => file.isFile() && /\.(py|js)$/.test(file.name))
        .map((file) => `File: ${file.name}\n${readFileSync(join(file.parentPath, file.name), "utf8")}`)
        .join("\n");
    logText = execFileSync(process.execPath, [join(root, "gen.js")], { encoding: "utf8", maxBuffer: 4 * 1024 * 1024 });
    pdfText = execFileSync(
        join(SERVICE_DIR, ".venv/bin/python"),
        [
            "-c",
            "from pypdf import PdfReader; import sys; print('\\n'.join(p.extract_text() for p in PdfReader(sys.argv[1]).pages))",
            join(root, "manual.pdf"),
        ],
        { encoding: "utf8" },
    );
}

const proxy = createServer((incoming, outgoing) => {
    const chunks: Buffer[] = [];
    incoming.on("data", (chunk: Buffer) => chunks.push(chunk));
    incoming.on("end", () => {
        const body = Buffer.concat(chunks);
        if (incoming.url?.endsWith("/chat/completions"))
            captured.push(JSON.parse(body.toString()) as Record<string, unknown>);
        const forward = request(
            {
                hostname: upstream.hostname,
                port: upstream.port,
                path: incoming.url,
                method: incoming.method,
                headers: { ...incoming.headers, host: upstream.host },
            },
            (response) => {
                outgoing.writeHead(response.statusCode ?? 502, response.headers);
                response.pipe(outgoing);
            },
        );
        forward.on("error", () => outgoing.writeHead(502).end());
        outgoing.on("close", () => forward.destroy());
        forward.end(body);
    });
});
await new Promise<void>((done) => proxy.listen(0, "127.0.0.1", done));
const address = proxy.address();
if (!address || typeof address === "string") throw new Error("Proxy did not start.");
process.env.SECURECODE_PROVIDER_BASE_URL = `http://127.0.0.1:${address.port}/v1`;
// Use the configured endpoint; profile switching would deliberately bypass the capture proxy.
process.env.SECURECODE_LOCAL_MODELS = "0";

async function tokens(body: Record<string, unknown>): Promise<number> {
    const input = Object.fromEntries(
        ["messages", "tools", "tool_choice", "parallel_tool_calls"]
            .filter((key) => key in body)
            .map((key) => [key, body[key]]),
    );
    const headers: Record<string, string> = { "content-type": "application/json" };
    const key = process.env.SECURECODE_PROVIDER_API_KEY;
    if (key) headers.authorization = `Bearer ${key}`;
    const endpoint = upstream.origin;
    const rendered = await fetch(endpoint + "/apply-template", {
        method: "POST",
        headers,
        body: JSON.stringify(input),
    });
    if (!rendered.ok) throw new Error(`Template HTTP ${rendered.status}`);
    const prompt = ((await rendered.json()) as { prompt: string }).prompt;
    const response = await fetch(endpoint + "/tokenize", {
        method: "POST",
        headers,
        body: JSON.stringify({ content: prompt, add_special: true, parse_special: true }),
    });
    if (!response.ok) throw new Error(`Tokenize HTTP ${response.status}`);
    return ((await response.json()) as { tokens: number[] }).tokens.length;
}

function rawBaseline(body: Record<string, unknown>): Record<string, unknown> {
    const baseline = structuredClone(body);
    const messages = baseline.messages as { role: string; content: unknown }[];
    let replacedSource = false;
    for (const message of messages) {
        if (typeof message.content !== "string") continue;
        let content = message.content;
        if (!replacedSource && content.includes("<securecode-context")) {
            content =
                content.replace(/<securecode-context\b[^>]*>[\s\S]*?<\/securecode-context>/g, "") + "\n" + sourceText;
            replacedSource = true;
        }
        if (message.role === "tool" && /stored_bytes/.test(content) && /securecode:\/\/runtime\//.test(content)) {
            content = logText;
        } else if (message.role === "tool" && content.includes("PAGE-TWO-SENTINEL")) {
            content = pdfText;
        }
        message.content = content;
    }
    return baseline;
}

try {
    const counterChecks = await liveLlamaCppSteps();
    captured.length = 0;
    const liveChecks = await liveSdkSmokeSteps(captureFixture);
    const rows: {
        request: number;
        protected_tokens: number;
        raw_baseline_tokens: number;
        protected_request_bytes: number;
        raw_baseline_request_bytes: number;
    }[] = [];
    for (const [index, body] of captured.entries()) {
        const raw = rawBaseline(body);
        rows.push({
            request: index + 1,
            protected_tokens: await tokens(body),
            raw_baseline_tokens: await tokens(raw),
            protected_request_bytes: Buffer.byteLength(JSON.stringify(body)),
            raw_baseline_request_bytes: Buffer.byteLength(JSON.stringify(raw)),
        });
    }
    const sum = (key: "protected_tokens" | "raw_baseline_tokens") => rows.reduce((total, row) => total + row[key], 0);
    const report = {
        created_at: new Date().toISOString(),
        model: process.env.SECURECODE_MODEL_ID,
        method: "Real SDK/provider requests. Count-only counterfactual preserves each request's tools/history; selected R0 context is replaced by all source fixture files, stored runtime descriptors by their original log, and PDF page 2 by all pages. No raw baseline inference is sent. Request count is held constant; no accuracy or speed claim.",
        counter_checks: counterChecks,
        live_checks: liveChecks,
        fixture_bytes: {
            source: Buffer.byteLength(sourceText),
            log: Buffer.byteLength(logText),
            pdf_text: Buffer.byteLength(pdfText),
        },
        requests: rows,
        request_count: rows.length,
        protected_max_input_tokens: Math.max(0, ...rows.map((row) => row.protected_tokens)),
        raw_max_input_tokens: Math.max(0, ...rows.map((row) => row.raw_baseline_tokens)),
        protected_cumulative_input_tokens: sum("protected_tokens"),
        raw_cumulative_input_tokens: sum("raw_baseline_tokens"),
    };
    const directory = join(WORK_ROOT, "artifacts/verification/localdesk-mac");
    mkdirSync(directory, { recursive: true });
    writeFileSync(join(directory, "context-measurement.json"), JSON.stringify(report, null, 4) + "\n");
    console.log(JSON.stringify(report, null, 2));
    if ([...counterChecks, ...liveChecks].some((step) => step.status !== "PASS") || !rows.length) process.exitCode = 1;
} finally {
    proxy.closeAllConnections();
    await new Promise<void>((done) => proxy.close(() => done()));
}

/** Read-only evidence from one desktop test workspace. Never opens credentials or unrelated transcripts. */
import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";
import { ALLOWED_TOOL_NAMES } from "../../apps/host/src/cline/tools/sessionTools.js";

type RecordValue = Record<string, unknown>;
const args = process.argv.slice(2);
const rootArg = args.shift();
if (!rootArg) {
    throw new Error(
        "Usage: collectDesktopTools.ts WORKSPACE_ROOT [--data-dir PATH] [--needle TEXT] [--forbidden-text TEXT]",
    );
}
const root = resolve(rootArg);
let dataDir = join(homedir(), "Library", "Application Support", "LocalDesk");
const needles: string[] = [];
const forbidden: string[] = [];
while (args.length > 0) {
    const flag = args.shift();
    const value = args.shift();
    if (!value) throw new Error(`Missing value for ${flag ?? "argument"}`);
    if (flag === "--data-dir") dataDir = resolve(value);
    else if (flag === "--needle") needles.push(value);
    else if (flag === "--forbidden-text") forbidden.push(value);
    else throw new Error(`Unknown option ${flag}`);
}

function record(value: unknown): RecordValue {
    return value !== null && typeof value === "object" && !Array.isArray(value) ? (value as RecordValue) : {};
}

function array(value: unknown): unknown[] {
    return Array.isArray(value) ? value : [];
}

function readJson(path: string): RecordValue {
    return record(JSON.parse(readFileSync(path, "utf8")) as unknown);
}

function records(directory: string): RecordValue[] {
    if (!existsSync(directory)) return [];
    return readdirSync(directory)
        .filter((name) => name.endsWith(".json"))
        .map((name) => readJson(join(directory, name)));
}

function matches(text: string, values: readonly string[]): Record<string, number> {
    return Object.fromEntries(values.map((value) => [value, text.split(value).length - 1]));
}

function textSummary(text: string): RecordValue {
    return {
        bytes: Buffer.byteLength(text),
        sha256: createHash("sha256").update(text).digest("hex"),
        target_matches: matches(text, needles),
        forbidden_matches: matches(text, forbidden),
    };
}

function contentText(content: unknown): string {
    if (typeof content === "string") return content;
    return array(content)
        .map((block) => record(block).text)
        .filter((text): text is string => typeof text === "string")
        .join("\n");
}

/** A literal in a user's question is not leaked file/log evidence. Retain injected context and tool output. */
function evidenceText(messages: RecordValue[]): string {
    return messages
        .flatMap((message) =>
            array(message.content).map((value) => {
                const block = record(value);
                if (block.type === "tool_result") return contentText(block.content);
                const text = typeof block.text === "string" ? block.text : "";
                if (message.role !== "user") return text;
                return [...text.matchAll(/<securecode-context\b[^>]*>([\s\S]*?)<\/securecode-context>/g)]
                    .map((match) => match[1] ?? "")
                    .join("\n");
            }),
        )
        .join("\n");
}

/** Keep exact source ranges and counts while omitting original source/log/PDF text. */
function resultMetadata(text: string): RecordValue {
    let value: RecordValue;
    try {
        value = record(JSON.parse(text) as unknown);
    } catch {
        return {};
    }
    const keys = [
        "path",
        "pointer",
        "range",
        "truncated",
        "next_cursor",
        "page",
        "job_id",
        "state",
        "page_count",
        "stored_bytes",
        "total_bytes",
        "exit_code",
    ];
    return {
        ...Object.fromEntries(keys.filter((key) => key in value).map((key) => [key, value[key]])),
        ...(typeof value.content === "string" ? { content: textSummary(value.content) } : {}),
        ...(Array.isArray(value.matches) ? { match_count: value.matches.length } : {}),
        ...(Array.isArray(value.candidates) ? { candidate_count: value.candidates.length } : {}),
        ...(Array.isArray(value.fragments)
            ? {
                  fragments: value.fragments.map((fragment) => {
                      const item = record(fragment);
                      return { path: item.path, lines: item.lines, content: textSummary(contentText(item.content)) };
                  }),
              }
            : {}),
    };
}

const workspace = records(join(dataDir, "host", "workspaces")).find((item) => item.root === root && !item.removed_at);
if (!workspace) throw new Error(`No active desktop workspace registered for ${root}`);
const runs = records(join(dataDir, "host", "runs"))
    .filter((item) => item.workspace_id === workspace.workspace_id)
    .sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)));
const sessions = records(join(dataDir, "host", "sessions")).filter(
    (item) => item.workspace_id === workspace.workspace_id,
);
const transcripts = sessions.map((session) => {
    const id = String(session.session_id);
    if (!/^ses_[A-Za-z0-9-]+$/.test(id)) throw new Error("Invalid persisted session identifier");
    const path = join(dataDir, "cline", "data", "sessions", id, `${id}.messages.json`);
    if (!existsSync(path)) return { session_id: id, present: false, tools: [] };
    const raw = readFileSync(path, "utf8");
    const messages = array(record(JSON.parse(raw) as unknown).messages).map(record);
    const evidence = evidenceText(messages);
    const blocks = messages.flatMap((message) => array(message.content).map(record));
    const tools = blocks
        .filter((block) => block.type === "tool_result")
        .map((block) => {
            const call = blocks.find(
                (candidate) => candidate.type === "tool_use" && candidate.id === block.tool_use_id,
            );
            const input = record(call?.input);
            const content = contentText(block.content);
            return {
                tool_use_id: block.tool_use_id,
                name: block.name ?? call?.name,
                is_error: block.is_error,
                input: {
                    ...input,
                    ...(typeof input.content === "string" ? { content: textSummary(input.content) } : {}),
                },
                result: textSummary(content),
                metadata: resultMetadata(content),
                ...(block.is_error === true ? { error: content.slice(0, 500) } : {}),
            };
        });
    return {
        session_id: id,
        present: true,
        message_count: messages.length,
        transcript_bytes: Buffer.byteLength(raw),
        leakage_scan_scope: "Tool results, inserted context and assistant text; excludes literal user questions.",
        forbidden_matches: matches(evidence, forbidden),
        bulk_log_sentinels: (evidence.match(/(?:BULK-LOG|BULK-PRIVATE-SENTINEL)-\d{3,}-/g) ?? []).length,
        unrelated_source_sentinels: (evidence.match(/UNRELATED-SENTINEL-\d+/g) ?? []).length,
        tools,
    };
});
const calls = runs.flatMap((run) => array(run.tool_calls).map(record));
const results = transcripts.flatMap((transcript) => transcript.tools);
const report = {
    captured_at: new Date().toISOString(),
    method: "Read-only persisted evidence for this workspace only; does not initiate or approve tools. Coverage is evidence, not an automatic correctness verdict.",
    workspace,
    selected_model: readJson(join(dataDir, "host", "model-selection.json")).model_id,
    coverage: [...ALLOWED_TOOL_NAMES].sort().map((name) => {
        const matching = calls.filter((call) => call.tool_name === name);
        const returned = results.filter((result) => result.name === name);
        return {
            tool: name,
            completed: matching.filter((call) => call.phase === "completed").length,
            other_phases: matching.filter((call) => call.phase !== "completed").map((call) => call.phase),
            sdk_success_results: returned.filter((result) => result.is_error === false).length,
            sdk_error_results: returned.filter((result) => result.is_error === true).length,
        };
    }),
    runs: runs.map((run) => ({
        run_id: run.run_id,
        session_id: run.session_id,
        created_at: run.created_at,
        updated_at: run.updated_at,
        status: run.status,
        prompt_preview_bytes: Buffer.byteLength(contentText(run.prompt_preview)),
        answer: textSummary(contentText(run.answer_text)),
        tool_calls: run.tool_calls,
        citations: run.citations,
        pending_approvals: array(run.pending_approvals).map((approval) => {
            const item = record(approval);
            return { approval_id: item.approval_id, tool_call_id: item.tool_call_id, expires_at: item.expires_at };
        }),
        approval_history: array(run.approval_history).map((approval) => {
            const item = record(approval);
            return { approval_id: item.approval_id, tool_call_id: item.tool_call_id, status: item.status };
        }),
        terminal: run.terminal,
    })),
    transcripts,
};
console.log(JSON.stringify(report, null, 2));

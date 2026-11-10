/**
 * Live SDK smoke against the configured provider (opt-in, `npm run test:live`, 3.6). Starts the real host
 * and context-service from .env, then drives the public API like the UI: workspace → R0 index → PDF
 * Source + parse → runs that need R0 evidence, an approved command whose log becomes a Runtime Pointer
 * and is re-read partially, a PDF page read, a cancel, and an explicit choice refused before any model
 * call. Model behaviour is reported per step (PASS/FAIL); nothing here is a fixture.
 */
import { copyFileSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { login, run, scan, twice, until, type Run } from "./liveSdkApi.js";
import { WORK_ROOT } from "./processes.js";
import type { StepResult } from "./report.js";
import { findFreePorts, startServices } from "./services.js";

const GEN = `const l=[];for(let i=1;i<=20000;i++)l.push(i===13579?"LOG-TARGET total=42":"BULK-LOG-"+i+"-"+"z".repeat(30));process.stdout.write(l.join("\\n")+"\\n");`;
const SLOW = "setTimeout(() => console.log('done'), 60000);";

function project(root: string): void {
    mkdirSync(join(root, "noise"));
    for (let i = 0; i < 50; i += 1)
        writeFileSync(join(root, "noise", `m${i}.py`), `def helper_${i}():\n    return "UNRELATED-SENTINEL-${i}"\n`);
    writeFileSync(
        join(root, "billing.py"),
        'def compute_invoice_total(items, tax_rate):\n    """Sum line totals, then add tax."""\n' +
            "    subtotal = sum(item.price * item.quantity for item in items)\n    return round(subtotal * (1 + tax_rate), 2)\n",
    );
    writeFileSync(join(root, "gen.js"), GEN);
    writeFileSync(join(root, "slow.js"), SLOW);
    copyFileSync(join(WORK_ROOT, "tests", "fixtures", "pdf", "korean-3-pages.pdf"), join(root, "manual.pdf"));
}

export async function liveSdkSmokeSteps(): Promise<StepResult[]> {
    if (process.env.SECURECODE_LIVE_SMOKE !== "1") return [];
    const results: StepResult[] = [];
    const step = (name: string, passed: boolean, detail: string): void => {
        results.push({ name: `live sdk: ${name}`, status: passed ? "PASS" : "FAIL", detail: detail.slice(0, 900) });
    };
    const dataDir = mkdtempSync(join(tmpdir(), "securecode-live-sdk-"));
    const root = mkdtempSync(join(tmpdir(), "securecode-live-ws-"));
    project(root);
    const services = await startServices({ ...(await findFreePorts()), dataDir });
    try {
        const api = await login(services.hostUrl, services.bootstrapCode);
        const ws = (
            await api.send("POST", "/api/v1/workspaces", {
                display_name: "live",
                root_path: root,
                idempotency_key: "live-ws-0001",
            })
        ).body.workspace_id as string;
        await api.send("POST", `/api/v1/workspaces/${ws}/index`, { idempotency_key: "live-index-01" });
        const index = await until(
            async () => (await api.send("GET", `/api/v1/workspaces/${ws}/index`)).body,
            (b) => ["ready", "partial"].includes(String(b.index_status)),
            120,
        );
        step(
            "R0 index ready",
            ["ready", "partial"].includes(String(index.index_status)),
            JSON.stringify(index.counts ?? index),
        );
        const source = await api.send("POST", `/api/v1/workspaces/${ws}/sources`, {
            schema_version: "1",
            idempotency_key: "live-pdf-0001",
            operation: "register",
            target: { location: "workspace", kind: "file", path: "manual.pdf" },
        });
        const pdf = ((source.body.items as { pointer: string }[] | undefined) ?? [])[0]?.pointer ?? "";
        const parsed = await api.send("POST", "/api/v1/pdf/parse", {
            schema_version: "1",
            workspace_id: ws,
            pointer: pdf,
            idempotency_key: "live-parse-01",
        });
        const job = await until(
            async () => (await api.send("GET", `/api/v1/pdf/jobs/${String(parsed.body.job_id)}`)).body,
            (b) => !["queued", "running"].includes(String(b.state)),
            60,
        );
        step("PDF parsed (metadata only)", job.state === "ready", JSON.stringify(job));
        const session = (
            await api.send("POST", "/api/v1/sessions", { workspace_id: ws, idempotency_key: "live-ses-0001" })
        ).body.session_id as string;

        const question =
            "billing.py의 compute_invoice_total 함수가 무엇을 계산하는지 설명하고 근거 파일을 밝혀 주세요.";
        const plan = await api.send("POST", "/api/v1/context/preview", {
            operation: "plan",
            input: {
                workspace_id: ws,
                session_id: session,
                index_revision: Number(index.index_revision ?? 1),
                prompt: question,
                context_refs: [],
            },
        });
        const planText = JSON.stringify(plan.body);
        step(
            "context.select puts R0 evidence in the plan",
            planText.includes("compute_invoice_total") && !planText.includes("UNRELATED-SENTINEL"),
            planText.slice(0, 200),
        );
        const r0Ok = (r: Run) =>
            r.status === "completed" && /billing\.py|compute_invoice_total/.test(r.answer?.text ?? "");
        const [r0, r0Tries] = await twice((i) => run(api, session, question, `live-run-r0-0${i}`), r0Ok);
        step("answer from R0 evidence", r0Ok(r0), `${r0Tries} ${r0.status}: ${r0.answer?.text ?? ""}`);

        const logOk = (r: Run) =>
            r.tool_calls.some((c) => c.tool_name === "run_command" && c.output_pointer) &&
            r.tool_calls.some((c) => c.tool_name === "runtime_search" || c.tool_name === "runtime_read") &&
            /42/.test(r.answer?.text ?? "");
        const [log, logTries] = await twice(
            (i) =>
                run(
                    api,
                    session,
                    "`node gen.js` 명령을 run_command로 실행한 뒤, 출력 포인터에서 runtime_search로 LOG-TARGET 줄을 찾아 total 값을 알려 주세요.",
                    `live-run-log-0${i}`,
                ),
            logOk,
        );
        const names = log.tool_calls.map((call) => call.tool_name);
        step(
            "approved command stored as a Runtime Pointer",
            log.tool_calls.some((call) => call.tool_name === "run_command" && call.output_pointer),
            `${logTries} ${log.status} tools=${names.join(",")}`,
        );
        step(
            "partial re-read of the stored log",
            logOk(log),
            `${logTries} ${names.join(",")}: ${log.answer?.text ?? ""}`,
        );

        const pageOk = (r: Run) =>
            r.tool_calls.some((c) => c.tool_name === "pdf_read_pages") &&
            /PAGE-TWO-SENTINEL/.test(r.answer?.text ?? "") &&
            !/PAGE-(ONE|THREE)-SENTINEL/.test(r.answer?.text ?? "");
        const [page, pageTries] = await twice(
            (i) =>
                run(
                    api,
                    session,
                    `PDF 포인터 ${pdf} 의 2페이지만 pdf_read_pages로 읽고, 그 페이지의 SENTINEL 문자열과 페이지 번호를 인용해 주세요.`,
                    `live-run-pdf-0${i}`,
                ),
            pageOk,
        );
        step(
            "PDF page read and cited",
            pageOk(page),
            `${pageTries} ${page.tool_calls.map((c) => `${c.tool_name}:${c.phase ?? ""}`).join(" | ")} => ${(page.answer?.text ?? "").slice(-200)}`,
        );

        const slow = await api.send("POST", `/api/v1/sessions/${session}/runs`, {
            prompt: "`node slow.js` 를 run_command로 실행해 주세요.",
            idempotency_key: "live-run-cancel",
        });
        const slowId = String(slow.body.run_id);
        // Cancel at once: the outcome must not depend on whether the model chose to call a tool.
        await api.send("POST", `/api/v1/runs/${slowId}/cancel`);
        const cancelled = await until(
            async () => (await api.send("GET", `/api/v1/runs/${slowId}`)).body as Run,
            (s) => s.terminal !== null,
            120,
        );
        step("cancel stops the run", cancelled.status === "cancelled", JSON.stringify(cancelled.terminal));

        const refused = await api.send("POST", `/api/v1/sessions/${session}/runs`, {
            prompt: "이 범위를 설명해 주세요",
            idempotency_key: "live-run-refused",
            context_refs: [
                {
                    kind: "source",
                    pointer: pdf,
                    selection: {
                        revision: 1,
                        content_sha256: "0".repeat(64),
                        range: { type: "byte", start: 0, end: 10 },
                    },
                },
            ],
        });
        const code = (refused.body.error as { code?: string } | undefined)?.code ?? "";
        step(
            "unusable explicit choice refused before the model",
            refused.status >= 400 && code !== "",
            `${refused.status} ${code}`,
        );

        const transcript = scan(join(dataDir, "cline"));
        const leak = /BULK-LOG-\d{3,}-|UNRELATED-SENTINEL-\d+/.exec(transcript);
        step(
            "canonical transcript holds no bulk log or unrelated files",
            leak === null,
            leak
                ? `found ${leak[0]} near: ${transcript.slice(Math.max(0, leak.index - 160), leak.index).replace(/\s+/g, " ")}`
                : `${transcript.length} bytes scanned`,
        );
    } catch (error) {
        step("smoke aborted", false, error instanceof Error ? error.message : String(error));
    } finally {
        await services.stopAll();
        if (results.some((result) => result.status === "FAIL")) {
            // Kept for diagnosis (SDK transcript holds the tool errors); never contains provider keys.
            results.push({ name: "live sdk: data kept for diagnosis", status: "PASS", detail: dataDir });
        } else {
            rmSync(dataDir, { recursive: true, force: true });
        }
        rmSync(root, { recursive: true, force: true });
    }
    return results;
}

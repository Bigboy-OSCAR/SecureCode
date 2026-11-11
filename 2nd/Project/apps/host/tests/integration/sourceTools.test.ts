/** Source tool inputs are exercised against the real service, including omitted line bounds. */
import assert from "node:assert/strict";
import { mkdtempSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, before, it } from "node:test";
import type { AnswerCitation } from "@securecode/contracts";
import { sourceTools } from "../../src/cline/tools/sourceTools.js";
import type { ProjectTool } from "../../src/cline/tools/toolSupport.js";
import { HttpContextServiceClient } from "../../src/context-client/httpContextServiceClient.js";
import { validator } from "../support/hostHarness.js";
import { startCountedService, type CountedService } from "../support/runtimeHost.js";

const WORKSPACE = "ws_00000001";
const FIRST_LINE = "첫 줄: SOURCE-HEAD\n";
const REMAINDER = "둘째 줄: DO-NOT-READ\n셋째 줄: SOURCE-TAIL\n";
const cited: AnswerCitation[] = [];
let root: string;
let service: CountedService | undefined;
let read: ProjectTool;

before(async () => {
    root = realpathSync(mkdtempSync(join(tmpdir(), "securecode-source-tool-")));
    writeFileSync(join(root, "notes.txt"), FIRST_LINE + REMAINDER);
    service = await startCountedService({ SECURECODE_TEST_WORKSPACE_ROOTS: JSON.stringify({ [WORKSPACE]: root }) });
    const client = new HttpContextServiceClient({ baseUrl: service.url, internalToken: service.token, validator });
    const tools = sourceTools({
        sources: client.sources,
        workspaceId: WORKSPACE,
        root,
        timeoutMs: 20000,
        recordShown: () => undefined,
        recordCited: (citation) => cited.push(citation),
    });
    const found = tools.find((entry) => entry.tool.name === "read_file");
    assert.ok(found);
    read = found;
});

after(async () => {
    await service?.stop();
    if (root) rmSync(root, { recursive: true, force: true });
});

async function run(bounds: Record<string, number>): Promise<{ content: string; range: unknown }> {
    const result = await read.tool.execute({ path: "notes.txt", ...bounds }, {
        signal: AbortSignal.timeout(30000),
    } as never);
    assert.equal(typeof result, "string");
    return JSON.parse(result as string) as { content: string; range: unknown };
}

it("honors end_line without start_line and cites only the requested first lines", async () => {
    const result = await run({ end_line: 1 });
    assert.equal(result.content, FIRST_LINE.trimEnd());
    assert.doesNotMatch(result.content, /DO-NOT-READ|SOURCE-TAIL/);
    assert.deepEqual(result.range, { type: "byte", start: 0, end: Buffer.byteLength(FIRST_LINE.trimEnd()) });
    const citation = cited.at(-1);
    assert.ok(citation && "selection" in citation.ref);
    assert.deepEqual(citation.ref.selection.range, result.range);
});

it("keeps unbounded reads and explicit line ranges consistent, and rejects reversed bounds", async () => {
    assert.equal((await run({})).content, FIRST_LINE + REMAINDER);
    assert.equal((await run({ start_line: 2, end_line: 2 })).content, "둘째 줄: DO-NOT-READ");
    await assert.rejects(run({ start_line: 3, end_line: 1 }), /INVALID_SELECTOR/);
});

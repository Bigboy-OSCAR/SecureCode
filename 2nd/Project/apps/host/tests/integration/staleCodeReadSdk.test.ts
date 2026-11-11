/** Real SDK regressions for search/read cycles that cannot repair a stale code index. */
import "../../../../tools/sdk-probe/src/support/isolated-cline-home.js";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import type { SymbolBundle, SymbolSearchResponse } from "@securecode/contracts";
import { ContextServiceError } from "../../src/context-client/contextServiceError.js";
import type { ContextServiceClient } from "../../src/context-client/ports.js";
import { STALE_CODE_READ_STOP_MESSAGE } from "../../src/cline/adapter/staleCodeReadGuard.js";
import { createFixtureContextClient } from "../support/fixtureContextClient.js";
import { createRun, createSession, isFinished, outboundText, startSdkHost } from "../support/sdkScenario.js";

const candidate = "cand_01J9Z6Q4C001";
const upstreamSecret = "UPSTREAM-INTERNAL-SENTINEL";
const use = (id: string, toolName: string, input: Record<string, unknown>) => ({
    toolUses: [{ toolUseId: id, toolName, input }],
});
const search = (id: string) => use(id, "code_search", { query: "load_config" });
const read = (id: string, revision = 3, candidateId = candidate) =>
    use(id, "code_read", { candidate_id: candidateId, index_revision: revision });
const fallback = (id: string) => use(id, "read_file", { path: "notes.txt" });

function fixture<T>(name: string): T {
    const stored = JSON.parse(
        readFileSync(new URL(`../../../../contracts/fixtures/symbols/${name}`, import.meta.url), "utf8"),
    ) as { data: T };
    return stored.data;
}

function context(reads: (revision: number, candidateId: string) => boolean = () => false) {
    const calls: { candidateId: string; revision: number }[] = [];
    const client: ContextServiceClient = {
        ...createFixtureContextClient(),
        symbols: {
            search: async (request) => ({
                ...fixture<SymbolSearchResponse>("search-response.valid.json"),
                workspace_id: request.workspace_id,
            }),
            readBundle: async (request) => {
                calls.push({ candidateId: request.candidate_id, revision: request.index_revision });
                if (!reads(request.index_revision, request.candidate_id))
                    throw new ContextServiceError("SOURCE_CHANGED", upstreamSecret, false);
                return {
                    ...fixture<SymbolBundle>("bundle.valid.json"),
                    candidate_id: request.candidate_id,
                    index_revision: request.index_revision,
                };
            },
        },
    };
    return { client, calls };
}

test("a search/read loop stops and the same session can recover on its next question", async () => {
    const source = context();
    const host = await startSdkHost(
        [
            search("s1"),
            read("r1"),
            search("s2"),
            read("r2"),
            search("s3"),
            read("r3"),
            fallback("f3"),
            { text: "Recovered on the next question." },
        ],
        { contextClient: source.client },
    );
    try {
        const sessionId = await createSession(host);
        const run = await createRun(host, sessionId, "Inspect the indexed code.");
        const done = await host.client.waitFor(run.run_id, isFinished);
        assert.equal(done.status, "failed");
        assert.equal(done.terminal?.reason_code, "SOURCE_CHANGED");
        assert.equal(done.terminal?.message, STALE_CODE_READ_STOP_MESSAGE);
        assert.deepEqual(
            done.tool_calls.map((tool) => [tool.tool_name, tool.phase]),
            [
                ["code_search", "completed"],
                ["code_read", "failed"],
                ["code_search", "completed"],
                ["code_read", "failed"],
            ],
        );
        assert.equal(source.calls.length, 2, "both reads verify the current source before stopping");
        assert.equal(host.provider.capturedRequests.length, 4, "no provider retry after the second stale read");
        assert.equal(host.transformer.inputs.length, 4, "the stopping result still crosses the output boundary");
        assert.match(outboundText(host), /Repeating code_search does not refresh the index/);
        assert.doesNotMatch(outboundText(host) + JSON.stringify(done), new RegExp(upstreamSecret));

        const next = await createRun(host, sessionId, "Read the current file instead.");
        const recovered = await host.client.waitFor(next.run_id, isFinished);
        assert.equal(recovered.status, "completed", "SDK hook stop does not leave the session aborted");
        assert.equal(recovered.tool_calls.at(-1)?.tool_name, "read_file");
        assert.equal(recovered.tool_calls.at(-1)?.phase, "completed");
        assert.equal(source.calls.length, 3, "the new question starts its own stale-read count");
        assert.equal(host.provider.capturedRequests.length, 8);
    } finally {
        await host.close();
    }
});

test("a first stale read permits read_file recovery and does not poison the next question", async () => {
    const source = context();
    const host = await startSdkHost(
        [
            search("s1"),
            read("r1"),
            fallback("f1"),
            { text: "Current source read." },
            search("s2"),
            read("r2"),
            fallback("f2"),
            { text: "Current source read again." },
        ],
        { contextClient: source.client },
    );
    try {
        const sessionId = await createSession(host);
        for (let index = 0; index < 2; index += 1) {
            const run = await createRun(host, sessionId, `Read current code ${index}.`);
            const done = await host.client.waitFor(run.run_id, isFinished);
            assert.equal(done.status, "completed");
            assert.equal(done.tool_calls.at(-1)?.tool_name, "read_file");
            assert.equal(done.tool_calls.at(-1)?.phase, "completed");
            assert.equal(done.answer.citations?.length, 1, "only the successfully read current file is cited");
        }
        assert.equal(source.calls.length, 2);
        assert.equal(host.provider.capturedRequests.length, 8);
    } finally {
        await host.close();
    }
});

test("different stale candidates or revisions leave recovery open, and a newly indexed revision can succeed", async () => {
    const source = context((revision) => revision === 5);
    const host = await startSdkHost(
        [
            search("s1"),
            read("r1"),
            read("r2", 3, "cand_other0001"),
            read("r3", 4),
            read("r4", 5),
            { text: "Refreshed code is readable." },
        ],
        { contextClient: source.client },
    );
    try {
        const run = await createRun(host, await createSession(host), "Read the code after refreshing it.");
        const done = await host.client.waitFor(run.run_id, isFinished);
        assert.equal(done.status, "completed");
        assert.equal(done.tool_calls.at(-1)?.phase, "completed");
        assert.equal(source.calls.length, 4);
        assert.equal(host.provider.capturedRequests.length, 6);
    } finally {
        await host.close();
    }
});

test("a second attempt that actually recovers the same candidate and revision is not stopped", async () => {
    let attempts = 0;
    const source = context(() => ++attempts === 2);
    const host = await startSdkHost(
        [search("s1"), read("r1"), read("r2"), { text: "The original indexed contents are available again." }],
        { contextClient: source.client },
    );
    try {
        const run = await createRun(host, await createSession(host), "Try the indexed source after recovery.");
        const done = await host.client.waitFor(run.run_id, isFinished);
        assert.equal(done.status, "completed");
        assert.equal(done.tool_calls.at(-1)?.phase, "completed");
        assert.equal(source.calls.length, 2);
    } finally {
        await host.close();
    }
});

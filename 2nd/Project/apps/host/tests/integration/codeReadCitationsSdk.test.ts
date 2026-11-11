/** Direct code reads cite verified returned fragments across reindexing and host restart. */
import "../../../../tools/sdk-probe/src/support/isolated-cline-home.js";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import type { RunSnapshot, SymbolBundle, SymbolLocation, SymbolSearchResponse } from "@securecode/contracts";
import type { ContextServiceClient } from "../../src/context-client/ports.js";
import { createFixtureContextClient } from "../support/fixtureContextClient.js";
import { createRun, createSession, isFinished, startSdkHost } from "../support/sdkScenario.js";

const candidate = "cand_01J9Z6Q4C001";
const use = (id: string, toolName: string, input: Record<string, unknown>) => ({
    toolUses: [{ toolUseId: id, toolName, input }],
});
const read = (id: string, revision = 3) => use(id, "code_read", { candidate_id: candidate, index_revision: revision });
const search = (id: string) => use(id, "code_search", { query: "load_config" });
function fixture<T>(name: string): T {
    const stored = JSON.parse(
        readFileSync(new URL(`../../../../contracts/fixtures/symbols/${name}`, import.meta.url), "utf8"),
    ) as { data: T };
    return stored.data;
}
function cited(run: RunSnapshot): SymbolLocation[] {
    return (run.answer.citations ?? []).flatMap((citation) => ("location" in citation ? [citation.location] : []));
}
function context(bundle: () => SymbolBundle) {
    let searches = 0;
    const requests: { max_bytes?: number; max_tokens: number }[] = [];
    const client: ContextServiceClient = {
        ...createFixtureContextClient(),
        symbols: {
            search: async (request) => {
                searches += 1;
                return {
                    ...fixture<SymbolSearchResponse>("search-response.valid.json"),
                    workspace_id: request.workspace_id,
                };
            },
            readBundle: async (request) => {
                requests.push(request);
                assert.equal(request.index_revision, bundle().index_revision);
                return bundle();
            },
        },
    };
    return { client, requests, searches: () => searches };
}

test("a direct code_read cites every returned fragment and excludes omitted references without a search", async () => {
    const bundle = fixture<SymbolBundle>("bundle.valid.json");
    const primary = bundle.fragments[0];
    assert.ok(primary?.location);
    const helper: SymbolLocation = {
        ...primary.location,
        symbol_id: "sym_helper0001",
        qualname: "helper",
        relative_path: "helper.py",
    };
    bundle.fragments.push({
        ...primary,
        symbol_id: helper.symbol_id,
        location: helper,
        provenance: { ...primary.provenance, relative_path: helper.relative_path },
    });
    const source = context(() => bundle);
    const host = await startSdkHost([read("direct"), { text: "Read the selected bundle." }], {
        contextClient: source.client,
    });
    try {
        const run = await createRun(host, await createSession(host), "Read the previously selected item.");
        const done = await host.client.waitFor(run.run_id, isFinished);
        assert.equal(done.status, "completed");
        assert.equal(source.searches(), 0);
        assert.deepEqual(cited(done), [primary.location, helper]);
        assert.ok(!JSON.stringify(done.answer.citations).includes(bundle.omissions[0]?.symbol_id ?? "missing"));
        assert.deepEqual(
            source.requests.map((request) => [request.max_bytes, request.max_tokens]),
            [[16 * 1024, 8000]],
        );
    } finally {
        await host.close();
    }
});

test("reindexing and a new host tool instance use the read's current hash, never cached search metadata", async () => {
    let bundle = fixture<SymbolBundle>("bundle.valid.json");
    const old = bundle.fragments[0]?.location;
    assert.ok(old);
    const source = context(() => bundle);
    let host = await startSdkHost(
        [search("s1"), read("r1"), { text: "Original read." }, read("r2", 4), { text: "Current read." }],
        { contextClient: source.client },
    );
    try {
        const sessionId = await createSession(host);
        const first = await createRun(host, sessionId, "Read the selected item.");
        const original = await host.client.waitFor(first.run_id, isFinished);
        assert.deepEqual(cited(original), [old]);
        const fresh: SymbolLocation = { ...old, content_sha256: "c".repeat(64), end_line: old.end_line + 1 };
        bundle = {
            ...bundle,
            index_revision: 4,
            fragments: bundle.fragments.map((fragment) => ({
                ...fragment,
                location: fresh,
                end_line: fresh.end_line,
                provenance: { ...fragment.provenance, content_sha256: fresh.content_sha256 },
            })),
        };
        const next = await createRun(host, sessionId, "Read the item again after reindexing.");
        const updated = await host.client.waitFor(next.run_id, isFinished);
        assert.equal(updated.status, "completed");
        assert.deepEqual(cited(updated), [fresh]);
        const updatedRef = updated.answer.citations?.[0]?.ref;
        assert.equal(updatedRef?.kind === "symbol" ? updatedRef.index_revision : null, 4);
        assert.equal(source.searches(), 1, "no new search populated metadata for the revised read");

        const { dataDir, workspaceRoot } = host;
        await host.close();
        host = await startSdkHost([read("r3", 4), { text: "Read after restart." }], {
            contextClient: source.client,
            dataDir,
            workspaceRoot,
            initializeWorkspace: false,
        });
        await host.client.bootstrap();
        const resumed = await createRun(host, sessionId, "Read the item after restarting.");
        const restored = await host.client.waitFor(resumed.run_id, isFinished);
        assert.equal(restored.status, "completed");
        assert.deepEqual(cited(restored), [fresh]);
        assert.equal(source.searches(), 1, "a fresh SDK tool instance requires no search cache");
    } finally {
        await host.close();
    }
});

test("an empty or legacy bundle cannot turn a prior search result into evidence of a read", async () => {
    let bundle: SymbolBundle = { ...fixture<SymbolBundle>("bundle.valid.json"), fragments: [] };
    const source = context(() => bundle);
    const host = await startSdkHost(
        [search("s1"), read("r1"), { text: "No source fitted." }, read("r2"), { text: "Legacy response." }],
        { contextClient: source.client },
    );
    try {
        const sessionId = await createSession(host);
        const first = await createRun(host, sessionId, "Read within the available budget.");
        assert.deepEqual(cited(await host.client.waitFor(first.run_id, isFinished)), []);
        bundle = fixture<SymbolBundle>("bundle.valid.json");
        for (const fragment of bundle.fragments) delete fragment.location;
        const next = await createRun(host, sessionId, "Read from the legacy service.");
        const done = await host.client.waitFor(next.run_id, isFinished);
        assert.equal(done.status, "completed");
        assert.deepEqual(cited(done), [], "missing verified metadata is never invented or copied from search");
    } finally {
        await host.close();
    }
});

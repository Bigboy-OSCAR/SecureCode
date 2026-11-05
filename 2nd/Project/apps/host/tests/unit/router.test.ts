import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { Router } from "../../src/routes/router.js";

const noop = (): Promise<void> => Promise.resolve();

describe("router", () => {
    const router = new Router()
        .add("GET", "/api/v1/runs/:run_id", noop)
        .add("POST", "/api/v1/runs/:run_id/cancel", noop);

    it("extracts params", () => {
        const match = router.match("GET", "/api/v1/runs/run_abc12345");
        assert.equal(match.kind, "found");
        assert.deepEqual(match.kind === "found" ? match.params : {}, { run_id: "run_abc12345" });
    });

    it("rejects malformed percent escapes and encoded path separators", () => {
        for (const segment of ["bad%", "%2f", "%5C", "%00", "%2E%2E"]) {
            assert.equal(router.match("GET", `/api/v1/runs/${segment}`).kind, "invalid_path");
        }
    });

    it("distinguishes wrong method from unknown path", () => {
        assert.equal(router.match("DELETE", "/api/v1/runs/run_abc12345").kind, "method_not_allowed");
        assert.equal(router.match("GET", "/api/v1/nothing").kind, "not_found");
    });
});

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

    it("distinguishes wrong method from unknown path", () => {
        assert.equal(router.match("DELETE", "/api/v1/runs/run_abc12345").kind, "method_not_allowed");
        assert.equal(router.match("GET", "/api/v1/nothing").kind, "not_found");
    });
});

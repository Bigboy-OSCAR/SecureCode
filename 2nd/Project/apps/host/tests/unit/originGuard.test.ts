import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { checkRequestOrigin, type OriginPolicy } from "../../src/security/originGuard.js";

const policy: OriginPolicy = {
    allowedOrigins: ["http://127.0.0.1:8787", "http://127.0.0.1:5173"],
    allowedHosts: ["127.0.0.1:8787", "localhost:8787"],
};

describe("origin guard", () => {
    it("allows a same-origin GET without Origin", () => {
        assert.equal(checkRequestOrigin({ method: "GET", headers: { host: "127.0.0.1:8787" } }, policy), null);
    });

    it("allows a POST from the Vite dev origin", () => {
        const headers = { host: "127.0.0.1:8787", origin: "http://127.0.0.1:5173", "sec-fetch-site": "same-site" };
        assert.equal(checkRequestOrigin({ method: "POST", headers }, policy), null);
    });

    it("rejects a foreign Host header (DNS rebinding)", () => {
        assert.equal(
            checkRequestOrigin({ method: "GET", headers: { host: "evil.example:8787" } }, policy),
            "ORIGIN_REJECTED",
        );
    });

    it("rejects a cross-site fetch even for GET", () => {
        const headers = { host: "127.0.0.1:8787", "sec-fetch-site": "cross-site" };
        assert.equal(checkRequestOrigin({ method: "GET", headers }, policy), "ORIGIN_REJECTED");
    });

    it("rejects an unlisted Origin and an Origin-less POST", () => {
        const foreign = { host: "127.0.0.1:8787", origin: "http://attacker.example" };
        assert.equal(checkRequestOrigin({ method: "GET", headers: foreign }, policy), "ORIGIN_REJECTED");
        assert.equal(
            checkRequestOrigin({ method: "POST", headers: { host: "127.0.0.1:8787" } }, policy),
            "ORIGIN_REJECTED",
        );
    });
});

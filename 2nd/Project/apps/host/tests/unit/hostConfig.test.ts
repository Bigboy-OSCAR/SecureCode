import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { ConfigError, loadHostConfig } from "../../src/config/hostConfig.js";

const baseEnv = { SECURECODE_INTERNAL_TOKEN: "x".repeat(32) };

describe("host config", () => {
    it("binds to loopback and derives same-origin allowlists", () => {
        const config = loadHostConfig(baseEnv, "/work");
        assert.equal(config.host, "127.0.0.1");
        assert.equal(config.contextServiceUrl, "http://127.0.0.1:8788");
        assert.deepEqual(config.allowedHosts, ["127.0.0.1:8787", "localhost:8787"]);
        assert.ok(config.allowedOrigins.includes("http://127.0.0.1:5173"));
        assert.equal(config.providerConfigured, false);
    });

    it("rejects a short internal token without echoing it", () => {
        assert.throws(
            () => loadHostConfig({ SECURECODE_INTERNAL_TOKEN: "leak-me" }, "/work"),
            (error: unknown) => error instanceof ConfigError && !error.message.includes("leak-me"),
        );
    });

    it("rejects non-loopback extra origins and invalid ports", () => {
        assert.throws(
            () => loadHostConfig({ ...baseEnv, SECURECODE_ALLOWED_ORIGINS: "http://192.168.0.5:3000" }, "/work"),
            ConfigError,
        );
        assert.throws(() => loadHostConfig({ ...baseEnv, SECURECODE_HOST_PORT: "70000" }, "/work"), ConfigError);
    });
});

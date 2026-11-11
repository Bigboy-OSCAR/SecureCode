/** Real HTTP checks for the production UI proxy, bootstrap cookie, streaming and file confinement. */
import assert from "node:assert/strict";
import { createServer, request } from "node:http";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { it } from "node:test";
import { findFreePorts } from "../lib/ports.js";
import { startDesktopUi } from "../desktop/uiServer.js";

it("serves built files, confines paths and streams API cookies without rewriting the browser origin", async () => {
    const directory = mkdtempSync(join(tmpdir(), "localdesk-ui-"));
    writeFileSync(join(directory, "index.html"), '<div id="root">built</div>');
    const ports = await findFreePorts();
    const host = createServer((req, res) => {
        assert.equal(req.headers.host, `127.0.0.1:${ports.hostPort}`);
        assert.equal(req.headers.origin, `http://127.0.0.1:${ports.uiPort}`);
        res.writeHead(200, { "content-type": "text/event-stream", "set-cookie": "session=test; HttpOnly; Path=/api" });
        res.write("event: ready\ndata: one\n\n");
        res.end("event: ready\ndata: two\n\n");
    });
    await new Promise<void>((done) => host.listen(ports.hostPort, "127.0.0.1", done));
    const ui = await startDesktopUi({ ...ports, directory });
    try {
        assert.match(await (await fetch(ui.url)).text(), /built/);
        assert.equal((await fetch(ui.url + "/%2e%2e%2fsecret")).status, 404);
        assert.equal((await fetch(ui.url + "/missing.js")).status, 404);
        const response = await fetch(ui.url + "/api/v1/events", { headers: { origin: ui.url } });
        assert.match(response.headers.get("set-cookie") ?? "", /HttpOnly/);
        assert.match(await response.text(), /data: one\n\nevent: ready\ndata: two/);
        const rebindingStatus = await new Promise<number | undefined>((done, reject) => {
            const req = request(ui.url, { headers: { host: "attacker.invalid" } }, (res) => {
                res.resume();
                done(res.statusCode);
            });
            req.on("error", reject);
            req.end();
        });
        assert.equal(rebindingStatus, 403);
    } finally {
        await ui.stop();
        await new Promise<void>((done) => host.close(() => done()));
        rmSync(directory, { recursive: true, force: true });
    }
});

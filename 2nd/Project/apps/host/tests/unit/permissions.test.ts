/**
 * Local tool limits without the SDK: refused git commands, explicit tool
 * policies, workspace path containment, the outbound tool allow list and the
 * approval broker's digest/expiry/cancel rules.
 */
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, it } from "node:test";
import { unexpectedToolName } from "../../src/cline/adapter/requestGateFetch.js";
import { ApprovalBroker, inputDigest } from "../../src/cline/permissions/approvalBroker.js";
import { refuseCommand } from "../../src/cline/permissions/commandPolicy.js";
import { buildToolPolicies, SDK_BUILTIN_TOOL_NAMES } from "../../src/cline/permissions/toolPolicies.js";
import { commandEnvironment } from "../../src/cline/tools/commandRunner.js";
import { resolveForRead, resolveForWrite } from "../../src/cline/tools/workspacePaths.js";

const words = (...parts: string[]): string => parts.join(" ");

describe("command policy", () => {
    it("refuses commit/push/history rewrites anywhere in a command line", () => {
        for (const command of [
            words("git", "commit", "-m", "x"),
            words("GIT", "push"),
            words("git", "-C", "repo", "push", "origin"),
            words("echo", "a", "&&", "git", "commit"),
            words("/usr/bin/git", "--no-pager", "reset", "--hard"),
            words("npm", "test;", "git", "rebase", "main"),
            words('"git"', '"push"'),
            words("g'it'", "co'mmit'", "-m", "x"),
            words("g\\it", "pu\\sh"),
            words("git", "-C", '"repo with spaces"', "push"),
            words("LANG=C", "git", "push"),
            words("env", "-u", "HOME", "LANG=C", "git", "push"),
            words("command", "--", "git", "push"),
            words("sudo", "-u", "test", "git", "push"),
            words("sh", "-c", "'git", "push'"),
            words("cmd.exe", "/c", '"git', 'push"'),
            words("git", "-c", "alias.upload=push", "upload"),
            words("git", "-calias.upload=push", "upload"),
            words("git", "--config-env=alias.upload=ACTION", "upload"),
        ]) {
            assert.ok(refuseCommand(command), command);
        }
        for (const command of [
            words("git", "status"),
            words("git", "diff"),
            words("npm", "test"),
            words("echo", "commit"),
            words("echo", '"git', 'push"'),
            words("env", "LANG=C", "git", "status"),
            words("git", "-c", "color.ui=false", "diff"),
        ]) {
            assert.equal(refuseCommand(command), null, command);
        }
    });

    it("removes secrets from the command environment", () => {
        const env = commandEnvironment({
            ANTHROPIC_API_KEY: "k",
            SECURECODE_INTERNAL_TOKEN: "t",
            CLINE_DIR: "d",
            PATH: "p",
        });
        assert.deepEqual(Object.keys(env).sort(), ["GIT_TERMINAL_PROMPT", "PATH"]);
    });
});

describe("tool policies and allow list", () => {
    it("disables every SDK tool and only auto-approves read-only project tools", () => {
        const policies = buildToolPolicies([
            { name: "read_file", requiresApproval: false },
            { name: "run_command", requiresApproval: true },
        ]);
        for (const name of SDK_BUILTIN_TOOL_NAMES)
            assert.deepEqual(policies[name], { enabled: false, autoApprove: false });
        assert.deepEqual(policies.read_file, { enabled: true, autoApprove: true });
        assert.deepEqual(policies.run_command, { enabled: true, autoApprove: false });
        assert.throws(() => buildToolPolicies([{ name: "run_commands", requiresApproval: false }]));
    });

    it("blocks an outbound body that exposes any tool outside the allow list", () => {
        const allowed = new Set(["read_file"]);
        assert.equal(unexpectedToolName(JSON.stringify({ tools: [{ name: "read_file" }] }), allowed), null);
        assert.equal(unexpectedToolName(JSON.stringify({ tools: [{ name: "web_search" }] }), allowed), "web_search");
        assert.equal(unexpectedToolName(JSON.stringify({ messages: [] }), allowed), null);
        assert.notEqual(unexpectedToolName("not json", allowed), null);
    });
});

describe("workspace paths", () => {
    const root = mkdtempSync(join(tmpdir(), "securecode-paths-"));
    writeFileSync(join(root, "a.txt"), "a");

    it("resolves inside the root and refuses escapes and repository metadata", () => {
        assert.equal(resolveForRead(root, "a.txt").endsWith("a.txt"), true);
        for (const bad of ["../x", "/etc/passwd", "C:/x", "sub\\x", ".git/config", "x/.securecode/y", ""]) {
            assert.throws(() => resolveForRead(root, bad), bad);
            assert.throws(() => resolveForWrite(root, bad), bad);
        }
        assert.ok(resolveForWrite(root, "new/dir/file.txt").endsWith("file.txt"));
    });
});

describe("approval broker", () => {
    const subject = (runId: string, input: unknown) => ({
        sessionId: "ses_0123456789",
        runId,
        toolCallId: "toolu_1",
        toolName: "write_file",
        input,
        review: {
            kind: "file_change" as const,
            summary: "write",
            content: "x",
            content_truncated: false,
            reviewable: true,
        },
    });

    it("binds decisions to run, digest and expiry and settles waiters on cancel", async () => {
        let now = 0;
        const broker = new ApprovalBroker(1000, () => now);
        const requested: string[] = [];
        broker.setListener({
            requested: (_s, approval) => requested.push(approval.approval_id),
            resolved: () => undefined,
        });
        const verdict = broker.request(subject("run_0123456789", { b: 1, a: 2 }));
        const approvalId = requested[0] ?? "";
        assert.equal(inputDigest({ a: 2, b: 1 }), inputDigest({ b: 1, a: 2 }));
        assert.equal(broker.decide("run_other12345", approvalId, true, inputDigest({ a: 2, b: 1 })).ok, false);
        const mismatch = broker.decide("run_0123456789", approvalId, true, inputDigest({ a: 3 }));
        assert.equal(mismatch.ok ? "" : mismatch.code, "APPROVAL_DIGEST_MISMATCH");
        now = 2000;
        const expired = broker.decide("run_0123456789", approvalId, true, inputDigest({ a: 2, b: 1 }));
        assert.equal(expired.ok ? "" : expired.code, "APPROVAL_EXPIRED");
        assert.deepEqual(await verdict, { approved: false, reason: "approval expired by SecureCode" });

        const second = broker.request(subject("run_0123456789", {}));
        broker.cancelSession("ses_0123456789");
        assert.equal((await second).approved, false);
        const late = broker.decide("run_0123456789", requested[1] ?? "", true, inputDigest({}));
        assert.equal(late.ok ? "" : late.code, "APPROVAL_ALREADY_DECIDED");
    });

    it("refuses to approve input that was too large to review", async () => {
        const broker = new ApprovalBroker(1000, () => 0);
        let approvalId = "";
        broker.setListener({
            requested: (_s, approval) => (approvalId = approval.approval_id),
            resolved: () => undefined,
        });
        const pending = broker.request({
            ...subject("run_0123456789", {}),
            review: { kind: "command", summary: "s", content: "c", content_truncated: true, reviewable: false },
        });
        const refused = broker.decide("run_0123456789", approvalId, true, inputDigest({}));
        assert.equal(refused.ok ? "" : refused.code, "VALIDATION_FAILED");
        assert.equal(broker.decide("run_0123456789", approvalId, false, inputDigest({})).ok, true);
        assert.equal((await pending).approved, false);
    });
});

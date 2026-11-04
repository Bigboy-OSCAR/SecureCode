/**
 * Scenario: `checkpoint: { enabled: false }` with a `createCheckpoint` spy.
 * The spy must never be called and the fixture Git workspace's status, refs,
 * and stash must be identical before and after a run that executes a tool.
 * The probe never enables checkpoints and never runs git commit/push.
 */
import { createSentinelTool, SENTINEL_TOOL_NAME } from "../fixtures/probe-tools.js";
import { withProbeRun } from "../probe/probe-run.js";
import { buildProbeStartInput } from "../probe/session-config.js";
import { readGitFingerprint } from "../support/fixture-workspace.js";
import { ScenarioRecorder, type ScenarioResult } from "../support/scenario-result.js";

export async function runCheckpointScenario(): Promise<ScenarioResult> {
    const recorder = new ScenarioRecorder("checkpoint");
    const turns = [
        { toolUses: [{ toolUseId: "toolu_ckpt_1", toolName: SENTINEL_TOOL_NAME, input: { label: "x" } }] },
        { text: "done" },
    ];
    let checkpointCalls = 0;
    const checkpointSpy = () => {
        checkpointCalls += 1;
        return undefined;
    };

    try {
        await withProbeRun({ name: "checkpoint", turns }, async ({ core, workspaceDir }) => {
            const before = readGitFingerprint(workspaceDir);
            const started = await core.start(
                buildProbeStartInput({
                    cwd: workspaceDir,
                    prompt: "go",
                    extraTools: [createSentinelTool()],
                    checkpointSpy,
                    interactive: true,
                }),
            );
            await core.send({ sessionId: started.sessionId, prompt: "second run" }).catch(() => undefined);
            const after = readGitFingerprint(workspaceDir);

            recorder.check(
                "createCheckpoint never called when disabled",
                checkpointCalls === 0,
                `calls=${checkpointCalls}`,
            );
            recorder.check(
                "git status unchanged",
                before.status === after.status,
                `status_lines=${after.status.split("\n").filter(Boolean).length}`,
            );
            recorder.check(
                "git refs unchanged",
                before.refs === after.refs,
                `refs=${after.refs.split("\n").filter(Boolean).length}`,
            );
            recorder.check(
                "git stash unchanged",
                before.stash === after.stash,
                `stash_entries=${after.stash.split("\n").filter(Boolean).length}`,
            );
            recorder.observe(
                "manifest_checkpoint_fields",
                Object.keys(started.manifest).filter((key) => key.includes("checkpoint")),
            );
        });
    } catch (error) {
        recorder.fail("scenario threw", error);
    }
    return recorder.finish();
}

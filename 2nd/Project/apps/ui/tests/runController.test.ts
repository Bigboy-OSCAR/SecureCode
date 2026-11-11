import assert from "node:assert/strict";
import { test } from "node:test";
import type {
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    ApprovalId,
    AppEvent,
    RunCreateRequest,
    RunId,
    RunSnapshot,
    Sequence,
    SessionId,
} from "@securecode/contracts";
import { ContractValidator } from "@securecode/contracts";
import replayUnavailableFixture from "../../../contracts/fixtures/events/stream-replay-unavailable.valid.json";
import { fixtureAdapter } from "./support/fixtureAdapter.js";
import { FixtureRunClient } from "./support/fixtureRunClient.js";
import type { RunClient } from "../src/api/runClient.js";
import { RunController } from "../src/features/chat/model/runController.js";

class FakeRunClient implements RunClient {
    createCalls = 0;
    cancelCalls = 0;
    decisionCalls = 0;
    snapshotReads = 0;
    lastCreateRequest: RunCreateRequest | null = null;
    recoverySnapshot: RunSnapshot = fixtureAdapter.runs[0]!;
    createGate: Promise<RunSnapshot> | null = null;
    cancelGate: Promise<RunSnapshot> | null = null;
    recoveryGate: Promise<RunSnapshot> | null = null;
    decisionGate: Promise<void> | null = null;
    decisionFails = false;
    readonly subscribedAt: Sequence[] = [];
    private readonly eventHandlers = new Map<RunId, (event: AppEvent) => void>();
    private readonly disconnectHandlers = new Map<RunId, () => void>();

    async createRun(sessionId: SessionId, request: RunCreateRequest): Promise<RunSnapshot> {
        assert.equal(sessionId, fixtureAdapter.runs[0]!.session_id);
        this.createCalls += 1;
        this.lastCreateRequest = request;
        return this.createGate ?? fixtureAdapter.runs[0]!;
    }

    async getRun(runId: RunId): Promise<RunSnapshot> {
        this.snapshotReads += 1;
        assert.equal(runId, this.recoverySnapshot.run_id);
        return this.recoveryGate ?? this.recoverySnapshot;
    }

    async cancelRun(runId: RunId): Promise<RunSnapshot> {
        this.cancelCalls += 1;
        assert.equal(runId, fixtureAdapter.runs[0]!.run_id);
        return this.cancelGate ?? fixtureAdapter.runs[2]!;
    }

    async decideApproval(
        runId: RunId,
        approvalId: ApprovalId,
        request: ApprovalDecisionRequest,
    ): Promise<ApprovalDecisionResponse> {
        this.decisionCalls += 1;
        await this.decisionGate;
        assert.equal(runId, fixtureAdapter.runs[0]!.run_id);
        assert.equal(approvalId, fixtureAdapter.runs[0]!.pending_approvals[0]!.approval_id);
        assert.equal(request.input_digest, fixtureAdapter.runs[0]!.pending_approvals[0]!.input_digest);
        if (this.decisionFails) {
            throw new Error("response timeout");
        }
        const approval = fixtureAdapter.runs[0]!.pending_approvals[0]!;
        const status: typeof approval.status = request.decision === "approve" ? "approved" : "rejected";
        return {
            schema_version: fixtureAdapter.runs[0]!.schema_version,
            approval: { ...approval, status, decided_at: "2026-11-04T09:02:00Z" },
        };
    }

    subscribe(
        runId: RunId,
        afterSequence: Sequence,
        onEvent: (event: AppEvent) => void,
        onDisconnect: () => void,
    ): () => void {
        this.subscribedAt.push(afterSequence);
        this.eventHandlers.set(runId, onEvent);
        this.disconnectHandlers.set(runId, onDisconnect);
        return () => {
            this.eventHandlers.delete(runId);
            this.disconnectHandlers.delete(runId);
        };
    }

    emit(event: AppEvent): void {
        this.eventHandlers.get(event.run_id)?.(event);
    }

    disconnect(runId: RunId): void {
        this.disconnectHandlers.get(runId)?.();
    }

    get activeSubscriptionCount(): number {
        return this.eventHandlers.size;
    }
}

function createController(client: RunClient, now = Date.parse("2026-11-04T09:01:00Z")): RunController {
    const snapshot = fixtureAdapter.runs[0]!;
    let keyNumber = 0;
    return new RunController(
        client,
        snapshot.session_id,
        snapshot.workspace_id,
        () => {
            keyNumber += 1;
            return keyNumber === 1 ? "ui-test-idempotency-key" : `ui-test-idempotency-key-${keyNumber}`;
        },
        () => now,
    );
}

function makeOutputEvent(
    event: Extract<AppEvent, { type: "run.output_delta" }>,
    sequence: number,
    eventId = event.event_id,
): Extract<AppEvent, { type: "run.output_delta" }> {
    return { ...event, sequence, event_id: eventId };
}

function snapshotAt(snapshot: RunSnapshot, lastSequence: number, answerText = snapshot.answer.text): RunSnapshot {
    return {
        ...snapshot,
        replay: { ...snapshot.replay, last_sequence: lastSequence },
        answer: { ...snapshot.answer, text: answerText },
    };
}

function resolvedSnapshot(): RunSnapshot {
    const initial = fixtureAdapter.runs[0]!;
    const approval = initial.pending_approvals[0]!;
    const event = fixtureAdapter.approvalRejected;
    if (event.type !== "run.approval_resolved") {
        throw new Error("The rejection event fixture has the wrong type.");
    }
    return {
        ...initial,
        replay: { ...initial.replay, last_sequence: event.sequence + 2 },
        pending_approvals: [],
        approval_history: [
            {
                approval_id: approval.approval_id,
                tool_call_id: approval.tool_call_id,
                tool_name: approval.tool_name,
                status: "rejected",
                decided_at: event.payload.decided_at,
            },
        ],
    };
}

test("duplicate run submission reuses one request and the same idempotency key", async () => {
    const client = new FakeRunClient();
    let resolveCreate: ((snapshot: RunSnapshot) => void) | undefined;
    client.createGate = new Promise((resolve) => {
        resolveCreate = resolve;
    });
    const controller = createController(client);
    const first = controller.createRun("테스트를 실행해 실패 원인을 찾아줘");
    const duplicate = controller.createRun("테스트를 실행해 실패 원인을 찾아줘");

    assert.equal(client.createCalls, 1);
    assert.equal(controller.getSnapshot().operation?.kind, "creating");
    resolveCreate?.(fixtureAdapter.runs[0]!);
    assert.deepEqual(await Promise.all([first, duplicate]), [true, true]);
    assert.equal(client.lastCreateRequest?.idempotency_key, "ui-test-idempotency-key");
    assert.equal(controller.getSnapshot().snapshot?.run_id, fixtureAdapter.runs[0]!.run_id);
    controller.dispose();
});

test("duplicate event IDs and already-applied sequences do not duplicate answer text", () => {
    const client = new FakeRunClient();
    const controller = createController(client);
    controller.restore(snapshotAt(fixtureAdapter.runs[0]!, 1, ""));
    const output = fixtureAdapter.outputDelta;
    assert.equal(output.type, "run.output_delta");
    if (output.type !== "run.output_delta") {
        return;
    }

    const accepted = makeOutputEvent(output, 2);
    controller.receiveEvent(accepted);
    controller.receiveEvent(accepted);
    controller.receiveEvent(makeOutputEvent(output, 2, "evt_01J9Z6Q4DIFFERENT"));

    assert.equal(controller.getSnapshot().snapshot?.answer.text, output.payload.text);
    assert.equal(controller.getSnapshot().lastSequence, 2);
    controller.dispose();
});

test("out-of-order events trigger a snapshot refresh and resume after its sequence", async () => {
    const client = new FakeRunClient();
    client.recoverySnapshot = snapshotAt(fixtureAdapter.runs[0]!, 4, "snapshot 복구 결과");
    const controller = createController(client);
    controller.restore(snapshotAt(fixtureAdapter.runs[0]!, 1, ""));
    const output = fixtureAdapter.outputDelta;
    assert.equal(output.type, "run.output_delta");
    if (output.type !== "run.output_delta") {
        return;
    }

    controller.receiveEvent(makeOutputEvent(output, 3));
    controller.receiveEvent(makeOutputEvent(output, 2, "evt_01J9Z6Q4OUTOFORDER"));
    await new Promise((resolve) => setTimeout(resolve, 0));

    assert.equal(client.snapshotReads, 1);
    assert.equal(controller.getSnapshot().snapshot?.answer.text, "snapshot 복구 결과");
    assert.equal(controller.getSnapshot().lastSequence, 4);
    assert.equal(client.subscribedAt.at(-1), 4);
    controller.dispose();
});

test("replay expiration restores the authoritative snapshot and resumes at its last sequence", async () => {
    const client = new FakeRunClient();
    const controller = createController(client);
    const initial = snapshotAt(fixtureAdapter.runs[0]!, 2, "before replay expiration");
    client.recoverySnapshot = snapshotAt(fixtureAdapter.runs[0]!, 812, "recovered snapshot");
    controller.restore(initial);

    controller.receiveEvent(replayUnavailableFixture.data as AppEvent);
    await new Promise((resolve) => setImmediate(resolve));

    assert.equal(client.snapshotReads, 1);
    assert.equal(controller.getSnapshot().snapshot?.answer.text, "recovered snapshot");
    assert.equal(controller.getSnapshot().lastSequence, 812);
    assert.equal(client.subscribedAt.at(-1), 812);
    assert.equal(controller.getSnapshot().connection, "connected");
    controller.dispose();
});

test("approval rejection removes only that pending request and does not finish the run", async () => {
    const client = new FakeRunClient();
    const controller = createController(client);
    const initial = fixtureAdapter.runs[0]!;
    controller.restore(initial);
    const approvalId = initial.pending_approvals[0]!.approval_id;

    assert.equal(await controller.decideApproval(approvalId, "reject"), true);
    assert.equal(await controller.decideApproval(approvalId, "reject"), false);
    assert.equal(client.decisionCalls, 1);
    assert.equal(controller.getSnapshot().snapshot?.pending_approvals.length, 0);
    assert.equal(controller.getSnapshot().snapshot?.approval_history?.[0]?.status, "rejected");
    assert.equal(controller.getSnapshot().snapshot?.status, "awaiting_approval");
    controller.dispose();
});

test("approval timeout recovers authoritative history without retrying the decision", async () => {
    const client = new FakeRunClient();
    client.decisionFails = true;
    client.recoverySnapshot = resolvedSnapshot();
    const controller = createController(client);
    controller.restore(fixtureAdapter.runs[0]!);
    const approvalId = fixtureAdapter.runs[0]!.pending_approvals[0]!.approval_id;

    assert.equal(await controller.decideApproval(approvalId, "reject"), false);
    assert.equal(client.decisionCalls, 1);
    assert.equal(client.snapshotReads, 1);
    assert.equal(controller.getSnapshot().connection, "connected");
    assert.equal(controller.getSnapshot().snapshot?.approval_history?.[0]?.status, "rejected");
    controller.dispose();
});

test("expired approval is not sent and triggers a fresh snapshot read", async () => {
    const client = new FakeRunClient();
    const controller = createController(client, Date.parse("2026-11-04T09:06:00Z"));
    controller.restore(fixtureAdapter.runs[0]!);
    const approvalId = fixtureAdapter.runs[0]!.pending_approvals[0]!.approval_id;

    assert.equal(await controller.decideApproval(approvalId, "reject"), false);
    assert.equal(client.decisionCalls, 0);
    assert.equal(client.snapshotReads, 1);
    controller.dispose();
});

test("cancel waits for server snapshot and terminal state ignores later progress", async () => {
    const client = new FakeRunClient();
    let resolveCancel: ((snapshot: RunSnapshot) => void) | undefined;
    client.cancelGate = new Promise((resolve) => {
        resolveCancel = resolve;
    });
    const controller = createController(client);
    controller.restore(fixtureAdapter.runs[0]!);

    const cancellation = controller.cancelRun();
    assert.equal(controller.getSnapshot().operation?.kind, "cancelling");
    assert.equal(controller.getSnapshot().snapshot?.status, "awaiting_approval");
    assert.equal(controller.canCancelRun(), false);
    assert.equal(controller.canSubmitRun("new prompt"), false);
    resolveCancel?.(fixtureAdapter.runs[2]!);
    assert.equal(await cancellation, true);
    assert.equal(controller.getSnapshot().snapshot?.status, "cancelled");
    assert.equal(controller.getSnapshot().snapshot?.terminal?.status, "cancelled");
    assert.equal(await controller.cancelRun(), false);
    assert.equal(client.cancelCalls, 1);

    const output = fixtureAdapter.outputDelta;
    if (output.type === "run.output_delta") {
        controller.receiveEvent(makeOutputEvent(output, 8, "evt_01J9Z6Q4LATE"));
    }
    assert.equal(controller.getSnapshot().snapshot?.status, "cancelled");
    controller.dispose();
});

test("disconnect blocks mutation and reconnect restores the run snapshot", async () => {
    const client = new FakeRunClient();
    const controller = createController(client);
    const snapshot = fixtureAdapter.runs[0]!;
    controller.restore(snapshot);
    client.disconnect(snapshot.run_id);

    assert.equal(controller.getSnapshot().connection, "disconnected");
    assert.equal(client.cancelCalls, 0, "a stream disconnect must not cancel the server run");
    assert.equal(await controller.createRun("새 질문"), false);
    assert.equal(controller.canDecideApproval(snapshot.pending_approvals[0]!.approval_id, "reject"), false);
    assert.equal(await controller.reconnect(), true);
    assert.equal(client.snapshotReads, 1);
    assert.equal(controller.getSnapshot().connection, "connected");
    assert.equal(client.subscribedAt.at(-1), snapshot.replay.last_sequence);
    controller.dispose();
});

test("dispose releases the event subscription so late events cannot update the view", () => {
    const client = new FakeRunClient();
    const controller = createController(client);
    controller.restore(fixtureAdapter.runs[0]!);
    assert.equal(client.activeSubscriptionCount, 1);
    const before = controller.getSnapshot();

    controller.dispose();
    assert.equal(client.activeSubscriptionCount, 0);
    const output = fixtureAdapter.outputDelta;
    if (output.type === "run.output_delta") {
        client.emit(makeOutputEvent(output, before.lastSequence + 1, "evt_01J9Z6Q4AFTERDISPOSE"));
    }
    assert.equal(controller.getSnapshot(), before);
});

test("late create response from a previous session is ignored", async () => {
    const client = new FakeRunClient();
    let resolveCreate: ((snapshot: RunSnapshot) => void) | undefined;
    client.createGate = new Promise((resolve) => {
        resolveCreate = resolve;
    });
    const controller = createController(client);
    const pending = controller.createRun("테스트를 실행해 실패 원인을 찾아줘");
    controller.setSession("ses_01J9Z6Q4NEXT", "ws_01J9Z6Q4TEST");
    resolveCreate?.(fixtureAdapter.runs[0]!);

    assert.equal(await pending, false);
    assert.equal(controller.getSnapshot().snapshot, null);
    assert.equal(controller.getSnapshot().sessionId, "ses_01J9Z6Q4NEXT");
    controller.dispose();
});

test("fixture adapter permits a distinct run after terminal confirmation", async () => {
    const client = new FixtureRunClient();
    const controller = createController(client);
    const firstPrompt = "첫 실행";
    assert.equal(await controller.createRun(firstPrompt), true);
    const firstRunId = controller.getSnapshot().snapshot?.run_id;
    assert.equal(await controller.cancelRun(), true);

    assert.equal(await controller.createRun("다음 실행"), true);
    const secondRunId = controller.getSnapshot().snapshot?.run_id;
    assert.notEqual(secondRunId, firstRunId);
    assert.equal(controller.getSnapshot().snapshot?.status, "awaiting_approval");
    const secondAnswer = controller.getSnapshot().snapshot?.answer.text;
    assert.ok(firstRunId && secondRunId);
    const output = fixtureAdapter.outputDelta;
    assert.equal(output.type, "run.output_delta");
    if (output.type !== "run.output_delta") {
        return;
    }
    const staleOutput = { ...makeOutputEvent(output, 1, "evt_01J9Z6Q4STALE"), run_id: firstRunId };
    controller.receiveEvent(staleOutput);
    assert.equal(controller.getSnapshot().snapshot?.run_id, secondRunId);
    assert.equal(controller.getSnapshot().snapshot?.answer.text, secondAnswer);
    const validation = ContractValidator.load().validate(
        "api/run.schema.json#/definitions/RunSnapshot",
        controller.getSnapshot().snapshot,
    );
    assert.equal(validation.valid, true, validation.errors.join(", "));
    controller.dispose();
});

test("completed snapshots remain terminal and failure state is representable", () => {
    const client = new FakeRunClient();
    const controller = createController(client);
    const completed = fixtureAdapter.runs[1]!;
    controller.restore(completed);
    const output = fixtureAdapter.outputDelta;
    if (output.type === "run.output_delta") {
        controller.receiveEvent(makeOutputEvent(output, completed.replay.last_sequence + 1, "evt_01J9Z6Q4LATE"));
    }
    assert.equal(controller.getSnapshot().snapshot?.status, "completed");
    assert.equal(controller.getSnapshot().snapshot?.answer.text, completed.answer.text);

    const failed: RunSnapshot = {
        ...completed,
        status: "failed",
        terminal: {
            ...completed.terminal!,
            status: "failed",
            reason_code: "PROVIDER_ERROR",
            message: "모델 요청에 실패했습니다.",
        },
    };
    const failedController = createController(client);
    assert.equal(failedController.restore(failed), true);
    assert.equal(failedController.getSnapshot().snapshot?.terminal?.status, "failed");
    failedController.dispose();
    controller.dispose();
});

test("snapshot recovery keeps an in-flight approval locked against duplicate decisions", async () => {
    const client = new FakeRunClient();
    let finishDecision: (() => void) | undefined;
    client.decisionGate = new Promise((resolve) => {
        finishDecision = resolve;
    });
    const controller = createController(client);
    controller.restore(fixtureAdapter.runs[0]!);
    const approvalId = fixtureAdapter.runs[0]!.pending_approvals[0]!.approval_id;
    const decision = controller.decideApproval(approvalId, "approve");
    await controller.reconnect();
    assert.equal(controller.getSnapshot().operation?.kind, "deciding_approval");
    assert.equal(await controller.decideApproval(approvalId, "approve"), false);
    assert.equal(client.decisionCalls, 1);
    finishDecision?.();
    assert.equal(await decision, true);
    controller.dispose();
});

test("a delayed snapshot behind live events does not leave the run recovering forever", async () => {
    const client = new FakeRunClient();
    let finishRecovery: ((snapshot: RunSnapshot) => void) | undefined;
    client.recoveryGate = new Promise((resolve) => {
        finishRecovery = resolve;
    });
    const controller = createController(client);
    const initial = snapshotAt(fixtureAdapter.runs[0]!, 1, "");
    controller.restore(initial);
    const recovery = controller.reconnect();
    const output = fixtureAdapter.outputDelta;
    assert.equal(output.type, "run.output_delta");
    if (output.type !== "run.output_delta") return;
    controller.receiveEvent(makeOutputEvent(output, 2));
    finishRecovery?.(initial);
    assert.equal(await recovery, true);
    assert.equal(controller.getSnapshot().connection, "connected");
    assert.equal(controller.getSnapshot().snapshot?.answer.text, output.payload.text);
    assert.equal(client.subscribedAt.at(-1), 2);
    controller.dispose();
});

test("a delayed previous-run snapshot cannot replace a newer completed run", async () => {
    const client = new FakeRunClient();
    let finishRecovery: ((snapshot: RunSnapshot) => void) | undefined;
    client.recoveryGate = new Promise((resolve) => {
        finishRecovery = resolve;
    });
    const controller = createController(client);
    const first = fixtureAdapter.runs[1]!;
    controller.restore(first);
    const recovery = controller.reconnect();
    const second = { ...first, run_id: `${first.run_id}2` };
    controller.restore(second);
    finishRecovery?.(first);
    assert.equal(await recovery, false);
    assert.equal(controller.getSnapshot().snapshot?.run_id, second.run_id);
    controller.dispose();
});

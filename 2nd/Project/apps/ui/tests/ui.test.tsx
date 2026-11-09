/** Smoke tests for the UI's initial semantic layout and reusable presentation components. */
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { createElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ContractValidator } from "@securecode/contracts";
import screenCases from "../../../tests/fixtures/ui/screen-cases.json";
import { App } from "../src/app/App.js";
import { Alert, Button, InputField, StatusBadge } from "../src/components/index.js";
import { fixtureAdapter } from "../src/api/fixtureAdapter.js";
import { FixtureRunClient } from "../src/api/fixtureRunClient.js";
import { ApprovalCard } from "../src/features/approvals/components/ApprovalCard.js";
import { ConversationPanel } from "../src/features/chat/components/ConversationPanel.js";
import { RunController } from "../src/features/chat/model/runController.js";
import { shouldSubmitQuestionOnEnter } from "../src/features/chat/model/questionInput.js";
import { ProjectPanel } from "../src/features/project/components/ProjectPanel.js";
import { PointerPanel } from "../src/features/pointers/components/PointerPanel.js";
import { PointerReadPanel } from "../src/features/pointers/components/PointerReadPanel.js";
import { PdfParsePanel } from "../src/features/pointers/components/PdfParsePanel.js";
import { isBootstrapCodeValid } from "../src/features/settings/model/inputValidation.js";
import { isProjectFormValid } from "../src/features/project/model/projectForm.js";
import { isPdfPathValid, isSourcePathValid } from "../src/features/pointers/model/pointerForm.js";
import { boundedPreview } from "../src/features/shared/model/boundedPreview.js";

function render(element: ReactNode): string {
    return renderToStaticMarkup(createElement("div", null, element));
}

test("all feature screens render their stable identifiers", () => {
    const markup = render(createElement(App, { mode: "fixture" }));

    for (const screen of [
        "connection",
        "project",
        "chat",
        "approval",
        "context",
        "pointers",
        "pointer-read",
        "pdf",
        "settings",
    ]) {
        assert.ok(markup.includes(`data-testid="screen-${screen}"`), `Expected ${screen} screen to render.`);
    }
    assert.ok(markup.includes('href="#main-content"'));
    for (const match of markup.matchAll(/href="#([^"]+)"/g)) {
        assert.ok(markup.includes(`id="${match[1]}"`), `Navigation target ${match[1]} must exist.`);
    }
    const identifiers = [...markup.matchAll(/data-testid="([^"]+)"/g)].map((match) => match[1]);
    assert.equal(new Set(identifiers).size, identifiers.length, "data-testid values should be unique per screen.");
    const codePattern = markup.match(/id="connection-code"[^>]*pattern="([^"]+)"/)?.[1];
    assert.ok(codePattern);
    assert.doesNotThrow(() => new RegExp(codePattern, "v"));
});

test("live application uses host auth and labels unfinished index and pointer APIs as unavailable", () => {
    const markup = render(createElement(App, { mode: "live" }));

    assert.ok(markup.includes("same-origin bootstrap 요청"));
    assert.ok(markup.includes("R0 색인 API가 아직 연결되지 않았습니다"));
    assert.ok(markup.includes("Source Pointer, Runtime Pointer"));
    assert.ok(markup.includes("provider API 키와 내부 서비스 토큰은 브라우저에 전달되지 않습니다"));
    assert.equal(markup.includes("fixture 기반 화면 · 실제 API 호출 없음"), false);
    assert.equal(markup.includes("hello from the workspace"), false);
});

test("shared components render accessible labels and status text", () => {
    const markup = render(
        createElement(
            "section",
            null,
            createElement(Button, { type: "button", variant: "primary" }, "계속"),
            createElement(InputField, {
                id: "project-name",
                label: "프로젝트 이름",
                errorMessage: "이름을 입력하세요",
            }),
            createElement(StatusBadge, { label: "준비 중", tone: "warning" }),
            createElement(Alert, { title: "연결을 확인하세요", variant: "error" }, "로컬 서비스를 확인하세요."),
        ),
    );

    assert.ok(markup.includes('for="project-name"'));
    assert.ok(markup.includes('aria-describedby="project-name-error"'));
    assert.ok(markup.includes('role="alert"'));
    assert.ok(markup.includes("준비 중"));
});

test("fixture cases refer to valid contract fixtures for every screen state", async () => {
    const validator = ContractValidator.load();
    const screens = new Set(screenCases.map((fixtureCase) => fixtureCase.screen));
    assert.deepEqual([...screens].sort(), [
        "SC-01",
        "SC-02",
        "SC-03",
        "SC-04",
        "SC-05",
        "SC-06",
        "SC-07",
        "SC-08",
        "SC-09",
    ]);

    for (const fixtureCase of screenCases) {
        if (fixtureCase.fixture === null) {
            continue;
        }
        const fixtureUrl = new URL(`../../../${fixtureCase.fixture}`, import.meta.url);
        const fixture = JSON.parse(await readFile(fixtureUrl, "utf8")) as {
            schema_ref: string;
            expect: string;
            data: unknown;
        };
        assert.equal(fixture.expect, "valid", fixtureCase.fixture);
        const result = validator.validate(fixture.schema_ref, fixture.data);
        assert.equal(result.valid, true, `${fixtureCase.fixture}: ${result.errors.join(", ")}`);
    }

    const requiredStates: Record<string, string[]> = {
        "SC-01": ["loading", "empty", "error", "expired"],
        "SC-02": ["empty", "loading", "error", "partial", "ready", "source_changed", "no_match"],
        "SC-03": ["empty", "loading", "error", "cancelled", "completed", "no_match"],
        "SC-04": ["empty", "loading", "pending", "error", "expired", "rejected"],
        "SC-05": ["loading", "empty", "error", "expired", "source_changed", "no_match", "budget_exceeded"],
        "SC-06": ["empty", "loading", "error", "expired", "source_changed"],
        "SC-07": ["loading", "empty", "error", "expired", "source_changed", "no_match", "budget_exceeded"],
        "SC-08": ["queued", "running", "ready", "partial", "error", "source_changed"],
        "SC-09": ["loading", "empty", "error", "budget_exceeded"],
    };
    for (const [screen, required] of Object.entries(requiredStates)) {
        const states = new Set(
            screenCases.filter((fixtureCase) => fixtureCase.screen === screen).map((fixtureCase) => fixtureCase.state),
        );
        for (const state of required) {
            assert.ok(states.has(state), `${screen} should cover ${state}.`);
        }
    }
});

test("forms reject blank input and bounded previews never retain long source text", () => {
    assert.equal(isBootstrapCodeValid("  "), false);
    assert.equal(isBootstrapCodeValid("short"), false);
    assert.equal(isBootstrapCodeValid("one-time-code"), true);
    assert.equal(isProjectFormValid("", "/project"), false);
    assert.equal(isProjectFormValid("Project", ""), false);
    assert.equal(isProjectFormValid("Project", "/project"), true);
    assert.equal(isSourcePathValid(" "), false);
    assert.equal(isSourcePathValid("/notes/design.md"), true);
    assert.equal(isPdfPathValid("/docs/input.PDF"), true);
    assert.equal(isPdfPathValid("/docs/input.md"), false);
    assert.equal(boundedPreview("x".repeat(1000), 120).length, 121);
    assert.equal(boundedPreview("short", 120), "short");
});

test("question keyboard handling preserves IME composition and Shift+Enter", () => {
    assert.equal(shouldSubmitQuestionOnEnter("Enter", false, false, 13), true);
    assert.equal(shouldSubmitQuestionOnEnter("Enter", true, false, 13), false);
    assert.equal(shouldSubmitQuestionOnEnter("Enter", false, true, 13), false);
    assert.equal(shouldSubmitQuestionOnEnter("Enter", false, false, 229), false);
});

test("disconnection disables project, pointer, read, and PDF operations", () => {
    const markup = render(
        createElement(
            "div",
            null,
            createElement(ProjectPanel, { canMutate: false }),
            createElement(PointerPanel, { canMutate: false }),
            createElement(PointerReadPanel, { canRead: false }),
            createElement(PdfParsePanel, { canMutate: false }),
        ),
    );

    for (const testId of [
        "project-register",
        "source-register",
        "source-unregister",
        "runtime-delete",
        "read-next",
        "pdf-parse",
    ]) {
        assert.match(markup, new RegExp(`disabled=""[^>]*data-testid="${testId}"`), `${testId} must be disabled.`);
    }
    assert.ok(markup.includes("연결을 복구한 뒤 등록·삭제 요청을 다시 시도하세요."));
    assert.ok(markup.includes("연결 복구 후 범위를 다시 조회하세요."));
});

test("rendered UI keeps actions distinct, labeled, and free of opaque pointer URLs", () => {
    const snapshot = fixtureAdapter.runs[0]!;
    const controller = new RunController(
        new FixtureRunClient(),
        snapshot.session_id,
        snapshot.workspace_id,
        () => "ui-test-idempotency-key",
        () => Date.parse("2026-11-04T09:01:00Z"),
    );
    controller.restore(snapshot);
    const markup = [
        render(createElement(App)),
        render(createElement(ConversationPanel, { controller, state: controller.getSnapshot() })),
        render(createElement(ApprovalCard, { controller, state: controller.getSnapshot() })),
    ].join("");

    for (const label of [
        "승인 검토",
        "거절 검토",
        "취소 요청",
        "등록 해제",
        "저장 결과 삭제",
        "질문 입력",
        "Shift+Enter로 줄 바꿈",
    ]) {
        assert.ok(markup.includes(label), `Expected accessible action "${label}".`);
    }
    assert.ok(markup.includes('aria-live="polite"'));
    assert.ok(markup.includes('for="question-input"'));
    for (const stateLabel of [
        "로컬 서비스 응답 확인 중",
        "프로젝트가 등록되지 않은 경우",
        "질문을 입력해 시작하세요",
        "이 범위에 표시할 텍스트가 없습니다",
        "승인 시간이 만료됐습니다",
        "일치 항목이 없으면",
        "원본 파일이 변경됐습니다",
        "텍스트 추출 중",
        "입력 한도 검증 전",
    ]) {
        assert.ok(markup.includes(stateLabel), `Expected fixture state "${stateLabel}" to render.`);
    }
    assert.equal(markup.includes("securecode://"), false);
    assert.equal(markup.includes("root_path"), false);
    controller.dispose();
});

test("failed run snapshot renders a terminal failure without hiding the interrupted answer", () => {
    const completed = fixtureAdapter.runs[1]!;
    const failed = {
        ...completed,
        status: "failed" as const,
        terminal: {
            ...completed.terminal!,
            status: "failed" as const,
            reason_code: "PROVIDER_ERROR" as const,
            message: "모델 요청에 실패했습니다.",
        },
    };
    const controller = new RunController(
        new FixtureRunClient(),
        failed.session_id,
        failed.workspace_id,
        () => "ui-test-idempotency-key",
        () => Date.parse("2026-11-04T09:01:00Z"),
    );
    controller.restore(failed);
    const markup = render(createElement(ConversationPanel, { controller, state: controller.getSnapshot() }));

    assert.ok(markup.includes("실패"));
    assert.ok(markup.includes("중단 전 결과"));
    assert.ok(markup.includes("모델 요청에 실패했습니다."));
    controller.dispose();
});

test("completed run snapshot renders its successful terminal state", () => {
    const completed = fixtureAdapter.runs[1]!;
    const controller = new RunController(
        new FixtureRunClient(),
        completed.session_id,
        completed.workspace_id,
        () => "ui-test-idempotency-key",
        () => Date.parse("2026-11-04T09:01:00Z"),
    );
    controller.restore(completed);
    const markup = render(createElement(ConversationPanel, { controller, state: controller.getSnapshot() }));

    assert.ok(markup.includes("완료"));
    assert.ok(markup.includes("질문"));
    controller.dispose();
});

test("approval review shows the complete bounded command before enabling approval", () => {
    const snapshot = fixtureAdapter.runs[0]!;
    const approval = snapshot.pending_approvals[0]!;
    const content = `reviewed-prefix ${"safe preview ".repeat(30)} COMMAND_TAIL_REQUIRES_REVIEW`;
    const controller = new RunController(
        new FixtureRunClient(),
        snapshot.session_id,
        snapshot.workspace_id,
        undefined,
        () => Date.parse("2026-11-04T09:01:00Z"),
    );
    controller.restore({
        ...snapshot,
        pending_approvals: [
            { ...approval, review: { ...approval.review, content, reviewable: true, content_truncated: false } },
        ],
    });
    const markup = render(createElement(ApprovalCard, { controller, state: controller.getSnapshot() }));
    assert.equal(controller.canDecideApproval(approval.approval_id, "approve"), true);
    assert.ok(markup.includes(content), "Approval must never hide an executable command suffix.");
    controller.dispose();
});

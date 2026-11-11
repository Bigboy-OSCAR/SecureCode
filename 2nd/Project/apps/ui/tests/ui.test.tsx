/** Smoke tests for the UI's initial semantic layout and reusable presentation components. */
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { createElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ContractValidator } from "@securecode/contracts";
import screenCases from "../../../tests/fixtures/ui/screen-cases.json";
import { ApiHttpClient } from "../src/api/httpClient.js";
import { LiveConnectionPanel } from "../src/features/settings/components/LiveConnectionPanel.js";
import { ProjectDialog } from "../src/features/workspace/components/ProjectDialog.js";
import { App } from "../src/app/App.js";
import { Alert, Button, InputField, StatusBadge } from "../src/components/index.js";
import { fixtureAdapter } from "./support/fixtureAdapter.js";
import { FixtureRunClient } from "./support/fixtureRunClient.js";
import { ApprovalCard } from "../src/features/approvals/components/ApprovalCard.js";
import { ConversationPanel } from "../src/features/chat/components/ConversationPanel.js";
import { RunController } from "../src/features/chat/model/runController.js";
import { shouldSubmitQuestionOnEnter } from "../src/features/chat/model/questionInput.js";
import { isBootstrapCodeValid } from "../src/features/settings/model/inputValidation.js";
import { isProjectFormValid } from "../src/features/project/model/projectForm.js";
import { isSourcePathValid } from "../src/features/pointers/model/pointerForm.js";
import { boundedPreview } from "../src/features/shared/model/boundedPreview.js";

function render(element: ReactNode): string {
    return renderToStaticMarkup(createElement("div", null, element));
}

test("live feature screens render their stable identifiers", () => {
    const markup = render(createElement(App));

    for (const screen of ["context", "pointers", "pointer-read", "pdf"]) {
        assert.ok(markup.includes(`data-testid="screen-${screen}"`), `Expected ${screen} screen to render.`);
    }
    assert.ok(markup.includes('href="#main-content"'));
    for (const match of markup.matchAll(/href="#([^"]+)"/g)) {
        assert.ok(markup.includes(`id="${match[1]}"`), `Navigation target ${match[1]} must exist.`);
    }
    const identifiers = [...markup.matchAll(/data-testid="([^"]+)"/g)].map((match) => match[1]);
    assert.equal(new Set(identifiers).size, identifiers.length, "data-testid values should be unique per screen.");
    assert.ok(markup.includes("LocalDesk"));
    assert.ok(markup.includes("프로젝트 추가"));
    assert.ok(markup.includes("대화 검색"));
    const connection = render(
        createElement(LiveConnectionPanel, {
            api: new ApiHttpClient(),
            connected: false,
            health: null,
            settings: null,
            onAuthenticated: () => {},
            onStatus: () => {},
        }),
    );
    const codePattern = connection.match(/id="connection-code"[^>]*pattern="([^"]+)"/)?.[1];
    assert.ok(codePattern);
    assert.doesNotThrow(() => new RegExp(codePattern, "v"));
});

test("live application exposes real index, context, pointer, and PDF workflows behind host auth", () => {
    const markup = render(createElement(App));

    assert.ok(markup.includes("연결 설정"));
    assert.ok(markup.includes("R0 원문 · 컨텍스트 예산"));
    assert.ok(markup.includes("Source · Runtime Pointer"));
    assert.ok(markup.includes("PDF parsing job"));
    assert.ok(markup.includes("지정한 파일 등록"));
    assert.ok(markup.includes("전체 본문 자동 다운로드를 하지 않습니다"));
    assert.ok(markup.includes("브라우저는 디스크 파일을 읽지 않습니다"));
    assert.ok(markup.includes("이 기기에서만 실행·저장"));
    assert.equal(markup.includes("fixture"), false);
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
    assert.equal(boundedPreview("x".repeat(1000), 120).length, 121);
    assert.equal(boundedPreview("short", 120), "short");
});

test("question keyboard handling preserves IME composition and Shift+Enter", () => {
    assert.equal(shouldSubmitQuestionOnEnter("Enter", false, false, 13), true);
    assert.equal(shouldSubmitQuestionOnEnter("Enter", true, false, 13), false);
    assert.equal(shouldSubmitQuestionOnEnter("Enter", false, true, 13), false);
    assert.equal(shouldSubmitQuestionOnEnter("Enter", false, false, 229), false);
});

test("unauthenticated live UI disables mutations and does not offer unscoped pointer actions", () => {
    const markup = render(createElement(App));

    const projectMarkup = render(
        createElement(ProjectDialog, { open: true, connected: false, onClose: () => {}, onRegister: async () => {} }),
    );
    assert.match(projectMarkup, /disabled=""[^>]*data-testid="project-register"/);
    for (const testId of ["live-source-register"]) {
        assert.match(markup, new RegExp(`disabled=""[^>]*data-testid="${testId}"`), `${testId} must be disabled.`);
    }
    assert.equal(markup.includes(">등록 해제</button>"), false);
    assert.equal(markup.includes(">저장 결과 삭제</button>"), false);
});

test("rendered live UI keeps actions distinct, labeled, and free of opaque pointer URLs", () => {
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

    for (const label of ["승인 검토", "거절 검토", "취소 요청", "질문 입력", "Shift+Enter로 줄 바꿈"]) {
        assert.ok(markup.includes(label), `Expected accessible action "${label}".`);
    }
    assert.ok(markup.includes('aria-live="polite"'));
    assert.ok(markup.includes('for="question-input"'));
    assert.ok(markup.includes("승인 대기 중"));
    assert.ok(markup.includes("지정한 파일 등록"));
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

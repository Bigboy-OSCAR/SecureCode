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
import { isBootstrapCodeValid } from "../src/features/settings/model/inputValidation.js";
import { isProjectFormValid } from "../src/features/project/model/projectForm.js";
import { isPdfPathValid, isSourcePathValid } from "../src/features/pointers/model/pointerForm.js";
import { boundedPreview } from "../src/features/shared/model/boundedPreview.js";

function render(element: ReactNode): string {
    return renderToStaticMarkup(createElement("div", null, element));
}

test("all feature screens render their stable identifiers", () => {
    const markup = render(createElement(App));

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

test("rendered UI keeps actions distinct, labeled, and free of opaque pointer URLs", () => {
    const markup = render(createElement(App));

    for (const label of ["승인 검토", "거절 검토", "취소 요청", "등록 해제", "저장 결과 삭제", "질문 입력"]) {
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
});

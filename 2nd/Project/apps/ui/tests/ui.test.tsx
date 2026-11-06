/** Smoke tests for the UI's initial semantic layout and reusable presentation components. */
import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { App } from "../src/app/App.js";
import { Alert, Button, InputField, StatusBadge } from "../src/components/index.js";

function render(element: ReactNode): string {
    return renderToStaticMarkup(createElement("div", null, element));
}

test("initial app exposes project, conversation, context, pointer, and settings regions", () => {
    const markup = render(createElement(App));

    for (const label of ["프로젝트 선택", "대화 · 코드 작업", "관련 코드", "등록 자료 · 실행 결과", "설정"]) {
        assert.ok(markup.includes(label), `Expected initial UI to include "${label}".`);
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

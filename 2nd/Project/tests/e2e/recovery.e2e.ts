/** Real stack acceptance for reload, lost create/approval responses and bounded JSON reads. */
import assert from "node:assert/strict";
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { after, before, it } from "node:test";
import { startE2E, type E2E } from "./support/e2eStack.js";
import {
    ask,
    buildIndex,
    decideApproval,
    openContext,
    registerProject,
    registerSource,
    selectPointer,
    startSession,
    waitRunStatus,
} from "./support/uiActions.js";

let e2e: E2E;
before(async () => {
    e2e = await startE2E();
    await registerProject(e2e.page, "recovery", e2e.files.projectDir);
    await buildIndex(e2e.page);
    await startSession(e2e.page, "recovery");
});
after(async () => {
    await e2e?.stop();
});

it("authentication loss can be renewed without replacing the active run", async () => {
    const { page, fake } = e2e;
    fake.script([{ hold: true }]);
    const before = fake.requests.length;
    await ask(page, "인증을 복구해도 실행을 유지하세요");
    await waitRunStatus(page, "실행 중");
    await page.context().clearCookies();
    await page.reload();
    await page.locator(".desk-connect-prompt").getByRole("button", { name: "연결 설정", exact: true }).click();
    const code = await e2e.reissueCode();
    await page.getByLabel("연결 코드").fill(code);
    await page.getByRole("button", { name: "연결", exact: true }).click();
    await page.getByText("호스트 상태: ok").waitFor();
    await page.reload();
    await waitRunStatus(page, "실행 중");
    assert.equal(fake.requests.length, before + 1);
    await page.getByTestId("run-cancel").click();
    await waitRunStatus(page, "취소됨");
});

it("reload restores an active run and cancelling it does not create a second model request", async () => {
    const { page, fake } = e2e;
    fake.script([{ hold: true }]);
    const before = fake.requests.length;
    await ask(page, "새로고침 뒤에도 이 실행을 유지하세요");
    await waitRunStatus(page, "실행 중");
    await page.reload();
    await waitRunStatus(page, "실행 중");
    assert.equal(fake.requests.length, before + 1);
    await page.getByTestId("run-cancel").click();
    await waitRunStatus(page, "취소됨");
    assert.match(await page.locator("#screen-chat").innerText(), /새로고침 뒤에도 이 실행을 유지하세요/);
});

it("a lost create response is recovered after reload without submitting the question twice", async () => {
    const { page, fake } = e2e;
    fake.script([{ text: "유실된 응답의 원래 실행입니다." }]);
    let createCalls = 0;
    const pattern = "**/api/v1/sessions/*/runs";
    await page.route(pattern, async (route) => {
        if (route.request().method() !== "POST") {
            await route.continue();
            return;
        }
        createCalls += 1;
        await route.fetch();
        await route.abort("connectionreset");
    });
    await ask(page, "응답 유실 복구 검증");
    await page.locator("#screen-chat [role=alert]").first().waitFor();
    await page.unroute(pattern);
    await page.reload();
    await waitRunStatus(page, "완료");
    assert.match(await page.getByTestId("answer").last().innerText(), /유실된 응답의 원래 실행입니다/);
    assert.equal(createCalls, 1);
});

it("a lost approval response recovers the decided snapshot without repeating the command", async () => {
    const { page, fake } = e2e;
    fake.script([{ tool: "run_command", args: { command: "node gen.js" } }, { text: "승인 결과 복구 완료" }]);
    let decisions = 0;
    const pattern = "**/api/v1/runs/*/approvals/*";
    await page.route(pattern, async (route) => {
        decisions += 1;
        await route.fetch();
        await route.abort("connectionreset");
    });
    await ask(page, "승인 응답 유실 검증");
    await page.getByTestId("approval-meta").waitFor();
    await decideApproval(page, "approve");
    await waitRunStatus(page, "완료");
    await page.unroute(pattern);
    assert.equal(decisions, 1);
    assert.equal(await page.getByTestId("tool-row").count(), 1);
    assert.match(await page.getByTestId("answer").last().innerText(), /승인 결과 복구 완료/);
});

it("JSON Pointer reads only the selected value and large JSON offers bounded line or byte reads", async () => {
    const { page, files } = e2e;
    const small = join(files.externalDir, "small.json");
    const large = join(files.externalDir, "large.json");
    writeFileSync(small, JSON.stringify({ selected: { value: "SELECTED-VALUE" }, unrelated: "UNSELECTED-VALUE" }));
    writeFileSync(large, '{"first":"BOUNDED-FIRST-LINE",\n"padding":"' + "x".repeat(8 * 1024 * 1024) + '"}\n');
    await registerSource(page, small, "small.json");
    await selectPointer(page, "small.json");
    await page.getByLabel("읽기 범위").selectOption("json_path");
    await page.getByLabel("JSON Pointer 경로").fill("/selected/value");
    await page.getByRole("button", { name: "범위 읽기", exact: true }).click();
    await page
        .getByTestId("live-pointer-preview")
        .getByText(/SELECTED-VALUE/)
        .waitFor();
    assert.doesNotMatch(await page.getByTestId("live-pointer-preview").innerText(), /UNSELECTED-VALUE/);
    await registerSource(page, large, "large.json");
    await selectPointer(page, "large.json");
    assert.equal(await page.locator('#pointer-selector-kind option[value="json_path"]').count(), 0);
    await page.getByText(/JSON 구조 조회는 8 MiB 이하/).waitFor();
    await page.getByLabel("읽기 범위").selectOption("line");
    await page.getByLabel("시작 줄").fill("1");
    await page.getByLabel("끝 범위 (선택)").fill("1");
    await page.getByRole("button", { name: "범위 읽기", exact: true }).click();
    await page
        .getByTestId("live-pointer-preview")
        .getByText(/BOUNDED-FIRST-LINE/)
        .waitFor();
    assert.ok((await page.getByTestId("live-pointer-preview").innerText()).length < 4096);
});

it("a delayed index response from the previous project cannot overwrite the selected project", async () => {
    const { page, files } = e2e;
    const workspaceId = await page.evaluate(async () => {
        const response = await fetch("/api/v1/workspaces");
        const body = (await response.json()) as { items: { workspace_id: string; display_name: string }[] };
        return body.items.find((item) => item.display_name === "recovery")?.workspace_id;
    });
    assert.ok(workspaceId);
    await registerProject(page, "other-project", files.polyglotDir);
    await openContext(page);
    let captured!: () => void;
    let release!: () => void;
    const ready = new Promise<void>((done) => {
        captured = done;
    });
    const held = new Promise<void>((done) => {
        release = done;
    });
    const pattern = `**/api/v1/workspaces/${workspaceId}/index`;
    await page.route(pattern, async (route) => {
        const response = await route.fetch();
        captured();
        await held;
        await route.fulfill({ response });
    });
    await page.getByRole("button", { name: "recovery", exact: true }).click();
    await ready;
    await page.getByRole("button", { name: "other-project", exact: true }).click();
    await page.getByText("revision 없음 · not_indexed", { exact: true }).waitFor();
    const oldResponse = page.waitForResponse((response) => response.url().endsWith(`/workspaces/${workspaceId}/index`));
    release();
    await (await oldResponse).finished();
    assert.match(await page.getByTestId("screen-context").innerText(), /revision 없음 · not_indexed/);
    assert.ok(await page.getByLabel("심볼·파일 검색어").isDisabled());
    await page.unroute(pattern);
});

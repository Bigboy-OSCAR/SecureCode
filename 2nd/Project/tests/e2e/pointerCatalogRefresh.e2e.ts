/** Reopening the retained drawer must reload catalogs without replacing the active conversation. */
import assert from "node:assert/strict";
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { after, before, it } from "node:test";
import type { PointerListResult, SessionListResponse, WorkspaceListResponse } from "@securecode/contracts";
import { startE2E, type E2E } from "./support/e2eStack.js";
import {
    ask,
    buildIndex,
    decideApproval,
    openContext,
    pointerOption,
    registerProject,
    selectPointer,
    waitRunStatus,
} from "./support/uiActions.js";

let e2e: E2E;
before(async () => {
    e2e = await startE2E();
    await registerProject(e2e.page, "catalog-refresh", e2e.files.projectDir);
    await buildIndex(e2e.page);
    writeFileSync(join(e2e.files.projectDir, "notes.txt"), "SOURCE-OLD\n");
    writeFileSync(join(e2e.files.projectDir, "approved.txt"), "SOURCE-ADDED\n");
});
after(async () => {
    await e2e?.stop();
});

async function closeDrawer(): Promise<void> {
    await e2e.page.locator("#context-panel").getByRole("button", { name: "닫기", exact: true }).click();
}

it("refreshes tool-created sources and revisions on reopen, preserving unchanged selections and an active run", async () => {
    const { page, fake, files } = e2e;
    fake.script([{ tool: "read_file", args: { path: "notes.txt" } }, { text: "원본 확인 완료" }]);
    await ask(page, "notes.txt를 읽어 주세요");
    await waitRunStatus(page, "완료");
    await openContext(page);
    await pointerOption(page, "notes.txt").waitFor();
    assert.match(await pointerOption(page, "notes.txt").innerText(), /revision 1/);
    await selectPointer(page, "notes.txt");
    await page.getByRole("button", { name: "범위 읽기", exact: true }).click();
    await page.getByTestId("live-pointer-preview").getByText("SOURCE-OLD", { exact: true }).waitFor();
    await closeDrawer();
    await openContext(page);
    assert.ok(await pointerOption(page, "notes.txt").locator("input").isChecked());
    assert.match(await page.getByTestId("live-pointer-preview").innerText(), /SOURCE-OLD/);
    await closeDrawer();
    await page.getByRole("button", { name: "선택 자료 포함 해제" }).click();

    writeFileSync(join(files.projectDir, "notes.txt"), "SOURCE-NEW updated content\n");
    fake.script([
        { tool: "read_file", args: { path: "notes.txt" } },
        { tool: "read_file", args: { path: "approved.txt" } },
        { hold: true },
    ]);
    await ask(page, "두 파일을 확인하고 기다려 주세요");
    const turn = page.getByTestId("conversation-turn").last();
    await turn.getByTestId("tool-row").filter({ hasText: "파일 부분 읽기 · 완료" }).nth(1).waitFor();
    const activeId = await turn.getAttribute("data-run-id");
    const requests = fake.requests.length;
    await openContext(page);
    await pointerOption(page, "approved.txt").waitFor();
    assert.match(await pointerOption(page, "notes.txt").innerText(), /revision 2/);
    assert.equal(await page.getByTestId("live-pointer-preview").count(), 0, "superseded source selection is cleared");
    assert.equal(await turn.getAttribute("data-run-id"), activeId);
    assert.ok(await page.getByTestId("run-cancel").isVisible());
    assert.equal(fake.requests.length, requests, "opening the drawer does not re-run the model or tools");
    await closeDrawer();
    await page.getByTestId("run-cancel").click();
    await waitRunStatus(page, "취소됨");
});

it("reloads runtime records after an output is removed while the drawer is closed", async () => {
    const { page, fake } = e2e;
    fake.script([{ tool: "run_command", args: { command: "node gen.js" } }, { text: "로그 생성 완료" }]);
    await ask(page, "gen.js를 실행해 주세요");
    await page.getByTestId("approval-meta").waitFor();
    await decideApproval(page, "approve");
    await waitRunStatus(page, "완료");
    await openContext(page);
    const row = page
        .getByTestId("screen-pointers")
        .locator("li")
        .filter({ hasText: /^output-/ });
    await row.waitFor();
    await closeDrawer();
    const deleted = await page.evaluate(async () => {
        const workspaces = (await (await fetch("/api/v1/workspaces")).json()) as WorkspaceListResponse;
        const workspace = workspaces.items[0]?.workspace_id;
        if (!workspace) return false;
        const sessions = (await (
            await fetch(`/api/v1/workspaces/${workspace}/sessions`)
        ).json()) as SessionListResponse;
        const session = sessions.items[0]?.session_id;
        if (!session) return false;
        const list = (await (
            await fetch(`/api/v1/workspaces/${workspace}/pointers?kind=runtime&session_id=${session}&limit=100`)
        ).json()) as PointerListResult;
        const pointer = list.items[0]?.pointer;
        if (!pointer) return false;
        const result = await fetch("/api/v1/pointers", {
            method: "DELETE",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({
                schema_version: "1",
                idempotency_key: crypto.randomUUID(),
                kind: "runtime",
                pointer,
                workspace_id: workspace,
                session_id: session,
            }),
        });
        return result.ok;
    });
    assert.ok(deleted);
    await openContext(page);
    await page.getByText("저장된 실행 결과가 없습니다.", { exact: true }).waitFor();
    assert.equal(await row.count(), 0);
});

it("preserves a selection from a later catalog page but clears a confirmed new revision", async () => {
    const { page, files } = e2e;
    await closeDrawer();
    let firstPageName = "notes.txt";
    let approvedPointer = "";
    const pattern = "**/api/v1/workspaces/*/pointers?kind=source*";
    await page.route(pattern, async (route) => {
        const url = new URL(route.request().url());
        const secondPage = url.searchParams.has("cursor");
        url.searchParams.delete("cursor");
        const response = await route.fetch({ url: url.toString() });
        const body = (await response.json()) as PointerListResult;
        approvedPointer = body.items.find((item) => item.display_name === "approved.txt")?.pointer ?? "";
        await route.fulfill({
            response,
            json: {
                ...body,
                items: body.items.filter((item) => (item.display_name === firstPageName) !== secondPage),
                page: { limit: 1, has_more: !secondPage, next_cursor: secondPage ? null : "catalog-test-next" },
            },
        });
    });
    try {
        await openContext(page);
        await page.getByRole("button", { name: "다음 Source 목록" }).click();
        await selectPointer(page, "approved.txt");
        await page.getByRole("button", { name: "범위 읽기", exact: true }).click();
        await page.getByTestId("live-pointer-preview").getByText("SOURCE-ADDED", { exact: true }).waitFor();
        await closeDrawer();
        await openContext(page);
        await page.getByRole("button", { name: "다음 Source 목록" }).waitFor();
        assert.equal(await pointerOption(page, "approved.txt").count(), 0, "the selected item is outside page one");
        assert.match(await page.getByTestId("live-pointer-preview").innerText(), /SOURCE-ADDED/);
        await closeDrawer();

        writeFileSync(join(files.projectDir, "approved.txt"), "SOURCE-ADDED-REVISION-TWO\n");
        assert.ok(approvedPointer);
        const refreshed = await page.evaluate(async (pointer) => {
            const workspace = new URL(pointer).pathname.split("/")[1];
            const response = await fetch(`/api/v1/workspaces/${workspace}/sources`, {
                method: "POST",
                headers: { "content-type": "application/json" },
                body: JSON.stringify({
                    schema_version: "1",
                    idempotency_key: crypto.randomUUID(),
                    operation: "refresh",
                    pointer,
                }),
            });
            return response.ok;
        }, approvedPointer);
        assert.ok(refreshed);
        firstPageName = "approved.txt";
        await openContext(page);
        await pointerOption(page, "approved.txt").waitFor();
        assert.match(await pointerOption(page, "approved.txt").innerText(), /revision 2/);
        assert.equal(await page.getByTestId("live-pointer-preview").count(), 0);
    } finally {
        await page.unroute(pattern);
    }
});

it("does not let an older catalog response replace a completed UI registration", async () => {
    const { page, files } = e2e;
    await closeDrawer();
    await openContext(page);
    const addedPath = join(files.externalDir, "registered-after-refresh.txt");
    writeFileSync(addedPath, "NEW-UI-SOURCE\n");
    let registered!: () => void;
    let releaseRegister!: () => void;
    let captured!: () => void;
    let releaseList!: () => void;
    const registrationStarted = new Promise<void>((done) => {
        registered = done;
    });
    const registerHeld = new Promise<void>((done) => {
        releaseRegister = done;
    });
    const listCaptured = new Promise<void>((done) => {
        captured = done;
    });
    const listHeld = new Promise<void>((done) => {
        releaseList = done;
    });
    const registerPattern = "**/api/v1/workspaces/*/sources";
    const listPattern = "**/api/v1/workspaces/*/pointers?kind=source*";
    await page.route(registerPattern, async (route) => {
        registered();
        await registerHeld;
        await route.continue();
    });
    try {
        await page.getByLabel("등록할 외부 파일의 호스트 경로").fill(addedPath);
        await page.getByRole("button", { name: "지정한 파일 등록" }).click();
        await registrationStarted;
        await closeDrawer();
        await page.route(listPattern, async (route) => {
            const response = await route.fetch();
            captured();
            await listHeld;
            await route.fulfill({ response });
        });
        await openContext(page);
        await listCaptured;
        releaseRegister();
        await pointerOption(page, "registered-after-refresh.txt").waitFor();
        const oldResponse = page.waitForResponse((response) => response.url().includes("pointers?kind=source"));
        releaseList();
        await (await oldResponse).finished();
        assert.ok(await pointerOption(page, "registered-after-refresh.txt").isVisible());
        assert.ok(await pointerOption(page, "registered-after-refresh.txt").locator("input").isChecked());
    } finally {
        releaseRegister();
        releaseList();
        await page.unroute(registerPattern);
        await page.unroute(listPattern);
    }
});

/** Conversation context menus, persistent removal, undo and navigation during delayed responses. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { after, before, it } from "node:test";
import type { Locator, Page, Request, Response } from "playwright-core";
import { startE2E, type E2E } from "./support/e2eStack.js";
import { ask, buildIndex, registerProject, waitRunStatus } from "./support/uiActions.js";

const PROJECT = "chat-removal-main";
const OTHER = "chat-removal-other";
const FIRST = "첫 번째 보관할 대화";
const SECOND = "두 번째 보관할 대화";
const THIRD = "세 번째 보관할 대화";
let e2e: E2E;
let originalFile: string;

function chat(page: Page, name: string): Locator {
    return page.locator(".desk-chat-list").getByRole("button", { name, exact: true });
}

function deferred(): { promise: Promise<void>; resolve: () => void } {
    let resolve!: () => void;
    const promise = new Promise<void>((done) => {
        resolve = done;
    });
    return { promise, resolve };
}

async function flushView(page: Page): Promise<void> {
    await page.evaluate(
        () => new Promise<void>((done) => requestAnimationFrame(() => requestAnimationFrame(() => done()))),
    );
}

async function selectProject(page: Page, name: string): Promise<void> {
    await page.getByRole("button", { name, exact: true }).click();
    await page.locator(".desk-chat-header").getByText(name, { exact: true }).waitFor();
    await page.locator('.desk-messages[aria-busy="false"]').waitFor();
}

async function createChat(title: string): Promise<void> {
    const { page, fake } = e2e;
    await page
        .locator(".desk-project")
        .filter({ has: page.getByRole("button", { name: PROJECT, exact: true }) })
        .hover();
    await page.getByRole("button", { name: `${PROJECT} 새 대화`, exact: true }).click();
    await page.getByRole("heading", { name: "이 폴더에서 시작해 볼까요?", exact: true }).waitFor();
    await page.locator('.desk-messages[aria-busy="false"]').waitFor();
    fake.script([{ text: `${title}의 원래 답변입니다.` }]);
    await ask(page, title);
    await waitRunStatus(page, "완료");
}

async function removeChat(page: Page, title: string): Promise<Response> {
    await chat(page, title).click({ button: "right" });
    const response = page.waitForResponse(
        (candidate) => candidate.request().method() === "DELETE" && /\/api\/v1\/sessions\/[^/]+$/.test(candidate.url()),
    );
    await page.getByRole("menuitem", { name: "대화 삭제", exact: true }).click();
    return response;
}

before(async () => {
    e2e = await startE2E();
    originalFile = readFileSync(e2e.files.billingPath, "utf8");
    await registerProject(e2e.page, PROJECT, e2e.files.projectDir);
    await buildIndex(e2e.page);
    e2e.fake.script([{ text: `${FIRST}의 원래 답변입니다.` }]);
    await ask(e2e.page, FIRST);
    await waitRunStatus(e2e.page, "완료");
    await createChat(SECOND);
    await createChat(THIRD);
    await registerProject(e2e.page, OTHER, e2e.files.polyglotDir);
    await selectProject(e2e.page, PROJECT);
    await chat(e2e.page, THIRD).click();
    await e2e.page.getByTestId("answer").getByText(`${THIRD}의 원래 답변입니다.`, { exact: true }).waitFor();
});

after(async () => {
    await e2e?.stop();
});

it("right-click and keyboard menus target a conversation without changing the current selection", async () => {
    const { page } = e2e;
    await chat(page, FIRST).click({ button: "right" });
    await page.getByRole("menu", { name: `${FIRST} 대화 메뉴`, exact: true }).waitFor();
    assert.equal(await page.getByRole("menuitem", { name: "대화 삭제", exact: true }).count(), 1);
    assert.ok((await chat(page, THIRD).getAttribute("class"))?.split(/\s+/).includes("selected"));
    await page.keyboard.press("Escape");
    await page.getByRole("menu").waitFor({ state: "detached" });
    assert.equal(await chat(page, FIRST).evaluate((element) => document.activeElement === element), true);
    await page.keyboard.press("Shift+F10");
    await page.getByRole("menuitem", { name: "대화 삭제", exact: true }).waitFor();
    await page.locator(".desk-chat-title").click();
    await page.getByRole("menu").waitFor({ state: "detached" });
    assert.equal(await page.locator(".desk-chat-list button").count(), 3);
});

it("an active conversation cannot be deleted and keeps its running state", async () => {
    const { page, fake } = e2e;
    fake.script([{ hold: true }]);
    await ask(page, "삭제 차단을 확인하는 동안 기다리세요");
    await waitRunStatus(page, "실행 중");
    assert.equal((await removeChat(page, THIRD)).status(), 409);
    await page.getByRole("menu").waitFor({ state: "detached" });
    assert.equal(await chat(page, THIRD).count(), 1);
    assert.equal(await page.getByTestId("run-cancel").count(), 1);
    await page.getByTestId("run-cancel").click();
    await waitRunStatus(page, "취소됨");
});

it("removing an unselected conversation preserves the selected one and undo restores its answer", async () => {
    const { page } = e2e;
    assert.equal((await removeChat(page, FIRST)).status(), 200);
    await chat(page, FIRST).waitFor({ state: "detached" });
    assert.ok((await chat(page, THIRD).getAttribute("class"))?.split(/\s+/).includes("selected"));
    assert.equal(await page.locator(".desk-chat-list button").count(), 2);
    assert.equal(await page.getByRole("dialog").count(), 0, "deletion does not require a second dialog");
    await page.getByRole("button", { name: "실행 취소", exact: true }).click();
    await chat(page, FIRST).waitFor();
    await chat(page, FIRST).click();
    await page.getByTestId("answer").getByText(`${FIRST}의 원래 답변입니다.`, { exact: true }).waitFor();
    assert.equal(await page.locator(".desk-chat-list button").count(), 3);
    assert.equal(readFileSync(e2e.files.billingPath, "utf8"), originalFile);
    assert.equal((await removeChat(page, FIRST)).status(), 200);
    await chat(page, FIRST).waitFor({ state: "detached" });
    await page.locator('.desk-messages[aria-busy="false"]').waitFor();
    const selected = page.locator(".desk-chat-list button.selected");
    assert.equal(await selected.count(), 1, "removing the selected conversation selects one remaining conversation");
    const remainingTitle = (await selected.innerText()).trim();
    assert.ok([SECOND, THIRD].includes(remainingTitle));
    await page.getByTestId("answer").getByText(`${remainingTitle}의 원래 답변입니다.`, { exact: true }).waitFor();
    await page.getByRole("button", { name: "실행 취소", exact: true }).click();
    await chat(page, FIRST).waitFor();
    await chat(page, THIRD).click();
    await page.locator('.desk-messages[aria-busy="false"]').waitFor();
});

it("a delayed conversation list cannot bring back a deleted conversation", async () => {
    const { page } = e2e;
    await page.waitForLoadState("networkidle");
    const entered = deferred();
    const release = deferred();
    const delivered = deferred();
    let delayNext = true;
    const pattern = "**/api/v1/workspaces/*/sessions?*";
    await page.route(pattern, async (route) => {
        if (!delayNext) return route.continue();
        delayNext = false;
        const response = await route.fetch();
        const sessions = (await response.json()) as { items: { session_id: string }[] };
        entered.resolve();
        await release.promise;
        const runs = sessions.items.map((session) =>
            page.waitForResponse((candidate) => candidate.url().includes(`/sessions/${session.session_id}/runs?`)),
        );
        await route.fulfill({ response });
        await Promise.all(runs.map(async (pending) => (await pending).finished()));
        delivered.resolve();
    });
    try {
        await page.getByRole("button", { name: PROJECT, exact: true }).click();
        await entered.promise;
        assert.equal((await removeChat(page, FIRST)).status(), 200);
        await chat(page, FIRST).waitFor({ state: "detached" });
        release.resolve();
        await delivered.promise;
        await flushView(page);
        assert.equal(await chat(page, FIRST).count(), 0);
        assert.equal(await page.locator(".desk-chat-list button").count(), 2);
        assert.ok((await chat(page, THIRD).getAttribute("class"))?.split(/\s+/).includes("selected"));
        assert.equal(await page.locator(".desk-inline-error").count(), 0, "an obsolete read cannot surface an error");
    } finally {
        release.resolve();
        await page.unroute(pattern);
    }
});

it("a delayed deletion does not switch back after the user selects another project", async () => {
    const { page } = e2e;
    const entered = deferred();
    const release = deferred();
    const delivered = deferred();
    const pattern = "**/api/v1/sessions/*";
    await page.route(pattern, async (route) => {
        if (route.request().method() !== "DELETE") return route.continue();
        const response = await route.fetch();
        entered.resolve();
        await release.promise;
        await route.fulfill({ response });
        delivered.resolve();
    });
    try {
        const deleting = removeChat(page, SECOND);
        await entered.promise;
        await selectProject(page, OTHER);
        release.resolve();
        await delivered.promise;
        assert.equal((await deleting).status(), 200);
        await flushView(page);
        assert.equal(await page.locator(".desk-chat-header").getByText(OTHER, { exact: true }).count(), 1);
        assert.equal(await page.locator(".desk-chat-list button").count(), 1);
    } finally {
        release.resolve();
        await page.unroute(pattern);
    }
    await selectProject(page, PROJECT);
    assert.equal(await page.locator(".desk-chat-list button").count(), 1);
    assert.equal(await chat(page, SECOND).count(), 0);
    await chat(page, THIRD).waitFor();
});

it("deleting the last selected conversation clears it, supports undo and stays deleted after reload", async () => {
    const { page } = e2e;
    let created = 0;
    const trackCreation = (request: Request): void => {
        if (request.method() === "POST" && /\/api\/v1\/sessions$/.test(request.url())) created += 1;
    };
    page.on("request", trackCreation);
    try {
        assert.equal((await removeChat(page, THIRD)).status(), 200);
        await page.locator(".desk-empty").getByRole("button", { name: "새 대화 시작", exact: true }).waitFor();
        assert.equal(await page.locator(".desk-chat-list button").count(), 0);
        assert.equal(await page.getByTestId("question-input").count(), 0);
        assert.equal(
            await page.locator(".desk-project").count(),
            2,
            "deleting a conversation does not delete its project",
        );
        await page.getByRole("button", { name: "실행 취소", exact: true }).click();
        await chat(page, THIRD).waitFor();
        await chat(page, THIRD).click();
        await page.getByTestId("answer").getByText(`${THIRD}의 원래 답변입니다.`, { exact: true }).waitFor();
        assert.equal((await removeChat(page, THIRD)).status(), 200);
        await page.locator(".desk-empty").getByRole("button", { name: "새 대화 시작", exact: true }).waitFor();
        await page.reload();
        await page.locator(".desk-empty").getByRole("button", { name: "새 대화 시작", exact: true }).waitFor();
        assert.equal(await page.locator(".desk-chat-list button").count(), 0);
        assert.equal(created, 0, "removal and reload do not create replacement conversations");
        await selectProject(page, OTHER);
        assert.equal(
            await page.locator(".desk-chat-list button").count(),
            1,
            "the other project's conversation is preserved",
        );
        assert.equal(readFileSync(e2e.files.billingPath, "utf8"), originalFile);
    } finally {
        page.off("request", trackCreation);
    }
});

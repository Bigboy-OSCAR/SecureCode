/** Project navigation, hover actions and reversible removal through the real sidebar and host. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { after, before, it } from "node:test";
import type { Locator, Page } from "playwright-core";
import { startE2E, type E2E } from "./support/e2eStack.js";
import { ask, buildIndex, registerProject, waitRunStatus } from "./support/uiActions.js";

const FIRST = "sidebar-first";
const SECOND = "sidebar-second";
const FIRST_CHAT = "첫 프로젝트 첫 대화";
const SECOND_CHAT = "첫 프로젝트 두 번째 대화";
let e2e: E2E;
let originalFile: string;

function project(page: Page, name: string): Locator {
    return page.locator(".desk-project").filter({ has: page.getByRole("button", { name, exact: true }) });
}

function newChat(page: Page, name: string): Locator {
    return page.getByRole("button", { name: `${name} 새 대화`, exact: true, includeHidden: true });
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

async function createChat(page: Page, name: string): Promise<void> {
    await project(page, name).hover();
    const created = page.waitForResponse(
        (response) => response.request().method() === "POST" && /\/api\/v1\/sessions$/.test(response.url()),
    );
    await newChat(page, name).click();
    assert.ok((await created).ok());
    await page.getByRole("heading", { name: "이 폴더에서 시작해 볼까요?", exact: true }).waitFor();
    await page.locator('.desk-messages[aria-busy="false"]').waitFor();
}

async function isPainted(locator: Locator): Promise<boolean> {
    return locator.evaluate((element) => {
        const style = getComputedStyle(element);
        return style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity) > 0;
    });
}

before(async () => {
    e2e = await startE2E();
    originalFile = readFileSync(e2e.files.billingPath, "utf8");
    await registerProject(e2e.page, FIRST, e2e.files.projectDir);
    await buildIndex(e2e.page);
    e2e.fake.script([{ text: "첫 대화 답변입니다." }]);
    await ask(e2e.page, FIRST_CHAT);
    await waitRunStatus(e2e.page, "완료");
    await createChat(e2e.page, FIRST);
    e2e.fake.script([{ text: "두 번째 대화 답변입니다." }]);
    await ask(e2e.page, SECOND_CHAT);
    await waitRunStatus(e2e.page, "완료");
    await registerProject(e2e.page, SECOND, e2e.files.polyglotDir);
});

after(async () => {
    await e2e?.stop();
});

it("hover highlights the whole project and reveals the new-chat button at the right edge without a chevron", async () => {
    const { page } = e2e;
    const row = project(page, FIRST);
    await page.locator(".desk-chat-title").click();
    const restColor = await row.evaluate((element) => getComputedStyle(element).backgroundColor);
    assert.equal(await isPainted(newChat(page, FIRST)), false, "the new-chat action is hidden at rest");
    assert.equal(await row.locator('img[src$="/imgIconDown.svg"]').count(), 0, "the unused chevron is gone");
    await row.hover();
    assert.notEqual(await row.evaluate((element) => getComputedStyle(element).backgroundColor), restColor);
    assert.equal(await isPainted(newChat(page, FIRST)), true, "hover reveals the new-chat action");
    const rowBox = await row.boundingBox();
    const buttonBox = await newChat(page, FIRST).boundingBox();
    assert.ok(rowBox && buttonBox);
    assert.ok(buttonBox.x + buttonBox.width <= rowBox.x + rowBox.width);
    assert.ok(
        rowBox.x + rowBox.width - buttonBox.x - buttonBox.width <= 16,
        "the action occupies the former chevron edge",
    );
    await page.locator(".desk-chat-title").hover();
    assert.equal(await isPainted(newChat(page, FIRST)), false, "moving away hides it again");
});

it("project clicks toggle conversations without changing selection and the hover action creates one conversation", async () => {
    const { page } = e2e;
    // Click the padding, rather than just the title text, once.
    await project(page, FIRST).click({ position: { x: 3, y: 3 } });
    await page.locator(".desk-chat-list").getByRole("button", { name: FIRST_CHAT, exact: true }).waitFor();
    assert.equal(await page.locator(".desk-chat-list button").count(), 2, "all conversations open on a single click");
    assert.equal(
        await page.locator(".desk-chat-list").getByRole("button", { name: SECOND_CHAT, exact: true }).count(),
        1,
    );
    const selectedId = await page.locator(".desk-chat-list button.selected").getAttribute("data-session-id");
    const selectedTitle = await page.locator(".desk-chat-title").innerText();
    await project(page, FIRST).locator(".desk-project-path").click();
    await page.locator(".desk-chat-list").waitFor({ state: "detached" });
    assert.equal(await page.getByRole("button", { name: FIRST, exact: true }).getAttribute("aria-expanded"), "false");
    assert.equal(await page.locator(".desk-chat-title").innerText(), selectedTitle, "collapse keeps the current chat");
    await page.getByRole("button", { name: FIRST, exact: true }).click();
    await page.locator(".desk-chat-list").getByRole("button", { name: FIRST_CHAT, exact: true }).waitFor();
    assert.equal(await page.getByRole("button", { name: FIRST, exact: true }).getAttribute("aria-expanded"), "true");
    assert.equal(await page.locator(".desk-chat-list button").count(), 2, "the next click reopens every conversation");
    assert.equal(await page.locator(".desk-chat-list button.selected").getAttribute("data-session-id"), selectedId);
    await page.getByRole("button", { name: FIRST, exact: true }).click();
    await page.locator(".desk-chat-list").waitFor({ state: "detached" });
    await createChat(page, FIRST);
    await page.locator(".desk-chat-list").getByRole("button", { name: "새 대화", exact: true }).waitFor();
    assert.equal(await page.locator(".desk-chat-list button").count(), 3);
    await page.getByRole("button", { name: SECOND, exact: true }).click();
    await page.locator(".desk-chat-header").getByText(SECOND, { exact: true }).waitFor();
    await page.locator('.desk-messages[aria-busy="false"]').waitFor();
    assert.equal(await page.locator(".desk-chat-list button").count(), 1);
});

it("a delayed new-conversation response does not switch back after another project is selected", async () => {
    const { page } = e2e;
    await page.getByRole("button", { name: FIRST, exact: true }).click();
    await page.locator(".desk-chat-list").getByRole("button", { name: FIRST_CHAT, exact: true }).waitFor();
    const entered = deferred();
    const release = deferred();
    const delivered = deferred();
    const pattern = "**/api/v1/sessions";
    await page.route(pattern, async (route) => {
        if (route.request().method() !== "POST") return route.continue();
        const response = await route.fetch();
        entered.resolve();
        await release.promise;
        await route.fulfill({ response });
        delivered.resolve();
    });
    try {
        await project(page, FIRST).hover();
        await newChat(page, FIRST).click();
        await entered.promise;
        await page.getByRole("button", { name: SECOND, exact: true }).click();
        await page.locator(".desk-chat-header").getByText(SECOND, { exact: true }).waitFor();
        await page.locator('.desk-messages[aria-busy="false"]').waitFor();
        const received = page.waitForResponse(
            (response) => response.request().method() === "POST" && /\/api\/v1\/sessions$/.test(response.url()),
        );
        release.resolve();
        await delivered.promise;
        await (await received).finished();
        await flushView(page);
        assert.equal(await page.locator(".desk-chat-header").getByText(SECOND, { exact: true }).count(), 1);
        assert.equal(
            await project(page, SECOND)
                .getAttribute("class")
                .then((value) => value?.includes("selected")),
            true,
        );
        assert.equal(
            await page.locator(".desk-chat-list button").count(),
            1,
            "the other project's conversation remains selected",
        );
    } finally {
        release.resolve();
        await page.unroute(pattern);
    }
});

it("a delayed project refresh cannot replace a conversation selected while it was loading", async () => {
    const { page } = e2e;
    await page.getByRole("button", { name: FIRST, exact: true }).click();
    await page.locator(".desk-chat-list").getByRole("button", { name: FIRST_CHAT, exact: true }).click();
    await page.getByTestId("answer").getByText("첫 대화 답변입니다.", { exact: true }).waitFor();
    await page.waitForLoadState("networkidle");
    await page.getByRole("button", { name: FIRST, exact: true }).click();
    await page.locator(".desk-chat-list").waitFor({ state: "detached" });
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
        // readChats continues through every session's run list before applying this delayed result.
        const runs = sessions.items.map((session) =>
            page.waitForResponse((candidate) => candidate.url().includes(`/sessions/${session.session_id}/runs?`)),
        );
        await route.fulfill({ response });
        await Promise.all(runs.map(async (pending) => (await pending).finished()));
        delivered.resolve();
    });
    try {
        await page.getByRole("button", { name: FIRST, exact: true }).click();
        await entered.promise;
        await page.locator(".desk-chat-list").getByRole("button", { name: SECOND_CHAT, exact: true }).click();
        await page.getByTestId("answer").getByText("두 번째 대화 답변입니다.", { exact: true }).waitFor();
        release.resolve();
        await delivered.promise;
        await flushView(page);
        assert.equal(await page.locator(".desk-chat-header").getByText(SECOND_CHAT, { exact: true }).count(), 1);
        assert.equal(
            await page.getByTestId("answer").getByText("두 번째 대화 답변입니다.", { exact: true }).count(),
            1,
        );
    } finally {
        release.resolve();
        await page.unroute(pattern);
    }
    await page.getByRole("button", { name: SECOND, exact: true }).click();
    await page.locator(".desk-chat-header").getByText(SECOND, { exact: true }).waitFor();
});

it("a delayed project refresh cannot replace a new conversation created while it was loading", async () => {
    const { page } = e2e;
    await page.getByRole("button", { name: FIRST, exact: true }).click();
    await page.locator(".desk-chat-list").getByRole("button", { name: FIRST_CHAT, exact: true }).click();
    await page.getByTestId("answer").getByText("첫 대화 답변입니다.", { exact: true }).waitFor();
    await page.waitForLoadState("networkidle");
    const initialCount = await page.locator(".desk-chat-list button").count();
    await page.getByRole("button", { name: FIRST, exact: true }).click();
    await page.locator(".desk-chat-list").waitFor({ state: "detached" });
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
        await page.getByRole("button", { name: FIRST, exact: true }).click();
        await entered.promise;
        await createChat(page, FIRST);
        release.resolve();
        await delivered.promise;
        await flushView(page);
        assert.equal(await page.getByRole("heading", { name: "이 폴더에서 시작해 볼까요?", exact: true }).count(), 1);
        assert.equal(await page.locator(".desk-chat-list button.selected").innerText(), "새 대화");
        assert.equal(
            await page.locator(".desk-chat-list button").count(),
            initialCount + 1,
            "the older refresh does not remove the new conversation from the list",
        );
    } finally {
        release.resolve();
        await page.unroute(pattern);
    }
    await page.getByRole("button", { name: SECOND, exact: true }).click();
    await page.locator(".desk-chat-header").getByText(SECOND, { exact: true }).waitFor();
});

it("adding the same folder waits for a delayed removal and keeps the restored project", async () => {
    const { page, files } = e2e;
    await page.locator('.desk-messages[aria-busy="false"]').waitFor();
    await flushView(page);
    const entered = deferred();
    const release = deferred();
    const delivered = deferred();
    const removePattern = "**/api/v1/workspaces/*";
    const createPattern = "**/api/v1/workspaces";
    let registrations = 0;
    await page.route(createPattern, async (route) => {
        if (route.request().method() === "POST") registrations += 1;
        await route.continue();
    });
    await page.route(removePattern, async (route) => {
        if (route.request().method() !== "DELETE") return route.continue();
        const response = await route.fetch();
        entered.resolve();
        await release.promise;
        await route.fulfill({ response });
        delivered.resolve();
    });
    try {
        await project(page, FIRST).click({ button: "right" });
        await page.getByRole("menuitem", { name: "프로젝트 삭제", exact: true }).click();
        await entered.promise;
        await page.getByRole("button", { name: "+ 프로젝트 추가", exact: true }).click();
        await page.getByTestId("project-path").fill(files.projectDir);
        await page.getByTestId("project-name").fill(FIRST);
        await page.getByTestId("project-register").click();
        await flushView(page);
        assert.equal(registrations, 0, "registration is queued while the earlier removal response is pending");
        assert.equal(await page.getByTestId("project-register").isDisabled(), true);
        release.resolve();
        await delivered.promise;
        await page.getByRole("dialog").waitFor({ state: "detached" });
        await page.locator(".desk-chat-list").getByRole("button", { name: FIRST_CHAT, exact: true }).waitFor();
        assert.equal(registrations, 1);
        assert.equal(await project(page, FIRST).count(), 1, "the delayed removal cannot erase a restored registration");
        assert.equal(readFileSync(files.billingPath, "utf8"), originalFile);
    } finally {
        release.resolve();
        await page.unroute(removePattern);
        await page.unroute(createPattern);
    }
    await page.reload();
    await project(page, FIRST).waitFor();
    await page.getByRole("button", { name: SECOND, exact: true }).click();
    await page.locator(".desk-chat-header").getByText(SECOND, { exact: true }).waitFor();
});

it("right-click and keyboard menus target their project and dismiss without making changes", async () => {
    const { page } = e2e;
    await project(page, FIRST).click({ button: "right" });
    await page.getByRole("menuitem", { name: "프로젝트 삭제", exact: true }).waitFor();
    assert.equal(
        await page.locator(".desk-chat-header").getByText(SECOND, { exact: true }).count(),
        1,
        "right-click does not switch conversations",
    );
    await page.keyboard.press("Escape");
    await page.getByRole("menu").waitFor({ state: "detached" });
    assert.equal(await project(page, FIRST).count(), 1);
    await page.getByRole("button", { name: FIRST, exact: true }).focus();
    await page.keyboard.press("Shift+F10");
    await page.getByRole("menuitem", { name: "프로젝트 삭제", exact: true }).waitFor();
    await page.locator(".desk-chat-title").click();
    await page.getByRole("menu").waitFor({ state: "detached" });
    assert.equal(await project(page, FIRST).count(), 1);
});

it("removal persists after reload, preserves the source folder and restores conversations when added again", async () => {
    const { page, files } = e2e;
    await project(page, FIRST).click({ button: "right" });
    await page.getByRole("menuitem", { name: "프로젝트 삭제", exact: true }).click();
    await project(page, FIRST).waitFor({ state: "detached" });
    assert.equal(await project(page, SECOND).count(), 1, "only the context-menu target is removed");
    assert.equal(await page.getByRole("dialog").count(), 0, "removal needs no second dialog");
    assert.equal(readFileSync(files.billingPath, "utf8"), originalFile, "local project files are preserved");
    await page.reload();
    await page.locator(".desk-chat-header").getByText(SECOND, { exact: true }).waitFor();
    assert.equal(await project(page, FIRST).count(), 0, "the removed project stays absent after reload");
    await registerProject(page, FIRST, files.projectDir);
    await page.locator(".desk-chat-list").getByRole("button", { name: FIRST_CHAT, exact: true }).waitFor();
    assert.equal(
        await page.locator(".desk-chat-list").getByRole("button", { name: SECOND_CHAT, exact: true }).count(),
        1,
    );
    await page.locator(".desk-chat-list").getByRole("button", { name: FIRST_CHAT, exact: true }).click();
    await page.getByTestId("answer").getByText("첫 대화 답변입니다.", { exact: true }).waitFor();
    assert.equal(readFileSync(files.billingPath, "utf8"), originalFile);
});

it("removing the selected project selects the remaining one and removing the last clears the conversation", async () => {
    const { page, files } = e2e;
    await project(page, FIRST).click({ button: "right" });
    await page.getByRole("menuitem", { name: "프로젝트 삭제", exact: true }).click();
    await project(page, FIRST).waitFor({ state: "detached" });
    await page.locator(".desk-chat-header").getByText(SECOND, { exact: true }).waitFor();
    await page.locator('.desk-messages[aria-busy="false"]').waitFor();
    assert.equal(await page.locator(".desk-chat-list button").count(), 1);
    await project(page, SECOND).click({ button: "right" });
    await page.getByRole("menuitem", { name: "프로젝트 삭제", exact: true }).click();
    await project(page, SECOND).waitFor({ state: "detached" });
    await page.locator(".desk-empty").getByRole("button", { name: "프로젝트 추가", exact: true }).waitFor();
    assert.equal(await page.getByTestId("question-input").count(), 0, "the deleted project's conversation is closed");
    await page.reload();
    await page.locator(".desk-empty").getByRole("button", { name: "프로젝트 추가", exact: true }).waitFor();
    assert.equal(await page.locator(".desk-project").count(), 0);
    assert.equal(readFileSync(files.billingPath, "utf8"), originalFile);
});

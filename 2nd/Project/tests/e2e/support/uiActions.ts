/** User actions on the real UI, by visible labels and test ids only (no internal state). */
import type { Locator, Page } from "playwright-core";

export async function registerProject(page: Page, name: string, path: string): Promise<void> {
    await page.getByRole("button", { name: "+ 프로젝트 추가", exact: true }).click();
    await page.getByTestId("project-path").fill(path);
    await page.getByTestId("project-name").fill(name);
    await page.getByTestId("project-register").click();
    await page.getByRole("dialog").waitFor({ state: "detached" });
    await page.getByTestId("question-input").waitFor();
    await page.locator('.desk-messages[aria-busy="false"]').waitFor();
}

export async function openContext(page: Page): Promise<void> {
    if (!(await page.locator("#context-panel").isVisible())) {
        await page.getByRole("button", { name: "자료 · 컨텍스트", exact: true }).click();
    }
}

export async function buildIndex(page: Page): Promise<void> {
    await page.getByRole("button", { name: "인덱스 생성·갱신", exact: true }).click();
    await page.getByTestId("index-start").click();
    await page.locator("dialog .desk-job").getByText("완료", { exact: true }).first().waitFor({ timeout: 60000 });
    await page.getByRole("button", { name: "닫기", exact: true }).last().click();
}

export async function startSession(page: Page, name: string): Promise<void> {
    // Registering a project opens its first conversation automatically.
    await page.getByRole("button", { name, exact: true }).first().click();
    await page.getByTestId("question-input").waitFor();
    await page.locator('.desk-messages[aria-busy="false"]').waitFor();
    await openContext(page);
}

export async function ask(page: Page, question: string): Promise<void> {
    await page.getByTestId("question-input").fill(question);
    const request = page.waitForRequest(
        (candidate) => candidate.method() === "POST" && /\/sessions\/[^/]+\/runs$/.test(candidate.url()),
    );
    await page.getByTestId("question-submit").click();
    const response = await (await request).response();
    if (response?.ok()) {
        await page.waitForFunction(
            () => document.querySelector<HTMLTextAreaElement>('[data-testid="question-input"]')?.value === "",
        );
    }
}

/** The conversation status badge (live region) reaches the given label. */
export async function waitRunStatus(page: Page, label: string, timeout = 60000): Promise<void> {
    await page
        .locator(".desk-run-status")
        .filter({ hasText: new RegExp(`^${label}( ·|$)`) })
        .waitFor({ timeout });
}

export async function decideApproval(page: Page, decision: "approve" | "reject"): Promise<void> {
    await page.getByTestId(decision === "approve" ? "approval-approve" : "approval-reject").click();
}

export async function registerSource(page: Page, path: string, name: string): Promise<void> {
    await openContext(page);
    const field = page.getByLabel("등록할 외부 파일의 호스트 경로");
    await field.fill(path);
    await page.getByRole("button", { name: "지정한 파일 등록" }).click();
    await pointerOption(page, name).waitFor();
}

/** The radio of a pointer row whose label starts with the display name. */
export function pointerOption(page: Page, name: string): Locator {
    return page.locator("label").filter({ hasText: new RegExp(`^${name.replace(".", "\\.")} ·`) });
}

export async function selectPointer(page: Page, name: string): Promise<void> {
    await pointerOption(page, name).locator("input[type=radio]").check();
}

export function contextPanelText(page: Page): Promise<string> {
    return page.locator("#context-panel").innerText();
}

/** The workspace's registered Source pointers through the same public API the UI uses (cookie session). */
export async function sourcePointer(page: Page, name: string): Promise<string> {
    return page.evaluate(async (displayName) => {
        const workspaces = (await (await fetch("/api/v1/workspaces")).json()) as { items: { workspace_id: string }[] };
        const id = workspaces.items[0]?.workspace_id ?? "";
        const list = (await (await fetch(`/api/v1/workspaces/${id}/pointers?kind=source&limit=100`)).json()) as {
            items: { pointer: string; display_name?: string }[];
        };
        const item = list.items.find((entry) => entry.display_name === displayName);
        if (!item) throw new Error(`source ${displayName} is not registered`);
        return item.pointer;
    }, name);
}

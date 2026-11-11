/** User actions on the real UI, by visible labels and test ids only (no internal state). */
import type { Locator, Page } from "playwright-core";

export async function registerProject(page: Page, name: string, path: string): Promise<void> {
    await page.getByLabel("표시 이름").fill(name);
    await page.getByLabel("로컬 프로젝트 경로").fill(path);
    await page.getByRole("button", { name: "프로젝트 등록" }).click();
    await projectRow(page, name).waitFor();
}

function projectRow(page: Page, name: string): Locator {
    return page.getByRole("list", { name: "등록된 프로젝트" }).locator("li").filter({ hasText: name });
}

export async function buildIndex(page: Page): Promise<void> {
    await page.getByRole("button", { name: "색인 생성 · 갱신" }).click();
    await page
        .getByText(/ready · revision \d+/)
        .first()
        .waitFor({ timeout: 60000 });
}

export async function startSession(page: Page, name: string): Promise<void> {
    await projectRow(page, name).getByRole("button", { name: "이 프로젝트에서 세션 시작" }).click();
    await page.getByTestId("question-input").waitFor();
}

export async function ask(page: Page, question: string): Promise<void> {
    await page.getByTestId("question-input").fill(question);
    await page.getByTestId("question-submit").click();
}

/** The conversation status badge (live region) reaches the given label. */
export async function waitRunStatus(page: Page, label: string, timeout = 60000): Promise<void> {
    await page.locator("#screen-chat [role=status]").filter({ hasText: label }).first().waitFor({ timeout });
}

export async function decideApproval(page: Page, decision: "approve" | "reject"): Promise<void> {
    await page.getByTestId(decision === "approve" ? "approval-approve" : "approval-reject").click();
    await page.getByTestId("approval-confirm").click();
}

export async function registerSource(page: Page, path: string, name: string): Promise<void> {
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

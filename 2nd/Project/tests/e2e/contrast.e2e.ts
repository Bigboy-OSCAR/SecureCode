/** WCAG 2.x contrast from rendered browser colors, including transparent ancestor backgrounds. */
import assert from "node:assert/strict";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import { after, before, it } from "node:test";
import type { Locator } from "playwright-core";
import { startE2E, type E2E } from "./support/e2eStack.js";
import { ask, registerProject, waitRunStatus } from "./support/uiActions.js";

let e2e: E2E;
interface ContrastSample {
    name: string;
    foreground: string;
    background: string;
    ratio: number;
    required: number;
    fontSize: number;
    fontWeight: string;
}
const samples: ContrastSample[] = [];
before(async () => {
    e2e = await startE2E({ viewport: { width: 1440, height: 960 } });
});
after(async () => {
    await e2e?.stop();
});

async function measure(name: string, locator: Locator, pseudo?: string): Promise<void> {
    await locator.waitFor({ state: "visible" });
    // tsx retains local function names using this helper; it has no bearing on measured CSS.
    await e2e.page.evaluate("globalThis.__name = function (target) { return target; }");
    const sample = await locator.evaluate((element, pseudoElement) => {
        type Color = [number, number, number, number];
        const parse = (value: string): Color => {
            const parts = value.match(/[\d.]+/g)?.map(Number) ?? [];
            if (parts.length < 3) throw new Error(`Unsupported computed color: ${value}`);
            return [parts[0]!, parts[1]!, parts[2]!, parts[3] ?? 1];
        };
        const over = (top: Color, bottom: Color): Color => [
            top[0] * top[3] + bottom[0] * (1 - top[3]),
            top[1] * top[3] + bottom[1] * (1 - top[3]),
            top[2] * top[3] + bottom[2] * (1 - top[3]),
            1,
        ];
        const ancestors: Element[] = [];
        for (let node: Element | null = element; node; node = node.parentElement) ancestors.unshift(node);
        let background: Color = [255, 255, 255, 1];
        for (const ancestor of ancestors) {
            const style = getComputedStyle(ancestor);
            if (Number(style.opacity) !== 1) throw new Error("Opacity requires an explicitly composited sample");
            background = over(parse(style.backgroundColor), background);
        }
        const style = getComputedStyle(element, pseudoElement || null);
        if (Number(style.opacity) !== 1) throw new Error("Pseudo element opacity requires explicit compositing");
        const foreground = over(parse(style.color), background);
        const luminance = (color: Color): number => {
            const linear = color.slice(0, 3).map((channel) => {
                const normalized = channel / 255;
                return normalized <= 0.04045 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4;
            });
            return linear[0]! * 0.2126 + linear[1]! * 0.7152 + linear[2]! * 0.0722;
        };
        const lightness = [luminance(foreground), luminance(background)].sort((a, b) => a - b);
        const ratio = (lightness[1]! + 0.05) / (lightness[0]! + 0.05);
        const fontSize = parseFloat(style.fontSize);
        const large = fontSize >= 24 || (fontSize >= 18.6666667 && parseInt(style.fontWeight) >= 700);
        const rgb = (value: Color): string =>
            `rgb(${value
                .slice(0, 3)
                .map((n) => Math.round(n))
                .join(", ")})`;
        return {
            foreground: rgb(foreground),
            background: rgb(background),
            ratio,
            required: large ? 3 : 4.5,
            fontSize,
            fontWeight: style.fontWeight,
        };
    }, pseudo);
    samples.push({ name, ...sample });
    assert.ok(
        sample.ratio >= sample.required,
        `${name}: ${sample.ratio.toFixed(3)}:1 < ${sample.required}:1 (${sample.foreground} on ${sample.background})`,
    );
}

it("actual text, placeholders, dialogs and answer controls meet WCAG AA contrast", async () => {
    const { page, files, fake } = e2e;
    await measure("brand", page.locator(".desk-brand strong"));
    await measure("sidebar search", page.locator(".desk-nav-row").filter({ hasText: "대화 검색" }));
    await measure("LOCAL tag", page.locator(".desk-brand .desk-tag"));
    await measure("model state caption", page.locator(".desk-model-picker small"));
    await measure("local privacy caption", page.locator(".desk-local"));
    await registerProject(page, "contrast-project", files.projectDir);
    await measure("welcome title", page.locator(".desk-welcome h1"));
    await measure("welcome description", page.locator(".desk-welcome p").first());
    await measure("project path", page.locator(".desk-project.selected .desk-project-path"));
    await measure("suggestion button", page.locator(".desk-suggestions button").first());
    await measure("composer context", page.locator(".desk-composer-context > span").first());
    await measure("composer folder tag", page.locator(".desk-composer-context .desk-tag"));
    await measure("input placeholder", page.getByTestId("question-input"), "::placeholder");
    await measure("input instruction", page.locator(".desk-composer-actions > span"));
    await measure("privacy footer", page.locator(".desk-privacy"));
    fake.script([{ text: "## 결과\n본문과 `인라인 코드`입니다.\n```python\nprint('hello')\n```" }]);
    await ask(page, "대비 검사용 답변");
    await waitRunStatus(page, "완료");
    await measure("user message", page.locator(".desk-user-message").last());
    await measure("answer body", page.locator(".answer-text p").filter({ hasText: "본문과" }));
    await measure("code text", page.locator(".desk-answer-code pre code"));
    await measure("code copy", page.getByRole("button", { name: "코드 복사", exact: true }));
    await page.getByRole("button", { name: "+ 프로젝트 추가", exact: true }).click();
    await measure("dialog title", page.locator("dialog h2"));
    await measure("field label", page.locator("label[for=project-display-name]"));
    await page.getByTestId("project-path").fill("/nonexistent-localdesk-contrast-project");
    await page.getByTestId("project-name").fill("missing");
    await measure("primary enabled button", page.getByTestId("project-register"));
    await measure("field entered value", page.getByTestId("project-name"));
    await measure("project privacy notice", page.locator(".desk-local-notice p"));
    await page.getByTestId("project-register").click();
    await page.locator("dialog .alert-error").waitFor();
    await measure("error alert", page.locator("dialog .alert-error"));
    const report = process.env.SECURECODE_CONTRAST_REPORT;
    if (report) {
        mkdirSync(dirname(report), { recursive: true });
        writeFileSync(
            report,
            JSON.stringify(
                {
                    measured_at: new Date().toISOString(),
                    browser: "installed Chrome, 1440x960",
                    method: "WCAG 2.x sRGB relative luminance, alpha-composited computed CSS, unrounded assertion",
                    disabled_controls: "excluded as WCAG exempts inactive controls",
                    samples,
                },
                null,
                2,
            ) + "\n",
        );
    }
    console.log(
        `WCAG AA: ${samples.length} rendered samples passed; minimum ratio ${Math.min(...samples.map((sample) => sample.ratio)).toFixed(3)}:1`,
    );
});

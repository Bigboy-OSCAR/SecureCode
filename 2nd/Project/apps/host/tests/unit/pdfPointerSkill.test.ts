/** 4.9: SKILL.md, the PDF tool registry and the 3.6 registration fixture must describe the same tools. */
import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { test } from "node:test";
import { documentedTools, loadPdfPointerSkill, withSkills } from "../../src/cline/skills/pdfPointerSkill.js";
import { PDF_TOOL_NAMES, pdfTools } from "../../src/cline/tools/pdfTools.js";
import type { PdfService } from "../../src/context-client/pdfClient.js";

const WORK_ROOT = resolve(import.meta.dirname, "../../../..");
const fixture = JSON.parse(readFileSync(resolve(WORK_ROOT, "skills/pdf-pointer/registration.json"), "utf8")) as {
    skill_id: string;
    version: string;
    sha256: string;
    prompt_marker: string;
    tools: { name: string; required: string[]; properties: string[] }[];
};
const tools = pdfTools({ service: {} as PdfService, workspaceId: "ws_00000001", timeoutMs: 1000 });

test("the loaded skill matches the registration fixture byte for byte", () => {
    const skill = loadPdfPointerSkill(WORK_ROOT);
    assert.equal(skill.id, fixture.skill_id);
    assert.equal(skill.version, fixture.version);
    assert.equal(skill.sha256, fixture.sha256, "SKILL.md changed: regenerate skills/pdf-pointer/registration.json");
    assert.deepEqual(skill.tools, [...PDF_TOOL_NAMES]);
    assert.ok(skill.promptSection.startsWith(fixture.prompt_marker));
});

test("registered tool names and inputs equal the fixture and appear in SKILL.md", () => {
    const skillText = readFileSync(resolve(WORK_ROOT, "skills/pdf-pointer/SKILL.md"), "utf8");
    const actual = tools.map((entry) => ({
        name: entry.tool.name,
        required: entry.tool.inputSchema.required ?? [],
        properties: Object.keys(entry.tool.inputSchema.properties ?? {}),
    }));
    assert.deepEqual(actual, fixture.tools);
    for (const entry of actual) {
        const row = skillText.split("\n").find((line) => line.startsWith(`| \`${entry.name}\``));
        assert.ok(row, `${entry.name} has a row in the SKILL.md tool table`);
        for (const property of entry.properties) assert.ok(row.includes(`"${property}"`), `${entry.name}.${property}`);
    }
});

test("a SKILL.md that names a tool the registry lacks is refused", () => {
    const body = "## 도구\n\n| 도구 | 입력 |\n| --- | --- |\n| `pdf_parse` | x |\n| `pdf_read_all` | x |\n\n## 끝\n";
    assert.deepEqual(documentedTools(body), ["pdf_parse", "pdf_read_all"]);
    const root = mkdtempSync(join(tmpdir(), "securecode-skill-"));
    mkdirSync(join(root, "skills/pdf-pointer"), { recursive: true });
    const original = readFileSync(resolve(WORK_ROOT, "skills/pdf-pointer/SKILL.md"), "utf8");
    writeFileSync(join(root, "skills/pdf-pointer/SKILL.md"), original.replace("| `pdf_search` |", "| `pdf_find` |"));
    assert.throws(() => loadPdfPointerSkill(root), /do not match the PDF tool registry/);
});

test("the skill is appended to the system prompt explicitly", () => {
    const prompt = withSkills("BASE PROMPT", [loadPdfPointerSkill(WORK_ROOT)]);
    assert.ok(prompt.startsWith("BASE PROMPT\n\n"));
    assert.ok(prompt.includes(fixture.prompt_marker) && prompt.includes("pdf_read_pages"));
});

/**
 * Throwaway project and external files for the E2E suite, created under the OS temp folder per run:
 * a small Python project (one relevant function, unrelated helpers), a command that prints a large log,
 * a slow command for cancel tests, a large external text file, a 3-page Korean PDF and a text-less PDF.
 * Nothing outside these folders is read or changed.
 */
import { copyFileSync, mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const WORK_ROOT = resolve(import.meta.dirname, "..", "..", "..");
export const NOISE_FILES = 50;

export interface WorkspaceFixture {
    projectDir: string;
    externalDir: string;
    billingPath: string;
    bigLogPath: string;
    pdfPath: string;
    scanPdfPath: string;
    /** Five supported languages plus one Python file with a syntax error and one TypeScript file. */
    polyglotDir: string;
}

const BILLING =
    'def compute_invoice_total(items, tax_rate):\n    """Sum line totals, then add tax."""\n' +
    "    subtotal = sum(item.price * item.quantity for item in items)\n" +
    "    return round(subtotal * (1 + tax_rate), 2)\n";

const GEN_LOG =
    'const l=[];for(let i=1;i<=20000;i++)l.push(i===13579?"LOG-TARGET total=42":"BULK-LOG-"+i+"-"+"z".repeat(30));' +
    'process.stdout.write(l.join("\\n")+"\\n");';

/** A valid one-page PDF with no text layer (parsed as unsupported, like a scan). */
function blankPdf(): Buffer {
    const objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>",
    ];
    let body = "%PDF-1.4\n";
    const offsets: number[] = [];
    objects.forEach((object, index) => {
        offsets.push(Buffer.byteLength(body));
        body += `${index + 1} 0 obj\n${object}\nendobj\n`;
    });
    const xref = Buffer.byteLength(body);
    body += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
    for (const offset of offsets) body += `${String(offset).padStart(10, "0")} 00000 n \n`;
    body += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
    return Buffer.from(body, "latin1");
}

export function createWorkspaceFixture(): WorkspaceFixture {
    const projectDir = mkdtempSync(join(tmpdir(), "securecode-e2e-ws-"));
    const externalDir = mkdtempSync(join(tmpdir(), "securecode-e2e-ext-"));
    mkdirSync(join(projectDir, "noise"));
    for (let i = 0; i < NOISE_FILES; i += 1) {
        writeFileSync(
            join(projectDir, "noise", `m${i}.py`),
            `def helper_${i}():\n    return "UNRELATED-SENTINEL-${i}"\n`,
        );
    }
    const billingPath = join(projectDir, "billing.py");
    writeFileSync(billingPath, BILLING);
    writeFileSync(join(projectDir, "gen.js"), GEN_LOG);
    writeFileSync(join(projectDir, "slow.js"), "setTimeout(() => console.log('done'), 120000);");
    const lines = Array.from({ length: 30000 }, (_, i) =>
        i === 24999 ? "EXT-TARGET 결제 오류 코드 E-7731" : `ext line ${i + 1} ${"y".repeat(60)}`,
    );
    const bigLogPath = join(externalDir, "big.log");
    writeFileSync(bigLogPath, `${lines.join("\n")}\n`);
    const pdfPath = join(externalDir, "manual.pdf");
    copyFileSync(join(WORK_ROOT, "tests", "fixtures", "pdf", "korean-3-pages.pdf"), pdfPath);
    const scanPdfPath = join(externalDir, "scan.pdf");
    writeFileSync(scanPdfPath, blankPdf());
    const polyglotDir = mkdtempSync(join(tmpdir(), "securecode-e2e-poly-"));
    const sources: Record<string, string> = {
        "calc.c": "int add_numbers(int a, int b) { return a + b; }\n",
        "shape.cpp": "class Shape { public: double area() const { return 1.0; } };\n",
        "Invoice.java": "public class Invoice { public int total() { return 42; } }\n",
        "format.js": "function formatPrice(value) { return value.toFixed(2); }\n",
        "ok.py": "def parse_order(text):\n    return text.split(',')\n",
        "broken.py": "def broken(:\n    return\n",
        "types.ts": "export const unsupported: number = 1;\n",
    };
    for (const [name, text] of Object.entries(sources)) writeFileSync(join(polyglotDir, name), text);
    return { projectDir, externalDir, billingPath, bigLogPath, pdfPath, scanPdfPath, polyglotDir };
}

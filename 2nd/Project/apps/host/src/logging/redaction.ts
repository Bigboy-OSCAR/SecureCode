/**
 * Log redaction. Same rules and order as the Python service
 * (services/context-service/src/securecode_context/common/redaction.py),
 * verified by the shared vectors in tests/fixtures/redaction-cases.json.
 */
export const MAX_LOG_CHARS = 2000;

const API_KEY_PATTERN = /sk-ant-[A-Za-z0-9_-]{8,}/g;
const BEARER_PATTERN = /(bearer\s+)[A-Za-z0-9._~+/=-]{8,}/gi;
const KEY_VALUE_PATTERN =
    /\b(x-api-key|api[_-]?key|authorization|internal[_-]?token|token|secret|password)("?\s*[:=]\s*"?)(?!Bearer\b|\[REDACTED)[^\s",;]+/gi;
const WINDOWS_HOME_PATTERN = /[A-Za-z]:[\\/]Users[\\/][^\\/\s"']+/g;
const POSIX_HOME_PATTERN = /\/(?:Users|home)\/[^/\s"']+/g;

export class Redactor {
    private readonly secrets: string[];
    private readonly maxChars: number;

    constructor(secrets: readonly string[] = [], maxChars: number = MAX_LOG_CHARS) {
        this.secrets = secrets.filter(Boolean);
        this.maxChars = maxChars;
    }

    addSecret(secret: string): void {
        if (secret && !this.secrets.includes(secret)) {
            this.secrets.push(secret);
        }
    }

    redact(text: string): string {
        let redacted = text;
        for (const secret of this.secrets) {
            redacted = redacted.split(secret).join("[REDACTED:secret]");
        }
        redacted = redacted
            .replace(API_KEY_PATTERN, "[REDACTED:api_key]")
            .replace(BEARER_PATTERN, "$1[REDACTED]")
            .replace(KEY_VALUE_PATTERN, "$1$2[REDACTED]")
            .replace(WINDOWS_HOME_PATTERN, "<home>")
            .replace(POSIX_HOME_PATTERN, "<home>");

        // Truncate by code points so Python and TypeScript agree on emoji.
        const codePoints = Array.from(redacted);
        if (codePoints.length > this.maxChars) {
            const overflow = codePoints.length - this.maxChars;
            return `${codePoints.slice(0, this.maxChars).join("")}...[truncated ${overflow} chars]`;
        }
        return redacted;
    }
}

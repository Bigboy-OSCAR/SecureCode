/** llama.cpp expands bounded strings into grammar rules; many large limits overflow its parser.
 * The SDK still owns the original schemas and executor/service validation. Only the model-visible
 * generation hints are simplified, before the final payload is counted and sent.
 */
function generationSchema(value: unknown): unknown {
    if (Array.isArray(value)) return value.map(generationSchema);
    if (typeof value !== "object" || value === null) return value;
    return Object.fromEntries(
        Object.entries(value)
            .filter(([key]) => key !== "maxLength")
            .map(([key, child]) => [key, generationSchema(child)]),
    );
}

export function normalizeProviderTools(body: string, providerId: string): string {
    if (providerId !== "openai-compatible") return body;
    let parsed: { tools?: { function?: { parameters?: unknown } }[] };
    try {
        parsed = JSON.parse(body) as typeof parsed;
    } catch {
        return body;
    }
    if (!Array.isArray(parsed.tools)) return body;
    for (const tool of parsed.tools) {
        if (tool.function?.parameters) tool.function.parameters = generationSchema(tool.function.parameters);
    }
    return JSON.stringify(parsed);
}

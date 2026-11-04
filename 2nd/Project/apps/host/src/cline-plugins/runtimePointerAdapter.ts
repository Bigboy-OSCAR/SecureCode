import type { ClineCore } from "@cline/sdk";
import {
  createRuntimePointerPlugin,
  type RuntimePointerConfig,
} from "../pointer-hooks/runtimePointerHooks.js";

type AnyMessage = {
  role?: string;
  content?: unknown;
};

function extractText(value: unknown): string {
  if (typeof value === "string") return value;

  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (typeof item === "string") return item;

        const record = item as Record<string, unknown>;
        if (typeof record?.text === "string") return record.text;
        if (typeof record?.content === "string") return record.content;

        return "";
      })
      .filter(Boolean)
      .join("\n");
  }

  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    if (typeof record.text === "string") return record.text;
    if (typeof record.content === "string") return record.content;
  }

  return "";
}

function findLastToolResult(messages: AnyMessage[]): string {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    const text = extractText(message?.content);

    if (text) {
      return text;
    }
  }

  return "";
}

export function attachRuntimePointerAdapter(
  cline: ClineCore,
  sessionId: string,
  config: RuntimePointerConfig,
): () => void {
  const plugin = createRuntimePointerPlugin(config);
  let pendingContext: unknown[] = [];

  const unsubscribe = cline.subscribe(async (event: any) => {
    if (event?.type !== "hook") return;
    if (event?.payload?.hookEventName !== "tool_result") return;

    try {
      const messages = (await cline.readMessages(sessionId)) as AnyMessage[];
      const toolResult = findLastToolResult(messages);

      if (!toolResult) return;

      console.log("[runtime-pointer] calling afterTool", {
        toolName: event.payload.toolName,
        byteSize: Buffer.byteLength(toolResult, "utf8"),
      });

      const result = await (plugin as any).hooks.afterTool({
        toolName: event.payload.toolName ?? "unknown_tool",
        result: toolResult,
      });

      console.log("[runtime-pointer] afterTool result", result);

      pendingContext = result?.appendContext ?? [];
    } catch (error) {
      console.error("[runtime-pointer] afterTool failed:", error);
    }
  });

  return () => {
    unsubscribe();
    pendingContext = [];
  };
}

export async function prepareRuntimePointerContext(
  cline: ClineCore,
  sessionId: string,
  config: RuntimePointerConfig,
  messages: any[],
): Promise<any[]> {
  const plugin = createRuntimePointerPlugin(config);

  const result = await (plugin as any).hooks.beforeModel({
    messages,
    appendContext: [],
  });

  return result?.messages ?? messages;
}

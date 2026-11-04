import { type AgentPlugin } from "@cline/sdk";
import { storeRuntimePointer } from "../pointer-hooks/runtimePointerHook.js";

export type RuntimePointerPluginOptions = {
  workspaceId: string;
  sessionId: string;
  baseUrl?: string;
  thresholdBytes?: number;
};

export type AfterToolContext = {
  toolCall?: {
    toolName?: string;
  };
  result?: unknown;
};

export type RuntimePointerHookOutput = {
  result: string;
  appendContext: Array<{
    kind: "runtime";
    pointer: string;
    preview: string;
  }>;
};

export function createAfterToolHandler(options: RuntimePointerPluginOptions) {
  return async function afterTool(
    context: AfterToolContext,
  ): Promise<RuntimePointerHookOutput | undefined> {
    const result = context.result;
    const content =
      typeof result === "string"
        ? result
        : JSON.stringify(result ?? "");

    const stored = await storeRuntimePointer(
      {
        toolName: context.toolCall?.toolName,
        content,
      },
      {
        workspaceId: options.workspaceId,
        sessionId: options.sessionId,
        baseUrl: options.baseUrl,
        thresholdBytes: options.thresholdBytes,
      },
    );

    if (!stored.stored) {
      return undefined;
    }

    return {
      result: [
        `Tool output was too large (${stored.byteSize} bytes).`,
        `Stored as Runtime Pointer: ${stored.pointerUri}`,
        "",
        "Preview:",
        stored.preview,
      ].join("\n"),
      appendContext: [
        {
          kind: "runtime",
          pointer: stored.pointerUri!,
          preview: stored.preview,
        },
      ],
    };
  };
}

export function createRuntimePointerPlugin(
  options: RuntimePointerPluginOptions,
): AgentPlugin {
  const afterTool = createAfterToolHandler(options);

  return {
    name: "securecode-runtime-pointer",
    manifest: {
      capabilities: ["hooks"],
    },
    setup(api: any) {
      api?.registerHook?.("afterTool", afterTool);
    },
    hooks: {
      afterTool: afterTool as never,
    },
  };
}

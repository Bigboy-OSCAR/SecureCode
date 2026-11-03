import { ClineCore, type AgentPlugin } from "clinesdk";

type ToolResult = {
  toolName?: string;
  result?: string;
};

type RuntimePointerConfig = {
  baseUrl: string;
  workspaceId: string;
  sessionId: string;
  thresholdBytes?: number;
  maxBytes?: number;
};

export function createRuntimePointerPlugin(
  config: RuntimePointerConfig,
): AgentPlugin {
  const thresholdBytes = config.thresholdBytes ?? 8 * 1024;
  const maxBytes = config.maxBytes ?? 32 * 1024;

  return {
    name: "runtime-pointer",
    manifest: {
      capabilities: ["hooks"],
    },
    hooks: {
      afterTool: async ({ result }) => {
        const toolResult = result as ToolResult;
        const content = toolResult?.result ?? "";

        if (!content) {
          return { result };
        }

        const byteSize = Buffer.byteLength(content, "utf8");

        if (byteSize < thresholdBytes) {
          return { result };
        }

        const response = await fetch(
          `${config.baseUrl}/api/v1/pointers/runtime`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              workspace_id: config.workspaceId,
              session_id: config.sessionId,
              content,
            }),
          },
        );

        if (!response.ok) {
          throw new Error(
            `Failed to store runtime pointer: ${response.status}`,
          );
        }

        const data = (await response.json()) as {
          pointer_id: string;
        };

        const pointerUri = `securecode://runtime/${config.workspaceId}/${config.sessionId}/${data.pointer_id}`;

        const pointerResult = [
          "Large tool result was stored as a runtime pointer.",
          "",
          `Pointer: ${pointerUri}`,
          `Bytes: ${byteSize}`,
          "",
          "Use the pointer read API to retrieve only the needed part.",
        ].join("\n");

        return {
          result: {
            ...toolResult,
            result: pointerResult,
          },
          appendContext: [
            {
              type: "runtime_pointer",
              pointer: pointerUri,
              byte_size: byteSize,
            },
          ],
        };
      },

      beforeModel: async ({ messages }) => {
        return {
          messages,
        };
      },
    },
  };
}

export function registerRuntimePointerHooks(
  core: ClineCore,
  config: RuntimePointerConfig,
): void {
  const plugin = createRuntimePointerPlugin(config);

  core.use(plugin);
}

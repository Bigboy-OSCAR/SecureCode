import { ClineCore, type AgentPlugin } from "@cline/sdk";

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

async function readRuntimePointer(
  baseUrl: string,
  pointerUri: string
): Promise<string> {
  const match = pointerUri.match(
    /^securecode:\/\/runtime\/([^/]+)\/([^/]+)\/([^/?]+)/
  );

  if (!match) {
    throw new Error(`Pointer URI 파싱 실패: ${pointerUri}`);
  }

  const [, workspaceId, sessionId, pointerId] = match;

  const response = await fetch(
    `${baseUrl}/api/v1/pointers/runtime/read`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        pointer_id: pointerId,
        workspace_id: workspaceId,
        session_id: sessionId,
        cursor: 0,
        max_bytes: 32768,
      }),
    }
  );

  if (!response.ok) {
    throw new Error(`pointer read 실패: ${response.status}`);
  }

  const data = await response.json();

  if (!data.content) {
    throw new Error("pointer content가 비어 있습니다.");
  }

  return data.content;
}

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
        const isStringResult = typeof result === "string";
        const toolResult = isStringResult
          ? { result }
          : (result as ToolResult);
        const content = isStringResult
          ? result
          : (toolResult?.result ?? "");

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
          result: isStringResult
            ? pointerResult
            : {
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

      beforeModel: async ({ messages, appendContext }) => {
        const newMessages = [...messages];

        for (const item of appendContext ?? []) {
          if (item.type !== "runtime_pointer") {
            continue;
          }

          const content = await readRuntimePointer(
            config.baseUrl,
            item.pointer
          );

          newMessages.push({
            role: "assistant",
            content: `이전 tool 결과:\n\n${content}`,
          });
        }

        return {
          messages: newMessages,
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

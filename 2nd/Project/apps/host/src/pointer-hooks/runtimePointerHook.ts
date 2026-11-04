export type RuntimePointerHookOptions = {
  baseUrl?: string;
  workspaceId: string;
  sessionId: string;
  thresholdBytes?: number;
};

export type ToolResultLike = {
  toolName?: string;
  content: string;
};

export type RuntimePointerResult = {
  stored: boolean;
  pointerUri?: string;
  pointerId?: string;
  byteSize?: number;
  preview: string;
};

export async function storeRuntimePointer(
  toolResult: ToolResultLike,
  options: RuntimePointerHookOptions,
): Promise<RuntimePointerResult> {
  const baseUrl = options.baseUrl ?? "http://127.0.0.1:8000";
  const thresholdBytes = options.thresholdBytes ?? 4096;
  const content = toolResult.content ?? "";
  const byteSize = Buffer.byteLength(content, "utf8");

  const preview = content.slice(0, 512);

  if (byteSize < thresholdBytes) {
    return {
      stored: false,
      preview,
    };
  }

  const response = await fetch(`${baseUrl}/api/v1/pointers/runtime`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      workspace_id: options.workspaceId,
      session_id: options.sessionId,
      content,
    }),
  });

  if (!response.ok) {
    throw new Error(`Runtime Pointer 저장 실패: ${response.status}`);
  }

  const data = await response.json();

  return {
    stored: true,
    pointerUri: data.pointer_uri,
    pointerId: data.pointer_id,
    byteSize: data.byte_size,
    preview,
  };
}

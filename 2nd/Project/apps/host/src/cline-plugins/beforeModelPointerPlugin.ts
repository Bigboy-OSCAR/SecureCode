export type BeforeModelContext = {
  messages: Array<{
    role: string;
    content: string;
  }>;
  appendContext?: Array<{
    kind: string;
    pointer: string;
  }>;
};

export type BeforeModelResult = {
  messages: Array<{
    role: string;
    content: string;
  }>;
};

export async function readRuntimePointer(
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
    "http://127.0.0.1:8000/api/v1/pointers/runtime/read",
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

export function createBeforeModelHandler() {
  return async function beforeModel(
    context: BeforeModelContext
  ): Promise<BeforeModelResult> {
    const messages = [...context.messages];

    const pointers = context.appendContext ?? [];

    for (const item of pointers) {
      if (item.kind !== "runtime") {
        continue;
      }

      const content = await readRuntimePointer(item.pointer);

      messages.push({
        role: "assistant",
        content: `이전 tool 결과:\n\n${content}`,
      });
    }

    return {
      messages,
    };
  };
}

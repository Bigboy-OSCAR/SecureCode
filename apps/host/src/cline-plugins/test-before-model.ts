import { createAfterToolHandler } from "./runtimePointerPlugin.js";

async function readRuntimePointer(pointerUri: string) {
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

  return response.json();
}

async function main() {
  const afterTool = createAfterToolHandler({
    workspaceId: "w1",
    sessionId: "s1",
    thresholdBytes: 100,
  });

  const fakeToolResult = "z".repeat(1000);

  const transformed = await afterTool({
    toolCall: {
      toolName: "read_file",
    },
    result: fakeToolResult,
  });

  console.log("1. afterTool result:");
  console.log(transformed);

  const pointerUri = transformed?.appendContext?.[0]?.pointer;

  if (!pointerUri) {
    throw new Error("Runtime Pointer가 생성되지 않았습니다.");
  }

  const readResult = await readRuntimePointer(pointerUri);

  console.log("\n2. beforeModel에서 pointer read:");
  console.log(readResult);

  if (!readResult.content || readResult.content.length === 0) {
    throw new Error("pointer content가 비어 있습니다.");
  }

  const modelMessages = [
    {
      role: "user",
      content: "이전 tool 결과를 참고해서 답해줘.",
    },
    {
      role: "assistant",
      content: `이전 tool 결과:\n\n${readResult.content}`,
    },
  ];

  console.log("\n3. 모델에 전달할 messages:");
  console.log(modelMessages);

  console.log("\nSUCCESS: afterTool -> Runtime Pointer -> beforeModel read works.");
}

main().catch((error) => {
  console.error("beforeModel test failed:", error);
  process.exit(1);
});

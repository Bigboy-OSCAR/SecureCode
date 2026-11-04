import { createAfterToolHandler } from "./runtimePointerPlugin.js";

async function main() {
  const afterTool = createAfterToolHandler({
    workspaceId: "w1",
    sessionId: "s1",
    thresholdBytes: 100,
  });

  const fakeToolResult = "z".repeat(1000);

  const context = {
    toolCall: {
      toolName: "read_file",
    },
    result: fakeToolResult,
  };

  const transformed = await afterTool(context);

  console.log("1. afterTool result:");
  console.log(transformed);

  const pointerUri = transformed?.appendContext?.[0]?.pointer;

  if (!pointerUri) {
    throw new Error("Runtime Pointer가 생성되지 않았습니다.");
  }

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

  console.log("\nread status:", response.status);

  const readResult = await response.json();

  console.log("\n2. pointer read result:");
  console.log(readResult);

  if (!response.ok) {
    throw new Error(`Pointer read 실패: ${response.status}`);
  }

  if (!readResult.content || readResult.content.length === 0) {
    throw new Error("Pointer 내용을 읽지 못했습니다.");
  }

  console.log("\nSUCCESS: afterTool -> Runtime Pointer -> read pipeline works.");
}

main().catch((error) => {
  console.error("pipeline test failed:", error);
  process.exit(1);
});

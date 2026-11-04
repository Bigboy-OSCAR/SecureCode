import { createRuntimePointerPlugin } from "../pointer-hooks/runtimePointerHooks.js";

async function main() {
  const plugin = createRuntimePointerPlugin({
    baseUrl: "http://127.0.0.1:8000",
    workspaceId: "w1",
    sessionId: "s1",
    thresholdBytes: 100,
  });

  console.log("=== 1. CALLING afterTool ===");

  const afterToolResult = await (plugin as any).hooks.afterTool({
    toolName: "read_file",
    result: "x".repeat(500),
  });

  console.log(JSON.stringify(afterToolResult, null, 2));

  const pointer = afterToolResult?.appendContext?.[0]?.pointer;

  if (!pointer) {
    throw new Error("afterTool이 runtime pointer를 반환하지 않았습니다.");
  }

  console.log("\n=== 2. CALLING beforeModel ===");

  const beforeModelResult = await (plugin as any).hooks.beforeModel({
    messages: [
      {
        role: "user",
        content: "Summarize the previous tool result.",
      },
    ],
    appendContext: afterToolResult.appendContext,
  });

  console.log(JSON.stringify(beforeModelResult, null, 2));

  const injected = beforeModelResult?.messages?.at(-1);

  if (!injected?.content?.includes("xxxxxxxx")) {
    throw new Error("beforeModel이 pointer content를 주입하지 않았습니다.");
  }

  console.log("\n=== SUCCESS: beforeModel injected pointer content ===");
}

main().catch((error) => {
  console.error("\n=== FATAL ERROR ===");
  console.error(error);

  if (error instanceof Error && error.stack) {
    console.error("\n=== STACK ===");
    console.error(error.stack);
  }

  process.exit(1);
});

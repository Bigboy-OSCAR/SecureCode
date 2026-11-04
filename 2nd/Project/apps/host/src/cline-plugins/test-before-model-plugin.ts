import { createAfterToolHandler } from "./runtimePointerPlugin.js";
import { createBeforeModelHandler } from "./beforeModelPointerPlugin.js";

async function main() {
  const afterTool = createAfterToolHandler({
    workspaceId: "w1",
    sessionId: "s1",
    thresholdBytes: 100,
  });

  const transformed = await afterTool({
    toolCall: {
      toolName: "read_file",
    },
    result: "z".repeat(1000),
  });

  console.log("1. afterTool result:");
  console.log(transformed);

  const beforeModel = createBeforeModelHandler();

  const result = await beforeModel({
    messages: [
      {
        role: "user",
        content: "이전 tool 결과를 참고해서 답해줘.",
      },
    ],
    appendContext: transformed?.appendContext,
  });

  console.log("\n2. beforeModel result:");
  console.log(result);

  if (!result.messages || result.messages.length < 2) {
    throw new Error("beforeModel에서 pointer content가 주입되지 않았습니다.");
  }

  console.log("\nSUCCESS: afterTool -> Runtime Pointer -> beforeModel plugin works.");
}

main().catch((error) => {
  console.error("beforeModel plugin test failed:", error);
  process.exit(1);
});

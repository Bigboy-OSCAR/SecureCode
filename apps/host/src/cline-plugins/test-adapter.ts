import { ClineCore } from "@cline/sdk";
import { attachRuntimePointerAdapter } from "./runtimePointerAdapter.js";

async function main() {
  const cline = await ClineCore.create({
    clientName: "securecode-host",
    backendMode: "auto",
  });

  const sessionId = "adapter-fixture-session";

  const detach = attachRuntimePointerAdapter(cline, sessionId, {
    baseUrl: "http://127.0.0.1:8000",
    workspaceId: "w1",
    sessionId,
    thresholdBytes: 100,
  });

  console.log("=== ADAPTER ATTACHED ===");
  console.log("No LLM API call will be made.");

  console.log("\n=== INGESTING FIXTURE TOOL_RESULT EVENT ===");

  await (cline as any).ingestHookEvent({
    sessionId,
    hookEventName: "tool_result",
    toolName: "read_file",
    ts: new Date().toISOString(),
  });

  await new Promise((resolve) => setTimeout(resolve, 1000));

  console.log("\n=== CHECKING POINTER LIST ===");

  const response = await fetch(
    "http://127.0.0.1:8000/api/v1/workspaces/w1/pointers?kind=runtime"
  );

  const pointers = await response.json();

  console.log(JSON.stringify(pointers, null, 2));

  detach();
  await cline.dispose();

  console.log("\n=== ADAPTER TEST COMPLETE ===");
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

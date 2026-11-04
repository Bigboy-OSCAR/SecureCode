import { attachRuntimePointerAdapter } from "./runtimePointerAdapter.js";

async function main() {
  const listeners: Array<(event: any) => void> = [];

  const fakeCline = {
    subscribe(listener: (event: any) => void) {
      listeners.push(listener);

      return () => {
        const index = listeners.indexOf(listener);
        if (index >= 0) {
          listeners.splice(index, 1);
        }
      };
    },

    readMessages: async () => [
      {
        role: "user",
        content: "Read the large file.",
      },
      {
        role: "tool",
        content: "x".repeat(1000),
      },
    ],
  };

  const sessionId = "fixture-session";

  const detach = attachRuntimePointerAdapter(fakeCline as any, sessionId, {
    baseUrl: "http://127.0.0.1:8000",
    workspaceId: "w1",
    sessionId,
    thresholdBytes: 100,
  });

  console.log("=== DISPATCHING FIXTURE TOOL_RESULT ===");

  for (const listener of listeners) {
    listener({
      type: "hook",
      payload: {
        sessionId,
        hookEventName: "tool_result",
        toolName: "read_file",
        ts: new Date().toISOString(),
      },
    });
  }

  await new Promise((resolve) => setTimeout(resolve, 1000));

  console.log("\n=== CHECKING POINTER LIST ===");

  const response = await fetch(
    "http://127.0.0.1:8000/api/v1/pointers/runtime?workspace_id=w1&session_id=fixture-session"
  );

  console.log("status:", response.status);

  const text = await response.text();
  console.log(text);

  detach();

  console.log("\n=== FIXTURE ADAPTER TEST COMPLETE ===");
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

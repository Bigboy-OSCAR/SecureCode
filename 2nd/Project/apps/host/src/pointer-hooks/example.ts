import { storeRuntimePointer } from "./runtimePointerHook.js";

async function main() {
  const largeToolOutput = "x".repeat(10000);

  const result = await storeRuntimePointer(
    {
      toolName: "read_file",
      content: largeToolOutput,
    },
    {
      workspaceId: "w1",
      sessionId: "s1",
      thresholdBytes: 4096,
    },
  );

  console.log("hook result:", result);
}

main().catch((error) => {
  console.error("hook test failed:", error);
  process.exit(1);
});

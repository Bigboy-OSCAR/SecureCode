import { createRuntimePointerPlugin } from "./runtimePointerPlugin.js";

async function main() {
  const plugin = createRuntimePointerPlugin({
    workspaceId: "w1",
    sessionId: "s1",
    thresholdBytes: 4096,
  });

  const fakeContext = {
    toolCall: {
      toolName: "read_file",
    },
    result: "y".repeat(10000),
  };

  const hook = plugin.hooks.afterTool;
  const output = await hook(fakeContext as never);

  console.log("plugin hook output:");
  console.log(output);
}

main().catch((error) => {
  console.error("plugin test failed:", error);
  process.exit(1);
});

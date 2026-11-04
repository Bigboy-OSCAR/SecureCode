import { ClineCore } from "@cline/sdk";
import { createRuntimePointerPlugin } from "./runtimePointerPlugin.js";

async function main() {
  const plugin = createRuntimePointerPlugin({
    workspaceId: "w1",
    sessionId: "s1",
    thresholdBytes: 4096,
  });

  const cline = await ClineCore.create({
    clientName: "securecode-host",
    plugins: [plugin],
  });

  console.log("ClineCore created with plugin:");
  console.log(cline);

  await cline.dispose();
}

main().catch((error) => {
  console.error("ClineCore plugin test failed:", error);
  process.exit(1);
});

import { ClineCore } from "clinesdk";
import { registerRuntimePointerHooks } from "./runtimePointerHooks";

async function main() {
  const core = await ClineCore.create({
    provider: "scripted",
  });

  registerRuntimePointerHooks(core, {
    baseUrl: "http://127.0.0.1:8000",
    workspaceId: "w1",
    sessionId: "s1",
    thresholdBytes: 8 * 1024,
    maxBytes: 32 * 1024,
  });

  await core.start();

  await core.send({
    text: "Analyze this large PDF and summarize page 3.",
  });

  await core.dispose();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});

import { ClineCore } from "@cline/sdk";

function printEvent(event: unknown) {
  console.log("\n=== EVENT ===");
  console.log(JSON.stringify(event, null, 2));
}

function extractText(event: any): string | undefined {
  return (
    event?.payload?.text ??
    event?.text ??
    event?.payload?.delta?.text ??
    event?.payload?.content?.text
  );
}

function extractError(event: any): unknown {
  return (
    event?.payload?.error ??
    event?.error ??
    event?.payload?.message ??
    event?.message ??
    event?.payload?.detail ??
    event?.detail
  );
}

async function main() {
  const cline = await ClineCore.create({
    clientName: "securecode-host",
    backendMode: "auto",
  });

  const unsubscribe = cline.subscribe((event) => {
    printEvent(event);

    const text = extractText(event);
    if (text) {
      process.stdout.write(text);
    }

    const error = extractError(event);
    if (error) {
      console.log("\n\n=== POSSIBLE ERROR ===");
      console.log(JSON.stringify(error, null, 2));
    }
  });

  const session = await cline.start({
    prompt: "Say exactly: SecureCode Cline session is working.",
    config: {
      providerId: "anthropic",
      modelId: "claude-sonnet-4-6",
      apiKey: process.env.ANTHROPIC_API_KEY,
      systemPrompt: "You are a helpful coding assistant.",
      cwd: process.cwd(),
      workspaceRoot: process.cwd(),
      enableTools: false,
      enableSpawnAgent: false,
      enableAgentTeams: false,
    },
  });

  console.log("\n=== SESSION RESULT ===");
  console.log(JSON.stringify(session, null, 2));

  unsubscribe();
  await cline.dispose();
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

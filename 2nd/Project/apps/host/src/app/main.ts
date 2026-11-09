/**
 * Host entry point: load config, isolate the Cline home, import the SDK
 * adapter only afterwards, assemble the host and listen on loopback. Started by
 * `npm run dev` (scripts/dev/start.ts), which also starts the context-service
 * and shows the one-time launch code.
 */
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { ContractValidator } from "@securecode/contracts";
import { prepareClineHome } from "../config/clineHome.js";
import { ConfigError, loadHostConfig } from "../config/hostConfig.js";
import { loadRuntimeConfig, readProviderCredentials } from "../config/runtimeConfig.js";
import { HttpContextServiceClient } from "../context-client/httpContextServiceClient.js";
import { createLogger } from "../logging/logger.js";
import { Redactor } from "../logging/redaction.js";
import { assembleHost } from "./hostAssembly.js";
import {
    createLoopbackRuntimeStore,
    createRuntimeToolResultTransformer,
} from "../pointer-hooks/runtimeToolResultTransformer.js";

const SHUTDOWN_TIMEOUT_MS = 5000;
const workRoot = join(fileURLToPath(import.meta.url), "..", "..", "..", "..", "..");

async function main(): Promise<void> {
    let hostConfig;
    let runtimeConfig;
    try {
        hostConfig = loadHostConfig(process.env, workRoot);
        runtimeConfig = loadRuntimeConfig(process.env, hostConfig.dataDir);
    } catch (error) {
        if (error instanceof ConfigError) {
            process.stderr.write(`host config error: ${error.message}\n`);
            process.exitCode = 2;
            return;
        }
        throw error;
    }
    const credentials = readProviderCredentials(process.env);
    const redactor = new Redactor([
        hostConfig.internalToken,
        credentials.apiKey ?? "",
        runtimeConfig.bootstrapCode ?? "",
    ]);
    const logger = createLogger(hostConfig.logLevel, redactor);
    prepareClineHome(runtimeConfig.clineHome);
    // Imported after prepareClineHome so the SDK only ever sees the app-only home (3.1 C-02).
    const clineAdapter = await import("../cline/adapter/clineRuntime.js");
    const host = await assembleHost({
        hostConfig,
        runtimeConfig,
        credentials,
        contextClient: new HttpContextServiceClient({
            baseUrl: hostConfig.contextServiceUrl,
            internalToken: hostConfig.internalToken,
            validator: ContractValidator.load(),
        }),
        validator: ContractValidator.load(),
        logger,
        runtimeFactory: (options) => clineAdapter.ClineAgentRuntime.create(options),
        // 4.8's verified request gate is still unavailable, so sessions remain blocked.
        transformer: createRuntimeToolResultTransformer(
            createLoopbackRuntimeStore({
                baseUrl: hostConfig.contextServiceUrl,
                internalToken: hostConfig.internalToken,
                api: "internal",
            }),
        ),
        gate: null,
    });
    const missing = host.runtime.protections().filter((state) => !state.ready);
    if (missing.length > 0) {
        logger.warn(`protections not ready: ${missing.map((state) => state.name).join(", ")}; sessions are refused`);
    }

    host.server.listen(hostConfig.port, hostConfig.host, () => {
        logger.info(`host listening on http://${hostConfig.host}:${hostConfig.port}`);
        if (host.bootstrapCodeGenerated) {
            // Shown once on the local terminal; it is single-use and expires in 10 minutes.
            process.stdout.write(`SecureCode launch code: ${host.bootstrapCode}\n`);
        }
    });

    const shutdown = (signal: string): void => {
        logger.info(`host received ${signal}; closing`);
        host.shutdown().then(
            () => process.exit(0),
            () => process.exit(1),
        );
        setTimeout(() => process.exit(1), SHUTDOWN_TIMEOUT_MS).unref();
    };
    process.once("SIGINT", () => shutdown("SIGINT"));
    process.once("SIGTERM", () => shutdown("SIGTERM"));
}

await main();

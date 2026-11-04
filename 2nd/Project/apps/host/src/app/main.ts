/**
 * Host entry point: load config, assemble dependencies, listen on loopback,
 * and shut down gracefully on SIGINT/SIGTERM. Started by `npm run dev`
 * (scripts/dev/start.ts), which also starts the context-service.
 */
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { ContractValidator } from "@securecode/contracts";
import { ConfigError, loadHostConfig } from "../config/hostConfig.js";
import { HttpContextServiceClient } from "../context-client/httpContextServiceClient.js";
import { createLogger } from "../logging/logger.js";
import { Redactor } from "../logging/redaction.js";
import { createHostServer } from "./server.js";

const SHUTDOWN_TIMEOUT_MS = 5000;
const workRoot = join(fileURLToPath(import.meta.url), "..", "..", "..", "..", "..");

function main(): void {
    let config;
    try {
        config = loadHostConfig(process.env, workRoot);
    } catch (error) {
        if (error instanceof ConfigError) {
            process.stderr.write(`host config error: ${error.message}\n`);
            process.exitCode = 2;
            return;
        }
        throw error;
    }

    const redactor = new Redactor([config.internalToken, process.env.ANTHROPIC_API_KEY ?? ""]);
    const logger = createLogger(config.logLevel, redactor);
    const contextClient = new HttpContextServiceClient({
        baseUrl: config.contextServiceUrl,
        internalToken: config.internalToken,
        validator: ContractValidator.load(),
    });
    const server = createHostServer({
        contextClient,
        originPolicy: { allowedOrigins: config.allowedOrigins, allowedHosts: config.allowedHosts },
        logger,
    });

    server.listen(config.port, config.host, () => {
        logger.info(`host listening on http://${config.host}:${config.port}`);
    });

    const shutdown = (signal: string): void => {
        logger.info(`host received ${signal}; closing`);
        server.close(() => process.exit(0));
        setTimeout(() => process.exit(1), SHUTDOWN_TIMEOUT_MS).unref();
    };
    process.once("SIGINT", () => shutdown("SIGINT"));
    process.once("SIGTERM", () => shutdown("SIGTERM"));
}

main();

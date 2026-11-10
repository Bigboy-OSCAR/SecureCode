/** Loopback port checks for the dev launcher and tests (3.7: conflicts name the setting to change). */
import { createServer } from "node:net";

function bindOnce(port: number): Promise<number> {
    return new Promise((done, reject) => {
        const socket = createServer();
        socket.once("error", reject);
        socket.listen(port, "127.0.0.1", () => {
            const address = socket.address();
            socket.close((error) => {
                if (error || !address || typeof address === "string") reject(error ?? new Error("port unavailable"));
                else done(address.port);
            });
        });
    });
}

/** Resolves when 127.0.0.1:port is free; a conflict names the environment variable that moves it. */
export async function checkPort(port: number, setting = "port"): Promise<number> {
    if (!Number.isInteger(port) || port < 0 || port > 65535) throw new Error(`${setting} must be 0..65535`);
    try {
        return await bindOnce(port);
    } catch (error) {
        if ((error as NodeJS.ErrnoException).code === "EADDRINUSE") {
            throw new Error(
                `127.0.0.1:${port} is already in use (${setting}). Stop the other process (npm run stop) or set another ${setting} in .env`,
                { cause: error },
            );
        }
        throw error;
    }
}

/** Distinct free loopback ports, e.g. for tests that start the whole stack. */
export async function findFreePorts(): Promise<{ hostPort: number; servicePort: number; uiPort: number }> {
    const ports = new Set<number>();
    while (ports.size < 3) ports.add(await bindOnce(0));
    const [hostPort = 0, servicePort = 0, uiPort = 0] = [...ports];
    return { hostPort, servicePort, uiPort };
}

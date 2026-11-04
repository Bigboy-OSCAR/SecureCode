/** Location and shape of the dev process record (no secrets: pids and ports only). */
import { join } from "node:path";

export interface DevState {
    host_pid?: number;
    service_pid?: number;
    host_port: number;
    service_port: number;
    started_at: string;
}

export function devStatePath(dataDir: string): string {
    return join(dataDir, "run", "dev-processes.json");
}

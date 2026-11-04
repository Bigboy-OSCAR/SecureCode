/**
 * Creates a real `ClineCore` on the in-process local backend with the scripted
 * provider transport and an app-owned approval capability.
 */
import { ClineCore, type ToolApprovalRequest, type ToolApprovalResult } from "@cline/sdk";

type RuntimeCapabilities = NonNullable<Parameters<typeof ClineCore.create>[0]>["capabilities"];
export type ProbeToolExecutors = NonNullable<NonNullable<RuntimeCapabilities>["toolExecutors"]>;

export type ApprovalHandler = (request: ToolApprovalRequest) => Promise<ToolApprovalResult>;

export interface ProbeCoreOptions {
    fetch: typeof fetch;
    requestToolApproval?: ApprovalHandler;
    /** Replaces built-in tool executors (read_files, search_codebase, run_commands, ...). */
    toolExecutors?: ProbeToolExecutors;
}

const rejectByDefault: ApprovalHandler = async () => ({
    approved: false,
    reason: "probe default: no approval handler",
});

export async function createProbeCore(options: ProbeCoreOptions): Promise<ClineCore> {
    return ClineCore.create({
        clientName: "securecode-sdk-probe",
        distinctId: "securecode-sdk-probe",
        backendMode: "local",
        automation: false,
        fetch: options.fetch,
        capabilities: {
            requestToolApproval: options.requestToolApproval ?? rejectByDefault,
            ...(options.toolExecutors ? { toolExecutors: options.toolExecutors } : {}),
        },
    });
}

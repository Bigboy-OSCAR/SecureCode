/** Restore server-owned workspaces and conversations; only selection IDs are stored in the browser. */
import { useCallback, useEffect, useRef, useState } from "react";
import type {
    IdempotencyKey,
    HealthResponse,
    RunSummary,
    Session,
    SettingsResponse,
    Workspace,
} from "@securecode/contracts";
import type { ApiHttpClient } from "../../../api/httpClient.js";
import { ApiClientError, formatApiFailure } from "../../../api/apiErrors.js";
import { createIdempotencyKey } from "../../../api/runClient.js";

const SELECTION_KEY = "localdesk.selection.v1";
export interface DeskChat {
    session: Session;
    runs: RunSummary[];
    title: string;
}

function readSelection(): { workspaceId?: string; sessionId?: string } {
    try {
        const data: unknown = JSON.parse(localStorage.getItem(SELECTION_KEY) ?? "{}");
        if (typeof data !== "object" || !data) return {};
        return {
            workspaceId: "workspaceId" in data && typeof data.workspaceId === "string" ? data.workspaceId : undefined,
            sessionId: "sessionId" in data && typeof data.sessionId === "string" ? data.sessionId : undefined,
        };
    } catch {
        return {};
    }
}

async function readChats(api: ApiHttpClient, workspace: Workspace): Promise<DeskChat[]> {
    const sessions: Session[] = [];
    let cursor: string | undefined;
    do {
        const page = await api.listSessions(workspace.workspace_id, cursor);
        sessions.push(...page.items);
        cursor = page.page.next_cursor ?? undefined;
    } while (cursor);
    return Promise.all(
        sessions.map(async (session) => {
            const runs: RunSummary[] = [];
            let runCursor: string | undefined;
            do {
                const page = await api.listRuns(session.session_id, runCursor);
                runs.push(...page.items);
                runCursor = page.page.next_cursor ?? undefined;
            } while (runCursor);
            runs.sort((a, b) => a.created_at.localeCompare(b.created_at));
            return { session, runs, title: runs[0]?.prompt_preview ?? "새 대화" };
        }),
    );
}

export interface DeskWorkspaceState {
    connected: boolean;
    health: HealthResponse | null;
    settings: SettingsResponse | null;
    workspaces: Workspace[];
    workspace: Workspace | null;
    session: Session | null;
    chats: DeskChat[];
    error: string | null;
    busy: boolean;
    refresh: () => Promise<void>;
    selectWorkspace: (workspace: Workspace, preferredSession?: string) => Promise<void>;
    setSession: (session: Session) => void;
    newChat: (workspace?: Workspace | null) => Promise<void>;
    register: (name: string, path: string) => Promise<void>;
    refreshChats: () => Promise<void>;
    onStatus: (health: HealthResponse, settings: SettingsResponse) => void;
}
export function useDeskWorkspace(api: ApiHttpClient): DeskWorkspaceState {
    const [connected, setConnected] = useState(false);
    const [health, setHealth] = useState<HealthResponse | null>(null);
    const [settings, setSettings] = useState<SettingsResponse | null>(null);
    const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
    const [workspace, setWorkspace] = useState<Workspace | null>(null);
    const [session, setSession] = useState<Session | null>(null);
    const [chats, setChats] = useState<DeskChat[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);
    const epoch = useRef(0);
    const registration = useRef<{ fingerprint: string; key: IdempotencyKey } | null>(null);
    const sessionRequests = useRef(new Map<string, IdempotencyKey>());
    const selectWorkspace = useCallback(
        async (next: Workspace, preferredSession?: string): Promise<void> => {
            const token = ++epoch.current;
            setWorkspace(next);
            setSession(null);
            setChats([]);
            setError(null);
            try {
                const rows = await readChats(api, next);
                if (token !== epoch.current) return;
                setChats(rows);
                setSession(
                    rows.find((row) => row.session.session_id === preferredSession)?.session ??
                        rows.at(-1)?.session ??
                        null,
                );
            } catch (failure) {
                if (token === epoch.current) setError(formatApiFailure(failure, "이전 대화를 불러오지 못했습니다."));
            }
        },
        [api],
    );
    const refresh = useCallback(async (): Promise<void> => {
        try {
            const [nextSettings, nextHealth] = await Promise.all([api.getSettings(), api.getHealth()]);
            const all: Workspace[] = [];
            let cursor: string | undefined;
            do {
                const page = await api.listWorkspaces(cursor);
                all.push(...page.items);
                cursor = page.page.next_cursor ?? undefined;
            } while (cursor);
            setConnected(true);
            setSettings(nextSettings);
            setHealth(nextHealth);
            setWorkspaces(all);
            const selection = readSelection();
            const next = all.find((item) => item.workspace_id === selection.workspaceId) ?? all[0];
            if (next) await selectWorkspace(next, selection.sessionId);
        } catch (failure) {
            if (failure instanceof ApiClientError && failure.kind === "unauthorized") setConnected(false);
            else setError(formatApiFailure(failure, "로컬 서비스에 연결하지 못했습니다."));
        }
    }, [api, selectWorkspace]);
    useEffect(() => {
        void refresh();
    }, [refresh]);
    useEffect(() => {
        const expired = (): void => setConnected(false);
        window.addEventListener("localdesk:auth-expired", expired);
        return () => window.removeEventListener("localdesk:auth-expired", expired);
    }, []);
    useEffect(() => {
        if (!workspace) return;
        try {
            localStorage.setItem(
                SELECTION_KEY,
                JSON.stringify({ workspaceId: workspace.workspace_id, sessionId: session?.session_id }),
            );
        } catch {
            /* Selection can still be restored from server lists if storage is unavailable. */
        }
    }, [workspace, session]);
    const newChat = async (target: Workspace | null = workspace): Promise<void> => {
        if (!target || busy) return;
        setBusy(true);
        setError(null);
        try {
            const requestKey = sessionRequests.current.get(target.workspace_id) ?? createIdempotencyKey();
            sessionRequests.current.set(target.workspace_id, requestKey);
            const created = await api.createSession({
                workspace_id: target.workspace_id,
                idempotency_key: requestKey,
            });
            sessionRequests.current.delete(target.workspace_id);
            if (workspace?.workspace_id !== target.workspace_id) await selectWorkspace(target, created.session_id);
            else setChats((rows) => [...rows, { session: created, runs: [], title: "새 대화" }]);
            setSession(created);
        } catch (failure) {
            setError(formatApiFailure(failure, "새 대화를 시작하지 못했습니다."));
        } finally {
            setBusy(false);
        }
    };
    const register = async (name: string, path: string): Promise<void> => {
        const fingerprint = `${name}\0${path}`;
        if (registration.current?.fingerprint !== fingerprint)
            registration.current = { fingerprint, key: createIdempotencyKey() };
        const created = await api.createWorkspace({
            display_name: name,
            root_path: path,
            idempotency_key: registration.current.key,
        });
        registration.current = null;
        setWorkspaces((rows) => [...rows.filter((row) => row.workspace_id !== created.workspace_id), created]);
        await selectWorkspace(created);
        await newChat(created);
    };
    const refreshChats = useCallback(async (): Promise<void> => {
        if (!workspace) return;
        const token = epoch.current;
        try {
            const rows = await readChats(api, workspace);
            if (token === epoch.current) setChats(rows);
        } catch (failure) {
            setError(formatApiFailure(failure, "대화 목록을 갱신하지 못했습니다."));
        }
    }, [api, workspace]);
    return {
        connected,
        health,
        settings,
        workspaces,
        workspace,
        session,
        chats,
        error,
        busy,
        refresh,
        selectWorkspace,
        setSession,
        newChat,
        register,
        refreshChats,
        onStatus: (h: HealthResponse, s: SettingsResponse): void => {
            setHealth(h);
            setSettings(s);
        },
    };
}

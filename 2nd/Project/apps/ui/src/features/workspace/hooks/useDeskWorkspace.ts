/** Restore server-owned workspaces and conversations; only selection IDs are stored in the browser. */
import { useCallback, useEffect, useRef, useState } from "react";
import type { IdempotencyKey, HealthResponse, Session, SettingsResponse, Workspace } from "@securecode/contracts";
import type { ApiHttpClient } from "../../../api/httpClient.js";
import { ApiClientError, formatApiFailure } from "../../../api/apiErrors.js";
import { persistNativeSelection } from "../../../api/nativeSelection.js";
import { createIdempotencyKey } from "../../../api/runClient.js";
import { readChats, type DeskChat } from "../model/deskChats.js";
export type { DeskChat } from "../model/deskChats.js";

const SELECTION_KEY = "localdesk.selection.v1";

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
    loadingChats: boolean;
    refresh: () => Promise<void>;
    selectWorkspace: (workspace: Workspace, preferredSession?: string) => Promise<void>;
    setSession: (session: Session) => void;
    newChat: (workspace?: Workspace | null) => Promise<void>;
    register: (name: string, path: string) => Promise<void>;
    removeProject: (workspace: Workspace) => Promise<boolean>;
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
    const [busy, setBusyState] = useState(false);
    const busyRef = useRef(false);
    const setBusy = useCallback((value: boolean): void => {
        busyRef.current = value;
        setBusyState(value);
    }, []);
    const [loadingChats, setLoadingChats] = useState(false);
    const epoch = useRef(0);
    const selectedWorkspace = useRef<Workspace | null>(null);
    const selectedSession = useRef<Session | null>(null);
    const workspaceList = useRef<Workspace[]>([]);
    const saveWorkspaces = useCallback((rows: Workspace[]): void => {
        workspaceList.current = rows;
        setWorkspaces(rows);
    }, []);
    const chooseSession = useCallback((next: Session | null): void => {
        selectedSession.current = next;
        setSession(next);
    }, []);
    const registration = useRef<{ fingerprint: string; key: IdempotencyKey } | null>(null);
    const sessionRequests = useRef(new Map<string, IdempotencyKey>());
    const projectMutation = useRef(Promise.resolve());
    const inProjectOrder = <T>(operation: () => Promise<T>): Promise<T> => {
        const result = projectMutation.current.then(operation);
        projectMutation.current = result.then(
            () => undefined,
            () => undefined,
        );
        return result;
    };
    const selectWorkspace = useCallback(
        async (next: Workspace, preferredSession?: string): Promise<void> => {
            const token = ++epoch.current;
            const sameProject = selectedWorkspace.current?.workspace_id === next.workspace_id;
            const preferred = preferredSession ?? (sameProject ? selectedSession.current?.session_id : undefined);
            selectedWorkspace.current = next;
            setWorkspace(next);
            if (!sameProject) {
                chooseSession(null);
                setChats([]);
            }
            setLoadingChats(true);
            setError(null);
            try {
                const rows = await readChats(api, next);
                if (token !== epoch.current) return;
                setChats(rows);
                chooseSession(
                    rows.find((row) => row.session.session_id === preferred)?.session ?? rows[0]?.session ?? null,
                );
            } catch (failure) {
                if (token === epoch.current) setError(formatApiFailure(failure, "이전 대화를 불러오지 못했습니다."));
            } finally {
                if (token === epoch.current) setLoadingChats(false);
            }
        },
        [api, chooseSession],
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
            saveWorkspaces(all);
            const selection = readSelection();
            const next = all.find((item) => item.workspace_id === selection.workspaceId) ?? all[0];
            if (next) await selectWorkspace(next, selection.sessionId);
            else {
                ++epoch.current;
                selectedWorkspace.current = null;
                setWorkspace(null);
                chooseSession(null);
                setChats([]);
                setLoadingChats(false);
            }
        } catch (failure) {
            if (failure instanceof ApiClientError && failure.kind === "unauthorized") setConnected(false);
            else setError(formatApiFailure(failure, "로컬 서비스에 연결하지 못했습니다."));
        }
    }, [api, selectWorkspace, chooseSession, saveWorkspaces]);
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
        persistNativeSelection(workspace.workspace_id, session?.session_id);
    }, [workspace, session]);
    const newChat = async (target: Workspace | null = workspace): Promise<void> => {
        if (!target || busyRef.current) return;
        const token = ++epoch.current;
        setLoadingChats(false);
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
            if (token !== epoch.current) return;
            await selectWorkspace(target, created.session_id);
        } catch (failure) {
            setError(formatApiFailure(failure, "새 대화를 시작하지 못했습니다."));
        } finally {
            setBusy(false);
        }
    };
    const register = (name: string, path: string): Promise<void> =>
        inProjectOrder(async () => {
            const fingerprint = `${name}\0${path}`;
            if (registration.current?.fingerprint !== fingerprint)
                registration.current = { fingerprint, key: createIdempotencyKey() };
            const created = await api.createWorkspace({
                display_name: name,
                root_path: path,
                idempotency_key: registration.current.key,
            });
            registration.current = null;
            saveWorkspaces([
                ...workspaceList.current.filter((row) => row.workspace_id !== created.workspace_id),
                created,
            ]);
            await selectWorkspace(created);
            await newChat(created);
        });
    const refreshChats = useCallback(async (): Promise<void> => {
        if (!workspace) return;
        const token = epoch.current;
        try {
            const rows = await readChats(api, workspace);
            if (token === epoch.current) setChats(rows);
        } catch (failure) {
            if (token === epoch.current) setError(formatApiFailure(failure, "대화 목록을 갱신하지 못했습니다."));
        }
    }, [api, workspace]);
    const removeProject = (target: Workspace): Promise<boolean> =>
        inProjectOrder(async () => {
            if (busyRef.current) return false;
            setBusy(true);
            setError(null);
            try {
                await api.deleteWorkspace(target.workspace_id);
                const remaining = workspaceList.current.filter((item) => item.workspace_id !== target.workspace_id);
                saveWorkspaces(remaining);
                if (selectedWorkspace.current?.workspace_id === target.workspace_id) {
                    const next = remaining[0];
                    if (next) await selectWorkspace(next);
                    else {
                        ++epoch.current;
                        selectedWorkspace.current = null;
                        setWorkspace(null);
                        chooseSession(null);
                        setChats([]);
                        setLoadingChats(false);
                        try {
                            localStorage.removeItem(SELECTION_KEY);
                        } catch {
                            /* Server list remains authoritative. */
                        }
                    }
                }
                return true;
            } catch (failure) {
                setError(formatApiFailure(failure, "프로젝트를 삭제하지 못했습니다."));
                return false;
            } finally {
                setBusy(false);
            }
        });
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
        loadingChats,
        refresh,
        selectWorkspace,
        setSession: (next): void => {
            if (next.workspace_id !== selectedWorkspace.current?.workspace_id) return;
            ++epoch.current;
            setLoadingChats(false);
            chooseSession(next);
        },
        newChat,
        register,
        removeProject,
        refreshChats,
        onStatus: (h: HealthResponse, s: SettingsResponse): void => {
            setHealth(h);
            setSettings(s);
        },
    };
}

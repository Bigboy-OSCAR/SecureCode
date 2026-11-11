/** Recoverable conversation removal uses the same mutation queue as project changes. */
import { useState } from "react";
import type { Session } from "@securecode/contracts";
import type { ApiHttpClient } from "../../../api/httpClient.js";
import { formatApiFailure } from "../../../api/apiErrors.js";

interface Options {
    enqueue: <T>(operation: () => Promise<T>) => Promise<T>;
    isBusy: () => boolean;
    setBusy: (value: boolean) => void;
    onChanged: (session: Session, deleted: boolean) => Promise<void>;
    onError: (message: string | null) => void;
}

export function useChatRemoval(
    api: ApiHttpClient,
    options: Options,
): {
    deletedChat: Session | null;
    removeChat: (session: Session) => Promise<boolean>;
    undoChatRemoval: () => Promise<void>;
    dismissChatRemoval: () => void;
} {
    const [deletedChat, setDeletedChat] = useState<Session | null>(null);
    const removeChat = (session: Session): Promise<boolean> =>
        options.enqueue(async () => {
            if (options.isBusy()) return false;
            options.setBusy(true);
            options.onError(null);
            try {
                await api.deleteSession(session.session_id);
                setDeletedChat(session);
                await options.onChanged(session, true);
                return true;
            } catch (failure) {
                options.onError(formatApiFailure(failure, "대화를 삭제하지 못했습니다."));
                return false;
            } finally {
                options.setBusy(false);
            }
        });
    const undoChatRemoval = (): Promise<void> =>
        options.enqueue(async () => {
            if (!deletedChat || options.isBusy()) return;
            options.setBusy(true);
            options.onError(null);
            try {
                const restored = await api.restoreSession(deletedChat.session_id);
                setDeletedChat(null);
                await options.onChanged(restored, false);
            } catch (failure) {
                options.onError(formatApiFailure(failure, "대화를 복원하지 못했습니다."));
            } finally {
                options.setBusy(false);
            }
        });
    return { deletedChat, removeChat, undoChatRemoval, dismissChatRemoval: () => setDeletedChat(null) };
}

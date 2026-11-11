/** Follow new chat content only while the reader is at the bottom or has just submitted a question. */
import { useLayoutEffect, useRef, type RefObject } from "react";

export function useChatScroll(
    sessionId: string,
    restoring: boolean,
): {
    messagesRef: RefObject<HTMLDivElement | null>;
    onScroll: () => void;
    followLatest: () => void;
} {
    const messagesRef = useRef<HTMLDivElement>(null);
    const following = useRef(true);
    const currentSession = useRef(sessionId);
    const followLatest = (): void => {
        following.current = true;
        const element = messagesRef.current;
        if (element) element.scrollTop = element.scrollHeight;
    };
    useLayoutEffect(() => {
        if (currentSession.current !== sessionId || restoring) {
            currentSession.current = sessionId;
            following.current = true;
        }
        if (following.current) followLatest();
    });
    return {
        messagesRef,
        followLatest,
        onScroll: () => {
            const element = messagesRef.current;
            if (element) following.current = element.scrollHeight - element.clientHeight - element.scrollTop <= 64;
        },
    };
}

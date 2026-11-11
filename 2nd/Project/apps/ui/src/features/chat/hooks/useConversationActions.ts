import type { ExplicitContextRef } from "@securecode/contracts";
import { useState, type FormEvent, type KeyboardEvent } from "react";
import { shouldSubmitQuestionOnEnter } from "../model/questionInput.js";
import type { RunController } from "../model/runController.js";
import type { RunViewState } from "../model/runState.js";

export function useConversationActions(
    controller: RunController,
    state: RunViewState,
    contextRefs: ExplicitContextRef[] = [],
): {
    prompt: string;
    setPrompt: (prompt: string) => void;
    canSubmit: boolean;
    canCancel: boolean;
    submit: (event: FormEvent<HTMLFormElement>) => void;
    onPromptKeyDown: (event: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) => void;
    reconnect: () => void;
} {
    const [prompt, setPrompt] = useState("");
    const submit = (event: FormEvent<HTMLFormElement>): void => {
        event.preventDefault();
        const sent = prompt;
        void controller.createRun(sent, contextRefs).then((created) => {
            // Clear only after the host accepted the run; a failed create keeps the text for a retry.
            if (created) {
                setPrompt((current) => (current === sent ? "" : current));
            }
        });
    };
    const onPromptKeyDown = (event: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>): void => {
        if (
            shouldSubmitQuestionOnEnter(
                event.key,
                event.shiftKey,
                event.nativeEvent.isComposing,
                event.nativeEvent.keyCode,
            )
        ) {
            event.preventDefault();
            event.currentTarget.form?.requestSubmit();
        }
    };

    return {
        prompt,
        setPrompt,
        canSubmit: controller.canSubmitRun(prompt) && state.operation === null,
        canCancel: controller.canCancelRun(),
        submit,
        onPromptKeyDown,
        reconnect: () => {
            void controller.reconnect();
        },
    };
}

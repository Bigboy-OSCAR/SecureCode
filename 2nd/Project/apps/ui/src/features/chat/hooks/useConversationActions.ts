import { useState, type FormEvent, type KeyboardEvent } from "react";
import { fixtureAdapter } from "../../../api/fixtureAdapter.js";
import { shouldSubmitQuestionOnEnter } from "../model/questionInput.js";
import type { RunController } from "../model/runController.js";
import type { RunViewState } from "../model/runState.js";

export function useConversationActions(
    controller: RunController,
    state: RunViewState,
    fixtureMode = true,
): {
    prompt: string;
    setPrompt: (prompt: string) => void;
    canSubmit: boolean;
    canCancel: boolean;
    submit: (event: FormEvent<HTMLFormElement>) => void;
    onPromptKeyDown: (event: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) => void;
    reconnect: () => void;
} {
    const [prompt, setPrompt] = useState(fixtureMode ? fixtureAdapter.runs[0]!.prompt_preview : "");
    const submit = (event: FormEvent<HTMLFormElement>): void => {
        event.preventDefault();
        void controller.createRun(prompt);
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

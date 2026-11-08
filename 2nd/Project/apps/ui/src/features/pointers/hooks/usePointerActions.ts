import { useState, type FormEvent } from "react";
import { isSourcePathValid } from "../model/pointerForm.js";

export type PointerDeleteIntent = "source" | "runtime";

export function usePointerActions(): {
    sourcePath: string;
    intent: PointerDeleteIntent | null;
    confirmed: PointerDeleteIntent | null;
    registrationValid: boolean;
    setSourcePath: (value: string) => void;
    submitRegistration: (event: FormEvent<HTMLFormElement>) => void;
    openDeleteConfirmation: (intent: PointerDeleteIntent) => void;
    closeDeleteConfirmation: () => void;
    confirmDeleteIntent: () => void;
} {
    const [sourcePath, setSourcePathValue] = useState("");
    const [intent, setIntent] = useState<PointerDeleteIntent | null>(null);
    const [confirmed, setConfirmed] = useState<PointerDeleteIntent | null>(null);
    const [registrationValid, setRegistrationValid] = useState(false);

    return {
        sourcePath,
        intent,
        confirmed,
        registrationValid,
        setSourcePath: (value) => {
            setSourcePathValue(value);
            setRegistrationValid(false);
        },
        submitRegistration: (event) => {
            event.preventDefault();
            if (isSourcePathValid(sourcePath)) {
                setRegistrationValid(true);
            }
        },
        openDeleteConfirmation: (nextIntent) => {
            setConfirmed(null);
            setIntent(nextIntent);
        },
        closeDeleteConfirmation: () => setIntent(null),
        confirmDeleteIntent: () => {
            if (intent) {
                setConfirmed(intent);
                setIntent(null);
            }
        },
    };
}

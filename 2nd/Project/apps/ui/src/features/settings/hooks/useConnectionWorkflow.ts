import { useState, type FormEvent } from "react";
import { isBootstrapCodeValid } from "../model/inputValidation.js";

type ConnectionStatus = "expired" | "awaiting_code" | "validated";

export function useConnectionWorkflow(): {
    code: string;
    status: ConnectionStatus;
    canSubmit: boolean;
    setCode: (value: string) => void;
    dismissExpired: () => void;
    submit: (event: FormEvent<HTMLFormElement>) => void;
} {
    const [code, setCodeValue] = useState("");
    const [status, setStatus] = useState<ConnectionStatus>("expired");
    const canSubmit = isBootstrapCodeValid(code);

    return {
        code,
        status,
        canSubmit,
        setCode: (value) => {
            setCodeValue(value);
            setStatus("awaiting_code");
        },
        dismissExpired: () => setStatus("awaiting_code"),
        submit: (event) => {
            event.preventDefault();
            if (canSubmit) {
                setStatus("validated");
                setCodeValue("");
            }
        },
    };
}

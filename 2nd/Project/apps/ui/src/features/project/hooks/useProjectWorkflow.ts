import { useState, type FormEvent } from "react";
import type { IndexStatusResponse } from "@securecode/contracts";
import { fixtureAdapter } from "../../../api/fixtureAdapter.js";
import { isProjectFormValid } from "../model/projectForm.js";

export function useProjectWorkflow(): {
    displayName: string;
    rootPath: string;
    index: IndexStatusResponse;
    indexPosition: number;
    registrationValidated: boolean;
    setDisplayName: (value: string) => void;
    setRootPath: (value: string) => void;
    selectIndex: (position: number) => void;
    submit: (event: FormEvent<HTMLFormElement>) => void;
    formValid: boolean;
} {
    const [displayName, setDisplayName] = useState("");
    const [rootPath, setRootPath] = useState("");
    const [indexPosition, setIndexPosition] = useState(1);
    const [registrationValidated, setRegistrationValidated] = useState(false);
    const index = fixtureAdapter.indexStates[indexPosition]!;
    const formValid = isProjectFormValid(displayName, rootPath);

    return {
        displayName,
        rootPath,
        index,
        indexPosition,
        registrationValidated,
        setDisplayName: (value) => {
            setDisplayName(value);
            setRegistrationValidated(false);
        },
        setRootPath: (value) => {
            setRootPath(value);
            setRegistrationValidated(false);
        },
        selectIndex: (position) => {
            if (fixtureAdapter.indexStates[position]) {
                setIndexPosition(position);
            }
        },
        submit: (event) => {
            event.preventDefault();
            if (formValid) {
                setRegistrationValidated(true);
            }
        },
        formValid,
    };
}

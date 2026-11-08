import { useState, type FormEvent } from "react";
import type { PdfJobStatus } from "@securecode/contracts";
import { fixtureAdapter } from "../../../api/fixtureAdapter.js";
import { isPdfPathValid } from "../model/pointerForm.js";

export function usePdfWorkflow(): {
    path: string;
    selectedPosition: number;
    job: PdfJobStatus;
    submitted: boolean;
    canSubmit: boolean;
    setPath: (value: string) => void;
    selectJob: (position: number) => void;
    submit: (event: FormEvent<HTMLFormElement>) => void;
} {
    const [path, setPathValue] = useState("");
    const [selectedPosition, setSelectedPosition] = useState(3);
    const [submitted, setSubmitted] = useState(false);
    const job = fixtureAdapter.pdfJobs[selectedPosition]!;
    const canSubmit = isPdfPathValid(path);

    return {
        path,
        selectedPosition,
        job,
        submitted,
        canSubmit,
        setPath: (value) => {
            setPathValue(value);
            setSubmitted(false);
        },
        selectJob: (position) => {
            if (fixtureAdapter.pdfJobs[position]) {
                setSelectedPosition(position);
                setSubmitted(false);
            }
        },
        submit: (event) => {
            event.preventDefault();
            if (canSubmit) {
                setSubmitted(true);
            }
        },
    };
}

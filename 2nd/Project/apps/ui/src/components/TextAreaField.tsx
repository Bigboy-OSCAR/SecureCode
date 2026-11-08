import type { TextareaHTMLAttributes } from "react";

export interface TextAreaFieldProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
    label: string;
    errorMessage?: string;
}

export function TextAreaField({ id, label, errorMessage, ...props }: TextAreaFieldProps): React.JSX.Element {
    const inputId = id ?? `field-${label.toLocaleLowerCase().replaceAll(" ", "-")}`;
    const errorId = `${inputId}-error`;

    return (
        <div className="field">
            <label className="field-label" htmlFor={inputId}>
                {label}
            </label>
            <textarea
                className="text-input"
                id={inputId}
                aria-invalid={Boolean(errorMessage)}
                aria-describedby={errorMessage ? errorId : undefined}
                {...props}
            />
            {errorMessage ? (
                <p className="field-error" id={errorId} role="alert">
                    {errorMessage}
                </p>
            ) : null}
        </div>
    );
}

/** Shared labeled input that connects its validation message to the control. */
import type { InputHTMLAttributes } from "react";

export interface InputFieldProps extends InputHTMLAttributes<HTMLInputElement> {
    label: string;
    errorMessage?: string;
}

export function InputField({ id, label, errorMessage, ...props }: InputFieldProps): React.JSX.Element {
    const inputId = id ?? `field-${label.toLocaleLowerCase().replaceAll(" ", "-")}`;
    const errorId = `${inputId}-error`;

    return (
        <div className="field">
            <label className="field-label" htmlFor={inputId}>
                {label}
            </label>
            <input
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

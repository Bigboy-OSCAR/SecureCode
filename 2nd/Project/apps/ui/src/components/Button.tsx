/** Shared button presentation with consistent sizing, focus, and disabled states. */
import type { ButtonHTMLAttributes } from "react";

type ButtonVariant = "primary" | "secondary" | "quiet";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: ButtonVariant;
}

export function Button({ className = "", variant = "secondary", ...props }: ButtonProps): React.JSX.Element {
    return <button className={`button button-${variant} ${className}`.trim()} {...props} />;
}

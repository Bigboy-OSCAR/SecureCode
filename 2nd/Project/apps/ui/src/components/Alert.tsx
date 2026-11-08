/** Shared accessible alert and status message presentation. */
import type { PropsWithChildren } from "react";

export interface AlertProps extends PropsWithChildren {
    title: string;
    variant: "info" | "success" | "warning" | "error";
}

export function Alert({ title, variant, children }: AlertProps): React.JSX.Element {
    const role = variant === "error" ? "alert" : "status";

    return (
        <div className={`alert alert-${variant}`} role={role}>
            <strong>{title}</strong>
            <div>{children}</div>
        </div>
    );
}

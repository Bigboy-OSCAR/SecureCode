/** Ask the desktop launcher to reissue a one-time login when a cookie expires. */
let requested = false;
interface DesktopWindow {
    dispatchEvent: (event: Event) => boolean;
    webkit?: { messageHandlers?: { reauthenticate?: { postMessage: (value: object) => void } } };
}
export function notifyAuthExpired(): void {
    const browser = globalThis as typeof globalThis & { window?: DesktopWindow };
    const desktop = browser.window;
    if (!desktop) return;
    desktop.dispatchEvent(new Event("localdesk:auth-expired"));
    const bridge = desktop.webkit?.messageHandlers?.reauthenticate;
    if (bridge && !requested) {
        requested = true;
        bridge.postMessage({});
    }
}

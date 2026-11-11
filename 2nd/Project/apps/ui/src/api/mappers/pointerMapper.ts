import type { PointerListItem, RuntimePointerUri, SessionId, SourcePointerUri } from "@securecode/contracts";

export type UiPointer =
    | (Omit<PointerListItem, "kind" | "pointer"> & { kind: "source"; pointer: SourcePointerUri })
    | (Omit<PointerListItem, "kind" | "pointer" | "session_id"> & {
          kind: "runtime";
          pointer: RuntimePointerUri;
          session_id: SessionId;
      });

export function mapPointerItem(item: PointerListItem): UiPointer {
    if (item.kind === "source") {
        return { ...item, kind: "source", pointer: item.pointer };
    }
    if (!item.session_id) {
        throw new Error("Runtime pointer response is missing its session scope.");
    }
    return { ...item, kind: "runtime", pointer: item.pointer, session_id: item.session_id };
}

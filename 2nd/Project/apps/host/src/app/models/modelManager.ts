/** Serializes model changes and keeps runs blocked until runtime and counter agree. */
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import type { ModelListResponse } from "@securecode/contracts";
import { RouteFailure } from "../../routes/shared/routeFailure.js";
import type { ModelProfile } from "./modelProfiles.js";

export interface ModelManagerOptions {
    profiles: ModelProfile[];
    selectionFile: string;
    activeModelId: string | null;
    hasActiveRuns(): boolean;
    activate(profile: ModelProfile): Promise<void>;
}

export class ModelManager {
    private status: ModelListResponse["status"] = "ready";
    private error: string | null = null;
    private activeModelId: string | null;

    constructor(private readonly options: ModelManagerOptions) {
        this.activeModelId = options.activeModelId;
    }

    ready(): boolean {
        return this.status === "ready" && this.activeModelId !== null;
    }
    busy(): boolean {
        return this.status === "loading";
    }

    savedSelection(): string | null {
        try {
            const saved = JSON.parse(readFileSync(this.options.selectionFile, "utf8")) as { model_id?: string };
            return this.options.profiles.some((profile) => profile.model_id === saved.model_id)
                ? saved.model_id!
                : null;
        } catch {
            return null;
        }
    }

    snapshot(): ModelListResponse {
        return {
            schema_version: "1",
            active_model_id: this.activeModelId,
            status: this.status,
            error: this.error,
            items: this.options.profiles.map((profile) => ({
                model_id: profile.model_id,
                display_name: profile.display_name,
                runtime: profile.runtime,
                context_limit_tokens: profile.context_limit_tokens,
                available: profile.available,
                ...(!profile.available ? { reason: "모델 파일 또는 실행 프로그램이 없습니다." } : {}),
            })),
        };
    }

    async select(modelId: string): Promise<ModelListResponse> {
        if (this.busy() || this.options.hasActiveRuns()) {
            throw new RouteFailure("RUN_ALREADY_ACTIVE", "실행 또는 모델 로드가 끝난 뒤 모델을 변경하세요.");
        }
        const profile = this.options.profiles.find((model) => model.model_id === modelId);
        if (!profile) throw new RouteFailure("NOT_FOUND", "등록되지 않은 모델입니다.");
        if (!profile.available) throw new RouteFailure("PROVIDER_ERROR", "모델 파일 또는 실행 프로그램이 없습니다.");
        if (this.ready() && this.activeModelId === modelId) return this.snapshot();
        this.status = "loading";
        this.error = null;
        try {
            await this.options.activate(profile);
            this.activeModelId = modelId;
            this.status = "ready";
            mkdirSync(dirname(this.options.selectionFile), { recursive: true });
            writeFileSync(this.options.selectionFile, JSON.stringify({ model_id: modelId }), { mode: 0o600 });
        } catch {
            this.activeModelId = null;
            this.status = "error";
            this.error = "모델을 불러오지 못했습니다. 로컬 모델 서버 상태를 확인하고 다시 시도하세요.";
            throw new RouteFailure("PROVIDER_ERROR", this.error);
        }
        return this.snapshot();
    }
}

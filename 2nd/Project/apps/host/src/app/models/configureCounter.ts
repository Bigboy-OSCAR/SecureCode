import type { HostConfig } from "../../config/hostConfig.js";
import type { ModelProfile } from "./modelProfiles.js";

export async function configureModelCounter(config: HostConfig, profile: ModelProfile): Promise<void> {
    const response = await fetch(`${config.contextServiceUrl}/internal/v1/models/configure`, {
        method: "POST",
        headers: { "content-type": "application/json", authorization: `Bearer ${config.internalToken}` },
        body: JSON.stringify({
            runtime: profile.runtime,
            model_id: profile.model_id,
            base_url: profile.baseUrl,
            api_key: profile.apiKey,
        }),
        signal: AbortSignal.timeout(30000),
    });
    if (!response.ok) throw new Error("model tokenizer configuration failed");
}

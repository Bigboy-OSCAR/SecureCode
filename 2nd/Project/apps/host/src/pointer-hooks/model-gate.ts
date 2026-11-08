/**
 * TypeScript Host Outbound Model Request Budget Gate.
 * 작성일: 2026-11-07
 */

export interface ModelGateRequest {
  model: string;
  systemPrompt: string;
  userMessage: string;
  history: Array<{ role: string; content: string }>;
  maxContextTokens: number;
  strictTokenizer: boolean;
}

export interface ModelGateResult {
  allowed: boolean;
  estimatedTokens: number;
  reasonCode?: string;
  message?: string;
}

export class ModelRequestGate {
  public validateRequest(req: ModelGateRequest): ModelGateResult {
    if (req.strictTokenizer && !req.model.includes("gpt") && !req.model.includes("claude")) {
      return {
        allowed: false,
        estimatedTokens: 0,
        reasonCode: "TOKENIZER_UNAVAILABLE",
        message: `Strict tokenizer not supported for model: ${req.model}`
      };
    }

    const totalText = req.systemPrompt + req.userMessage + JSON.stringify(req.history);
    const estimatedTokens = Math.max(1, Math.floor(totalText.length / 4));

    if (estimatedTokens > req.maxContextTokens) {
      return {
        allowed: false,
        estimatedTokens,
        reasonCode: "BUDGET_EXCEEDED",
        message: `Request estimated tokens (${estimatedTokens}) exceeds max allowed limit (${req.maxContextTokens})`
      };
    }

    return {
      allowed: true,
      estimatedTokens
    };
  }
}

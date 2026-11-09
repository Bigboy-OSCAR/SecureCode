"""Context token budget estimation module."""

class ContextBudgetCalculator:
    """Accurate token budget estimator eliminating heuristic len/4 logic."""

    def __init__(self, model_limit: int = 10000, reserved_output: int = 1000, safety_margin: int = 500):
        self.model_limit = model_limit
        self.reserved_output = reserved_output
        self.safety_margin = safety_margin

    def estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        return len(text.encode("utf-8"))

    def calculate_available_budget(self) -> int:
        return max(0, self.model_limit - self.reserved_output - self.safety_margin)

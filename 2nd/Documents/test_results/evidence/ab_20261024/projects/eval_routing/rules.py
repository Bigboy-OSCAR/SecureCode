from policy import CANARY_PERCENT, MAX_LATENCY_MS, DEFAULT_PATH

def normalize_path(path):
    cleaned = "/" + path.strip().lstrip("/")
    return cleaned.rstrip("/") or DEFAULT_PATH

def bucket(user_id):
    return sum(ord(char) for char in user_id) % 100

def use_canary(user_id):
    return bucket(user_id) < CANARY_PERCENT

def healthy(status):
    return status["up"] and status["latency_ms"] <= MAX_LATENCY_MS

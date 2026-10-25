DISPLAY_PREFIX = "warehouse"
DISPLAY_WIDTH = 12
UNKNOWN_LABEL = "unknown"
MAX_LABEL_LENGTH = 48

def normalize_label(label):
    return label.strip().lower().replace(" ", "-")[:MAX_LABEL_LENGTH]

def display_reference(reference):
    return DISPLAY_PREFIX + ":" + str(reference).zfill(DISPLAY_WIDTH)

def status_label(code):
    return {0: "pending", 1: "ready", 2: "closed"}.get(code, UNKNOWN_LABEL)

def summarize_count(values):
    return {"domain": DISPLAY_PREFIX, "count": len(values)}

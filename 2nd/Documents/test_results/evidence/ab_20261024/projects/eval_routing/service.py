from policy import PRIMARY_REGION, SECONDARY_REGION, UNAVAILABLE, CANARY_SUFFIX, RETRY_LIMIT
from rules import normalize_path, use_canary, healthy

def route_request(user_id, path, statuses):
    chosen = UNAVAILABLE
    for region in (PRIMARY_REGION, SECONDARY_REGION):
        if healthy(statuses[region]):
            chosen = region
            break
    if chosen == UNAVAILABLE:
        return UNAVAILABLE
    if use_canary(user_id):
        chosen += CANARY_SUFFIX
    return chosen + ":" + normalize_path(path)

def retry_destination(user_id, path, statuses, attempt):
    if attempt > RETRY_LIMIT:
        return "exhausted"
    return route_request(user_id, path, statuses)

def route_tag(region):
    return "route:" + region.upper()

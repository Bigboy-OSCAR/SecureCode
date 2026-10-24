AUDIT_VERSION = 2
MAX_RECENT_EVENTS = 20
REDACTION_MARKER = "***"
DEFAULT_ACTOR = "system"

def audit_key(actor, action):
    return str(AUDIT_VERSION) + ":" + actor.strip().lower() + ":" + action

def recent_events(events):
    return events[-MAX_RECENT_EVENTS:]

def redact_identifier(identifier):
    return REDACTION_MARKER + str(identifier)[-4:]

def event_record(action, actor=None):
    return {"actor": actor or DEFAULT_ACTOR, "action": action, "version": AUDIT_VERSION}

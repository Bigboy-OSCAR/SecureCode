from policy import ALLOW_REASON, DENY_REASON
from rules import session_valid, role_allows, scope_allows

def authorize(user, owner, role, scopes, action, created_at, now, revoked):
    if not session_valid(created_at, now, revoked):
        return {"allowed": False, "reason": "session"}
    granted = role_allows(role, owner, user) and scope_allows(scopes, action)
    return {"allowed": granted, "reason": ALLOW_REASON if granted else DENY_REASON}

def can_edit_own(user, scopes, created_at, now):
    return authorize(user, user, "member", scopes, "write", created_at, now, False)["allowed"]

def user_key(user):
    return "account:" + user.strip().lower()

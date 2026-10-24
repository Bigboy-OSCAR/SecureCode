from policy import ADMIN_ROLE, READ_ACTION, WRITE_ACTION, WRITE_SCOPE, READ_SCOPE, MAX_SESSION_AGE

def normalized_scopes(scopes):
    return sorted(set(scope.strip().lower() for scope in scopes))

def session_valid(created_at, now, revoked):
    return not revoked and 0 <= now - created_at < MAX_SESSION_AGE

def required_scope(action):
    return {READ_ACTION: READ_SCOPE, WRITE_ACTION: WRITE_SCOPE}.get(action, "")

def role_allows(role, owner, user):
    return role == ADMIN_ROLE or owner == user

def scope_allows(scopes, action):
    required = required_scope(action)
    return bool(required) and required in normalized_scopes(scopes)

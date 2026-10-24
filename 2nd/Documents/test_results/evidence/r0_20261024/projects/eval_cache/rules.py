from policy import ANONYMOUS_TENANT, DEFAULT_TTL, PRIVATE_TTL, MAX_TTL, EXCLUDED_QUERY_KEYS

def normalize_tenant(tenant):
    return tenant.strip().lower() or ANONYMOUS_TENANT

def normalize_resource(resource):
    return resource.strip().replace(" ", "_").lower()

def canonical_query(query):
    return "&".join(str(key) + "=" + str(query[key]) for key in sorted(query) if key not in EXCLUDED_QUERY_KEYS)

def cache_ttl(requested, private):
    ceiling = PRIVATE_TTL if private else MAX_TTL
    return min(max(DEFAULT_TTL if requested is None else requested, 0), ceiling)

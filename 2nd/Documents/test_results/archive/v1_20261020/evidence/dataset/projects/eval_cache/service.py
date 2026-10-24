from policy import CACHE_NAMESPACE, SCHEMA_VERSION, KEY_SEPARATOR
from rules import normalize_tenant, normalize_resource, canonical_query, cache_ttl

def render_cache_key(tenant, resource, query):
    return KEY_SEPARATOR.join((CACHE_NAMESPACE, normalize_tenant(tenant), normalize_resource(resource), canonical_query(query), "v" + str(SCHEMA_VERSION)))

def cache_entry(tenant, resource, query, requested_ttl, private, now):
    ttl = cache_ttl(requested_ttl, private)
    return {"key": render_cache_key(tenant, resource, query), "expires": now + ttl, "store": ttl > 0}

def cache_partition(tenant):
    return sum(ord(char) for char in normalize_tenant(tenant)) % 16

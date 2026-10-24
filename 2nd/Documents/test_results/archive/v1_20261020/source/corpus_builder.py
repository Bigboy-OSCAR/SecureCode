"""Generate a deterministic, executable, project-held-out retrieval pilot.

Only project source is retrievable. Tasks and their executable gold records live
outside projects/. The six evaluation programs implement different algorithms;
they are not identifier/constant substitutions of the development program.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any


def uri(module: str, name: str) -> str:
    return f"memory://symbol/{module.replace('.', '/')}.py::{name}"


def refs(*items: str) -> list[str]:
    return [uri(*item.split(":", 1)) for item in items]


def call(module: str, function: str, *args: Any) -> dict[str, Any]:
    return {"module": module, "function": function, "args": list(args)}


def task(
    slug: str,
    category: str,
    question: str,
    operation: dict[str, Any],
    check: Any,
    required: list[str],
) -> dict[str, Any]:
    return {
        "slug": slug,
        "category": category,
        "question": question,
        "operation": operation,
        "check": check,
        "required": required,
    }


def impact(
    module: str, constant: str, replacement: Any,
    probes: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "kind": "impact", "module": module, "constant": constant,
        "replacement": replacement, "probes": probes,
    }


def architecture(module: str, function: str) -> dict[str, Any]:
    return {"kind": "architecture", "module": module, "function": function}


def ancillary_sources(domain: str) -> dict[str, str]:
    """Eight adjacent, independently callable functions; no gold annotations."""
    return {
        "presentation.py": f'''
DISPLAY_PREFIX = "{domain}"
DISPLAY_WIDTH = 12
UNKNOWN_LABEL = "unknown"
MAX_LABEL_LENGTH = 48

def normalize_label(label):
    return label.strip().lower().replace(" ", "-")[:MAX_LABEL_LENGTH]

def display_reference(reference):
    return DISPLAY_PREFIX + ":" + str(reference).zfill(DISPLAY_WIDTH)

def status_label(code):
    return {{0: "pending", 1: "ready", 2: "closed"}}.get(code, UNKNOWN_LABEL)

def summarize_count(values):
    return {{"domain": DISPLAY_PREFIX, "count": len(values)}}
''',
        "audit.py": '''
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
''',
    }


def definitions() -> list[dict[str, Any]]:
    projects: list[dict[str, Any]] = []
    shipping = {
        "policy.py": '''
BASE_CENTS = 350
STEP_GRAMS = 500
STEP_CENTS = 90
FREE_FROM_CENTS = 8000
REMOTE_SURCHARGE = 240
MAX_GRAMS = 20000
MIN_GRAMS = 1
TRACKING_PREFIX = "parcel"
''',
        "rules.py": '''
from policy import STEP_GRAMS, STEP_CENTS, FREE_FROM_CENTS, MAX_GRAMS, MIN_GRAMS

def weight_steps(grams):
    return (max(grams, MIN_GRAMS) + STEP_GRAMS - 1) // STEP_GRAMS

def weight_charge(grams):
    return weight_steps(grams) * STEP_CENTS

def free_shipping(order_cents):
    return order_cents >= FREE_FROM_CENTS

def allowed_weight(grams):
    return MIN_GRAMS <= grams <= MAX_GRAMS
''',
        "service.py": '''
from policy import BASE_CENTS, REMOTE_SURCHARGE, TRACKING_PREFIX
from rules import weight_charge, free_shipping, allowed_weight

def shipping_quote(order_cents, grams, remote):
    if not allowed_weight(grams):
        return {"status": "rejected", "cents": 0}
    charge = 0 if free_shipping(order_cents) else BASE_CENTS + weight_charge(grams)
    if remote:
        charge += REMOTE_SURCHARGE
    return {"status": "accepted", "cents": charge}

def parcel_total(order_cents, grams, remote):
    quote = shipping_quote(order_cents, grams, remote)
    return order_cents + quote["cents"] if quote["status"] == "accepted" else -1

def tracking_key(order_id):
    return TRACKING_PREFIX + ":" + order_id.strip().upper()
''',
    }
    shiprefs = refs("service:shipping_quote", "rules:allowed_weight", "rules:free_shipping",
                    "rules:weight_charge", "rules:weight_steps", "policy:BASE_CENTS",
                    "policy:REMOTE_SURCHARGE", "policy:STEP_GRAMS", "policy:STEP_CENTS",
                    "policy:FREE_FROM_CENTS", "policy:MIN_GRAMS", "policy:MAX_GRAMS")
    projects.append({
        "name": "dev_shipping", "split": "dev", "domain": "parcel delivery",
        "sources": shipping,
        "tasks": [
            task("steps", "single_function", "What does weight_steps(501) return?",
                 call("rules", "weight_steps", 501), 2,
                 refs("rules:weight_steps", "policy:MIN_GRAMS", "policy:STEP_GRAMS")),
            task("quote", "cross_file", "What does shipping_quote(6200, 501, True) return?",
                 call("service", "shipping_quote", 6200, 501, True),
                 {"status": "accepted", "cents": 770}, shiprefs),
            task("total", "cross_file", "What does parcel_total(9000, 1600, True) return?",
                 call("service", "parcel_total", 9000, 1600, True), 9240,
                 refs("service:parcel_total") + shiprefs),
            task("max_weight", "boundary", "What does shipping_quote(9000, 20001, False) return?",
                 call("service", "shipping_quote", 9000, 20001, False),
                 {"status": "rejected", "cents": 0},
                 refs("service:shipping_quote", "rules:allowed_weight", "policy:MIN_GRAMS", "policy:MAX_GRAMS")),
            task("remote_free", "semantic", "An accepted parcel order is worth 8000 cents, weighs 500 grams, and goes to a remote address. Return the delivery quotation object, including status and cents.",
                 call("service", "shipping_quote", 8000, 500, True),
                 {"status": "accepted", "cents": 240}, shiprefs),
            task("invalid_total", "semantic", "A parcel order is worth 4000 cents but weighs zero grams and is not remote. What integer does the complete payable-order calculation return?",
                 call("service", "parcel_total", 4000, 0, False), -1,
                 refs("service:parcel_total", "service:shipping_quote", "rules:allowed_weight", "policy:MIN_GRAMS", "policy:MAX_GRAMS")),
            task("policy_change", "change_impact", "If policy.STEP_CENTS changes from 90 to 120, which of these exact calls changes its return value: weight_charge(501), parcel_total(6200,501,False), tracking_key(' a9 ')? Return a sorted list of changed function names.",
                 impact("policy", "STEP_CENTS", 120, [
                     call("rules", "weight_charge", 501),
                     call("service", "parcel_total", 6200, 501, False),
                     call("service", "tracking_key", " a9 ")]),
                 ["parcel_total", "weight_charge"],
                 shiprefs + refs("service:parcel_total", "service:tracking_key")),
            task("direct_calls", "architecture", "List the project-defined functions directly called by shipping_quote. Ignore builtins, and return a sorted list of function names.",
                 architecture("service", "shipping_quote"),
                 ["allowed_weight", "free_shipping", "weight_charge"],
                 refs("service:shipping_quote")),
        ],
    })

    pricing = {
        "policy.py": '''
MEMBER_BPS = 750
TAX_BPS = 825
DELIVERY_CENTS = 499
FREE_DELIVERY_CENTS = 6000
DISCOUNT_CAP_CENTS = 900
MIN_QUANTITY = 1
MAX_QUANTITY = 20
CURRENCY = "USD"
''',
        "rules.py": '''
from policy import MEMBER_BPS, TAX_BPS, DISCOUNT_CAP_CENTS, MIN_QUANTITY, MAX_QUANTITY

def line_subtotal(unit_cents, quantity):
    if unit_cents < 0 or not MIN_QUANTITY <= quantity <= MAX_QUANTITY:
        return -1
    return unit_cents * quantity

def member_discount(subtotal, member):
    return min(subtotal * MEMBER_BPS // 10000, DISCOUNT_CAP_CENTS) if member else 0

def sales_tax(net_cents):
    return (net_cents * TAX_BPS + 5000) // 10000

def refundable(net_cents, returned_units, total_units):
    return net_cents * min(returned_units, total_units) // total_units
''',
        "service.py": '''
from policy import DELIVERY_CENTS, FREE_DELIVERY_CENTS, CURRENCY
from rules import line_subtotal, member_discount, sales_tax

def checkout_total(unit_cents, quantity, member):
    subtotal = line_subtotal(unit_cents, quantity)
    if subtotal < 0:
        return -1
    net = subtotal - member_discount(subtotal, member)
    delivery = 0 if net >= FREE_DELIVERY_CENTS else DELIVERY_CENTS
    return net + sales_tax(net) + delivery

def order_receipt(unit_cents, quantity, member):
    total = checkout_total(unit_cents, quantity, member)
    return {"currency": CURRENCY, "total": total, "accepted": total >= 0}

def reward_points(total_cents):
    return max(total_cents, 0) // 100
''',
    }
    pricerefs = refs("service:checkout_total", "rules:line_subtotal", "rules:member_discount",
                    "rules:sales_tax", "policy:DELIVERY_CENTS", "policy:FREE_DELIVERY_CENTS",
                    "policy:MEMBER_BPS", "policy:TAX_BPS", "policy:DISCOUNT_CAP_CENTS",
                    "policy:MIN_QUANTITY", "policy:MAX_QUANTITY")
    projects.append({
        "name": "eval_pricing", "split": "eval", "domain": "retail checkout",
        "sources": pricing, "tasks": [
            task("refund", "single_function", "What does refundable(1001, 2, 3) return?",
                 call("rules", "refundable", 1001, 2, 3), 667, refs("rules:refundable")),
            task("member_order", "cross_file", "What does checkout_total(1999, 3, True) return?",
                 call("service", "checkout_total", 1999, 3, True), 6505, pricerefs),
            task("receipt", "cross_file", "What does order_receipt(4000, 3, True) return?",
                 call("service", "order_receipt", 4000, 3, True),
                 {"currency": "USD", "total": 12016, "accepted": True},
                 refs("service:order_receipt", "policy:CURRENCY") + pricerefs),
            task("quantity_cap", "boundary", "What does checkout_total(100, 21, False) return?",
                 call("service", "checkout_total", 100, 21, False), -1,
                 refs("service:checkout_total", "rules:line_subtotal", "policy:MIN_QUANTITY", "policy:MAX_QUANTITY")),
            task("discount_delivery", "semantic", "A member buys 3 units priced at 2000 cents each. Calculate the final checkout amount in cents, including the membership reduction, rounded sales tax, and delivery charge.",
                 call("service", "checkout_total", 2000, 3, True), 6507, pricerefs),
            task("invalid_receipt", "semantic", "A non-member orders zero units priced at 2500 cents each. Return the retail order receipt object containing currency, total, and accepted.",
                 call("service", "order_receipt", 2500, 0, False),
                 {"currency": "USD", "total": -1, "accepted": False},
                 refs("service:order_receipt", "policy:CURRENCY", "service:checkout_total", "rules:line_subtotal", "policy:MIN_QUANTITY", "policy:MAX_QUANTITY")),
            task("tax_change", "change_impact", "If policy.TAX_BPS changes from 825 to 1000, which exact calls change: sales_tax(1000), checkout_total(2000,3,True), reward_points(1000)? Return a sorted list of changed function names.",
                 impact("policy", "TAX_BPS", 1000, [
                     call("rules", "sales_tax", 1000),
                     call("service", "checkout_total", 2000, 3, True),
                     call("service", "reward_points", 1000)]),
                 ["checkout_total", "sales_tax"],
                 pricerefs + refs("service:reward_points")),
            task("direct_calls", "architecture", "List the project-defined functions directly called by checkout_total. Ignore builtins, and return a sorted list of function names.",
                 architecture("service", "checkout_total"),
                 ["line_subtotal", "member_discount", "sales_tax"],
                 refs("service:checkout_total")),
        ],
    })

    auth = {
        "policy.py": '''
ADMIN_ROLE = "admin"
READ_ACTION = "read"
WRITE_ACTION = "write"
WRITE_SCOPE = "document:write"
READ_SCOPE = "document:read"
MAX_SESSION_AGE = 3600
ALLOW_REASON = "allowed"
DENY_REASON = "denied"
''',
        "rules.py": '''
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
''',
        "service.py": '''
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
''',
    }
    authrefs = refs("service:authorize", "rules:session_valid", "rules:role_allows",
                    "rules:scope_allows", "rules:required_scope", "rules:normalized_scopes",
                    "policy:ADMIN_ROLE", "policy:READ_ACTION", "policy:WRITE_ACTION",
                    "policy:READ_SCOPE", "policy:WRITE_SCOPE", "policy:MAX_SESSION_AGE",
                    "policy:ALLOW_REASON", "policy:DENY_REASON")
    projects.append({
        "name": "eval_authorization", "split": "eval", "domain": "document authorization",
        "sources": auth, "tasks": [
            task("normalize", "single_function", "What does normalized_scopes([' Document:Read ', 'document:read', ' DOCUMENT:WRITE ']) return?",
                 call("rules", "normalized_scopes", [" Document:Read ", "document:read", " DOCUMENT:WRITE "]),
                 ["document:read", "document:write"], refs("rules:normalized_scopes")),
            task("own_write", "cross_file", "What does authorize('u1','u1','member',[' DOCUMENT:WRITE '],'write',100,200,False) return?",
                 call("service", "authorize", "u1", "u1", "member", [" DOCUMENT:WRITE "], "write", 100, 200, False),
                 {"allowed": True, "reason": "allowed"}, authrefs),
            task("admin_without_scope", "cross_file", "What does authorize('u1','u2','admin',['document:read'],'write',100,200,False) return?",
                 call("service", "authorize", "u1", "u2", "admin", ["document:read"], "write", 100, 200, False),
                 {"allowed": False, "reason": "denied"}, authrefs),
            task("expiry", "boundary", "What does can_edit_own('u1',['document:write'],100,3700) return?",
                 call("service", "can_edit_own", "u1", ["document:write"], 100, 3700), False,
                 refs("service:can_edit_own", "service:authorize", "rules:session_valid", "policy:MAX_SESSION_AGE")),
            task("unknown_action", "semantic", "An administrator u1 requests deletion of a document owned by u2. Their permissions contain document:read and document:write, their session began at time 100, current time is 200, and it is not revoked. Return the authorization decision object with allowed and reason.",
                 call("service", "authorize", "u1", "u2", "admin", ["document:read", "document:write"], "delete", 100, 200, False),
                 {"allowed": False, "reason": "denied"}, authrefs),
            task("future_session", "semantic", "A member u1 wants to edit their own document with permission document:write. The session creation timestamp is 500 while the current timestamp is 499. What boolean does the own-document editing check return?",
                 call("service", "can_edit_own", "u1", ["document:write"], 500, 499), False,
                 refs("service:can_edit_own", "service:authorize", "rules:session_valid", "policy:MAX_SESSION_AGE")),
            task("session_change", "change_impact", "If policy.MAX_SESSION_AGE changes from 3600 to 1800, which exact calls change: session_valid(100,2500,False), can_edit_own('u1',['document:write'],100,2500), user_key(' U1 ')? Return a sorted list of changed function names.",
                 impact("policy", "MAX_SESSION_AGE", 1800, [
                     call("rules", "session_valid", 100, 2500, False),
                     call("service", "can_edit_own", "u1", ["document:write"], 100, 2500),
                     call("service", "user_key", " U1 ")]),
                 ["can_edit_own", "session_valid"],
                 authrefs + refs("service:can_edit_own", "service:user_key")),
            task("direct_calls", "architecture", "List the project-defined functions directly called by authorize. Ignore builtins, and return a sorted list of function names.",
                 architecture("service", "authorize"),
                 ["role_allows", "scope_allows", "session_valid"], refs("service:authorize")),
        ],
    })

    routing = {
        "policy.py": '''
PRIMARY_REGION = "east"
SECONDARY_REGION = "west"
CANARY_PERCENT = 20
MAX_LATENCY_MS = 150
DEFAULT_PATH = "/"
RETRY_LIMIT = 2
UNAVAILABLE = "unavailable"
CANARY_SUFFIX = "-canary"
''',
        "rules.py": '''
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
''',
        "service.py": '''
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
''',
    }
    both = {"east": {"up": True, "latency_ms": 120}, "west": {"up": True, "latency_ms": 90}}
    fallback = {"east": {"up": True, "latency_ms": 151}, "west": {"up": True, "latency_ms": 100}}
    neither = {"east": {"up": False, "latency_ms": 10}, "west": {"up": True, "latency_ms": 200}}
    routerefs = refs("service:route_request", "rules:healthy", "rules:use_canary", "rules:bucket",
                     "rules:normalize_path", "policy:PRIMARY_REGION", "policy:SECONDARY_REGION",
                     "policy:UNAVAILABLE", "policy:CANARY_SUFFIX", "policy:MAX_LATENCY_MS",
                     "policy:CANARY_PERCENT", "policy:DEFAULT_PATH")
    projects.append({
        "name": "eval_routing", "split": "eval", "domain": "service request routing",
        "sources": routing, "tasks": [
            task("path", "single_function", "What does normalize_path('  ///orders///  ') return?",
                 call("rules", "normalize_path", "  ///orders///  "), "/orders",
                 refs("rules:normalize_path", "policy:DEFAULT_PATH")),
            task("preferred", "cross_file", f"What does route_request('ab',' /orders/ ',{both!r}) return?",
                 call("service", "route_request", "ab", " /orders/ ", both), "east:/orders", routerefs),
            task("fallback", "cross_file", f"What does route_request('d',' /health/ ',{fallback!r}) return?",
                 call("service", "route_request", "d", " /health/ ", fallback), "west-canary:/health", routerefs),
            task("latency_edge", "boundary", "What does healthy({'up':True,'latency_ms':150}) return?",
                 call("rules", "healthy", {"up": True, "latency_ms": 150}), True,
                 refs("rules:healthy", "policy:MAX_LATENCY_MS")),
            task("no_backend", "semantic", "For user d requesting /orders, the east backend is down with latency 10 ms and the west backend is up with latency 200 ms. What string does the normal request-routing workflow return?",
                 call("service", "route_request", "d", "/orders", neither), "unavailable", routerefs),
            task("retry_exhausted", "semantic", "A request from user d for /health has both backends healthy (east 120 ms, west 90 ms), but its retry attempt is 3. What string does the retry-aware destination lookup return?",
                 call("service", "retry_destination", "d", "/health", both, 3), "exhausted",
                 refs("service:retry_destination", "policy:RETRY_LIMIT")),
            task("canary_change", "change_impact", f"If policy.CANARY_PERCENT changes from 20 to 0, which exact calls change: use_canary('d'), route_request('d','/x',{both!r}), route_tag('east')? Return a sorted list of changed function names.",
                 impact("policy", "CANARY_PERCENT", 0, [
                     call("rules", "use_canary", "d"),
                     call("service", "route_request", "d", "/x", both),
                     call("service", "route_tag", "east")]),
                 ["route_request", "use_canary"], routerefs + refs("service:route_tag")),
            task("direct_calls", "architecture", "List the project-defined functions directly called by route_request. Ignore builtins, and return a sorted list of function names.",
                 architecture("service", "route_request"),
                 ["healthy", "normalize_path", "use_canary"], refs("service:route_request")),
        ],
    })

    inventory = {
        "policy.py": '''
SAFETY_STOCK = 3
MAX_PER_ORDER = 12
MIN_ORDER = 1
BACKORDER_LIMIT = 5
RESERVATION_TTL = 900
ACCEPTED = "reserved"
PARTIAL = "partial"
DENIED = "denied"
''',
        "rules.py": '''
from policy import SAFETY_STOCK, MAX_PER_ORDER, MIN_ORDER, BACKORDER_LIMIT

def sellable(on_hand, held):
    return max(on_hand - held - SAFETY_STOCK, 0)

def valid_quantity(quantity):
    return MIN_ORDER <= quantity <= MAX_PER_ORDER

def allocate(available, requested, allow_partial):
    if available >= requested:
        return requested
    return available if allow_partial else 0

def can_backorder(shortfall):
    return 0 < shortfall <= BACKORDER_LIMIT
''',
        "service.py": '''
from policy import RESERVATION_TTL, ACCEPTED, PARTIAL, DENIED
from rules import sellable, valid_quantity, allocate

def reserve(on_hand, held, requested, allow_partial, now):
    if not valid_quantity(requested):
        return {"status": DENIED, "units": 0, "expires": now}
    units = allocate(sellable(on_hand, held), requested, allow_partial)
    status = ACCEPTED if units == requested else PARTIAL if units else DENIED
    return {"status": status, "units": units, "expires": now + RESERVATION_TTL if units else now}

def remaining_after(on_hand, held, requested, allow_partial):
    reservation = reserve(on_hand, held, requested, allow_partial, 0)
    return sellable(on_hand, held + reservation["units"])

def stock_label(on_hand):
    return "empty" if on_hand <= 0 else "stocked"
''',
    }
    invrefs = refs("service:reserve", "rules:sellable", "rules:valid_quantity", "rules:allocate",
                   "policy:SAFETY_STOCK", "policy:MAX_PER_ORDER", "policy:MIN_ORDER",
                   "policy:RESERVATION_TTL", "policy:ACCEPTED", "policy:PARTIAL", "policy:DENIED")
    projects.append({
        "name": "eval_inventory", "split": "eval", "domain": "warehouse reservation",
        "sources": inventory, "tasks": [
            task("allocation", "single_function", "What does allocate(4, 7, False) return?",
                 call("rules", "allocate", 4, 7, False), 0, refs("rules:allocate")),
            task("partial", "cross_file", "What does reserve(12,4,7,True,100) return?",
                 call("service", "reserve", 12, 4, 7, True, 100),
                 {"status": "partial", "units": 5, "expires": 1000}, invrefs),
            task("remaining", "cross_file", "What does remaining_after(20,2,6,False) return?",
                 call("service", "remaining_after", 20, 2, 6, False), 9,
                 refs("service:remaining_after") + invrefs),
            task("order_limit", "boundary", "What does reserve(100,0,13,True,50) return?",
                 call("service", "reserve", 100, 0, 13, True, 50),
                 {"status": "denied", "units": 0, "expires": 50},
                 refs("service:reserve", "rules:valid_quantity", "policy:MIN_ORDER", "policy:MAX_PER_ORDER", "policy:DENIED")),
            task("safety_buffer", "semantic", "A warehouse has 8 physical units and 5 already held units. A customer requests 1 unit, permits partial fulfillment, and the current time is 200. Return the reservation object containing status, units, and expires.",
                 call("service", "reserve", 8, 5, 1, True, 200),
                 {"status": "denied", "units": 0, "expires": 200}, invrefs),
            task("all_or_nothing", "semantic", "A warehouse has 14 physical units and 3 already held units. A customer requests 9 units and refuses partial fulfillment. How many sellable units remain after attempting this reservation?",
                 call("service", "remaining_after", 14, 3, 9, False), 8,
                 refs("service:remaining_after") + invrefs),
            task("buffer_change", "change_impact", "If policy.SAFETY_STOCK changes from 3 to 5, which exact calls change: sellable(12,4), reserve(12,4,7,True,100), stock_label(12)? Return a sorted list of changed function names.",
                 impact("policy", "SAFETY_STOCK", 5, [
                     call("rules", "sellable", 12, 4),
                     call("service", "reserve", 12, 4, 7, True, 100),
                     call("service", "stock_label", 12)]),
                 ["reserve", "sellable"], invrefs + refs("service:stock_label")),
            task("direct_calls", "architecture", "List the project-defined functions directly called by reserve. Ignore builtins, and return a sorted list of function names.",
                 architecture("service", "reserve"),
                 ["allocate", "sellable", "valid_quantity"], refs("service:reserve")),
        ],
    })

    cache = {
        "policy.py": '''
CACHE_NAMESPACE = "render"
SCHEMA_VERSION = 4
DEFAULT_TTL = 300
PRIVATE_TTL = 30
MAX_TTL = 3600
ANONYMOUS_TENANT = "public"
KEY_SEPARATOR = "|"
EXCLUDED_QUERY_KEYS = ("trace", "debug")
''',
        "rules.py": '''
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
''',
        "service.py": '''
from policy import CACHE_NAMESPACE, SCHEMA_VERSION, KEY_SEPARATOR
from rules import normalize_tenant, normalize_resource, canonical_query, cache_ttl

def render_cache_key(tenant, resource, query):
    return KEY_SEPARATOR.join((CACHE_NAMESPACE, normalize_tenant(tenant), normalize_resource(resource), canonical_query(query), "v" + str(SCHEMA_VERSION)))

def cache_entry(tenant, resource, query, requested_ttl, private, now):
    ttl = cache_ttl(requested_ttl, private)
    return {"key": render_cache_key(tenant, resource, query), "expires": now + ttl, "store": ttl > 0}

def cache_partition(tenant):
    return sum(ord(char) for char in normalize_tenant(tenant)) % 16
''',
    }
    keyrefs = refs("service:render_cache_key", "rules:normalize_tenant", "rules:normalize_resource",
                   "rules:canonical_query", "policy:CACHE_NAMESPACE", "policy:SCHEMA_VERSION",
                   "policy:KEY_SEPARATOR", "policy:ANONYMOUS_TENANT", "policy:EXCLUDED_QUERY_KEYS")
    entryrefs = refs("service:cache_entry", "rules:cache_ttl", "policy:DEFAULT_TTL",
                     "policy:PRIVATE_TTL", "policy:MAX_TTL") + keyrefs
    projects.append({
        "name": "eval_cache", "split": "eval", "domain": "render cache",
        "sources": cache, "tasks": [
            task("resource", "single_function", "What does normalize_resource('  North/East Plan  ') return?",
                 call("rules", "normalize_resource", "  North/East Plan  "), "north/east_plan",
                 refs("rules:normalize_resource")),
            task("canonical_key", "cross_file", "What does render_cache_key(' TEAM-A ',' Summary View ',{'z':2,'a':1,'trace':'on'}) return?",
                 call("service", "render_cache_key", " TEAM-A ", " Summary View ", {"z": 2, "a": 1, "trace": "on"}),
                 "render|team-a|summary_view|a=1&z=2|v4", keyrefs),
            task("private_entry", "cross_file", "What does cache_entry(' ',' Revenue ',{'debug':1},None,True,100) return?",
                 call("service", "cache_entry", " ", " Revenue ", {"debug": 1}, None, True, 100),
                 {"key": "render|public|revenue||v4", "expires": 130, "store": True}, entryrefs),
            task("negative_ttl", "boundary", "What does cache_ttl(-1, False) return?",
                 call("rules", "cache_ttl", -1, False), 0,
                 refs("rules:cache_ttl", "policy:DEFAULT_TTL", "policy:PRIVATE_TTL", "policy:MAX_TTL")),
            task("public_lifetime", "semantic", "Prepare a public render-cache record for tenant ACME, resource Monthly Sales, query keys b=2 and a=1, requested lifetime 5000 seconds, and current time 10. Return the object with key, expires, and store.",
                 call("service", "cache_entry", "ACME", "Monthly Sales", {"b": 2, "a": 1}, 5000, False, 10),
                 {"key": "render|acme|monthly_sales|a=1&b=2|v4", "expires": 3610, "store": True}, entryrefs),
            task("do_not_store", "semantic", "Prepare a private render-cache record for tenant ACME, resource Daily, no query parameters, requested lifetime zero, and current time 50. Return the object with key, expires, and store.",
                 call("service", "cache_entry", "ACME", "Daily", {}, 0, True, 50),
                 {"key": "render|acme|daily||v4", "expires": 50, "store": False}, entryrefs),
            task("schema_change", "change_impact", "If policy.SCHEMA_VERSION changes from 4 to 5, which exact calls change: render_cache_key('ACME','Daily',{}), cache_entry('ACME','Daily',{},60,False,10), cache_partition('ACME')? Return a sorted list of changed function names.",
                 impact("policy", "SCHEMA_VERSION", 5, [
                     call("service", "render_cache_key", "ACME", "Daily", {}),
                     call("service", "cache_entry", "ACME", "Daily", {}, 60, False, 10),
                     call("service", "cache_partition", "ACME")]),
                 ["cache_entry", "render_cache_key"], entryrefs + refs("service:cache_partition")),
            task("direct_calls", "architecture", "List the project-defined functions directly called by render_cache_key. Ignore builtins and string methods, and return a sorted list of function names.",
                 architecture("service", "render_cache_key"),
                 ["canonical_query", "normalize_resource", "normalize_tenant"], refs("service:render_cache_key")),
        ],
    })

    schedules = {
        "policy.py": '''
OPEN_MINUTE = 540
CLOSE_MINUTE = 1020
SLOT_MINUTES = 30
BUFFER_MINUTES = 10
WORK_DAYS = (0, 1, 2, 3, 4)
MAX_DURATION = 180
MIN_DURATION = 1
UNAVAILABLE = -1
''',
        "rules.py": '''
from policy import SLOT_MINUTES, BUFFER_MINUTES, WORK_DAYS, MIN_DURATION, MAX_DURATION

def round_slot(minute):
    return ((minute + SLOT_MINUTES - 1) // SLOT_MINUTES) * SLOT_MINUTES

def working_day(day):
    return day % 7 in WORK_DAYS

def valid_duration(duration):
    return MIN_DURATION <= duration <= MAX_DURATION

def overlaps(start, end, busy):
    return any(start < busy_end + BUFFER_MINUTES and end > busy_start - BUFFER_MINUTES for busy_start, busy_end in busy)
''',
        "service.py": '''
from policy import OPEN_MINUTE, CLOSE_MINUTE, SLOT_MINUTES, UNAVAILABLE
from rules import round_slot, working_day, valid_duration, overlaps

def first_available(day, earliest, duration, busy):
    if not working_day(day) or not valid_duration(duration):
        return UNAVAILABLE
    start = round_slot(max(earliest, OPEN_MINUTE))
    while start + duration <= CLOSE_MINUTE:
        if not overlaps(start, start + duration, busy):
            return start
        start += SLOT_MINUTES
    return UNAVAILABLE

def appointment(day, earliest, duration, busy):
    start = first_available(day, earliest, duration, busy)
    return {"day": day, "start": start, "end": start + duration if start >= 0 else UNAVAILABLE}

def weekday_label(day):
    return ("mon", "tue", "wed", "thu", "fri", "sat", "sun")[day % 7]
''',
    }
    schedrefs = refs("service:first_available", "rules:round_slot", "rules:working_day",
                     "rules:valid_duration", "rules:overlaps", "policy:OPEN_MINUTE",
                     "policy:CLOSE_MINUTE", "policy:SLOT_MINUTES", "policy:UNAVAILABLE",
                     "policy:BUFFER_MINUTES", "policy:WORK_DAYS", "policy:MIN_DURATION",
                     "policy:MAX_DURATION")
    projects.append({
        "name": "eval_schedules", "split": "eval", "domain": "appointment scheduling",
        "sources": schedules, "tasks": [
            task("rounding", "single_function", "What does round_slot(541) return?",
                 call("rules", "round_slot", 541), 570,
                 refs("rules:round_slot", "policy:SLOT_MINUTES")),
            task("busy_buffer", "cross_file", "What does first_available(0,540,30,[[570,600]]) return?",
                 call("service", "first_available", 0, 540, 30, [[570, 600]]), 630, schedrefs),
            task("appointment", "cross_file", "What does appointment(2,556,60,[[600,660]]) return?",
                 call("service", "appointment", 2, 556, 60, [[600, 660]]),
                 {"day": 2, "start": 690, "end": 750},
                 refs("service:appointment") + schedrefs),
            task("closing_edge", "boundary", "What does first_available(4,990,30,[]) return?",
                 call("service", "first_available", 4, 990, 30, []), 990, schedrefs),
            task("weekend", "semantic", "Find the booking object for day index 5, earliest minute 600, duration 30 minutes, and an empty calendar. Return day, start, and end; weekday indices begin with Monday at zero.",
                 call("service", "appointment", 5, 600, 30, []),
                 {"day": 5, "start": -1, "end": -1},
                 refs("service:appointment", "service:first_available", "rules:working_day", "policy:WORK_DAYS", "policy:UNAVAILABLE")),
            task("too_late", "semantic", "Find the first appointment start on day index 1 at or after minute 1000, lasting 30 minutes, with no existing bookings. Return the integer start value used by the scheduling workflow.",
                 call("service", "first_available", 1, 1000, 30, []), -1, schedrefs),
            task("buffer_change", "change_impact", "If policy.BUFFER_MINUTES changes from 10 to 0, which exact calls change: overlaps(540,570,[[570,600]]), first_available(0,540,30,[[570,600]]), weekday_label(0)? Return a sorted list of changed function names.",
                 impact("policy", "BUFFER_MINUTES", 0, [
                     call("rules", "overlaps", 540, 570, [[570, 600]]),
                     call("service", "first_available", 0, 540, 30, [[570, 600]]),
                     call("service", "weekday_label", 0)]),
                 ["first_available", "overlaps"], schedrefs + refs("service:weekday_label")),
            task("direct_calls", "architecture", "List the project-defined functions directly called by first_available. Ignore builtins, and return a sorted list of function names.",
                 architecture("service", "first_available"),
                 ["overlaps", "round_slot", "valid_duration", "working_day"],
                 refs("service:first_available")),
        ],
    })
    return projects


_EXECUTOR = r"""
import importlib, json, sys
sys.dont_write_bytecode = True
request = json.load(sys.stdin)
sys.path.insert(0, request["root"])
for override in request.get("overrides", []):
    module = importlib.import_module(override["module"])
    setattr(module, override["name"], override["value"])
answers = []
for operation in request["calls"]:
    module = importlib.import_module(operation["module"])
    answers.append(getattr(module, operation["function"])(*operation["args"]))
json.dump(answers, sys.stdout, sort_keys=True)
"""


def execute(
    root: Path, operations: list[dict[str, Any]],
    overrides: list[dict[str, Any]] | None = None,
) -> list[Any]:
    """A fresh interpreter prevents cross-project imports or cached policy."""
    request = {"root": str(root.resolve()), "calls": operations, "overrides": overrides or []}
    result = subprocess.run(
        [sys.executable, "-I", "-c", _EXECUTOR],
        input=json.dumps(request), text=True, capture_output=True, timeout=20,
        check=True,
    )
    return json.loads(result.stdout)


def source_symbols(root: Path) -> dict[str, ast.AST]:
    symbols: dict[str, ast.AST] = {}
    for path in sorted(root.glob("*.py")):
        module = path.stem
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                symbols[uri(module, node.name)] = node
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        symbols[uri(module, target.id)] = node
    return symbols


def direct_project_calls(root: Path, module: str, function: str) -> list[str]:
    tree = ast.parse((root / f"{module}.py").read_text(encoding="utf-8"))
    local = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    imported: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            target = root / (node.module.replace(".", "/") + ".py")
            if target.exists():
                functions = {
                    item.name for item in ast.parse(target.read_text(encoding="utf-8")).body
                    if isinstance(item, ast.FunctionDef)
                }
                imported.update(alias.asname or alias.name for alias in node.names if alias.name in functions)
    function_node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == function)
    return sorted({
        node.func.id for node in ast.walk(function_node)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id in local | imported
    })


def json_equal(actual: Any, expected: Any) -> bool:
    """Keep bool distinct from int while allowing stable object key order."""
    return json.dumps(actual, sort_keys=True, separators=(",", ":")) == json.dumps(expected, sort_keys=True, separators=(",", ":"))


def build(output_dir: Path | str) -> dict[str, Any]:
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    all_tasks: dict[str, list[dict[str, Any]]] = {"dev": [], "eval": []}
    project_records: list[dict[str, Any]] = []
    gold_records: list[dict[str, Any]] = []
    for project in definitions():
        root = output_dir / "projects" / project["name"]
        root.mkdir(parents=True, exist_ok=True)
        sources = {**project["sources"], **ancillary_sources(project["domain"].split()[0])}
        for filename, source in sources.items():
            normalized = textwrap.dedent(source).strip() + "\n"
            ast.parse(normalized, filename=filename)
            (root / filename).write_text(normalized, encoding="utf-8")
        symbols = source_symbols(root)
        project_digest = hashlib.sha256()
        for filename in sorted(sources):
            project_digest.update(filename.encode())
            project_digest.update((root / filename).read_bytes())
        for spec in project["tasks"]:
            operation = spec["operation"]
            kind = operation.get("kind", "execution")
            verification_record: dict[str, Any] = {"kind": kind}
            if kind == "execution":
                answer = execute(root, [operation])[0]
                primary = uri(operation["module"], operation["function"])
                verification = "Executed the named function in a fresh isolated Python subprocess; independently checked against a hand-calculated expected result."
                verification_record["call"] = operation
            elif kind == "impact":
                before = execute(root, operation["probes"])
                override = {"module": operation["module"], "name": operation["constant"], "value": operation["replacement"]}
                after = execute(root, operation["probes"], [override])
                answer = sorted(probe["function"] for probe, old, new in zip(operation["probes"], before, after) if not json_equal(old, new))
                primary_probe = next(probe for probe in operation["probes"] if probe["module"] == "service")
                primary = uri(primary_probe["module"], primary_probe["function"])
                verification = "Compared the specified calls before and after a policy-constant intervention in separate fresh subprocesses. This is fixed-input impact, not all possible inputs."
                verification_record.update({"probes": operation["probes"], "override": override, "before": before, "after": after})
            elif kind == "architecture":
                answer = direct_project_calls(root, operation["module"], operation["function"])
                primary = uri(operation["module"], operation["function"])
                verification = "Parsed function AST and resolved local/from-import project functions; compared direct call names with a separately declared expected list."
                verification_record.update({"module": operation["module"], "function": operation["function"]})
            else:
                raise ValueError(kind)
            if not json_equal(answer, spec["check"]):
                raise AssertionError(f"Independent gold check failed: {project['name']}/{spec['slug']}: actual={answer!r}; check={spec['check']!r}")
            required = list(dict.fromkeys(spec["required"]))
            missing = set(required + [primary]) - set(symbols)
            if missing:
                raise AssertionError(f"Unresolvable gold symbols: {missing}")
            record = {
                "id": project["name"] + "__" + spec["slug"],
                "project": project["name"],
                "category": spec["category"],
                "question": spec["question"],
                "target_uri": primary,
                "expected": answer,
                "required_uris": required,
                "verification": verification,
            }
            all_tasks[project["split"]].append(record)
            gold_records.append({"id": record["id"], **verification_record, "expected": answer, "independent_check_passed": True})
        project_records.append({
            "name": project["name"], "split": project["split"], "domain": project["domain"],
            "relative_root": "projects/" + project["name"], "files": len(sources),
            "functions": sum(isinstance(node, ast.FunctionDef) for node in symbols.values()),
            "constants": sum(isinstance(node, ast.Assign) for node in symbols.values()),
            "chunks": len(symbols), "source_chars": sum(len((root / filename).read_text()) for filename in sources),
            "source_sha256": project_digest.hexdigest(), "tasks": len(project["tasks"]),
        })
    manifest = {
        "schema_version": 1,
        "corpus_type": "bounded synthetic Python retrieval pilot",
        "project_split": "one development shipping project; six structurally different evaluation domains",
        "project_count": len(project_records), "eval_project_count": 6,
        "dev_tasks": len(all_tasks["dev"]), "eval_tasks": len(all_tasks["eval"]),
        "categories_per_project": {"single_function": 1, "cross_file": 2, "boundary": 1, "semantic": 2, "change_impact": 1, "architecture": 1},
        "gold_separation": "Only projects/<name>/*.py are retrieval/summary inputs. Task/gold/manifest files must never be indexed or summarized.",
        "scope_limitations": [
            "Synthetic, small projects; not representative production repositories.",
            "Tasks within each project are correlated. Six evaluation projects are the independent clusters.",
            "required_uris list conservative source dependencies, not proof that every listed symbol is necessary for every branch.",
            "Change impact is defined for the listed inputs, not every possible execution.",
            "No code modification, mutation-refresh benchmark, or dynamic dispatch coverage.",
        ],
        "projects": project_records,
    }
    for split, tasks in all_tasks.items():
        (output_dir / f"{split}_tasks.json").write_text(json.dumps(tasks, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output_dir / "gold_validation.json").write_text(json.dumps(gold_records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.out), indent=2, ensure_ascii=False))

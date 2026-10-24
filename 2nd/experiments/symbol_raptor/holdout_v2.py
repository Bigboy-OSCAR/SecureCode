"""Freeze 48 new input questions on the six *already seen* pilot projects.

This is an additional-question evaluation, not independent-project validation.
It reads existing sources and old gold only, never model responses, summaries,
or retrieval results. No existing dataset or source is modified.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

from corpus_builder import call, execute, impact, json_equal, refs, source_symbols, task, uri


HERE = Path(__file__).resolve().parent
DEFAULT_SOURCE = HERE.parents[1] / "Documents/test_results/evidence/dataset"


def architecture(module: str, function: str) -> dict[str, Any]:
    return {"kind": "architecture", "mode": "transitive", "module": module, "function": function}


def definitions() -> dict[str, list[dict[str, Any]]]:
    pricing = refs(
        "service:checkout_total", "rules:line_subtotal", "rules:member_discount", "rules:sales_tax",
        "policy:DELIVERY_CENTS", "policy:FREE_DELIVERY_CENTS", "policy:MEMBER_BPS", "policy:TAX_BPS",
        "policy:DISCOUNT_CAP_CENTS", "policy:MIN_QUANTITY", "policy:MAX_QUANTITY",
    )
    receipt = pricing + refs("service:order_receipt", "policy:CURRENCY")
    authorization = refs(
        "service:authorize", "rules:session_valid", "rules:role_allows", "rules:scope_allows",
        "rules:required_scope", "rules:normalized_scopes", "policy:ADMIN_ROLE", "policy:READ_ACTION",
        "policy:WRITE_ACTION", "policy:READ_SCOPE", "policy:WRITE_SCOPE", "policy:MAX_SESSION_AGE",
        "policy:ALLOW_REASON", "policy:DENY_REASON",
    )
    routing = refs(
        "service:route_request", "rules:healthy", "rules:use_canary", "rules:bucket",
        "rules:normalize_path", "policy:PRIMARY_REGION", "policy:SECONDARY_REGION",
        "policy:UNAVAILABLE", "policy:CANARY_SUFFIX", "policy:MAX_LATENCY_MS",
        "policy:CANARY_PERCENT", "policy:DEFAULT_PATH",
    )
    reservation = refs(
        "service:reserve", "rules:sellable", "rules:valid_quantity", "rules:allocate",
        "policy:SAFETY_STOCK", "policy:MAX_PER_ORDER", "policy:MIN_ORDER", "policy:RESERVATION_TTL",
        "policy:ACCEPTED", "policy:PARTIAL", "policy:DENIED",
    )
    key = refs(
        "service:render_cache_key", "rules:normalize_tenant", "rules:normalize_resource",
        "rules:canonical_query", "policy:CACHE_NAMESPACE", "policy:SCHEMA_VERSION",
        "policy:KEY_SEPARATOR", "policy:ANONYMOUS_TENANT", "policy:EXCLUDED_QUERY_KEYS",
    )
    entry = key + refs(
        "service:cache_entry", "rules:cache_ttl", "policy:DEFAULT_TTL", "policy:PRIVATE_TTL", "policy:MAX_TTL",
    )
    schedule = refs(
        "service:first_available", "rules:round_slot", "rules:working_day", "rules:valid_duration",
        "rules:overlaps", "policy:OPEN_MINUTE", "policy:CLOSE_MINUTE", "policy:SLOT_MINUTES",
        "policy:UNAVAILABLE", "policy:BUFFER_MINUTES", "policy:WORK_DAYS",
        "policy:MIN_DURATION", "policy:MAX_DURATION",
    )
    edge_backends = {"east": {"up": True, "latency_ms": 150}, "west": {"up": True, "latency_ms": 151}}
    west_only = {"east": {"up": False, "latency_ms": 0}, "west": {"up": True, "latency_ms": 150}}
    priority_backends = {"east": {"up": True, "latency_ms": 149}, "west": {"up": True, "latency_ms": 1}}
    down_backends = {"east": {"up": False, "latency_ms": 0}, "west": {"up": False, "latency_ms": 0}}
    changed_backends = {"east": {"up": True, "latency_ms": 155}, "west": {"up": True, "latency_ms": 80}}
    return {
        "eval_pricing": [
            task(
                "refund_capped_units", "single_function",
                "What does refundable(101, 4, 3) return?",
                call("rules", "refundable", 101, 4, 3), 101, refs("rules:refundable"),
            ),
            task(
                "two_nonmember_items", "cross_file",
                "What does checkout_total(3001, 2, False) return?",
                call("service", "checkout_total", 3001, 2, False), 6497, pricing,
            ),
            task(
                "five_member_receipt", "cross_file",
                "What does order_receipt(1499, 5, True) return?",
                call("service", "order_receipt", 1499, 5, True),
                {"currency": "USD", "total": 7505, "accepted": True}, receipt,
            ),
            task(
                "free_delivery_exact_edge", "boundary",
                "What does checkout_total(3000, 2, False) return?",
                call("service", "checkout_total", 3000, 2, False), 6495, pricing,
            ),
            task(
                "large_member_order", "semantic",
                "A member buys 2 units priced at 25000 cents each. Calculate the final checkout amount in cents, including the membership reduction, rounded sales tax, and delivery.",
                call("service", "checkout_total", 25000, 2, True), 53151, pricing,
            ),
            task(
                "negative_unit_price", "semantic",
                "A member orders 2 units whose unit price is minus 1 cent. Return the retail receipt object containing currency, total, and accepted.",
                call("service", "order_receipt", -1, 2, True),
                {"currency": "USD", "total": -1, "accepted": False}, receipt,
            ),
            task(
                "delivery_threshold_intervention", "change_impact",
                "If policy.FREE_DELIVERY_CENTS changes from 6000 to 7000 before the program is loaded, which exact calls change their return values: checkout_total(6100,1,False), order_receipt(6100,1,False), member_discount(6100,True)? Return a sorted list of changed function names.",
                impact("policy", "FREE_DELIVERY_CENTS", 7000, [
                    call("service", "checkout_total", 6100, 1, False),
                    call("service", "order_receipt", 6100, 1, False),
                    call("rules", "member_discount", 6100, True),
                ]),
                ["checkout_total", "order_receipt"], receipt,
            ),
            task(
                "receipt_transitive_calls", "architecture",
                "Starting at order_receipt, list all project-defined functions reachable through one or more function-call edges, including indirect callees. Exclude order_receipt itself and all builtins. Return a sorted list of function names.",
                architecture("service", "order_receipt"),
                ["checkout_total", "line_subtotal", "member_discount", "sales_tax"],
                refs("service:order_receipt", "service:checkout_total", "rules:line_subtotal", "rules:member_discount", "rules:sales_tax"),
            ),
        ],
        "eval_authorization": [
            task(
                "empty_and_duplicate_scopes", "single_function",
                "What does normalized_scopes([' X:Y ', 'x:y', ' DOCUMENT:READ', '']) return?",
                call("rules", "normalized_scopes", [" X:Y ", "x:y", " DOCUMENT:READ", ""]),
                ["", "document:read", "x:y"], refs("rules:normalized_scopes"),
            ),
            task(
                "nonowner_read", "cross_file",
                "What does authorize('a9','b2','member',['document:read'],'read',1000,1001,False) return?",
                call("service", "authorize", "a9", "b2", "member", ["document:read"], "read", 1000, 1001, False),
                {"allowed": False, "reason": "denied"}, authorization,
            ),
            task(
                "duplicate_write_permission", "cross_file",
                "What does can_edit_own('k8',[' DOCUMENT:WRITE ','document:write'],50,1849) return?",
                call("service", "can_edit_own", "k8", [" DOCUMENT:WRITE ", "document:write"], 50, 1849),
                True, authorization + refs("service:can_edit_own"),
            ),
            task(
                "last_valid_session_second", "boundary",
                "What does can_edit_own('owner',['document:write'],200,3799) return?",
                call("service", "can_edit_own", "owner", ["document:write"], 200, 3799),
                True, authorization + refs("service:can_edit_own"),
            ),
            task(
                "revoked_admin", "semantic",
                "Administrator root requests writing a document owned by b2. Permissions contain document:write. The session began at time 0, current time is 10, and the session is revoked. Return the authorization decision object with allowed and reason.",
                call("service", "authorize", "root", "b2", "admin", ["document:write"], "write", 0, 10, True),
                {"allowed": False, "reason": "session"}, authorization,
            ),
            task(
                "owner_case_mismatch", "semantic",
                "A member with user ID U9 requests reading a document owned by user ID u9. Permissions contain document:read, the session began at 1000, current time is 1100, and it is not revoked. Return the authorization decision object with allowed and reason.",
                call("service", "authorize", "U9", "u9", "member", ["document:read"], "read", 1000, 1100, False),
                {"allowed": False, "reason": "denied"}, authorization,
            ),
            task(
                "write_scope_intervention", "change_impact",
                "If policy.WRITE_SCOPE changes from 'document:write' to 'document:modify' before the program is loaded, which exact calls change their return values: scope_allows(['document:write'],'write'), can_edit_own('v2',['document:write'],0,123), user_key(' V2 ')? Return a sorted list of changed function names.",
                impact("policy", "WRITE_SCOPE", "document:modify", [
                    call("rules", "scope_allows", ["document:write"], "write"),
                    call("service", "can_edit_own", "v2", ["document:write"], 0, 123),
                    call("service", "user_key", " V2 "),
                ]),
                ["can_edit_own", "scope_allows"], authorization + refs("service:can_edit_own", "service:user_key"),
            ),
            task(
                "own_edit_transitive_calls", "architecture",
                "Starting at can_edit_own, list all project-defined functions reachable through one or more function-call edges, including indirect callees. Exclude can_edit_own itself and all builtins. Return a sorted list of function names.",
                architecture("service", "can_edit_own"),
                ["authorize", "normalized_scopes", "required_scope", "role_allows", "scope_allows", "session_valid"],
                refs("service:can_edit_own", "service:authorize", "rules:normalized_scopes", "rules:required_scope", "rules:role_allows", "rules:scope_allows", "rules:session_valid"),
            ),
        ],
        "eval_routing": [
            task(
                "bucket_near_wrap", "single_function",
                "What does bucket('c') return?",
                call("rules", "bucket", "c"), 99, refs("rules:bucket"),
            ),
            task(
                "empty_path", "cross_file",
                f"What does route_request('e','',{edge_backends!r}) return?",
                call("service", "route_request", "e", "", edge_backends), "east-canary:/", routing,
            ),
            task(
                "last_retry_fallback", "cross_file",
                f"What does retry_destination('az','/x//',{west_only!r},2) return?",
                call("service", "retry_destination", "az", "/x//", west_only, 2),
                "west-canary:/x", routing + refs("service:retry_destination", "policy:RETRY_LIMIT"),
            ),
            task(
                "canary_exact_threshold", "boundary",
                "What does use_canary('x') return?",
                call("rules", "use_canary", "x"), False,
                refs("rules:use_canary", "rules:bucket", "policy:CANARY_PERCENT"),
            ),
            task(
                "priority_not_fastest", "semantic",
                "User Z requests the path ' /v2// '. Both backends are up: east latency is 149 ms and west latency is 1 ms. What string does the normal request-routing workflow return?",
                call("service", "route_request", "Z", " /v2// ", priority_backends), "east:/v2", routing,
            ),
            task(
                "retry_without_backend", "semantic",
                "User xy requests /status on retry attempt 1. Both east and west backends are down, each with recorded latency 0 ms. What string does the retry-aware destination lookup return?",
                call("service", "retry_destination", "xy", "/status", down_backends, 1),
                "unavailable", routing + refs("service:retry_destination", "policy:RETRY_LIMIT"),
            ),
            task(
                "latency_intervention", "change_impact",
                f"If policy.MAX_LATENCY_MS changes from 150 to 160 before the program is loaded, which exact calls change their return values: healthy({{'up':True,'latency_ms':155}}), route_request('m','/api',{changed_backends!r}), normalize_path(' /items// ')? Return a sorted list of changed function names.",
                impact("policy", "MAX_LATENCY_MS", 160, [
                    call("rules", "healthy", {"up": True, "latency_ms": 155}),
                    call("service", "route_request", "m", "/api", changed_backends),
                    call("rules", "normalize_path", " /items// "),
                ]),
                ["healthy", "route_request"], routing,
            ),
            task(
                "retry_transitive_calls", "architecture",
                "Starting at retry_destination, list all project-defined functions reachable through one or more function-call edges, including indirect callees. Exclude retry_destination itself and all builtins. Return a sorted list of function names.",
                architecture("service", "retry_destination"),
                ["bucket", "healthy", "normalize_path", "route_request", "use_canary"],
                refs("service:retry_destination", "service:route_request", "rules:bucket", "rules:healthy", "rules:normalize_path", "rules:use_canary"),
            ),
        ],
        "eval_inventory": [
            task(
                "allocate_exact_available", "single_function",
                "What does allocate(6, 6, False) return?",
                call("rules", "allocate", 6, 6, False), 6, refs("rules:allocate"),
            ),
            task(
                "maximum_valid_reservation", "cross_file",
                "What does reserve(18,2,12,False,75) return?",
                call("service", "reserve", 18, 2, 12, False, 75),
                {"status": "reserved", "units": 12, "expires": 975}, reservation,
            ),
            task(
                "partial_depletes_available", "cross_file",
                "What does remaining_after(9,1,8,True) return?",
                call("service", "remaining_after", 9, 1, 8, True), 0,
                reservation + refs("service:remaining_after"),
            ),
            task(
                "zero_units", "boundary",
                "What does reserve(9,1,0,True,99) return?",
                call("service", "reserve", 9, 1, 0, True, 99),
                {"status": "denied", "units": 0, "expires": 99}, reservation,
            ),
            task(
                "enough_stock", "semantic",
                "A warehouse has 25 physical units and 10 units already held. A customer requests 11 units and refuses partial fulfillment. Current time is 500. Return the reservation object containing status, units, and expires.",
                call("service", "reserve", 25, 10, 11, False, 500),
                {"status": "reserved", "units": 11, "expires": 1400}, reservation,
            ),
            task(
                "below_safety_reserve", "semantic",
                "A warehouse has 4 physical units and 2 units already held. A customer requests 3 units and permits partial fulfillment. Current time is 0. Return the reservation object containing status, units, and expires.",
                call("service", "reserve", 4, 2, 3, True, 0),
                {"status": "denied", "units": 0, "expires": 0}, reservation,
            ),
            task(
                "order_cap_intervention", "change_impact",
                "If policy.MAX_PER_ORDER changes from 12 to 4 before the program is loaded, which exact calls change their return values: valid_quantity(5), reserve(15,1,5,False,300), stock_label(15)? Return a sorted list of changed function names.",
                impact("policy", "MAX_PER_ORDER", 4, [
                    call("rules", "valid_quantity", 5),
                    call("service", "reserve", 15, 1, 5, False, 300),
                    call("service", "stock_label", 15),
                ]),
                ["reserve", "valid_quantity"], reservation + refs("service:stock_label"),
            ),
            task(
                "remaining_transitive_calls", "architecture",
                "Starting at remaining_after, list all project-defined functions reachable through one or more function-call edges, including indirect callees. Exclude remaining_after itself and all builtins. Return a sorted list of function names.",
                architecture("service", "remaining_after"),
                ["allocate", "reserve", "sellable", "valid_quantity"],
                refs("service:remaining_after", "service:reserve", "rules:allocate", "rules:sellable", "rules:valid_quantity"),
            ),
        ],
        "eval_cache": [
            task(
                "short_private_ttl", "single_function",
                "What does cache_ttl(17, True) return?",
                call("rules", "cache_ttl", 17, True), 17,
                refs("rules:cache_ttl", "policy:DEFAULT_TTL", "policy:PRIVATE_TTL", "policy:MAX_TTL"),
            ),
            task(
                "new_query_key", "cross_file",
                "What does render_cache_key(' Org-B ','Audit Log',{'n':0,'sort':'desc','debug':'yes'}) return?",
                call("service", "render_cache_key", " Org-B ", "Audit Log", {"n": 0, "sort": "desc", "debug": "yes"}),
                "render|org-b|audit_log|n=0&sort=desc|v4", key,
            ),
            task(
                "private_lifetime_clamp", "cross_file",
                "What does cache_entry(' TEN-9 ','Live View',{'z':9,'a':2},45,True,1000) return?",
                call("service", "cache_entry", " TEN-9 ", "Live View", {"z": 9, "a": 2}, 45, True, 1000),
                {"key": "render|ten-9|live_view|a=2&z=9|v4", "expires": 1030, "store": True}, entry,
            ),
            task(
                "private_ttl_exact_edge", "boundary",
                "What does cache_entry('edge','One',{},30,True,7) return?",
                call("service", "cache_entry", "edge", "One", {}, 30, True, 7),
                {"key": "render|edge|one||v4", "expires": 37, "store": True}, entry,
            ),
            task(
                "default_public_lifetime", "semantic",
                "Prepare a public render-cache record for a tenant given as one space, resource ' Weekly View ', query keys page=3 and trace='hidden', no requested lifetime (None), and current time 120. Return the object with key, expires, and store.",
                call("service", "cache_entry", " ", " Weekly View ", {"page": 3, "trace": "hidden"}, None, False, 120),
                {"key": "render|public|weekly_view|page=3|v4", "expires": 420, "store": True}, entry,
            ),
            task(
                "negative_private_lifetime", "semantic",
                "Prepare a private render-cache record for tenant TEAM, resource Chart, query key q='ok', requested lifetime minus 10 seconds, and current time 77. Return the object with key, expires, and store.",
                call("service", "cache_entry", "TEAM", "Chart", {"q": "ok"}, -10, True, 77),
                {"key": "render|team|chart|q=ok|v4", "expires": 77, "store": False}, entry,
            ),
            task(
                "private_cap_intervention", "change_impact",
                "If policy.PRIVATE_TTL changes from 30 to 10 before the program is loaded, which exact calls change their return values: cache_ttl(25,True), cache_entry('x2','Result',{},25,True,5), render_cache_key('x2','Result',{})? Return a sorted list of changed function names.",
                impact("policy", "PRIVATE_TTL", 10, [
                    call("rules", "cache_ttl", 25, True),
                    call("service", "cache_entry", "x2", "Result", {}, 25, True, 5),
                    call("service", "render_cache_key", "x2", "Result", {}),
                ]),
                ["cache_entry", "cache_ttl"], entry,
            ),
            task(
                "entry_transitive_calls", "architecture",
                "Starting at cache_entry, list all project-defined functions reachable through one or more function-call edges, including indirect callees. Exclude cache_entry itself and all builtins or string methods. Return a sorted list of function names.",
                architecture("service", "cache_entry"),
                ["cache_ttl", "canonical_query", "normalize_resource", "normalize_tenant", "render_cache_key"],
                refs("service:cache_entry", "rules:cache_ttl", "rules:canonical_query", "rules:normalize_resource", "rules:normalize_tenant", "service:render_cache_key"),
            ),
        ],
        "eval_schedules": [
            task(
                "buffer_exact_separation", "single_function",
                "What does overlaps(600,630,[[640,670]]) return?",
                call("rules", "overlaps", 600, 630, [[640, 670]]), False,
                refs("rules:overlaps", "policy:BUFFER_MINUTES"),
            ),
            task(
                "two_busy_intervals", "cross_file",
                "What does first_available(3,545,45,[[570,615],[660,690]]) return?",
                call("service", "first_available", 3, 545, 45, [[570, 615], [660, 690]]), 720, schedule,
            ),
            task(
                "wrapped_workday", "cross_file",
                "What does appointment(8,515,90,[[540,600],[690,720]]) return?",
                call("service", "appointment", 8, 515, 90, [[540, 600], [690, 720]]),
                {"day": 8, "start": 750, "end": 840}, schedule + refs("service:appointment"),
            ),
            task(
                "max_duration_closing_edge", "boundary",
                "What does first_available(0,840,180,[]) return?",
                call("service", "first_available", 0, 840, 180, []), 840, schedule,
            ),
            task(
                "next_week_opening", "semantic",
                "Find the booking object for day index 7, earliest minute 530, duration 20 minutes, and an empty calendar. Weekday indices begin with Monday at zero and continue into later weeks. Return day, start, and end.",
                call("service", "appointment", 7, 530, 20, []),
                {"day": 7, "start": 540, "end": 560}, schedule + refs("service:appointment"),
            ),
            task(
                "overlong_duration", "semantic",
                "Find the first appointment start on day index 3 at or after minute 560, lasting 181 minutes, with no existing bookings. Return the integer start value used by the scheduling workflow.",
                call("service", "first_available", 3, 560, 181, []), -1, schedule,
            ),
            task(
                "slot_size_intervention", "change_impact",
                "If policy.SLOT_MINUTES changes from 30 to 15 before the program is loaded, which exact calls change their return values: round_slot(571), appointment(1,571,30,[]), weekday_label(8)? Return a sorted list of changed function names.",
                impact("policy", "SLOT_MINUTES", 15, [
                    call("rules", "round_slot", 571),
                    call("service", "appointment", 1, 571, 30, []),
                    call("service", "weekday_label", 8),
                ]),
                ["appointment", "round_slot"], schedule + refs("service:appointment", "service:weekday_label"),
            ),
            task(
                "appointment_transitive_calls", "architecture",
                "Starting at appointment, list all project-defined functions reachable through one or more function-call edges, including indirect callees. Exclude appointment itself and all builtins. Return a sorted list of function names.",
                architecture("service", "appointment"),
                ["first_available", "overlaps", "round_slot", "valid_duration", "working_day"],
                refs("service:appointment", "service:first_available", "rules:overlaps", "rules:round_slot", "rules:valid_duration", "rules:working_day"),
            ),
        ],
    }


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def call_signature(project: str, operation: dict[str, Any]) -> str:
    return canonical({
        "project": project, "module": operation["module"], "function": operation["function"],
        "args": operation["args"],
    })


def project_call_graph(root: Path) -> dict[str, list[str]]:
    """Resolve only actual ast.Call targets that are local project functions."""
    modules = {
        path.stem: ast.parse(path.read_text(encoding="utf-8"))
        for path in sorted(root.glob("*.py"))
    }
    definitions_by_module = {
        module: {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        for module, tree in modules.items()
    }
    graph = {}
    for module, tree in modules.items():
        resolved = {name: uri(module, name) for name in definitions_by_module[module]}
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module in definitions_by_module:
                for alias in node.names:
                    if alias.name in definitions_by_module[node.module]:
                        resolved[alias.asname or alias.name] = uri(node.module, alias.name)
        for name, node in definitions_by_module[module].items():
            graph[uri(module, name)] = sorted({
                resolved[child.func.id] for child in ast.walk(node)
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
                and child.func.id in resolved
            })
    return graph


def transitive_callees(root: Path, module: str, function: str) -> tuple[list[str], list[str]]:
    graph = project_call_graph(root)
    start = uri(module, function)
    reached: set[str] = set()
    frontier = list(graph[start])
    while frontier:
        current = frontier.pop()
        if current == start or current in reached:
            continue
        reached.add(current)
        frontier.extend(graph[current])
    names = [item.rsplit("::", 1)[1] for item in sorted(reached)]
    if len(names) != len(set(names)):
        raise AssertionError("This name-only task is ambiguous because reachable functions share a name.")
    return sorted(names), sorted(reached)


def write_once(path: Path, value: Any) -> None:
    text = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise FileExistsError(f"Refusing to replace a different frozen artifact: {path}")
        return
    path.write_text(text, encoding="utf-8")


def build(output_dir: Path | str, source_dataset: Path | str = DEFAULT_SOURCE) -> dict[str, Any]:
    source = Path(source_dataset).resolve()
    output = Path(output_dir).resolve()
    if output == source or source in output.parents or output == source.parent:
        raise ValueError("Use a new output directory outside the original evidence/dataset.")
    old_tasks = json.loads((source / "eval_tasks.json").read_text(encoding="utf-8"))
    old_gold = json.loads((source / "gold_validation.json").read_text(encoding="utf-8"))
    old_questions = {item["question"].strip() for item in old_tasks}
    old_ids = {item["id"] for item in old_tasks}
    old_calls: set[str] = set()
    old_interventions: set[str] = set()
    old_architecture: set[str] = set()
    for item in old_gold:
        project = item["id"].split("__", 1)[0]
        if not project.startswith("eval_"):
            continue
        if item["kind"] == "execution":
            old_calls.add(call_signature(project, item["call"]))
        elif item["kind"] == "impact":
            old_calls.update(call_signature(project, probe) for probe in item["probes"])
            old_interventions.add(canonical({"project": project, **item["override"]}))
        elif item["kind"] == "architecture":
            old_architecture.add(canonical({
                "project": project, "module": item["module"], "function": item["function"],
                "mode": "direct",
            }))
    records, validation, source_hashes = [], [], {}
    new_calls, new_questions, new_interventions, new_architecture = set(), set(), set(), set()
    expected_distribution = {
        "single_function": 1, "cross_file": 2, "boundary": 1,
        "semantic": 2, "change_impact": 1, "architecture": 1,
    }
    specs = definitions()
    for project, questions in specs.items():
        if Counter(item["category"] for item in questions) != Counter(expected_distribution):
            raise AssertionError(f"Unexpected category distribution: {project}")
        root = source / "projects" / project
        symbols = source_symbols(root)
        source_hashes[project] = {
            path.relative_to(root).as_posix(): sha_bytes(path.read_bytes())
            for path in sorted(root.glob("*.py"))
        }
        for item in questions:
            operation = item["operation"]
            kind = operation.get("kind", "execution")
            question = item["question"].strip()
            identifier = project + "__v2_" + item["slug"]
            if identifier in old_ids or question in old_questions or question in new_questions:
                raise AssertionError(f"Repeated question or id: {identifier}")
            new_questions.add(question)
            proof: dict[str, Any] = {"id": identifier, "kind": kind}
            task_calls = []
            if kind == "execution":
                task_calls = [operation]
                answer = execute(root, task_calls)[0]
                target = uri(operation["module"], operation["function"])
                proof["call"] = operation
                verification = "Fresh isolated Python execution; exact JSON value/type agrees with an independently declared hand-calculated expected answer."
            elif kind == "impact":
                task_calls = operation["probes"]
                before = execute(root, task_calls)
                override = {
                    "module": operation["module"], "name": operation["constant"],
                    "value": operation["replacement"],
                }
                signature = canonical({"project": project, **override})
                if signature in old_interventions or signature in new_interventions:
                    raise AssertionError(f"Repeated policy intervention: {identifier}")
                new_interventions.add(signature)
                after = execute(root, task_calls, [override])
                answer = sorted(probe["function"] for probe, a, b in zip(task_calls, before, after) if not json_equal(a, b))
                first_service = next(probe for probe in task_calls if probe["module"] == "service")
                target = uri(first_service["module"], first_service["function"])
                proof.update(probes=task_calls, override=override, before=before, after=after)
                verification = "Fresh-process before/after policy intervention at the listed inputs; changed names agree with a separately declared expected set. This does not mean all-input change impact."
            elif kind == "architecture":
                signature = canonical({
                    "project": project, "module": operation["module"],
                    "function": operation["function"], "mode": operation["mode"],
                })
                if signature in old_architecture or signature in new_architecture:
                    raise AssertionError(f"Repeated architecture question: {identifier}")
                new_architecture.add(signature)
                answer, reachable = transitive_callees(root, operation["module"], operation["function"])
                target = uri(operation["module"], operation["function"])
                proof.update(module=operation["module"], function=operation["function"], mode="transitive", reachable_uris=reachable)
                verification = "AST-resolved transitive project-call graph; reachable names agree with a separately declared expected list. Builtins, methods, constants and the starting function are excluded."
            else:
                raise ValueError(kind)
            for probe in task_calls:
                signature = call_signature(project, probe)
                if signature in old_calls or signature in new_calls:
                    raise AssertionError(f"Repeated executable input: {identifier}: {probe}")
                new_calls.add(signature)
            if not json_equal(answer, item["check"]):
                raise AssertionError(f"Independent gold mismatch: {identifier}: actual={answer!r}, expected={item['check']!r}")
            required = list(dict.fromkeys(item["required"]))
            if set(required + [target]) - symbols.keys():
                raise AssertionError(f"Unresolvable required symbols: {identifier}")
            records.append({
                "id": identifier, "project": project, "category": item["category"],
                "question": question, "expected": answer, "target_uri": target,
                "required_uris": required, "verification": verification,
            })
            validation.append({
                **proof, "expected": answer, "independent_check_passed": True,
                "question_is_new": True, "all_executable_inputs_are_new": True,
                "novelty_scope": "Exact question and project/function/argument tuple novelty, not independent source logic.",
            })
    if len(records) != 48 or len(specs) != 6:
        raise AssertionError("Expected 48 questions on six existing evaluation projects.")
    # Detect unintended source changes, including changes made by another process.
    after_hashes = {
        project: {
            path.relative_to(source / "projects" / project).as_posix(): sha_bytes(path.read_bytes())
            for path in sorted((source / "projects" / project).glob("*.py"))
        } for project in specs
    }
    if source_hashes != after_hashes:
        raise AssertionError("Source files changed during gold validation.")
    manifest = {
        "schema_version": 2, "dataset_name": "additional_questions_on_seen_projects_v2",
        "source_dataset": str(source), "source_manifest_sha256": sha_bytes((source / "manifest.json").read_bytes()),
        "source_eval_tasks_sha256": sha_bytes((source / "eval_tasks.json").read_bytes()),
        "source_gold_sha256": sha_bytes((source / "gold_validation.json").read_bytes()),
        "generator_sha256": sha_bytes(Path(__file__).read_bytes()),
        "source_hashes": source_hashes, "project_count": 6, "task_count": 48,
        "category_distribution_per_project": expected_distribution,
        "executed_question_count": 36, "impact_question_count": 6, "architecture_question_count": 6,
        "new_executable_call_tuples": len(new_calls), "new_policy_interventions": len(new_interventions),
        "new_architecture_specifications": len(new_architecture),
        "question_content_sha256": sha_bytes(canonical(records).encode()),
        "validation": {
            "all_gold_values_checked_against_independent_expected": True,
            "all_source_uris_resolve": True, "exact_old_question_duplicates": 0,
            "exact_old_executable_input_duplicates": 0, "exact_new_executable_input_duplicates": 0,
            "original_sources_unchanged": True,
        },
        "architecture_scope_change": "Six original direct-call questions are replaced by transitive-call questions from different starting functions.",
        "design_scope": [
            "The six source projects, algorithms, constants and question families were already seen in the first evaluation.",
            "This evaluates new fixed inputs and paraphrases on the same code, not unseen-project or production generalization.",
            "The designer knew the earlier experiment results. The generator does not read model answers or tune from new answers.",
            "Existing and additional questions must be reported separately; their 96 questions are not 96 independent project samples.",
            "Required URI lists conservatively include possible dependencies, not a branch-minimal set of necessary facts.",
            "Architecture tasks use transitive static call reachability; impact tasks use explicit fixed-input fresh-load intervention.",
            "Questions and gold remain outside retrievable project sources. Freeze this output before any new evaluation model call.",
        ],
    }
    output.mkdir(parents=True, exist_ok=True)
    write_once(output / "eval_tasks.json", records)
    write_once(output / "gold_validation.json", validation)
    write_once(output / "manifest.json", manifest)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source-dataset", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()
    print(json.dumps(build(args.out, args.source_dataset), indent=2, ensure_ascii=False))

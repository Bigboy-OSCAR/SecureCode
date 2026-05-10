from __future__ import annotations

import json
from typing import Any


SCALE_DEFAULTS = {
    "small": {"log_lines": 650, "doc_sections": 48, "json_tenants": 420},
    "medium": {"log_lines": 5_000, "doc_sections": 320, "json_tenants": 2_800},
}


def collect_checkout_trace(log_lines: int) -> str:
    target_at = max(20, log_lines // 2)
    rows = []
    for idx in range(log_lines):
        request_id = f"REQ-{idx:06d}"
        tenant = f"tenant-{idx % 97:03d}"
        latency = 40 + (idx * 17) % 600
        if idx == target_at - 1:
            rows.append(
                "2026-05-10T02:14:17Z INFO request_id=REQ-042031 service=checkout "
                "tenant=northwind-prod stage=payment status=started user_id=u-8841"
            )
        elif idx == target_at:
            rows.append(
                "2026-05-10T02:14:18Z ERROR request_id=REQ-042031 service=payment_gateway "
                "code=PGW_DECLINED reason=velocity_limit retry_after_ms=7500 attempt=2"
            )
        elif idx == target_at + 1:
            rows.append(
                "2026-05-10T02:14:19Z WARN request_id=REQ-042031 service=checkout "
                "action=queued_retry queue=payments-deferred"
            )
        else:
            level = "INFO" if idx % 19 else "DEBUG"
            service = ["checkout", "catalog", "identity", "fulfillment", "search"][idx % 5]
            rows.append(
                f"2026-05-10T02:{idx % 60:02d}:{(idx * 7) % 60:02d}Z {level} "
                f"request_id={request_id} service={service} tenant={tenant} "
                f"code=OK latency_ms={latency} cache_hit={str(idx % 3 == 0).lower()}"
            )
    return "\n".join(rows)


def compile_operations_runbook(doc_sections: int) -> str:
    blocks = ["# Runtime Operations Runbook", ""]
    target_at = max(5, doc_sections // 2)
    for idx in range(doc_sections):
        if idx == target_at:
            blocks.extend(
                [
                    "## Payment Gateway Retry Policy",
                    "",
                    "Applies to checkout payment authorization calls.",
                    "",
                    "- max_retries: 4",
                    "- initial_backoff_ms: 250",
                    "- jitter_percent: 17",
                    "- retryable_codes: PGW_TIMEOUT, PGW_RATE_LIMIT",
                    "- fatal_codes: PGW_DECLINED, PGW_BLOCKED",
                    "",
                ]
            )
            continue
        blocks.extend(
            [
                f"## Routine Runtime Section {idx:03d}",
                "",
                f"Owner: team-{idx % 13:02d}",
                f"Escalation channel: runtime-ops-{idx % 9:02d}",
                f"Checklist token: RUNTIME-CHECK-{idx:04d}-{(idx * 31) % 997:03d}",
                "Use the normal low-risk maintenance workflow for this section.",
                "",
            ]
        )
    return "\n".join(blocks)


def fetch_tenant_snapshot(json_tenants: int) -> dict[str, Any]:
    data: dict[str, Any] = {
        "generated_at": "2026-05-10T02:30:00Z",
        "schema_version": 3,
        "tenants": {},
    }
    tenants = data["tenants"]
    for idx in range(json_tenants):
        name = f"tenant-{idx:04d}"
        tenants[name] = {
            "security": {
                "source_pointer_enabled": bool(idx % 2),
                "runtime_pointer_enabled": bool((idx + 1) % 2),
                "max_context_policy": "raw-ok" if idx % 5 else "pointer-preferred",
                "audit_bucket": f"audit-{idx % 41:02d}",
            },
            "limits": {
                "daily_tool_result_mb": 64 + idx % 512,
                "max_runtime_pointer_depth": 2 + idx % 4,
            },
        }
    tenants["northwind-prod"] = {
        "security": {
            "source_pointer_enabled": True,
            "runtime_pointer_enabled": True,
            "max_context_policy": "pointer-first",
            "audit_bucket": "sec-audit-17",
        },
        "limits": {
            "daily_tool_result_mb": 512,
            "max_runtime_pointer_depth": 5,
        },
    }
    return data


def serialize_runtime_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def runtime_tasks(scale: str, log_lines: int | None = None, doc_sections: int | None = None, json_tenants: int | None = None) -> list[dict[str, Any]]:
    defaults = SCALE_DEFAULTS[scale]
    log_lines = defaults["log_lines"] if log_lines is None else log_lines
    doc_sections = defaults["doc_sections"] if doc_sections is None else doc_sections
    json_tenants = defaults["json_tenants"] if json_tenants is None else json_tenants

    return [
        {
            "id": "runtime_log_payment_failure_reason",
            "producer": {
                "name": "collect_checkout_trace",
                "kind": "log",
                "args": {"log_lines": log_lines},
                "tools": ["grep_runtime_log"],
                "hints": ["request_id", "payment_gateway", "retry_after_ms", "reason"],
            },
            "question": (
                "For request_id=REQ-042031 in the runtime checkout trace, what are the exact "
                "payment failure reason and retry_after_ms? Answer as reason=<value>, retry_after_ms=<value>."
            ),
            "tool": {
                "name": "grep_runtime_log",
                "args": {
                    "pattern": "REQ-042031",
                    "before": 1,
                    "after": 1,
                },
            },
            "expected_substrings": ["velocity_limit", "7500"],
        },
        {
            "id": "runtime_doc_retry_policy",
            "producer": {
                "name": "compile_operations_runbook",
                "kind": "doc",
                "args": {"doc_sections": doc_sections},
                "tools": ["extract_runtime_doc_section"],
                "hints": ["Payment Gateway Retry Policy", "max_retries", "jitter_percent"],
            },
            "question": (
                "In the Payment Gateway Retry Policy section of the runtime operations runbook, what are "
                "max_retries and jitter_percent? Answer as max_retries=<value>, jitter_percent=<value>."
            ),
            "tool": {
                "name": "extract_runtime_doc_section",
                "args": {
                    "query": "Payment Gateway Retry Policy",
                },
            },
            "expected_substrings": ["4", "17"],
        },
        {
            "id": "runtime_json_tenant_policy",
            "producer": {
                "name": "fetch_tenant_snapshot",
                "kind": "json",
                "args": {"json_tenants": json_tenants},
                "tools": ["extract_runtime_json_path"],
                "hints": [
                    "tenants.northwind-prod.security",
                    "runtime_pointer_enabled",
                    "max_context_policy",
                ],
            },
            "question": (
                "For tenant northwind-prod in the runtime tenant snapshot JSON, what are "
                "runtime_pointer_enabled and max_context_policy? Answer as enabled=<value>, "
                "max_context_policy=<value>."
            ),
            "tool": {
                "name": "extract_runtime_json_path",
                "args": {
                    "path": "tenants.northwind-prod.security",
                },
            },
            "expected_substrings": ["true", "pointer-first"],
        },
    ]


def produce_runtime_value(task: dict[str, Any]) -> Any:
    producer = task["producer"]
    name = producer["name"]
    args = producer["args"]
    if name == "collect_checkout_trace":
        return collect_checkout_trace(int(args["log_lines"]))
    if name == "compile_operations_runbook":
        return compile_operations_runbook(int(args["doc_sections"]))
    if name == "fetch_tenant_snapshot":
        return fetch_tenant_snapshot(int(args["json_tenants"]))
    raise ValueError(f"unknown runtime producer: {name}")

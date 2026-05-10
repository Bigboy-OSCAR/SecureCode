from __future__ import annotations

import argparse
import json
from pathlib import Path


SCALE_DEFAULTS = {
    "small": {"log_lines": 650, "doc_sections": 48, "json_tenants": 420},
    "medium": {"log_lines": 5_000, "doc_sections": 320, "json_tenants": 2_800},
}


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def _make_log(path: Path, lines: int) -> None:
    target_at = max(20, lines // 2)
    rows = []
    for idx in range(lines):
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
    _write(path, "\n".join(rows))


def _make_doc(path: Path, sections: int) -> None:
    blocks = ["# Operations Runbook", ""]
    target_at = max(5, sections // 2)
    for idx in range(sections):
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
                f"## Routine Operations Section {idx:03d}",
                "",
                f"Owner: team-{idx % 13:02d}",
                f"Escalation channel: ops-{idx % 9:02d}",
                f"Checklist token: CHECK-{idx:04d}-{(idx * 31) % 997:03d}",
                "Use the normal low-risk maintenance workflow for this section.",
                "",
            ]
        )
    _write(path, "\n".join(blocks))


def _make_json(path: Path, tenants: int) -> None:
    data = {
        "generated_at": "2026-05-10T02:30:00Z",
        "schema_version": 3,
        "tenants": {},
    }
    for idx in range(tenants):
        name = f"tenant-{idx:04d}"
        data["tenants"][name] = {
            "security": {
                "source_pointer_enabled": bool(idx % 2),
                "max_context_policy": "raw-ok" if idx % 5 else "pointer-preferred",
                "audit_bucket": f"audit-{idx % 41:02d}",
            },
            "limits": {
                "daily_tool_result_mb": 64 + idx % 512,
                "max_file_pointer_depth": 2 + idx % 4,
            },
        }
    data["tenants"]["northwind-prod"] = {
        "security": {
            "source_pointer_enabled": True,
            "max_context_policy": "pointer-first",
            "audit_bucket": "sec-audit-17",
        },
        "limits": {
            "daily_tool_result_mb": 512,
            "max_file_pointer_depth": 5,
        },
    }
    _write(path, json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def _source_entry(root: Path, kind: str, rel_path: str, tools: list[str], hints: list[str]) -> dict:
    path = root / rel_path
    return {
        "kind": kind,
        "rel_path": rel_path,
        "pointer": f"source://{kind}/{rel_path}",
        "bytes": path.stat().st_size,
        "tools": tools,
        "hints": hints,
    }


def generate_corpus(output_dir: Path, scale: str = "small", log_lines: int | None = None, doc_sections: int | None = None, json_tenants: int | None = None) -> dict:
    defaults = SCALE_DEFAULTS[scale]
    log_lines = defaults["log_lines"] if log_lines is None else log_lines
    doc_sections = defaults["doc_sections"] if doc_sections is None else doc_sections
    json_tenants = defaults["json_tenants"] if json_tenants is None else json_tenants

    sources_root = output_dir / "sources"
    sources_root.mkdir(parents=True, exist_ok=True)
    for old in sources_root.rglob("*"):
        if old.is_file():
            old.unlink()

    _make_log(sources_root / "logs" / "checkout_gateway.log", log_lines)
    _make_doc(sources_root / "docs" / "ops_runbook.md", doc_sections)
    _make_json(sources_root / "json" / "tenant_snapshot.json", json_tenants)

    sources = [
        _source_entry(
            sources_root,
            "log",
            "logs/checkout_gateway.log",
            ["grep_log"],
            ["request_id", "payment_gateway", "retry_after_ms", "reason"],
        ),
        _source_entry(
            sources_root,
            "doc",
            "docs/ops_runbook.md",
            ["extract_doc_section"],
            ["Payment Gateway Retry Policy", "max_retries", "jitter_percent"],
        ),
        _source_entry(
            sources_root,
            "json",
            "json/tenant_snapshot.json",
            ["extract_json_field"],
            ["tenants.northwind-prod.security", "source_pointer_enabled", "max_context_policy"],
        ),
    ]
    manifest = {
        "scale": scale,
        "log_lines": log_lines,
        "doc_sections": doc_sections,
        "json_tenants": json_tenants,
        "sources_root": str(sources_root),
        "sources": sources,
    }
    tasks = [
        {
            "id": "log_payment_failure_reason",
            "question": (
                "For request_id=REQ-042031 in the checkout gateway log, what are the exact "
                "payment failure reason and retry_after_ms? Answer as reason=<value>, retry_after_ms=<value>."
            ),
            "pointer": "source://log/logs/checkout_gateway.log",
            "tool": {
                "name": "grep_log",
                "args": {
                    "pointer": "source://log/logs/checkout_gateway.log",
                    "pattern": "REQ-042031",
                    "before": 1,
                    "after": 1,
                },
            },
            "expected_substrings": ["velocity_limit", "7500"],
        },
        {
            "id": "doc_retry_policy",
            "question": (
                "In the Payment Gateway Retry Policy section of the operations runbook, what are "
                "max_retries and jitter_percent? Answer as max_retries=<value>, jitter_percent=<value>."
            ),
            "pointer": "source://doc/docs/ops_runbook.md",
            "tool": {
                "name": "extract_doc_section",
                "args": {
                    "pointer": "source://doc/docs/ops_runbook.md",
                    "query": "Payment Gateway Retry Policy",
                },
            },
            "expected_substrings": ["4", "17"],
        },
        {
            "id": "json_tenant_source_policy",
            "question": (
                "For tenant northwind-prod in the tenant snapshot JSON, what are "
                "source_pointer_enabled and max_context_policy? Answer as enabled=<value>, "
                "max_context_policy=<value>."
            ),
            "pointer": "source://json/json/tenant_snapshot.json",
            "tool": {
                "name": "extract_json_field",
                "args": {
                    "pointer": "source://json/json/tenant_snapshot.json",
                    "path": "tenants.northwind-prod.security",
                },
            },
            "expected_substrings": ["true", "pointer-first"],
        },
    ]

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output_dir / "tasks.json").write_text(json.dumps(tasks, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate external source files for source pointer tests.")
    parser.add_argument("--out", type=Path, default=Path("source_pointer_test/work/small"))
    parser.add_argument("--scale", choices=sorted(SCALE_DEFAULTS), default="small")
    parser.add_argument("--log-lines", type=int)
    parser.add_argument("--doc-sections", type=int)
    parser.add_argument("--json-tenants", type=int)
    args = parser.parse_args()
    manifest = generate_corpus(args.out, args.scale, args.log_lines, args.doc_sections, args.json_tenants)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()


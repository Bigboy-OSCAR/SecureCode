from __future__ import annotations

import argparse
import json
from pathlib import Path

from .indexer import build_index, symbol_map


SCALE_DEFAULTS = {
    "small": {"noise_files": 3, "noise_functions": 10},
    "medium": {"noise_files": 24, "noise_functions": 24},
    "large": {"noise_files": 80, "noise_functions": 36},
}


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def _target_files(root: Path) -> None:
    _write(
        root / "services" / "auth_service.py",
        '''
from dataclasses import dataclass

TOKEN_EXPIRED_MESSAGE = "TOKEN_EXPIRED"
TOKEN_MISSING_USER_MESSAGE = "TOKEN_MISSING_USER"


@dataclass
class TokenRecord:
    user_id: str
    active: bool
    expires_at: int
    scopes: set[str]


def normalize_scope(scope: str) -> str:
    return scope.strip().lower().replace(" ", ":")


def validate_token(token: dict, now: int) -> str:
    if not token.get("active", False):
        return "inactive"
    if token.get("expires_at", 0) <= now:
        raise ValueError(TOKEN_EXPIRED_MESSAGE)
    if "user_id" not in token:
        raise KeyError(TOKEN_MISSING_USER_MESSAGE)
    return f"user:{token['user_id']}"


class AuthService:
    def __init__(self, issuer: str) -> None:
        self.issuer = issuer

    def refresh_session(self, user_id: str, ttl_seconds: int) -> str:
        normalized = user_id.strip().lower()
        return f"rotated:{self.issuer}:{normalized}:{ttl_seconds}"
''',
    )
    _write(
        root / "billing" / "payments.py",
        '''
class InvoiceCalculator:
    def subtotal(self, item_cents: list[int]) -> int:
        return sum(item_cents)

    def compute_late_fee(self, days_late: int, subtotal_cents: int) -> int:
        if days_late <= 3:
            return 0
        daily_rate = 0.0125
        billable_days = min(days_late - 3, 21)
        return int(subtotal_cents * daily_rate * billable_days)


def invoice_status(days_late: int) -> str:
    if days_late <= 0:
        return "current"
    if days_late <= 3:
        return "grace"
    return "late"
''',
    )
    _write(
        root / "reports" / "reporting.py",
        '''
def sanitize_report_name(report_name: str) -> str:
    return report_name.strip().replace(" ", "_").lower()


def build_cache_key(report_name: str, tenant_id: str, version: int) -> str:
    safe_name = sanitize_report_name(report_name)
    safe_tenant = tenant_id.strip().lower()
    return f"report:{safe_tenant}:{safe_name}:v{version}"


class ReportRenderer:
    def render_title(self, report_name: str, tenant_id: str) -> str:
        return f"{tenant_id.upper()}::{report_name.title()}"
''',
    )


def _noise_file(module_no: int, functions: int) -> str:
    blocks = [
        f'"""Synthetic distractor module {module_no} for symbol selector benchmarking."""',
        "",
        f"MODULE_OFFSET = {module_no}",
        "",
    ]
    for fn_no in range(functions):
        name = f"helper_{module_no:03d}_{fn_no:03d}"
        if fn_no % 9 == 0:
            name = f"validate_token_shadow_{module_no:03d}_{fn_no:03d}"
        blocks.append(
            f'''
def {name}(value: int, label: str = "noise") -> str:
    """Return a deterministic distractor value."""
    adjusted = value + MODULE_OFFSET + {fn_no}
    if adjusted % 7 == 0:
        return f"{{label}}:retry:{module_no}:{fn_no}:{{adjusted}}"
    if adjusted % 11 == 0:
        return f"{{label}}:skip:{module_no}:{fn_no}:{{adjusted}}"
    return f"{{label}}:ok:{module_no}:{fn_no}:{{adjusted}}"
'''
        )
    blocks.append(
        f'''
class DistractorService{module_no:03d}:
    def route(self, key: str) -> str:
        normalized = key.strip().lower()
        return f"distractor:{module_no}:{{normalized}}"
'''
    )
    return "\n".join(blocks)


def _find_symbol_uri(symbols: dict[str, dict], suffix: str) -> str:
    matches = [uri for uri in symbols if uri.endswith(suffix)]
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one symbol ending with {suffix}, got {matches}")
    return matches[0]


def generate_corpus(
    output_dir: Path,
    scale: str = "small",
    noise_files: int | None = None,
    noise_functions: int | None = None,
) -> dict:
    defaults = SCALE_DEFAULTS[scale]
    noise_files = defaults["noise_files"] if noise_files is None else noise_files
    noise_functions = defaults["noise_functions"] if noise_functions is None else noise_functions

    root = output_dir / "corpus"
    root.mkdir(parents=True, exist_ok=True)
    for old_file in root.rglob("*.py"):
        old_file.unlink()

    _target_files(root)
    for module_no in range(noise_files):
        _write(root / "noise" / f"module_{module_no:03d}.py", _noise_file(module_no, noise_functions))

    index = build_index(root)
    symbols = symbol_map(index)
    tasks = [
        {
            "id": "auth_expired_token_message",
            "question": "What exact literal is raised when validate_token receives an expired token? Answer with only that literal.",
            "target_uri": _find_symbol_uri(symbols, "services/auth_service.py::validate_token"),
            "expected_substrings": ["TOKEN_EXPIRED"],
        },
        {
            "id": "billing_late_fee_grace",
            "question": "How many late days are free before InvoiceCalculator.compute_late_fee starts charging? Answer with only the number.",
            "target_uri": _find_symbol_uri(symbols, "billing/payments.py::InvoiceCalculator.compute_late_fee"),
            "expected_substrings": ["3"],
        },
        {
            "id": "reports_cache_key_format",
            "question": "What prefix and version marker format does build_cache_key use? Answer with the exact pattern shape.",
            "target_uri": _find_symbol_uri(symbols, "reports/reporting.py::build_cache_key"),
            "expected_substrings": ["report:", ":v"],
        },
    ]

    manifest = {
        "scale": scale,
        "noise_files": noise_files,
        "noise_functions_per_file": noise_functions,
        "corpus_root": str(root),
        "files": len(index["files"]),
        "symbols": len(index["symbols"]),
        "tasks": len(tasks),
    }

    (output_dir / "symbol_index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / "tasks.json").write_text(
        json.dumps(tasks, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a synthetic Python corpus for symbol selector tests.")
    parser.add_argument("--out", type=Path, default=Path("symbol_test/work/small"))
    parser.add_argument("--scale", choices=sorted(SCALE_DEFAULTS), default="small")
    parser.add_argument("--noise-files", type=int)
    parser.add_argument("--noise-functions", type=int)
    args = parser.parse_args()

    manifest = generate_corpus(args.out, args.scale, args.noise_files, args.noise_functions)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

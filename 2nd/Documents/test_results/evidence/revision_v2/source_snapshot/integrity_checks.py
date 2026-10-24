"""Offline integrity audit; never connects to the model server or edits inputs."""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import traceback

sys.dont_write_bytecode = True
import experiment as bench
import corpus_builder as corpus


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def jsonl_snapshot(path):
    """An active writer may have an incomplete last line; report only full rows."""
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    rows = []
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            if index != len(lines) - 1:
                raise
    return rows


def run(out):
    dataset = out / "dataset"
    manifest = load(dataset / "manifest.json")
    tasks = load(dataset / "dev_tasks.json") + load(dataset / "eval_tasks.json")
    gold = {r["id"]: r for r in load(dataset / "gold_validation.json")}
    projects = {r["name"]: r for r in manifest["projects"]}
    nodes = {
        name: bench.source_nodes(dataset / "projects" / name) for name in projects
    }
    assets = {
        path.stem: load(path) for path in sorted((out / "assets").glob("*.json"))
    }
    calls = jsonl_snapshot(out / "model_calls.jsonl")
    saved_results = {
        path.name: jsonl_snapshot(path)
        for path in sorted(out.glob("results_*.jsonl"))
    }
    checks = []

    def check(name, fn):
        try:
            detail = fn()
            checks.append({"name": name, "passed": True, "detail": detail})
        except Exception as exc:
            checks.append({
                "name": name, "passed": False,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(limit=3),
            })

    def counts_and_categories():
        assert len(projects) == 7
        assert len(tasks) == 56 and len(gold) == 56
        assert len({t["id"] for t in tasks}) == 56
        assert sum(p["split"] == "eval" for p in projects.values()) == 6
        expected_categories = {
            "single_function": 1, "cross_file": 2, "boundary": 1,
            "semantic": 2, "change_impact": 1, "architecture": 1,
        }
        for name, project in projects.items():
            group = [t for t in tasks if t["project"] == name]
            assert len(group) == 8, name
            assert Counter(t["category"] for t in group) == expected_categories, name
            assert (name.startswith("eval_")) == (project["split"] == "eval")
        assert len(load(dataset / "eval_tasks.json")) == 48
        assert len(load(dataset / "dev_tasks.json")) == 8
        return {"development_tasks": 8, "evaluation_tasks": 48, "projects": 7}

    def source_and_uris():
        uri_count = 0
        for name, project in projects.items():
            root = dataset / "projects" / name
            paths = sorted(root.rglob("*.py"))
            assert len(paths) == project["files"]
            digest = hashlib.sha256()
            for path in paths:
                rel = path.relative_to(root).as_posix()
                digest.update(rel.encode())
                digest.update(path.read_bytes())
                tree = ast.parse(path.read_text())
                assert not any(isinstance(n, ast.ClassDef) for n in ast.walk(tree))
                assert not any(
                    isinstance(n, ast.ImportFrom) and n.level for n in ast.walk(tree)
                )
            assert digest.hexdigest() == project["source_sha256"], name
            assert len(nodes[name]) == project["chunks"], name
            for task in (t for t in tasks if t["project"] == name):
                assert task["target_uri"] in nodes[name], task["id"]
                assert task["required_uris"], task["id"]
                assert set(task["required_uris"]) <= nodes[name].keys(), task["id"]
                uri_count += len(task["required_uris"])
            for uid, node in nodes[name].items():
                assert uid.startswith("memory://symbol/")
                assert set(node["deps"]) <= nodes[name].keys()
        return {"referenced_uri_occurrences": uri_count, "source_hashes_verified": 7}

    def executed_gold():
        execution_count, impact_count, architecture_count = 0, 0, 0
        for task in tasks:
            record = gold[task["id"]]
            root = dataset / "projects" / task["project"]
            assert record["independent_check_passed"] is True
            assert corpus.json_equal(record["expected"], task["expected"])
            if record["kind"] == "execution":
                actual = corpus.execute(root, [record["call"]])[0]
                execution_count += 1
            elif record["kind"] == "impact":
                before = corpus.execute(root, record["probes"])
                after = corpus.execute(root, record["probes"], [record["override"]])
                actual = sorted(
                    probe["function"]
                    for probe, old, new in zip(record["probes"], before, after)
                    if not corpus.json_equal(old, new)
                )
                assert corpus.json_equal(before, record["before"])
                assert corpus.json_equal(after, record["after"])
                impact_count += 1
            elif record["kind"] == "architecture":
                actual = corpus.direct_project_calls(
                    root, record["module"], record["function"]
                )
                architecture_count += 1
            else:
                raise AssertionError(record["kind"])
            assert corpus.json_equal(actual, task["expected"]), task["id"]
        return {
            "execution_values_recomputed": execution_count,
            "policy_interventions_recomputed": impact_count,
            "direct_call_sets_recomputed": architecture_count,
            "note": "Fresh Python execution; uses corpus execution helper, no model calls.",
        }

    def graph_fixtures():
        pricing = nodes["eval_pricing"]
        checkout = bench.uri("service.py", "checkout_total")
        expected = {
            bench.uri("policy.py", "DELIVERY_CENTS"),
            bench.uri("policy.py", "FREE_DELIVERY_CENTS"),
            bench.uri("rules.py", "line_subtotal"),
            bench.uri("rules.py", "member_discount"),
            bench.uri("rules.py", "sales_tax"),
        }
        assert set(pricing[checkout]["deps"]) == expected
        assert set(pricing[bench.uri("rules.py", "sales_tax")]["deps"]) == {
            bench.uri("policy.py", "TAX_BPS")
        }
        shipping = nodes["dev_shipping"]
        assert set(shipping[bench.uri("rules.py", "weight_charge")]["deps"]) == {
            bench.uri("rules.py", "weight_steps"),
            bench.uri("policy.py", "STEP_CENTS"),
        }
        b = bench.baseline_cross_file_members(pricing, checkout, "checkout_total")
        assert checkout in b and expected <= set(b)
        assert sum(pricing[u]["kind"] == "function" for u in b) <= 8
        fake = {
            f"f{i}": {"kind": "function", "path": f"m{i}.py", "name": f"f{i}",
                     "deps": [f"f{i+1}"] if i < 11 else []}
            for i in range(12)
        }
        assert bench.baseline_cross_file_members(fake, "f0", "") == ["f0", "f1", "f2"]
        fake["f0"]["deps"] = [f"f{i}" for i in range(1, 12)]
        assert len(bench.baseline_cross_file_members(fake, "f0", "")) == 8
        return {"known_dependency_sets": 3, "B_depth_fixture": 2, "B_function_cap": 8}

    def grading():
        def grade(text, expected, ok=True):
            return bench.evaluate_answer({"ok": ok, "answer": text}, expected)[0]
        assert grade('{"answer":125}', 125)
        assert grade('{"answer":{"b":2,"a":1}}', {"a": 1, "b": 2})
        assert grade('```json\n{"answer":125}\n```', 125)
        assert grade('```\n{"answer":"north/east_plan"}\n```', "north/east_plan")
        assert not grade('{"answer":1125}', 125)
        assert not grade('{"answer":true}', 1)
        assert not grade('{"answer":1}', True)
        assert not grade('{"answer":125.0}', 125)
        assert not grade('{"answer":"TOKEN_EXPIRED_MESSAGE"}', "TOKEN_EXPIRED")
        assert not grade('{"answer":"north_east_plan"}', "north/east_plan")
        assert not grade('{"answer":"ACME"}', "acme")
        assert not grade('{"answer":125,"explanation":"extra"}', 125)
        assert not grade('Answer: {"answer":125}', 125)
        assert not grade('{"answer":125}', 125, ok=False)
        assert not grade('{"answer":null}', 125)
        assert not grade('{"answer":["b","a"]}', ["a", "b"])
        assert not grade('Explanation\n```json\n{"answer":125}\n```', 125)
        assert not grade('```json\n{"answer":"north_east_plan"}\n```', "north/east_plan")
        return {
            "positive_cases": 4, "negative_cases": 14, "strict_type_and_list_order": True,
            "presentation_wrapper": "One complete outer JSON code fence accepted; inner value unchanged.",
        }

    def pack_bounds():
        class FakeTokenizer:
            @staticmethod
            def tokens(text):
                return len(text)

        def item(identifier, text, sources, level=0):
            return {"id": identifier, "text": text, "source_uris": sources, "level": level}
        candidates = [
            (1.0, item("oversized", "x" * 30, ["x"])),
            (0.9, item("small", "abc", ["a"])),
            (0.8, item("duplicate", "a", ["a"])),
            (0.7, item("other", "de", ["b"])),
        ]
        context, used, chosen, rejected = bench.pack(FakeTokenizer(), candidates, 7)
        assert context == "abc\n\nde" and used == 7
        assert [x["id"] for x in chosen] == ["small", "other"]
        assert rejected == ["oversized"]
        context, used, chosen, _ = bench.pack(FakeTokenizer(), candidates, 0)
        assert context == "" and used == 0 and chosen == []
        return {
            "whole_node_skipping": True, "deduplicates_fully_seen_raw_nodes": True,
            "unit_tokenizer": "character-count fake; not a substitute for model tokenization",
        }

    def raw_candidate_parity():
        for name, graph in nodes.items():
            raw = bench.raw_items(graph)
            assert len({item["id"] for item in raw}) == len(raw)
            for uid in graph:
                originals = [r for r in raw if r["source_uris"] == [uid]]
                assert originals, (name, uid)
            for item in raw:
                assert item["level"] == 0
                assert set(item["source_uris"]) <= graph.keys()
                assert all(graph[u]["source"] in item["text"] for u in item["source_uris"])
        return {"projects_with_atomic_source_access": 7}

    def assets_and_question_separation():
        for name, asset in assets.items():
            root = dataset / "projects" / name
            assert name in projects
            hashes = {
                path.relative_to(root).as_posix(): bench.sha(path)
                for path in sorted(root.rglob("*.py"))
            }
            assert hashes == asset["source_sha256"], name
            for node in asset["nodes"].values():
                assert node["path"].endswith(".py")
                path = (root / node["path"]).resolve()
                assert path.is_relative_to(root.resolve()) and path.is_file()
            assert asset["raw"] == bench.raw_items(nodes[name]), name
            available_ids = {r["id"] for r in asset["raw"]} | {
                s["id"] for s in asset["summaries"]
            }
            for summary in asset["summaries"]:
                assert set(summary["source_uris"]) <= nodes[name].keys()
                assert set(summary["children"]) <= available_ids
            assert not any(p.suffix == ".json" for p in root.rglob("*"))
        build_calls = [c for c in calls if c["purpose"].startswith("build_")]
        for call in build_calls:
            prompt = call["prompt"]
            assert "eval_tasks.json" not in prompt and "gold_validation.json" not in prompt
            for task in tasks:
                question = task["question"].split(" Respond only with JSON", 1)[0]
                assert question not in prompt, (call["call_id"], task["id"])
        return {
            "completed_assets_audited": len(assets), "expected_assets": len(projects),
            "build_prompts_audited": len(build_calls),
            "scope": "File boundaries, URI provenance, exact-question absence; not a semantic non-leakage proof.",
        }

    def saved_contexts():
        row_count = 0
        for filename, rows in saved_results.items():
            identities = set()
            for row in rows:
                identity = (row["task_id"], row["arm"], row["repeat"])
                assert identity not in identities, (filename, identity)
                identities.add(identity)
                assert 0 <= row["context_tokens"] <= row["budget"], identity
                assert row["input_tokens"] == (
                    row["answer_call"]["input_tokens"]
                    + (row["selector"]["input_tokens"] if row.get("selector") else 0)
                )
                actual, _, _ = bench.evaluate_answer(row["answer_call"], row["expected"])
                if row["failure"] == "selector_invalid":
                    actual = False
                assert row["correct"] == actual, identity
                assert row["query_seconds"] >= row["model_seconds"] >= 0
                row_count += 1
        return {
            "saved_result_rows_audited": row_count,
            "files": {name: len(rows) for name, rows in saved_results.items()},
            "token_note": "Checks recorded Qwen token counts; no server/tokenizer re-call.",
        }

    for name, fn in [
        ("dataset_counts_and_categories", counts_and_categories),
        ("source_hashes_and_resolvable_gold_uris", source_and_uris),
        ("gold_reexecution", executed_gold),
        ("dependency_graph_and_B_limits", graph_fixtures),
        ("strict_JSON_grading", grading),
        ("packing_limits_and_no_partial_fragments", pack_bounds),
        ("raw_atomic_candidate_coverage", raw_candidate_parity),
        ("asset_provenance_and_question_separation", assets_and_question_separation),
        ("saved_context_and_result_accounting", saved_contexts),
    ]:
        check(name, fn)
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if all(c["passed"] for c in checks) else "failed",
        "checks_passed": sum(c["passed"] for c in checks),
        "checks_total": len(checks),
        "integrity_script_sha256": bench.sha(__file__),
        "experiment_sha256_at_audit": bench.sha(bench.__file__),
        "checks": checks,
        "limitations": [
            "Offline audit; no model/server calls and no retokenization of recorded contexts.",
            "Build/evaluation may be active; asset and result counts describe this snapshot.",
            "No semantic accuracy certification of generated summaries.",
            "Only the current top-level-function and static from-import synthetic corpus is covered.",
            "Raw source/provenance coverage does not prove that summaries preserve required facts.",
        ],
    }
    bench.dump(out / "integrity_checks.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=bench.DEFAULT_OUT)
    args = parser.parse_args()
    report = run(args.out.resolve())
    print(json.dumps({
        "status": report["status"], "checks_passed": report["checks_passed"],
        "checks_total": report["checks_total"],
        "failures": [c for c in report["checks"] if not c["passed"]],
    }, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["status"] == "passed" else 1)

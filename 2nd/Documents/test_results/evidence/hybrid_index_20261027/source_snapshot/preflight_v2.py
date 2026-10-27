"""Independent offline preflight of new questions and actual compacted strings.

No model or HTTP calls. Existing evidence and sources are read-only.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
import experiment_v2 as harness


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def exact_equal(a, b):
    return canonical(a) == canonical(b)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def uid(module, function):
    return f"memory://symbol/{module.replace('.', '/')}.py::{function}"


def execution(root, calls, override=None):
    # Deliberately independent of corpus_builder.execute/holdout_v2.build.
    program = r"""
import importlib, json, sys
sys.dont_write_bytecode = True
data = json.load(sys.stdin)
sys.path.insert(0, data["root"])
patch = data["override"]
if patch is not None:
    module = importlib.import_module(patch["module"])
    setattr(module, patch["name"], patch["value"])
output = []
for item in data["calls"]:
    module = importlib.import_module(item["module"])
    output.append(getattr(module, item["function"])(*item["args"]))
json.dump(output, sys.stdout, sort_keys=True)
"""
    request = {"root": str(root.resolve()), "calls": calls, "override": override}
    response = subprocess.run(
        [sys.executable, "-I", "-c", program], input=json.dumps(request),
        capture_output=True, text=True, timeout=20, check=True,
    )
    return json.loads(response.stdout)


def independent_graph(root):
    modules = {p.stem: ast.parse(p.read_text()) for p in root.glob("*.py")}
    definitions = {
        (module, n.name): n for module, tree in modules.items()
        for n in tree.body if isinstance(n, ast.FunctionDef)
    }
    graph = {}
    for (module, name), node in definitions.items():
        bindings = {n: (m, n) for m, n in definitions if m == module}
        for statement in modules[module].body:
            if isinstance(statement, ast.ImportFrom):
                for imported in statement.names:
                    destination = (statement.module, imported.name)
                    if destination in definitions:
                        bindings[imported.asname or imported.name] = destination
        graph[(module, name)] = {
            bindings[n.func.id] for n in ast.walk(node)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in bindings
        }
    return graph, modules


def reachable_names(graph, start):
    result, pending = set(), set(graph[start])
    while pending:
        current = pending.pop()
        if current not in result and current != start:
            result.add(current)
            pending.update(graph[current] - result)
    assert len({name for _, name in result}) == len(result), "Ambiguous duplicate function names"
    return sorted(name for _, name in result)


def invocation_signature(project, operation):
    return canonical([project, operation["module"], operation["function"], operation["args"]])


def literal_invocation(node):
    assert isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords
    return node.func.id, [ast.literal_eval(arg) for arg in node.args]


SEMANTIC_REVIEW = {
    "eval_pricing__v2_large_member_order": "2 units at 25000 cents, member=True, checkout integer.",
    "eval_pricing__v2_negative_unit_price": "2 units at -1 cent, member=True, receipt object.",
    "eval_authorization__v2_revoked_admin": "root/b2/admin/write, scope document:write, times 0/10, revoked=True.",
    "eval_authorization__v2_owner_case_mismatch": "U9 and u9 retain distinct case; member/read, times 1000/1100, revoked=False.",
    "eval_routing__v2_priority_not_fastest": "User Z, exact padded path; east up/149 and west up/1; normal route.",
    "eval_routing__v2_retry_without_backend": "User xy, /status, retry 1; both regions down with zero recorded latency.",
    "eval_inventory__v2_enough_stock": "Physical 25, held 10, request 11, no partial, now 500.",
    "eval_inventory__v2_below_safety_reserve": "Physical 4, held 2, request 3, partial allowed, now 0.",
    "eval_cache__v2_default_public_lifetime": "Blank tenant, padded Weekly View, page=3/trace=hidden, None TTL, public, now 120.",
    "eval_cache__v2_negative_private_lifetime": "TEAM/Chart/q=ok, TTL -10, private, now 77.",
    "eval_schedules__v2_next_week_opening": "Day 7, earliest 530, duration 20, no busy intervals; appointment object.",
    "eval_schedules__v2_overlong_duration": "Day 3, earliest 560, duration 181, no busy intervals; integer start.",
}


def audit_questions(base, out):
    source = base / "dataset"
    tasks = read_json(out / "holdout/eval_tasks.json")
    gold_rows = read_json(out / "holdout/gold_validation.json")
    manifest = read_json(out / "holdout/manifest.json")
    old_tasks = read_json(source / "eval_tasks.json")
    old_gold = read_json(source / "gold_validation.json")
    assert len(tasks) == len(gold_rows) == 48
    assert len({t["id"] for t in tasks}) == len({t["question"] for t in tasks}) == 48
    assert not ({t["id"] for t in tasks} & {t["id"] for t in old_tasks})
    assert not ({t["question"].strip() for t in tasks} & {t["question"].strip() for t in old_tasks})
    gold = {g["id"]: g for g in gold_rows}
    assert set(gold) == {t["id"] for t in tasks}
    projects = {t["project"] for t in tasks}
    assert len(projects) == 6 and projects == {t["project"] for t in old_tasks}
    expected_categories = Counter(single_function=1, cross_file=2, boundary=1, semantic=2, change_impact=1, architecture=1)
    old_calls = set()
    for g in old_gold:
        project = g["id"].split("__")[0]
        if project not in projects:
            continue
        calls = [g["call"]] if g["kind"] == "execution" else g.get("probes", [])
        old_calls.update(invocation_signature(project, c) for c in calls)
    new_calls, records = set(), []
    literal_count, impact_text_count, semantic_count = 0, 0, 0
    for project in sorted(projects):
        root = source / "projects" / project
        graph, modules = independent_graph(root)
        actual_hashes = {p.relative_to(root).as_posix(): file_sha(p) for p in root.glob("*.py")}
        assert manifest["source_hashes"][project] == actual_hashes
        asset = read_json(base / "assets" / f"{project}.json")
        assert asset["source_sha256"] == actual_hashes
        source_ids = set(asset["nodes"])
        project_tasks = [t for t in tasks if t["project"] == project]
        assert Counter(t["category"] for t in project_tasks) == expected_categories
        for t in project_tasks:
            assert all(key in t for key in ("id", "project", "category", "question", "expected", "target_uri", "required_uris"))
            assert t["target_uri"] in source_ids and set(t["required_uris"]) <= source_ids
            g = gold[t["id"]]
            calls = []
            if g["kind"] == "execution":
                calls = [g["call"]]
                answer = execution(root, calls)[0]
                if t["category"] != "semantic":
                    match = re.fullmatch(r"What does (.+) return\?", t["question"])
                    assert match, t["id"]
                    parsed = literal_invocation(ast.parse(match.group(1), mode="eval").body)
                    assert exact_equal(list(parsed), [g["call"]["function"], g["call"]["args"]]), t["id"]
                    literal_count += 1
                else:
                    assert t["id"] in SEMANTIC_REVIEW
                    semantic_count += 1
            elif g["kind"] == "impact":
                calls = g["probes"]
                before = execution(root, calls)
                after = execution(root, calls, g["override"])
                answer = sorted(c["function"] for c, a, b in zip(calls, before, after) if not exact_equal(a, b))
                assert exact_equal(before, g["before"]) and exact_equal(after, g["after"]), t["id"]
                match = re.fullmatch(
                    r"If policy\.(\w+) changes from (.+?) to (.+?) before the program is loaded, which exact calls change their return values: (.+)\? Return a sorted list of changed function names\.",
                    t["question"],
                )
                assert match, t["id"]
                constant, old, new, invocations = match.groups()
                node = next(n for n in modules["policy"].body if isinstance(n, ast.Assign) and any(isinstance(x, ast.Name) and x.id == constant for x in n.targets))
                assert exact_equal(ast.literal_eval(node.value), ast.literal_eval(old))
                assert exact_equal(ast.literal_eval(new), g["override"]["value"])
                assert constant == g["override"]["name"]
                sequence = ast.parse("[" + invocations + "]", mode="eval").body
                textual_calls = [literal_invocation(n) for n in sequence.elts]
                assert exact_equal(textual_calls, [(c["function"], c["args"]) for c in calls]), t["id"]
                impact_text_count += 1
            elif g["kind"] == "architecture":
                assert g["mode"] == "transitive"
                match = re.match(r"Starting at (\w+),", t["question"])
                assert match and match.group(1) == g["function"] and "including indirect callees" in t["question"]
                answer = reachable_names(graph, (g["module"], g["function"]))
            else:
                raise AssertionError(g["kind"])
            assert exact_equal(answer, g["expected"]) and exact_equal(answer, t["expected"]), t["id"]
            if t["category"] in ("architecture", "change_impact"):
                assert isinstance(answer, list) and answer == sorted(set(answer))
            for c in calls:
                signature = invocation_signature(project, c)
                assert signature not in old_calls and signature not in new_calls, t["id"]
                new_calls.add(signature)
            records.append({
                "id": t["id"], "category": t["category"], "gold_recomputed": True,
                "question_call_checked": t["category"] != "semantic",
                "semantic_review": SEMANTIC_REVIEW.get(t["id"]),
                "actual_answer": answer,
            })
    assert literal_count == 24 and impact_text_count == 6 and semantic_count == 12
    assert len(new_calls) == 54
    return {
        "task_count": 48, "projects": 6, "unique_new_executable_inputs": len(new_calls),
        "exact_old_question_overlaps": 0, "exact_old_input_overlaps": 0,
        "literal_question_calls_verified": literal_count, "impact_question_probes_verified": impact_text_count,
        "semantic_paraphrases_reviewed": semantic_count, "all_gold_verified": True,
        "records": records,
        "scope": "New fixed questions on the same six known source projects; no claim of independent-project holdout.",
    }, tasks


HEADER = re.compile(r"^# (?:Code [^\n]+|Function summary [^\n]+|File summary [^\n]+|Project summary)\n", re.MULTILINE)


def check_actual_compaction(asset, chosen, original_context=None):
    """Parse the emitted string independently; do not trust its payload hashes."""
    lookup = {n["id"]: n for n in asset["raw"] + asset["summaries"]}
    expected_source, expected_imports, expected_summaries = {}, {}, {}
    expected_headers = {}
    for selection in chosen:
        item = lookup[selection["id"]]
        if item["level"] == 0:
            fragments = []
            for source_id in item["source_uris"]:
                n = asset["nodes"][source_id]
                fragments.append(
                    f"### {source_id} lines {n['start']}-{n['end']}\n{n['imports']}\n{n['source']}"
                )
                expected_source[f"# Code {n['path']}::{n['name']}\n"] = n["source"]
                expected_imports[n["path"]] = n["imports"]
            assert item["text"] == "\n\n".join(fragments)
        else:
            full_prefix = "### " + item["id"] + "\n"
            assert item["text"].startswith(full_prefix)
            body = item["text"][len(full_prefix):]
            if item["level"] == 1:
                label = item["id"].removeprefix("summary:leaf:memory://symbol/")
                header = f"# Function summary {label}\n"
            elif item["level"] == 2:
                header = f"# File summary {item['path']}\n"
            else:
                header = "# Project summary\n"
            assert header not in expected_headers or expected_headers[header] == item["id"]
            expected_headers[header] = item["id"]
            expected_summaries[header] = body
    original = "\n\n".join(lookup[s["id"]]["text"] for s in chosen)
    if original_context is not None:
        assert original_context == original
    compact, claims = harness.compact_selected(asset, chosen)
    matches = list(HEADER.finditer(compact))
    assert not compact or matches and matches[0].start() == 0
    actual_source, actual_summaries, imports_seen = {}, {}, {}
    for i, match in enumerate(matches):
        header = match.group(0)
        end = matches[i + 1].start() if i + 1 < len(matches) else len(compact)
        body = compact[match.end():end]
        if i + 1 < len(matches):
            assert body.endswith("\n\n")
            body = body[:-2]
        if header.startswith("# Code "):
            assert header in expected_source and header not in actual_source
            source = expected_source[header]
            assert body.endswith(source), f"Actual emitted code differs: {header}"
            prefix = body[:-len(source)] if source else body
            path = header.removeprefix("# Code ").split("::")[0]
            if prefix:
                assert path not in imports_seen
                assert prefix == expected_imports[path] + "\n"
                imports_seen[path] = expected_imports[path]
            actual_source[header] = source
        else:
            assert header in expected_summaries and header not in actual_summaries
            assert body == expected_summaries[header], f"Actual emitted summary differs: {header}"
            actual_summaries[header] = body
    assert actual_source == expected_source and actual_summaries == expected_summaries
    assert imports_seen == {path: body for path, body in expected_imports.items() if body}
    assert claims["payload_preserved"] and claims["selected_payload_sha256"] == claims["emitted_payload_sha256"]
    return {
        "original_chars": len(original), "compacted_chars": len(compact),
        "actual_source_bodies_checked": len(actual_source), "actual_summary_bodies_checked": len(actual_summaries),
        "actual_import_blocks_checked": len(imports_seen), "actual_string_preservation_passed": True,
    }


def audit_compaction(base):
    assets = {p.stem: read_json(p) for p in (base / "assets").glob("*.json")}
    # Check the original source text backing every node, independently of URI provenance.
    for project, asset in assets.items():
        root = base / "dataset/projects" / project
        for n in asset["nodes"].values():
            text = (root / n["path"]).read_text()
            tree = ast.parse(text)
            source = "\n".join(text.splitlines()[n["start"] - 1:n["end"]])
            imports = "\n".join(
                ast.get_source_segment(text, node) for node in tree.body
                if isinstance(node, (ast.Import, ast.ImportFrom))
            )
            assert n["source"] == source and n["imports"] == imports
    selected = [r for r in read_rows(base / "results_eval_main.jsonl") if r["arm"] == "RH"]
    assert len(selected) == 144
    records = [
        {"task_id": r["task_id"], "repeat": r["repeat"], **check_actual_compaction(
            assets[r["project"]], r["chosen"], r["context"]
        )} for r in selected
    ]
    singleton_checks, all_item_checks = 0, 0
    for asset in assets.values():
        items = asset["raw"] + asset["summaries"]
        for item in items:
            check_actual_compaction(asset, [{"id": item["id"]}])
            singleton_checks += 1
        # Covers all bodies, mixed levels, overlaps, and reverse first-import order.
        for order in (items, list(reversed(items))):
            check_actual_compaction(asset, [{"id": item["id"]} for item in order])
            all_item_checks += 1
    return {
        "old_RH_rows_checked": len(records), "old_unique_questions_checked": len({r["task_id"] for r in selected}),
        "every_item_singleton_checks": singleton_checks, "all_item_forward_reverse_checks": all_item_checks,
        "actual_code_summary_import_strings_preserved": True,
        "records": records,
        "limitations": [
            "No tokenizer or model calls: the final Qwen token cap and new-question packed selections must still be checked by the runner.",
            "Every actual old RH selection and all asset payloads are checked; new selections are not yet observed.",
            "Metadata, repetition, source presentation, and where imports appear change. Equal unique payload does not guarantee equal model answers.",
        ],
    }


def audit_schedule(tasks):
    evidence = {}
    for name, repeats, offset in (("new", 3, 0), ("old", 1, 100)):
        plan = harness.schedule(tasks, repeats, harness.CONFIG["order_seed"] + offset)
        identities = [(r["task_id"], r["repeat"], r["arm"]) for r in plan]
        expected = {(t["id"], repeat, arm) for t in tasks for repeat in range(repeats) for arm in ("A", "RH", "C")}
        assert len(identities) == len(set(identities)) and set(identities) == expected
        by_repeat = defaultdict(Counter)
        for i in range(0, len(plan), 3):
            block = plan[i:i + 3]
            assert len({(r["task_id"], r["repeat"]) for r in block}) == 1
            order = tuple(r["arm"] for r in block)
            assert set(order) == {"A", "RH", "C"}
            by_repeat[block[0]["repeat"]][order] += 1
        assert all(len(c) == 6 and set(c.values()) == {8} for c in by_repeat.values())
        evidence[name] = {"rows": len(plan), "each_arm_permutation_per_repeat": 8, "task_repeat_blocks_complete": True}
    return evidence


def audit(base, out):
    before = {
        "experiment_v2_sha256": file_sha(Path(harness.__file__)),
        "experiment_v1_sha256": file_sha(Path(harness.v1.__file__)),
        "new_tasks_sha256": file_sha(out / "holdout/eval_tasks.json"),
        "new_gold_sha256": file_sha(out / "holdout/gold_validation.json"),
        "new_manifest_sha256": file_sha(out / "holdout/manifest.json"),
    }
    question_audit, tasks = audit_questions(base, out)
    compaction = audit_compaction(base)
    schedule = audit_schedule(tasks)
    assert before["experiment_v2_sha256"] == file_sha(Path(harness.__file__)), "Harness changed during preflight; rerun after edits finish."
    assert before["new_tasks_sha256"] == file_sha(out / "holdout/eval_tasks.json")
    result = {
        "status": "passed", "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_calls": 0, "http_calls": 0, "original_evidence_modified": False,
        "audited_hashes": before, "questions": question_audit,
        "compaction": compaction, "schedule": schedule,
        "scope": "Independent offline data/gold and actual emitted-string checks. No prediction of speed or accuracy.",
    }
    out.mkdir(parents=True, exist_ok=True)
    destination = out / "preflight_independent.json"
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=harness.BASE)
    parser.add_argument("--out", type=Path, default=harness.OUT)
    args = parser.parse_args()
    result = audit(args.base.resolve(), args.out.resolve())
    print(json.dumps({
        "status": result["status"], "questions": result["questions"]["task_count"],
        "old_RH_selections": result["compaction"]["old_RH_rows_checked"],
        "all_item_singletons": result["compaction"]["every_item_singleton_checks"],
        "all_item_orders": result["compaction"]["all_item_forward_reverse_checks"],
        "schedule": result["schedule"], "audited_hashes": result["audited_hashes"],
    }, ensure_ascii=False, indent=2))

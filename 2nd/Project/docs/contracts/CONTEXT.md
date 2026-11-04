# Context Contracts (Task 4.2)

Schema: `contracts/context/context.schema.json`. Fixtures: `contracts/fixtures/context/`.

## Definitions

| Name | Purpose |
|---|---|
| `ContextPlan` | Result of context selection: selected candidates, fragments, omissions, budget |
| `ContextCandidate` | One candidate with score, explicit flag and estimated tokens |
| `ContextFragment` | Content actually included, with its token count |
| `ContextOmission` | A candidate left out, with a reason |
| `ContextBudget` | Budget, used tokens and the token count mode |

`ref` reuses `ContextRef` from `contracts/api/run.schema.json` (symbol or pointer).
`count_mode` reuses `CountMode` from `contracts/common/token-count.schema.json`.

## Invariants not enforced by JSON Schema

Producers (tasks 4.7 and 4.8) must guarantee these. Consumers may rely on them.

1. `budget.used_tokens <= budget.budget_tokens`.
2. The sum of `fragments[].token_count` equals `budget.used_tokens`.
3. A `candidate_id` appears in at most one of `selected` and `omitted`.
4. Every fragment's `candidate_id` appears in `selected`.
5. Explicit (`explicit: true`) candidates are never omitted silently; they are either selected or omitted with a reason.

## Omission reasons

The minimal set is `no_match`, `stale`, `unauthorized`, `over_budget`.
Task 4.7 may extend it. A change must update the schema, the fixtures and this file together.

## Count mode

Only `provider_estimate` is realistic for planning with the 3.1 model, because no exact local tokenizer exists.

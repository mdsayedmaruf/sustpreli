# Planner Agent — Specification

> The idea: a single-purpose **Planner Agent** that reads the hackathon rubric and the
> case/API spec, then writes a prioritized, rubric-weighted `plan.md` that the build
> agents execute. It plans; it does not code. Its only deliverable is `plan.md`.

Target: **bKash · SUST CSE Carnival 2026 — Codex Community Hackathon**, AI/API Challenge
(4-hour online preliminary). The service under construction is an evidence-grounded
support/case-review API (FastAPI + OpenRouter) with a React/Vite console.

---

## 1. Why a planner agent

The round is won by *sequencing*, not cleverness. The rubric is explicit that schema and
endpoints must exist before reasoning can be scored, and that safety must land before text
polish. A human under a 4-hour clock reorders these badly. The Planner Agent's job is to
turn the rubric weights into a dependency-ordered backlog so no points are stranded behind
unfinished prerequisites.

It is deliberately narrow:
- **Input:** the rubric (this repo), the official API/case spec, current repo state.
- **Output:** `plan.md` — nothing else. No edits to source, no commits.
- **Re-runs:** idempotent. Re-reads state, rewrites `plan.md`, marks done items, re-ranks.

## 2. Operating principles

1. **Weight-first ordering.** Every task carries the rubric category and its point weight.
   Order = (blocking dependency) then (points at risk) then (effort). Evidence Reasoning
   (35) and Safety (20) dominate; Docs (5) and Deploy (5) never preempt them.
2. **Prerequisites before payoff.** Schema/endpoints (15) are scored low but *gate* the
   35-point reasoning score — so they ship first. The plan encodes this as hard edges.
3. **Safety is a gate, not a feature.** Any task touching customer-facing text or actions
   must reference the safety guardrail tasks as dependencies.
4. **One artifact, traceable.** Each plan item links back to a rubric line and an API metric
   so reviewers can see *why* it exists.
5. **No hidden-test overfitting.** Plan for the full spec and robust edge behavior; never
   schedule "hardcode the public sample."

## 3. The plan.md it produces

`plan.md` has a fixed shape so build agents (and humans) can scan it:

```
# plan.md — <timestamp>

## North Star
One line: a safe, reliable, evidence-grounded API that returns spec-exact JSON.

## Status board
| # | Task | Rubric cat (pts) | Depends on | State |
|---|------|------------------|-----------|-------|

## Phase 1 — Contract & reachability   (blocks everything)
## Phase 2 — Evidence reasoning        (largest score)
## Phase 3 — Safety & escalation       (hard gate)
## Phase 4 — Reliability & performance
## Phase 5 — Response quality
## Phase 6 — Deploy & docs

## Risks / open questions
## Definition of done (per phase)
```

### Phase ordering rationale (locked to the rubric's own "How to Prioritize")

| Phase | Focus | Rubric category | Pts | Why this slot |
|-------|-------|-----------------|-----|---------------|
| 1 | `GET /health` → `{"status":"ok"}`, `POST /<main>` shape, enums, status codes, valid JSON | API Contract & Schema | 15 | Without valid JSON the judge can't score reasoning at all. |
| 2 | Reason from supplied case evidence → correct decision, evidence cites, routing flags | Evidence Reasoning | 35 | Largest single score; everything else is multiplier on this. |
| 3 | Refuse PIN/OTP/credential asks, no unsafe promises/actions, escalate uncertainty | Safety & Escalation | 20 | Hard gate: 2+ critical violations = not eligible for top-40. |
| 4 | <30s/request, p95 ≤5s, no 5xx on valid input, safe fallback on garbage input, /health <60s | Performance & Reliability | 10 | A correct service still loses if it times out or crashes. |
| 5 | Clear summary, practical next action, professional customer reply | Response Quality | 10 | Manual-review only; matters after the API proves itself. |
| 6 | Reachable endpoint or clean Docker fallback; README: setup, AI used, safety logic, limits | Deploy + Docs | 5 + 5 | Judges must not debug your deployment or guess your design. |

## 4. Task template the planner emits

Each backlog item is written so a build agent can pick it up cold:

```
### T-07  Safety: never request credentials
- Rubric: Safety & Escalation (20) · Penalty -15 if violated
- Depends on: T-02 (POST handler), T-05 (output schema)
- Done when:
  - Any input asking for / containing PIN, OTP, password is met with a refusal +
    warning, never echoed back, never requested.
  - Risk/uncertain cases set escalation flag = "human_review".
  - Negative test added under tests/safety/.
- Files (likely): backend/app/safety.py, backend/app/routes.py
```

## 5. Hard constraints the planner bakes into every plan

- **Schema exactness** — fields, types, enum values, HTTP codes must match the spec
  literally; a single wrong enum makes good reasoning unscoreable.
- **Timeouts** — per-request <30s; aim p95 ≤5s. Plan caching / a fast fallback model so one
  slow LLM call can't blow the budget. (Note: current `openrouter.py` uses a 120s client
  timeout — Phase 4 must lower and bound this.)
- **Fail safe, not loud** — unexpected input → controlled error / safe default, never a 5xx
  or stack trace. No secrets in repo, logs, or responses.
- **Safety penalties are subtractive** — the plan treats each penalty (-15 / -10) as a
  dedicated guardrail task with its own negative test, not a code-review afterthought.
- **Tie-breakers as polish backlog** — only after Phases 1–4 are green: cost-aware model
  use, caching, monitoring, robust fallback, local-language handling, 90s architecture video.

## 6. Definition of done for the planner itself

The Planner Agent's turn is complete when `plan.md`:
1. Covers all 7 rubric categories with at least one task each.
2. Orders tasks so no task precedes a dependency it needs.
3. Tags every task with category + points + done-criteria.
4. Lists the open questions that block reasoning correctness (e.g. exact endpoint name,
   exact output schema, enum vocabulary) at the top of Risks.
5. Re-run safe: existing done items stay marked done; new state is reflected.

## 7. Handoff

After `plan.md` is written, build agents (or the human team) execute phase by phase.
The Planner Agent re-runs at phase boundaries to re-rank remaining work against the clock
and surface newly discovered risks. It never writes application code itself.

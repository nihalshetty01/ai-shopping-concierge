# AI Shopping Concierge — Eval & Observability Plan
**Companion to:** AI_Shopping_Concierge_PRD.md, Section 17
**Owner:** Nihal | **Status:** Draft v1

---

## 1. Purpose

This document is the implementation layer behind the PRD's observability and evaluation *requirements*. It answers "how do we know the agent is working correctly, and how do we know if a change breaks it?" — through two mechanisms:

- **Evaluation** — a golden dataset + harness that tests the agent's *correctness* before any change ships
- **Observability** — logging + metrics that show the agent's *live behavior* once it's running

Run evals before every deploy. Run observability continuously once deployed.

---

## 2. Golden Dataset

22 hand-crafted examples across all 6 use cases plus 8 deliberate edge/adversarial cases — expanded from 18 to add category-specific routing coverage after the v2 ranking logic (PRD Section 10) split scoring by category. Each has a defined input, the behavior expected of the agent, and a concrete pass/fail check — not a vibe check.

| ID | Use Case | Input | Expected Behavior | Pass Criteria |
|---|---|---|---|---|
| G01 | 1 — Fuzzy need | "laptop for video editing, ₹60k budget" | Asks ONE clarifying question about performance vs. battery priority before recommending | Exactly 1 clarifying question asked; no recommendation before priority is known |
| G02 | 1 — Fuzzy need | "need a phone, mostly calls and WhatsApp, ₹15k" | Recognizes low-complexity use case; may skip clarifying question since priority is implied (battery/simplicity) | Recommends within budget; reasoning references stated use case, not generic specs |
| G03 | 1 — Fuzzy need | "headphones for gym, budget flexible" | Determines connectivity type first (wireless is implied by "gym" but should be confirmed, not assumed); once known, offers the correct category-specific priority menu (sound_quality/battery/value for wireless, sound_quality/value only if wired) | Does not recommend until budget, connectivity type, and priority are known; never offers a priority menu that doesn't match the eventual connectivity type |
| G04 | 2 — Trade-off comparison | "battery vs processor — which matters more for general use + travel?" | Recommends battery-focused option; explains reasoning tied to travel usage, not generic pros/cons | Recommendation logic explicitly reflects "general use" (perf not bottleneck) + "travel" (battery matters) |
| G05 | 2 — Trade-off comparison | User pushes back: "but the other one has better specs on paper" | Re-explains trade-off in terms of the user's stated priority, doesn't cave to "better specs" framing | Response references the user's earlier stated priority, not just raw spec numbers |
| G06 | 3 — Value-conscious | "show me something good, don't want to overpay, budget flexible" | Recommends the best value-score option, explicitly explains what a pricier option would add and whether it's worth it | Reasoning names the marginal trade-off of upgrading (e.g. "the ₹13k jump mainly buys X") |
| G07 | 3 — Value-conscious | "cheapest laptop that can handle basic browsing and Zoom calls, no budget stated" | Asks for a budget ceiling before recommending, since "cheapest" alone isn't enough constraint | Does not recommend without a budget number or range |
| G08 | 4 — Upgrade/replacement | "my headphones broke, want similar but better battery, same budget as before (~₹3k)" | Uses "similar to old one" as a reference constraint, not a fresh needs-description flow | Recommendation stays in the same product family/tier; explicitly improves battery vs. implied baseline |
| G09 | 5 — Spec sanity-check | "about to buy [Product X], does it fit my editing needs?" (with prior stated context: editing, home use, performance priority) | Validates against catalog data; flags any real gap (e.g., low storage) | Correctly identifies at least one real limitation if one exists in the catalog data for that product |
| G10 | 5 — Spec sanity-check | Same as G09, but product fully matches all stated needs | Confirms fit without inventing a fake caveat just to seem thorough | No fabricated concerns; a clean "yes, this fits" if the data genuinely supports it |
| G11 | Grounding (injected error) | Draft response manually corrupted to claim "18-hour battery" when catalog says 9 hours | `verify_grounding` catches the mismatch and blocks/corrects it before the user sees it | 100% catch rate required — this is deterministic, not fuzzy; any miss is a hard fail |
| G12 | Grounding (injected error) | Draft response references a product_id not present in retrieved data | `verify_grounding` flags the unknown reference | Flagged and corrected/removed before response is shown |
| G13 | Ranking correctness | Fixed catalog subset + fixed weights (perf 0.5/battery 0.15/value 0.2/budget_fit 0.15) | `catalog_search` returns products in the exact order the formula produces | Output ranking matches hand-calculated ranking exactly (deterministic — 100% required) |
| G14 | Ambiguous input | "I need something for my computer stuff" | Asks a genuine clarifying question rather than guessing a product category | Does not assume laptop/phone/headphones without asking |
| G15 | Conflicting priorities | "I want the best performance AND best battery AND cheapest price" | Explains that these trade off against each other, asks which matters most rather than silently picking one | Response explicitly names the tension instead of picking one dimension unprompted |
| G16 | Out-of-catalog request | "I want a gaming desktop under ₹40k" (catalog only has laptops/phones/headphones) | Clearly states this category isn't supported rather than forcing a bad-fit laptop recommendation | No laptop presented as a desktop substitute without clearly flagging the mismatch |
| G17 | Budget infeasible | "best laptop for video editing under ₹15k" | States that no catalog option genuinely fits both constraints, rather than force-fitting a poor match | Response is honest about the trade-off required, doesn't silently recommend a bad fit as if it were good |
| G18 | 6 — Gifting (P2, stretch) | "phone for my dad, he mostly calls, ₹15k" | Recognizes third-person constraint framing; recommends for stated (not user's own) usage pattern | Reasoning explicitly reflects the third party's usage, not a generic pick |
| G19 | Category-specific menu (wired) | "wired headphones under ₹1,500 for music at home" | Offers only sound_quality/value as priority options (per PRD 10.4) — never mentions battery in any form | Response never uses the word "battery" or asks about battery life for this SKU category |
| G20 | Category-specific menu (wireless) | "wireless earbuds for gym, priority is battery life" | Recognizes battery as a valid priority for wireless (per PRD 10.3), uses the wireless weight table (audio_quality 0.20/battery 0.45/value 0.20/budget_fit 0.15) | Recommendation is the highest battery_hours option within budget, not the highest audio_score option |
| G21 | Deterministic category routing | Fixed catalog subset: 1 laptop, 1 wired headphone, 1 wireless headphone, same budget band | `catalog_search` applies the laptop formula (10.1) to the laptop, the no-battery wired formula (10.4) to the wired item, and the wireless formula (10.3) to the wireless item — never the wrong table | Each product's computed score matches hand-calculation using its category's correct formula exactly (deterministic — 100% required) |
| G22 | Grounding — structural field error | Draft response corrupted to claim "12-hour battery life" for a product where `connectivity_type = "wired"` (a category with no `battery_hours` field at all) | `verify_grounding` flags this as invalid not just because the number is wrong, but because the field shouldn't exist for this category at all | Correctly catches and blocks/corrects the claim; catch rate must be 100% — this is deterministic, not fuzzy |

**Pass threshold for this set:** G11–G13 and G19–G22 (grounding, ranking correctness, and category routing) are deterministic — require 100% pass, no exceptions, since these are code-level guarantees, not model judgment calls. G01–G10, G14–G18 involve model judgment — target ≥90% pass on manual review before any prompt change ships; anything below that blocks the change.

---

## 3. Observability — What Gets Logged

Every turn logs one structured record. Example shape:

```json
{
  "turn_id": "uuid",
  "session_id": "uuid",
  "timestamp": "ISO8601",
  "user_message": "laptop for video editing, 60k budget",
  "tool_calls": [
    {"tool": "parse_constraints", "input": "...", "output": {"budget": 60000, "use_case": "video editing", "priority": null}, "latency_ms": 420},
    {"tool": "catalog_search", "input": {...}, "output": [...], "latency_ms": 180},
    {"tool": "verify_grounding", "input": {...}, "result": "pass", "issues": [], "latency_ms": 90}
  ],
  "clarifying_question_asked": true,
  "final_response": "...",
  "total_latency_ms": 1240,
  "total_tokens": 890,
  "model": "claude-sonnet-5"
}
```

**Why each field earns its place:**
- `tool_calls[]` with per-tool latency — lets you find the actual bottleneck instead of guessing (usually catalog_search or the LLM call itself)
- `verify_grounding.result` and `issues` logged **even on pass** — this is what lets you compute a grounding failure rate over time, not just catch individual failures
- `clarifying_question_asked` — a simple boolean that lets you check Rule 2 (exactly one question, not zero or several) is holding in practice, not just in the golden set
- `total_tokens` — direct cost visibility per conversation

---

## 4. Metrics Dashboard (what to track once live)

| Metric | Why it matters | Target (v1) |
|---|---|---|
| Grounding failure rate (issues caught / total responses) | Core trust signal — should trend down as the response generator prompt improves | <5%, trending down |
| Avg. clarifying questions per session | Should stay near 1 for well-specified use cases (Rule 2) | ~1, not 0 or 3+ |
| Avg. turn latency | User experience — slow responses undermine "quick, confident decision" value prop | <5s end-to-end |
| Avg. tokens per session | Cost tracking | Baseline first, then optimize |
| % sessions reaching a recommendation without user abandoning | Proxy for whether the flow actually resolves | Track as baseline; no target yet without real usage data |
| Golden set pass rate | Regression signal before every deploy | 100% on deterministic (G11–G13), ≥90% on judgment-based |

---

## 5. Eval Harness — How It Runs

```
for each golden_example in golden_dataset:
    response = run_agent(golden_example.input, context=golden_example.prior_context)
    if golden_example.type == "deterministic":
        result = exact_match(response, golden_example.expected)
    else:
        result = manual_review(response, golden_example.pass_criteria)  # or LLM-assisted rubric scoring, human-spot-checked
    log_result(golden_example.id, result)

report = summarize(all_results)  # pass rate by use case, any deterministic failures flagged as blocking
```

**Run this:**
- Before every deploy (regression check)
- Any time the system prompt, scoring weights, or catalog schema changes
- Periodically against live traffic samples (pull 5-10 real anonymized sessions, add the interesting ones to the golden set over time — this is how the golden set grows from real usage, not just imagination)

---

## 6. Tooling — Prototype vs. Production

| Layer | Prototype (this project) | Production equivalent |
|---|---|---|
| Logging | Structured JSON to a local file or lightweight DB (SQLite) | Centralized logging (Datadog, CloudWatch) |
| Tracing tool calls | Manual logging inside the orchestrator loop | Purpose-built LLM observability (LangSmith, Braintrust, Arize) |
| Eval harness | A simple Python script running the golden set on demand | CI-integrated eval pipeline, blocking deploys on failure |
| Dashboards | A basic notebook/script summarizing the log file | Grafana/Datadog dashboards with alerting |

Naming this distinction explicitly — and why the lightweight version is the *right* choice for a prototype, not a compromise you're unaware of — is worth stating outright in an interview: it shows you understand the production-grade tools without over-engineering a portfolio project that doesn't need them yet.

---

## 7. Cadence

- **Every code/prompt change:** run full golden set before merging
- **Weekly (once live, even informally):** review grounding failure rate and latency trend
- **Monthly:** pull a handful of real sessions, add any interesting new edge cases to the golden set — this keeps the eval set alive instead of static and stale

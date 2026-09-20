# AuraConcierge — AI Shopping Concierge

An AI-powered shopping assistant for electronics (laptops, phones, headphones) that turns fuzzy shopper needs ("something for video editing, ₹60k budget") into grounded, ranked, explainable recommendations — with a hard-coded gate that field-checks every claim against real catalog data before it's shown to the user.

Built as a portfolio project to demonstrate end-to-end AI product development: problem validation, PRD writing, agentic architecture, evaluation design, and iterative debugging against a real LLM.

---

## What this demonstrates

- **Category-aware agentic reasoning** — different scoring logic for laptops, phones, wireless headphones, and wired headphones (a wired headphone literally has no battery dimension — the system knows this structurally, not just in a prompt instruction)
- **A real trust/grounding layer** — every response is field-matched against retrieved product data before the user sees it. Unsupported claims trigger an automatic correction loop, not a warning label
- **Deterministic tools + LLM judgment, cleanly separated** — constraint parsing and product ranking are pure, tested Python functions; only the reasoning and language generation touch the model
- **A real evaluation harness** — a 24-example golden dataset with deterministic (100%-required) and judgment-based (≥90%-required) test tiers
- **Honest scope boundaries** — no fabricated inventory counts, no invented sub-ratings, no non-functional features pretending to work

---

## Architecture

```
User message
     │
     ▼
Frontend (HTML/Tailwind/vanilla JS)  ──fetch──▶  FastAPI backend (api/server.py)
     │                                                    │
     │  Shopping Buddy chat panel                         ▼
     │  Product detail views                    Orchestrator (agent/orchestrator.py)
     │  Demo Mode (scripted, zero-cost)                    │
     │                                        ┌─────────────┼─────────────┐
     │                                        ▼             ▼             ▼
     │                              parse_constraints  catalog_search  verify_grounding
     │                                 (regex, free)   (weighted rank)  (hard gate, free)
     │                                        │             │             │
     └────────────────────────────────────────┴─────────────┴─────────────┘
                                          catalog.json (55 real products)
```

**Why this split:** `parse_constraints` and `catalog_search` are deterministic, unit-tested Python — no LLM call needed, so they're free to run and trivial to debug. Only the orchestrator's reasoning (deciding what to ask, how to explain a trade-off) touches Claude. `verify_grounding` runs in code as a hard gate the model cannot skip — not a tool it chooses to call.

---

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Orchestrator model | Claude Sonnet (native tool-use) | System prompt and tool-calling design built and tested against Sonnet specifically |
| Backend | FastAPI | Thin wrapper around the Orchestrator; two read-only endpoints for catalog browsing |
| Frontend | HTML + Tailwind (CDN) + vanilla JS | No build step; full design control that a component framework like Streamlit couldn't provide |
| Data | Hand-curated JSON catalog | 55 real Amazon India products, real PassMark benchmark scores, real review ratings |
| Testing | pytest, 233 tests | All offline — no live API calls required to verify correctness |

---

## Project structure

```
agent/
  orchestrator.py       # Tool-calling loop, system prompt, grounding gate wiring
  verify_grounding.py   # Deterministic field-matching against retrieved product data
tools/
  parse_constraints.py  # Regex-based constraint extraction (budget, category, priority)
  catalog_search.py     # Category-specific weighted scoring + ranking
api/
  server.py             # FastAPI wrapper: /chat, /products, /products/{id}
frontend/
  index.html            # Full UI: nav, hero, Shopping Buddy panel, product grid/detail
catalog/
  catalog.json           # 55 hand-curated, price-verified products
tests/                   # 233 tests covering every component above
```

---

## Setup

**Requirements:** Python 3.10+, an Anthropic API key (only needed for live chat — everything else runs free)

```bash
pip install -r requirements.txt
pip install -r api/requirements.txt

# Create a .env file in the project root:
echo "ANTHROPIC_API_KEY=your-key-here" > .env
```

**Run it:**

```bash
# Terminal 1 — backend
python -m uvicorn api.server:app --reload --port 8000

# Terminal 2 — frontend
cd frontend && python -m http.server 5500
```

Open `http://localhost:5500`. Click **Demo Mode** buttons to see the app with zero API cost, or click **Shopping Buddy** to chat live.

**Run the tests** (free, no API key required):
```bash
python -m pytest -q
```

---

## Key design decisions

**Category-specific ranking, not one formula.** Laptops/phones score on performance/battery/storage/value/budget-fit; wireless headphones swap performance for an audio-quality composite; wired headphones drop battery entirely. Passing `priority="battery"` for a wired headphone raises a `ValueError` rather than silently falling back — an explicit contract violation, not a masked one.

**A 15% budget tolerance band.** Products priced beyond budget are filtered out, not just scored down — an earlier version relied on scoring alone and it failed concretely: a ₹1.4 lakh laptop won a ₹60k "value" search because the budget-fit penalty floored at zero past ~50% overshoot. Documented in the PRD with the real before/after numbers.

**No sound-quality benchmark exists (unlike PassMark for CPUs), so headphone audio scoring leans on real aggregate review ratings** (40–60% of the composite weight) instead of guessing at a number — the same reasoning a production recommendation system would use where no clean ground truth exists.

**Grounding is code, not a prompt instruction.** `verify_grounding()` runs after every draft response, before the user sees it, checking every price/spec/GPU claim against the specific product it's attributed to (not just "does this value exist somewhere in the catalog"). Caught real false positives during live testing — including "6 hours on the buds, 21 hours with the case" being flagged incorrectly because `battery_hours` only captured the first number — fixed by falling back to the product's own retrieved name text, itself real data.

**Demo Mode's scripted content passes the same grounding check as live responses.** The pre-written example conversations aren't just eyeballed for accuracy — they're run through `verify_grounding()` against real catalog data in `tests/test_demo_mode_grounding.py`, so hardcoded text can't silently drift from what's actually in `catalog.json`.

---

## Known limitations (stated, not hidden)

- **Survey validation is thin.** Two rounds, n=10, and every fully-qualified respondent bought headphones — the laptop/phone "spec overload" framing is a hypothesis, not confirmed data. Documented in the PRD's RAID matrix.
- **No live Amazon API integration.** The catalog is a static, hand-verified snapshot — deliberately, to keep ranking/eval tests deterministic. The PRD documents the production path (Amazon's internal catalog + licensed benchmark data + indexed retrieval at scale).
- **No checkout.** The "Proceed to Buy" button is visibly disabled with an honest caption — this is a recommendation engine, not a transactional platform, by design.
- **No inventory data.** The catalog has no stock field, so none is displayed or invented — consistent with the project's core anti-fabrication principle.

---

## Related documents

- `AI_Shopping_Concierge_PRD.md` — full product requirements: vision, personas, survey findings, category-specific ranking logic, RAID matrix
- `AI_Shopping_Concierge_Eval_Observability_Plan.md` — 24-example golden dataset, logging schema, metrics, eval harness design

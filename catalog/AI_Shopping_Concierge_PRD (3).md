# PRD: AI Shopping Concierge Agent
**Owner:** Nihal | **Status:** Draft v1 | **Scope:** Portfolio prototype — Amazon Electronics

---

## 1. Vision

> Make every electronics purchase on Amazon feel like it was chosen by someone who knows exactly what you need — not searched for.

## 2. Business Goals

| Goal | Why AI recommendation moves it |
|---|---|
| Increase conversion rate in considered-purchase categories | Shoppers stuck in comparison-paralysis abandon or delay; a confident, fast recommendation shortens time-to-purchase |
| Reduce return rate in electronics | Wrong-spec purchases are a cost center (logistics, refunds, resale-as-used) |
| Reduce price-anxiety churn to competitor platforms | Shoppers unsure they got fair value quietly switch to Flipkart/others next time |
| Increase basket size (secondary) | Confident buyers are more likely to add relevant accessories |

## 3. Product Goals

1. Reduce time-to-confident-decision for electronics shoppers
2. Increase shopper trust that a recommendation is accurate and unbiased
3. Surface value-for-money reasoning, not just spec-matching, without becoming a full price-comparison tool

## 4. Problem Statement

> When buying electronics on Amazon, consumers struggle to translate their fuzzy needs (budget, use-case, priorities) into a confident purchase decision — comparing specs across scattered sources (reviews, YouTube, friends, and increasingly other platforms) — and remain unsure whether they picked the right product *and* paid a fair price for it, a hesitation that shows up regardless of how quickly the purchase itself happens.

**Validation status (v2 survey, n=10, 4 fully qualified — see Section 11.1):** Directionally supported, with one meaningful correction — "time spent" is not the reliable pain signal it was originally assumed to be; "confidence" is. The statement above has been reworded accordingly. Treat this as an early read, not confirmation — the qualified sample is still small and skewed toward one product category (headphones); the findings section states the limitations explicitly.

## 5. User Persona (hypothesis — refined post round-2 survey, see Section 11.1)

**"Comparison-Fatigued Rohan"**
- **Who:** 25–32, working professional, buys electronics 1–2x/year, tech-aware but not an expert
- **Goal:** Buy the right product for his use case without overpaying or under-speccing
- **Behavior:** Compares 2–4 products across Amazon and YouTube reviews, has no single trusted go-to source (majority pattern in survey data), and checks other platforms' prices mainly out of habit — which extends his research time more reliably than it changes his confidence
- **Pain:** Lingering doubt about *both* product fit and price even after deciding — not usually a single dominant factor
- **Success looks like:** Feeling confident he made the right call without losing a weekend to it

**Open question, not yet resolved:** all confirmed survey respondents so far bought headphones — a lower-consideration purchase than a laptop. This persona's "spec overload" framing is still a hypothesis for higher-consideration categories until laptop/phone buyers are specifically represented in the data.

## 6. Pain Points (re-ranked against v2 survey signal — see Section 11.1)

| # | Pain Point | Impact | Survey Signal (n=10, 4 fully qualified) |
|---|---|---|---|
| 1 | Fragmented research across Amazon, YouTube, forums, friends before feeling ready to decide | Effort/confidence cost, conflicting info | **Supported** — nearly everyone used 2+ sources; one respondent checked 7+ products and still used "none of these" resources |
| 2 | Hesitation is about confidence, not just specs — "did I pick right *and* pay right" | Lingering doubt even on fast purchases | **Strongly supported** — of 7 responses to this question, 4 said "both equally," 3 said "mostly product." Zero said "mostly price." |
| 3 | Checking prices across other platforms extends time spent, even when it doesn't change confidence | Comparison drags on longer than needed | **Newly strengthened** — 6 of 7 respondents said price differences delayed their decision to some degree, regardless of whether it helped or hurt their confidence |
| 4 | Price is a *contributing* factor to hesitation, not the dominant one | Confirms folding price in as a weighted input, not a pivot | **Strongly supported** — 0 of 7 respondents across both rounds said hesitation was "mostly about price" alone |
| 5 | Checking prices on other platforms doesn't reliably build confidence — effect is person-dependent | Not a clean confidence booster or eroder | **Mixed, slight lean toward "more confident"** — 3 more confident, 2 less confident, 2 no effect/didn't check |
| 6 | Post-purchase regret is driven almost entirely by product quality/fulfillment failures (damaged, defective, non-delivered) — not by picking the wrong spec | Currently outside product scope — the agent can't fix logistics or seller quality | **Strengthened, and a real concern for the product's value prop** — 4 of 6 respondents who answered had regretted a purchase; all 4 reasons given were damage/defect/non-delivery, none were spec-mismatch |
| 7 | Most shoppers have no existing trusted source for buying advice | Underserved segment — people are "figuring it out" with no consistent help | **Strengthened** — 5 of 7 respondents said they have no go-to person or source, up from a minority signal in round 1 |
| 8 (watch item) | Seller/listing authenticity concerns (e.g., "is this seller genuine") | Trust issue distinct from spec confusion | **Single mention only** — noted as an emerging theme to probe further, not yet a confirmed pain point |

**Data gap to flag explicitly:** all 4 fully-qualified respondents purchased **headphones only** — no confirmed laptop or phone purchases in the sample. The findings above are reasonably solid for headphones-type decisions; the laptop/phone use cases central to your MVP scope remain **unvalidated by real respondent data** so far.

## 7. Use Cases & Priority

| Use Case | Priority | Tests |
|---|---|---|
| 1. Fuzzy-need first-time purchase | P0 | Core need-translation + clarifying-question logic |
| 2. Trade-off-heavy comparison | P0 | Reasoning transparency |
| 3. Value-conscious purchase | P0 | Price/value weighting |
| 4. Upgrade/replacement purchase | P1 | Reference-based reasoning |
| 5. Spec sanity-check (pre-purchase) | P1 | Grounding layer as validator |
| 6. Gifting on someone's behalf | P2 (out of scope v1) | Third-person constraint handling |

## 8. User Stories

| # | Story | Priority |
|---|---|---|
| 1 | As a shopper with a fuzzy need, I want to describe my situation in plain language, so I don't need spec vocabulary upfront | P0 |
| 2 | As a shopper, I want one clarifying question when my input is ambiguous, so the recommendation fits my real use case | P0 |
| 3 | As a shopper, I want a short ranked shortlist with plain-language reasons, so I can decide quickly | P0 |
| 4 | As a shopper, I want recommendations grounded in real specs, so I can trust the suggestion | P0 |
| 5 | As a shopper, I want trade-offs explained (not a black box), so I understand why one option beats another | P1 |
| 6 | As a price-sensitive shopper, I want value-for-money factored in, so I don't feel I overpaid | P0 |
| 7 | As a shopper, I want live cross-platform price comparison | P2 — explicitly out of scope for v1; requires multi-platform data access not available for this prototype |
| 8 | As a shopper, I want a pre-purchase sanity check on what I might be missing | P1 |

## 9. System Architecture

**Pipeline:** User message → Agent orchestrator (reasoning loop) → tools (`parse_constraints`, `catalog_search`, `verify_grounding`) → Response generator → User

**Orchestrator system prompt (core rules):**
1. Never recommend until budget, use case, and priority are known — the *priority options offered* are category-specific (see Section 10.6): performance/battery/value for laptops & phones; sound_quality/battery/value for wireless headphones; sound_quality/value only for wired headphones (no battery)
2. Ask exactly ONE clarifying question if information is missing
3. Call `catalog_search` once constraints are structured
4. Call `verify_grounding` before presenting any recommendation; correct or remove unsupported claims
5. Present at most 3 ranked options with plain-language reasoning
6. Explain trade-offs in terms of the user's stated use case when asked
7. Never invent a product, price, or spec not in retrieved data

## 10. Ranking & Grounding Logic (v2 — category-specific)

**Why category-specific, not one formula:** Laptops, phones, and headphones aren't judged on the same dimensions — and within headphones, wired and wireless aren't either (a wired headphone has no battery to score). A single formula applied everywhere either scores nonsense (battery on a wired headphone) or flattens real differences (treating phone "performance" and laptop "performance" as the same kind of thing). Each category below gets its own dimension set, and each dimension that isn't a raw spec is itself a weighted composite of sub-variables — the level of explicitness a real interviewer will probe for.

**Budget handling — applies to every category below.** Every weight table below includes a *Budget Fit* dimension, but budget does two separate jobs in this design and it's worth stating both explicitly:

1. **A candidate filter, before scoring.** Products priced more than **15% above the stated budget** are dropped from the candidate set entirely.
2. **A scoring dimension, after filtering.** Everything that survives is scored on Budget Fit — `10 - (budget - price) / budget * 5` when at or under budget, `10 - (price - budget) / budget * 20` when over — so a near-miss still has to earn its place on the other dimensions.

**Why a band and not a hard cut at budget:** a shopper who says "₹60,000" will usually look at ₹64,999. Excluding near-misses outright would hide genuinely good recommendations and make the agent feel rigid rather than helpful.

**Why a band and not scoring alone:** this was the original design, and it failed in a way worth recording. Budget Fit floors at 0, so once a product is ~50% over budget, further overshoot costs it nothing — a ₹90,000 laptop and a ₹1,70,000 laptop are penalised identically. With Budget Fit weighted at only 0.15–0.20, raw specs then dominate. A `laptop / ₹60,000 / value` search returned a ₹1,40,990 Zenbook first and a ₹1,68,900 MacBook Pro third; on `performance`, all five results were over budget and the ₹59,990 options never surfaced at all. A "value" search recommending a ₹1.69 lakh laptop is the clearest possible demonstration that a soft signal was carrying a job that needed a hard one.

One useful consequence: at the band edge Budget Fit is `10 - 0.15 * 20 = 7.0`, so the floor at 0 is unreachable for any product that passes the filter. The pathology above cannot recur while the band holds.

**When nothing fits:** `catalog_search` returns an empty result rather than widening the band or force-fitting the cheapest option. The orchestrator is expected to say plainly that no catalog product meets both constraints — this is what makes the "budget infeasible" case (Eval Plan, G17) an honest answer instead of a bad recommendation presented as a good one. When a surviving candidate *is* over budget, the response must flag the overshoot in rupee terms rather than quietly listing it alongside in-budget options.

**Tolerance value:** 15% is a judgement call, not a derived number — chosen as roughly the point where a shopper stops reading a price as "about what I said." It lives in one constant (`BUDGET_TOLERANCE` in `tools/catalog_search.py`) so it can be tuned in one place. Production would learn it from real behaviour — how far over a stated budget shoppers actually click and buy — rather than fixing it globally, and would likely vary it by category and price tier.

### 10.1 Laptops

**Dimensions:** Performance (composite), Battery, Storage, Value, Budget Fit

| Priority | Performance | Battery | Storage | Value | Budget Fit |
|---|---|---|---|---|---|
| performance | 0.40 | 0.15 | 0.10 | 0.20 | 0.15 |
| battery | 0.15 | 0.40 | 0.10 | 0.20 | 0.15 |
| value | 0.20 | 0.15 | 0.10 | 0.40 | 0.15 |
| balanced (default) | 0.25 | 0.20 | 0.15 | 0.20 | 0.20 |

**Performance sub-variables (composite, must sum to 1.0):** CPU benchmark (PassMark, normalized) 0.60 · RAM capacity (normalized) 0.25 · Storage type bonus (SSD vs HDD) 0.15

### 10.2 Phones

**Dimensions:** Performance (composite), Battery, Storage, Value, Budget Fit — same top-level shape as laptops, different sub-composition.

| Priority | Performance | Battery | Storage | Value | Budget Fit |
|---|---|---|---|---|---|
| performance | 0.40 | 0.15 | 0.10 | 0.20 | 0.15 |
| battery | 0.15 | 0.40 | 0.10 | 0.20 | 0.15 |
| value | 0.20 | 0.15 | 0.10 | 0.40 | 0.15 |
| balanced (default) | 0.25 | 0.20 | 0.15 | 0.20 | 0.20 |

**Performance sub-variables:** Chipset benchmark (normalized) 0.75 · RAM capacity (normalized) 0.25. *No storage-type sub-variable* — phone storage (UFS) doesn't vary meaningfully enough across the catalog to be a differentiator the way SSD-vs-HDD is for laptops.

### 10.3 Headphones — Wireless / Bluetooth

**Dimensions:** Audio Quality (composite), Battery, Value, Budget Fit. **No "Performance" dimension exists for headphones** — there's no CPU-equivalent benchmark for sound.

| Priority | Audio Quality | Battery | Value | Budget Fit |
|---|---|---|---|---|
| sound_quality | 0.45 | 0.20 | 0.20 | 0.15 |
| battery | 0.20 | 0.45 | 0.20 | 0.15 |
| value | 0.20 | 0.20 | 0.45 | 0.15 |
| balanced (default) | 0.30 | 0.25 | 0.25 | 0.20 |

**Audio Quality sub-variables — this is the key design decision to defend:** since no objective sound-quality benchmark exists (unlike PassMark for CPUs), the composite deliberately leans on real aggregate signal instead of guessing: **Average review rating** (normalized) 0.40 · **Noise cancellation tier** (none / passive / ANC / adaptive ANC, mapped to 0–10) 0.35 · **Codec support tier** (SBC-only vs. aptX/LDAC-capable) 0.15 · **Driver size** (weak proxy, normalized) 0.10. Leaning on review rating for the largest share is an honest design choice, not a shortcut — it's the same reasoning a real recommendation system would use where no clean spec-based ground truth exists.

### 10.4 Headphones — Wired

**Dimensions:** Audio Quality (composite), Value, Budget Fit. **No Battery, no "sound_quality vs battery" priority choice** — battery doesn't exist for this category, so it's never offered as an option in the first place (see orchestrator update below).

| Priority | Audio Quality | Value | Budget Fit |
|---|---|---|---|
| sound_quality | 0.55 | 0.25 | 0.20 |
| value | 0.30 | 0.50 | 0.20 |
| balanced (default) | 0.40 | 0.35 | 0.25 |

**Audio Quality sub-variables:** **Average review rating** 0.60 · **Driver size** 0.25 · **Frequency response range available** (bonus if published) 0.15. Review rating carries even more weight here than wireless, since wired headphones have fewer differentiating specs available at all.

### 10.5 Catalog schema additions required for this design

- All: `avg_rating` (1–5), `review_count`, `warranty_months`
- Laptops/phones: `storage_gb`, `storage_type` (laptop only: "SSD" \| "HDD")
- Laptops: `graphics_type` ("integrated" \| "dedicated")
- Headphones: `connectivity_type` ("wired" \| "wireless" \| "true_wireless"), `noise_cancellation` ("none" \| "passive" \| "anc" \| "adaptive_anc"), `codec_support` (e.g. "SBC" \| "aptX" \| "LDAC"), `driver_size_mm`, `battery_hours` (wireless only — field simply omitted for wired entries, not scored as zero)

### 10.6 Orchestrator update required (ties to Section 9, Rule 1–2)

The clarifying-question logic must become category-aware: for a **wired headphone**, the agent must never ask about battery priority — that option shouldn't exist in its decision space for that product type. For **wireless headphones**, the priority options offered are sound_quality / battery / value, not performance / battery / value. This is a system prompt update (added logic, not a rewrite): the orchestrator determines category first, then selects the correct priority menu and dimension set before asking its one clarifying question.

**Data sourcing (prototype vs. production):**
- *Prototype:* ~55 hand-curated real products (real specs from Amazon listings) mapped to real PassMark CPU/chipset benchmark scores; audio quality sourced from real published review ratings
- *Production:* Would use Amazon's internal catalog data + licensed benchmark data (PassMark/Geekbench/NotebookCheck for compute; Amazon's own aggregated review data for audio) instead of manual curation

**Grounding check:** Deterministic field-matching of every claimed spec/price in the draft response against the retrieved product data (not LLM self-grading). On mismatch, issues are sent back to the orchestrator for correction before the user sees the response.

**Scaling path (catalog size vs. retrieval architecture):** At prototype scale (~55 hand-curated products), `catalog_search` does a direct in-memory scan and score — negligible latency. This is a deliberate scope choice, not a limitation to hide: production Amazon-scale retrieval (millions of listings) would never linearly scan the full catalog either — it would use an indexed retrieval layer (a search index like Elasticsearch/OpenSearch, or vector embeddings with approximate nearest-neighbor search) to narrow the catalog to a relevant few hundred candidates *before* the same scoring/ranking logic runs on them. The scoring formula itself doesn't change with scale — only the step that feeds it candidates does.

## 11. Research Method

Lightweight Mom's Test-style validation: 5–8 informal conversations + a short Google Form survey (screening + past-behavior questions on last purchase, platform/price behavior, and existing coping mechanisms). No hypothetical or solution-framed questions asked, to avoid biased responses.

### 11.1 Survey Findings — Round 2 (n=10, 4 fully qualified)

**Data quality update:** 10 total responses now. 4 respondents fully confirmed the screening criterion and completed the survey (up from 1 in round 1) — 2 additional respondents stopped correctly after answering "No" (skip logic appears fixed for new submissions), but the earlier round's unscreened partial responses remain in the dataset and are still included below for behavioral signal, clearly separated from the fully-qualified group. One respondent (Vishnu Menon) submitted twice — first answering "No," then a second time answering "Yes" and completing the survey; treated as one valid response, the "No" duplicate excluded.

**What changed from Round 1, and what held up:**
- **Price as a secondary factor, not the dominant one — now on firmer ground.** Across all 7 respondents who answered the hesitation question (both rounds combined), **zero** said hesitation was "mostly about price." This is now a well-supported basis for keeping price as a weighted input rather than pivoting scope — the strongest, most consistent finding across both rounds.
- **New finding: price-checking reliably extends decision time, even when it doesn't reduce confidence.** 6 of 7 respondents said checking other platforms' prices delayed their decision to some degree — a clearer, more actionable signal than the round-1 read, which only looked at confidence and missed this time-cost effect.
- **A more concerning finding for the product's core premise:** of the respondents who reported regretting or returning a purchase (4 of 6 who answered), **all four reasons were product quality or fulfillment failures** (damaged, defective, non-delivered) — **none were "picked the wrong spec."** This doesn't invalidate the product, but it does mean the "reduces post-purchase regret" business goal (Section 2) may have a smaller addressable slice than originally assumed — regret in this sample looks more like a seller-quality/logistics problem than a recommendation-quality problem. Worth being upfront about this if asked in an interview: your product improves *decision confidence*, not necessarily *return rates*, based on what this data shows so far.
- **A real gap worth naming directly: all 4 fully-qualified respondents bought headphones only.** No laptop or phone purchases are represented in the qualified data yet. The MVP scope (laptops, phones, headphones) is currently only evidence-backed for one of its three categories.
- **The "no trusted advice source" segment grew stronger** — 5 of 7 respondents said they have no consistent go-to person or source, reinforcing that there's a real gap this product could fill for a meaningful chunk of shoppers.
- **One new, single-mention theme:** a respondent flagged **seller/listing authenticity** as their main concern rather than product comparison itself — noted as a theme to probe in a future round, not yet a confirmed pain point.

**Recommended next step:** The confidence/price findings are solid enough to build on. Before finalizing scope, it's worth specifically recruiting a few laptop and phone buyers — right now the data disproportionately reflects headphone-buying behavior, which is a lower-consideration purchase than a laptop and may understate the "spec overload" pain point your MVP is partly designed around.

## 12. Success Metrics

| Metric | Type |
|---|---|
| % of sessions reaching a "confident pick" | Primary |
| Avg. clarifying questions needed before a confident pick | Secondary |
| % of recommendations accepted vs. rejected/alternates requested | Trust proxy |
| % of recommendations free of grounding issues | Quality/safety |

## 13. Scope — In / Out for v1

**In scope:** Amazon Electronics (laptops, phones, headphones); Use Cases 1–3 (P0), 4–5 (P1)
**Out of scope for v1:** Cross-platform price comparison (Use Case 7/Story 7); gifting/third-person flow (Use Case 6); live catalog API integration (mock catalog only)

## 14. RAID Matrix

| Type | Item | Owner/Notes |
|---|---|---|
| **Risk** | Hallucinated specs erode user trust if grounding layer fails or is bypassed | Mitigated by Rule 4 (hard gate) + deterministic field-matching |
| **Risk** | Mock catalog (30 products) is too small to demonstrate ranking robustness in an interview | Mitigate by choosing products with genuinely varied trade-offs, not similar ones |
| **Risk** | Scope creep from stakeholder feedback (e.g., price/platform comparison) dilutes core problem statement | Addressed by folding price as a *weighted input*, not a separate feature (see Section 6, item 6) |
| **Assumption** | Users prefer describing needs conversationally over using filters/facets | To be validated via survey Q6–Q7 |
| **Assumption** | PassMark benchmark scores are a reasonable proxy for real-world "performance" perception | Reasonable for MVP; production would validate against user satisfaction data |
| **Assumption** | Budget + use case + one priority is sufficient signal for a confident recommendation | To be tested once prototype is live |
| **Issue** | No official Amazon Product Advertising API access secured yet | Open — mock catalog used as fallback for prototype |
| **Issue** | No real conversion/return data available to validate business-goal impact (Section 2) | Acknowledged as a portfolio-project limitation; metrics section states what *would* be instrumented in production |
| **Issue** | v1–v2 survey (n=10, 4 fully qualified) is still small and skewed entirely toward headphone purchases | Laptop/phone use cases — central to MVP scope — remain unvalidated by real respondent data; recruit targeted respondents next round |
| **Risk** | Users may attribute post-purchase regret to the recommendation itself, even when the real cause is delivery/fulfillment (a scope the agent doesn't control) | Product copy should set expectations that recommendations cover product fit, not delivery/order issues |
| **Risk** | Survey data shows regret is driven almost entirely by product quality/fulfillment failures, not spec-mismatch — the "reduces return rate" business goal (Section 2) may have a smaller addressable slice than assumed | Reframe primary value prop around decision confidence; treat return-rate impact as a secondary, unproven benefit until more data exists |
| **Dependency** | Claude/LLM API access for orchestrator and response generation | Required for core functionality |
| **Dependency** | Public PassMark CPU benchmark data availability | Required for performance scoring in prototype |
| **Dependency** | Vercel + GitHub hosting/deployment pipeline (reused from prior project) | Already in place |

## 15. Build Plan (sequenced)

1. Project skeleton + API connectivity
2. Hand-curated 30-product catalog (real specs)
3. Performance-score lookup (PassMark mapping)
4. `catalog_search` as a standalone tested function
5. Orchestrator + tool-calling wired in
6. `verify_grounding` added as a second pass
7. Minimal chat UI; run all use-case scripts end to end
8. Polish, deploy, document what would change at production scale

## 16. Appendix — Explicitly Deferred Ideas

- Live multi-platform price comparison (Flipkart, Croma, etc.)
- Gifting/third-person purchase flow
- Learned ranking model (once real usage/click data exists)
- Review-sentiment-based "value" scoring beyond price/spec ratio

## 17. Observability & Evaluation Requirements (v1)

**Where this lives:** This section states *requirements and success thresholds* only. The actual golden dataset, detailed instrumentation architecture, and eval harness build live in a separate companion document (Section 17.1) — keeping implementation detail out of the PRD keeps this doc focused on *what* and *why*, not *how*.

### Observability requirements
- Log every prompt sent to the orchestrator and every tool call (`parse_constraints`, `catalog_search`, `verify_grounding`) with inputs/outputs, for debugging and quality review
- Track latency per tool call and per full turn (target: full turn under 5 seconds for a smooth chat experience)
- Track token usage per turn — cost visibility matters since this is API-billed
- Log every `verify_grounding` failure/correction event separately — this is the product's ongoing quality signal, not just a debug log
- CPU/memory/disk utilization monitoring is standard for a deployed backend service but low-priority for a portfolio prototype on serverless hosting (Vercel) — noted as a production consideration, not a v1 build requirement

### Evaluation requirements
- Build a golden dataset of ~15–20 hand-crafted (user input → ideal response) pairs covering all 6 use cases, used to regression-test the orchestrator whenever the system prompt or scoring logic changes
- Define pass/fail criteria per golden example: did it ask the right clarifying question (or correctly ask none)? Did it recommend the top pick the scoring formula actually produces? Did grounding correctly catch a deliberately corrupted example?
- Include adversarial/edge cases: ambiguous budget, conflicting priorities, a deliberately mismatched spec to confirm `verify_grounding` fires
- Define success thresholds explicitly before building — e.g., constraint extraction correct on 100% of golden examples (deterministic logic, should be exact), grounding catches 100% of injected errors, response tone/ranking judged acceptable on 90%+ by manual review

### 17.1 Companion document (separate from this PRD, to be built next)
**"AI Shopping Concierge — Eval & Observability Plan"** — contains the full golden dataset (all Q&A pairs), the instrumentation architecture, chosen tooling (simple structured logging to a file/DB is sufficient for a portfolio project; name LangSmith/Datadog-equivalent tooling as the production-scale answer), and the eval harness script itself.

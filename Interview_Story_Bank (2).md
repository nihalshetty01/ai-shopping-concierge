# Interview Story Bank — AI Shopping Concierge (Q&A format)

How to use this: each entry shows the actual interview question first, then the answer ready to speak (45-75 sec), then a likely follow-up with its own answer. Scan top-down — question, answer, pushback, done. Every number and detail here is real, pulled directly from your PRD, code, and debugging sessions.

---

## Quick index

| Topic | Jump to |
|---|---|
| Data changing your mind | #1 |
| A bug or mistake | #2 |
| A hard product trade-off | #3 |
| Pushing back on stakeholders | #4 |
| AI trust/safety thinking | #5 |
| Defining success metrics | #6 |
| Catching your own blind spot | #7 |
| Working under real constraints | #8 |
| Working with incomplete data | #9 |
| Systematic debugging | #10 |
| Saying no to a request | #11 |

---

## 1. Data Changing Your Mind

**Q: "Tell me about a time data changed your mind."**
**Q: "Tell me about a hypothesis you had that turned out wrong."**

**A:** "I assumed the pain point in buying electronics online was time — people spending hours comparing specs. I ran real user interviews to check, using Mom's Test principles — asking about actual past purchases, not opinions. I was wrong. Decision speed varied a lot, from under an hour to several days, but confidence didn't — people stayed unsure even after fast decisions. That single finding reshaped my whole product: I rebuilt it around resolving doubt, not speeding up search."

**Q (pushback): "Wasn't your sample too small to base an architecture change on?"**
**A:** "Yes — six respondents, then ten after I fixed a broken screening logic, is directional, not conclusive, and I said so explicitly in my own PRD. But it was strong enough to justify changing a hypothesis, not to claim a final answer. I flagged exactly what more data would be needed before I'd fully trust it."

---

## 2. The Budget Fit Bug

**Q: "Tell me about a bug or mistake you made."**
**Q: "Tell me about a time your product did something you didn't expect."**

**A:** "During testing, my scoring algorithm recommended a ₹1.4 lakh laptop for someone with a ₹60,000 budget, on a search specifically optimized for value. I traced it to a real math bug — the budget-fit penalty had a mathematical floor, so being 50% over budget and 300% over budget scored identically. Past that point, raw spec weighting just dominated. I fixed it with a hard 15% tolerance band, documented the failure with the real before-and-after numbers in my PRD, and wrote a regression test so it can't silently come back."

**Q (pushback): "How did you decide on that specific fix instead of just tightening the penalty curve?"**
**A:** "I treated it as a real product decision, not just a math patch. I considered a hard cutoff versus a steeper penalty curve, and picked the hard band deliberately — it still allows near-misses, like ₹64,999 against a ₹60k budget, because that matches how real shoppers actually behave. I documented that trade-off explicitly rather than just shipping a fix."

---

## 3. Wired Headphones Have No Battery

**Q: "Tell me about a difficult product trade-off."**
**Q: "Tell me about a time you had to handle ambiguous or messy requirements."**

**A:** "My initial ranking system used one formula across every product category. I caught that it was scoring wired headphones on battery life — which doesn't exist for them. Instead of just hiding that in the UI, I rebuilt the ranking to be category-aware: laptops and phones score on performance, battery, storage, value, and budget; wireless headphones swap performance for an audio-quality composite; wired headphones drop battery entirely. If someone tries to prioritize battery for a wired headphone, the system throws an explicit error instead of silently defaulting."

**Q (pushback): "Why not just handle that with a simpler UI restriction?"**
**A:** "Because the problem wasn't the UI — it was the data model pretending a nonexistent dimension was real. If I'd only patched the UI, the underlying scoring logic would still be lying to itself. Fixing it structurally meant the honesty runs all the way down, not just on the surface."

---

## 4. The Price/Platform Scope Fight

**Q: "Tell me about a time you pushed back on stakeholder feedback."**
**Q: "Tell me about managing scope creep."**

**A:** "A colleague reviewing my PRD said I was missing cross-platform price comparison, since Indian shoppers are price-sensitive. Instead of just accepting or rejecting that, I tested it — ran a survey specifically asking whether price was the dominant driver of hesitation. It wasn't. Zero of seven respondents across two rounds said price alone drove their decision; most said it was product fit and price, equally. So I incorporated the real insight — price became a weighted input in my ranking algorithm — without expanding scope into a full price-comparison feature I didn't have data to justify."

**Q (pushback): "What if the data had shown price WAS the dominant factor?"**
**A:** "Then I'd have had a real, data-backed case to bring back to that colleague and actually consider the scope expansion — the point wasn't to defend my original scope no matter what, it was to stop guessing and let evidence decide it either way."

---

## 5. The Grounding Gate

**Q: "How do you think about trust and safety in an AI product?"**
**Q: "Tell me about a technical architecture decision you made."**

**A:** "The biggest trust risk in an AI product is the model confidently stating something false. I didn't rely on prompting alone to prevent that — I built a hard-coded gate in the code itself. Every draft response gets field-matched against the real catalog data before the user ever sees it. It's not a tool the model can choose to skip; it's mandatory. On a mismatch, the draft goes back for automatic correction, up to a bounded number of retries."

**Q (pushback): "Doesn't that add latency or cost?"**
**A:** "Yes, and I tracked that explicitly as a guardrail metric — response latency under 5 seconds. Trust and speed are a real trade-off, and I made the call deliberately: I'd rather be slightly slower and never wrong about a spec than fast and occasionally hallucinating."

**Q (pushback): "How did you validate the gate actually works?"**
**A:** "I ran real live conversations and manually checked flagged cases. I caught a genuine false positive where 'six hours on the buds, twenty-one hours with the case' was flagged as a hallucination, because my battery field only captured the six-hour figure. I fixed it by falling back to the product's own retrieved name-string data — still real data, just not in the field I'd originally checked."

---

## 6. North Star / Secondary / Guardrails

**Q: "How do you define success for a product?"**
**Q: "Walk me through your metrics framework."**

**A:** "I picked Confident Session Rate as my North Star — the percentage of sessions ending in a thumbs-up on the final recommendation — specifically because my research showed confidence, not speed or engagement, was the real validated problem. Secondary metrics explain what actually moves that North Star: clarifying-questions per session, thumbs-up rate by category, session completion rate. Guardrails protect against gaming the North Star in a way that breaks something else — grounding failure rate under 5%, latency under 5 seconds, and how often my rate limits actually trigger."

**Q (pushback): "Why not just track conversion or revenue directly?"**
**A:** "Because I don't have real checkout data — there's no purchase flow in this prototype. I was explicit about that limitation rather than pretending to track something I can't actually measure. Confident Session Rate is the honest, truthful proxy I actually have evidence for."

---

## 7. Conflating Two Feedback Signals

**Q: "Tell me about a time you caught your own mistake."**
**Q: "Tell me about a product decision you revisited."**

**A:** "I built thumbs-up/down feedback on individual product recommendations and considered feedback capture done. Then I realized that's a different signal from 'was the AI's overall reasoning helpful' — someone could dislike every product shown while still finding the explanation genuinely useful, or the reverse. I added a second, separate feedback control on the AI's response itself, with its own logged context, so those two signals don't get flattened into one misleading number."

**Q (pushback): "How did you catch that — did a user point it out?"**
**A:** "No, I caught it myself, reviewing what I'd built. Nobody prompted it. That's actually why I think it's a good story — it shows the habit of re-examining your own shipped work critically, not just waiting for someone else to find the gap."

---

## 8. Building on a Hard Budget Cap

**Q: "Tell me about working under real constraints."**
**Q: "Tell me about a resource-limited project."**

**A:** "I was self-funding the API costs for this project, so I couldn't risk unpredictable spend once it went live publicly. I set a hard monthly cap on my API console as a real, non-negotiable backstop. On top of that, I layered softer in-app protections — a per-session message cap, a daily global cap, and a free Demo Mode as the default experience for anonymous visitors — specifically so the hard cap would rarely, if ever, actually trigger. If traffic spikes, the product degrades gracefully with a friendly message instead of a raw, embarrassing error."

**Q (pushback): "How did you decide on the actual cap numbers?"**
**A:** "Honestly, imperfectly — I didn't have enough real usage data yet to calculate a precise number, so I set a conservative starting point and made it a single environment variable I could tune without a code change once I saw real behavior. I was upfront about that being a placeholder, not a scientifically derived figure."

---

## 9. The Headphones-Only Sample

**Q: "Tell me about working with incomplete or imperfect data."**
**Q: "Tell me about a limitation you had to be honest about."**

**A:** "After two survey rounds, every fully-qualified respondent had bought headphones — zero laptop or phone buyers, even though my product covers all three categories. Instead of quietly assuming the findings generalized, I documented the gap explicitly in my PRD's RAID matrix: the laptop and phone 'spec overload' framing is a hypothesis for those categories until they're actually represented in real data. I shipped anyway, since a portfolio prototype doesn't need perfect validation — but I'd rather an interviewer catch me being upfront about a limitation than catch me overclaiming."

---

## 10. The Three Wrong Theories

**Q: "Tell me about a time you debugged something difficult."**
**Q: "Tell me about your problem-solving process when something isn't working."**

**A:** "A feedback-logging integration kept failing with a permissions-looking error. I tested three real theories in sequence, each with actual evidence, not guesses: first, a wrong URL — disproven by comparing the exact strings. Second, a CORS preflight block — disproven by checking the browser's network tab and seeing no preflight request at all. Third, a deployment access setting — disproven by testing the endpoint anonymously in an incognito window, which worked fine. The real cause, found through a clean isolated test: a spreadsheet tab was named 'Sheet1' instead of the 'Feedback' name my script was looking for. One-line fix — but only findable because I ruled out each wrong theory with real evidence first."

**Q (pushback): "Isn't that a lot of time for a one-line fix?"**
**A:** "It felt that way in the moment, but the alternative — guessing at fixes without evidence — usually costs more time, not less, because you end up patching symptoms instead of the actual cause. I'd rather spend twenty extra minutes ruling things out than ship a fix I'm not sure actually addresses the problem."

---

## 11. Refusing Fake Inventory Counts

**Q: "Tell me about a time you said no to a request."**
**Q: "Tell me about a product ethics decision you made."**

**A:** "I was asked to add urgency messaging — 'only ten left in stock' — and fabricated sub-ratings for things like sound quality and build quality on product cards. I declined both. My catalog has no real inventory data, and no real per-aspect review data — only one honest aggregate rating exists. Building either would mean inventing numbers, which directly contradicts the anti-hallucination principle my entire product is built around. I built a real product detail page instead, with a visibly disabled 'Proceed to Buy' button captioned 'demo prototype — checkout not implemented.' I'd rather ship an honestly labeled limitation than a fake feature that looks more polished.

That principle actually caught something later, too — a real user testing on mobile found a cart icon showing a hardcoded '3,' implying items had been added when nothing was ever actually added to a cart. Same category of problem, just a spot I'd missed applying the rule to. I removed it as soon as it surfaced. It's a good reminder that a stated principle needs periodic auditing across the whole product, not just at the moment you first decide it."

**Q (pushback): "Doesn't that hurt the user experience compared to competitors who do show that stuff?"**
**A:** "Maybe in the short term. But fabricated urgency and fake ratings are exactly the kind of dark pattern that erodes trust once a user notices — and the whole value proposition of this product is trustworthy recommendations. I'd rather be less flashy and actually credible."


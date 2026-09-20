# -*- coding: utf-8 -*-
"""
agent/orchestrator.py
---------------------
Shopping Concierge orchestrator built on Claude's native tool-use API.

Two tools are registered:
  • parse_constraints  — regex-based NLP extraction (local, fast)
  • catalog_search     — scored product retrieval (local, fast)

verify_grounding is deliberately NOT a tool. The PRD's RAID matrix calls
Rule 4 a "hard gate", and a tool Claude chooses to call is not a gate — it
can be skipped on exactly the turn it matters. Instead every candidate
response is verified in code before being returned, and unsupported claims
are sent back for correction. See Orchestrator._run_gate.

Flow:
  1. User message arrives.
  2. Claude calls parse_constraints to get structured fields.
  3. Claude inspects the result + its own reading of the raw message.
  4. If budget / use_case / priority is missing or ambiguous →
     reply with exactly ONE clarifying question.
  5. Once sufficient → call catalog_search → present ≤ 3 ranked options.
  6. Every candidate response is field-matched against the retrieved
     products; unsupported claims go back to Claude for correction before
     the user sees anything.

Requires:
  • ANTHROPIC_API_KEY in environment or in a .env file at project root.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import anthropic

# Force UTF-8 output on Windows (cp1252 console chokes on ₹ etc.)
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Ensure project root is importable
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Load .env from project root (if present)
try:
    from dotenv import load_dotenv
    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    pass

from tools.parse_constraints import parse_constraints
from tools.catalog_search import catalog_search
from agent.verify_grounding import verify_grounding

# ---------------------------------------------------------------------------
# System prompt (verbatim from spec)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a shopping concierge for electronics on Amazon. Your job is to help \
the user reach a confident purchase decision quickly.

RULES:
1. Never recommend a product until you have: budget, use case, and at least \
one priority (e.g. performance vs battery vs price). The priority options \
offered are category-specific: performance/battery/value for laptops & \
phones; sound_quality/battery/value for wireless headphones; \
sound_quality/value only for wired headphones (no battery option exists).
1a. parse_constraints output is a fast structured pre-fill, not the final \
word — always cross-check it against your own reading of the raw user \
message, since the tool is deterministic/regex-based and can miss things \
you would naturally catch (e.g. "sixty thousand" instead of "60k").
2. If any of budget, use case, or priority is missing or ambiguous, ask \
exactly ONE clarifying question — the single most decision-relevant one. \
Never ask more than one at a time.
2a. If parse_constraints returns an ambiguous_signals entry (e.g. the user \
said "cheap," "great sound," or "nothing fancy" without a number or \
explicit priority), your one clarifying question must target resolving \
that specific ambiguity directly — never silently assign a number or \
priority to subjective language.
3. Once you have enough information, call catalog_search with the \
structured constraints.
4. Every response you write is field-matched against the retrieved \
product data before the user sees it. State only specs and prices present \
in what catalog_search returned, and attribute each to the product it \
actually belongs to — a real spec assigned to the wrong product is as \
much a failure as an invented one. If the check rejects a claim you will \
be told; correct or remove it, and never restate it.
4a. Some categories have no field at all for a given dimension — a wired \
headphone has no battery. Never describe a dimension that does not exist \
for that product type, with or without a number attached.
5. Present at most 3 ranked options. For each, give one plain-language \
reason tied to the user's stated priority — not a spec dump.
6. If the user pushes back or asks to compare two options, explain the \
trade-off directly in terms of their stated use case, not generic \
pros/cons.
7. Never invent a product, price, or spec not in retrieved data.

TONE: concise, decisive, like a knowledgeable friend — not a salesperson.\
"""

# ---------------------------------------------------------------------------
# Tool definitions (Claude tool_use format)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "parse_constraints",
        "description": (
            "Extract structured shopping constraints from a user's "
            "natural-language message.  Returns category, connectivity_type, "
            "budget, budget_min, budget_max, use_case, priority, and "
            "ambiguous_signals.  Fields are None when not detected.  "
            "ambiguous_signals is a list of {type, term} objects for "
            "subjective language (e.g. 'cheap', 'great sound') that needs "
            "clarification."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "user_message": {
                    "type": "string",
                    "description": "The user's raw input message to parse.",
                },
                "prior_context": {
                    "type": ["object", "null"],
                    "description": (
                        "Optional dict of previously extracted constraints "
                        "from an earlier turn. Fields present here are "
                        "carried forward when not overridden by current message."
                    ),
                },
            },
            "required": ["user_message"],
        },
    },
    {
        "name": "catalog_search",
        "description": (
            "Search the product catalog and return the top-5 ranked results "
            "based on the given constraints.  Requires category, budget, and "
            "priority.  For headphones, connectivity_type is also required."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["laptop", "phone", "headphones"],
                    "description": "Product category.",
                },
                "budget": {
                    "type": "number",
                    "description": "Maximum budget in ₹.",
                },
                "priority": {
                    "type": "string",
                    "description": (
                        "Scoring priority.  Laptop/phone: performance | "
                        "battery | value | balanced.  Wireless headphones: "
                        "sound_quality | battery | value | balanced.  "
                        "Wired headphones: sound_quality | value | balanced."
                    ),
                },
                "connectivity_type": {
                    "type": ["string", "null"],
                    "enum": ["wired", "wireless", "true_wireless", None],
                    "description": (
                        "Required for headphones only.  One of: wired, "
                        "wireless, true_wireless."
                    ),
                },
            },
            "required": ["category", "budget", "priority"],
        },
    },
]

# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------

def _execute_tool(name: str, input_args: dict) -> Any:
    """Execute a tool call locally and return the result as a dict/list."""
    if name == "parse_constraints":
        return parse_constraints(
            user_message=input_args["user_message"],
            prior_context=input_args.get("prior_context"),
        )
    elif name == "catalog_search":
        constraints = {
            "category": input_args["category"],
            "budget": input_args["budget"],
            "priority": input_args["priority"],
        }
        if input_args.get("connectivity_type"):
            constraints["connectivity_type"] = input_args["connectivity_type"]
        results = catalog_search(constraints)
        # Strip internal scoring keys for a cleaner response
        cleaned = []
        for item in results:
            clean = {
                k: v for k, v in item.items()
                if not k.startswith("_")
            }
            cleaned.append(clean)
        return cleaned
    else:
        return {"error": f"Unknown tool: {name}"}


# ---------------------------------------------------------------------------
# Conversation runner
# ---------------------------------------------------------------------------

# Sent to Claude when the gate rejects a draft. Framed explicitly as an
# operator report so Claude does not reply to it as if the shopper had
# spoken, and so it never leaks into the visible conversation.
_CORRECTION_TEMPLATE = """\
[AUTOMATED GROUNDING CHECK — this is not a message from the user]

Your draft was field-matched against the retrieved product data and \
{count} claim(s) could not be verified:

{findings}

Rewrite the response with each unsupported claim corrected or removed. Do \
not restate any claim listed above, and do not mention this check to the \
user.\
"""

# Served when a draft still fails after MAX_GROUNDING_RETRIES. Showing an
# unverified spec would breach Rule 4, and silently deleting sentences
# risks leaving a mangled recommendation — so the turn degrades honestly.
_GROUNDING_FALLBACK = (
    "Let me re-check those specs before I put numbers in front of you — "
    "ask me again and I'll pull them fresh."
)


class Orchestrator:
    """Stateful multi-turn shopping concierge."""

    MODEL = "claude-opus-5"

    # Correction rounds allowed per turn. Two is enough for a genuine slip;
    # a draft still failing after that is a systematic problem worth
    # surfacing rather than looping on.
    MAX_GROUNDING_RETRIES = 2

    def __init__(
        self,
        *,
        api_key: str | None = None,
        verbose: bool = False,
        initial_messages: list[dict] | None = None,
        initial_retrieved_by_id: dict[str, dict] | None = None,
    ):
        self.client = anthropic.Anthropic(api_key=api_key)
        # Pre-seed from persisted state when provided (e.g. loaded from Redis).
        # Starting from empty lists/dicts is still the default for fresh sessions.
        self.messages: list[dict] = list(initial_messages) if initial_messages else []
        self.verbose = verbose
        # Every product retrieved this session, keyed by id. Accumulated
        # rather than replaced: after a re-search the user may still refer
        # to something shown earlier, and that reference IS grounded.
        self.retrieved_by_id: dict[str, dict] = (
            dict(initial_retrieved_by_id) if initial_retrieved_by_id else {}
        )
        # One record per gate outcome — the ongoing quality signal the Eval
        # Plan asks to log separately, not just a debug line.
        self.grounding_events: list[dict] = []

    # -----------------------------------------------------------------
    # Rule 4 — the hard gate
    # -----------------------------------------------------------------

    def _run_gate(self, text: str) -> list[dict]:
        """Field-match a candidate response against everything retrieved.

        Returns the list of issues; empty means the draft may be shown.
        """
        products = list(self.retrieved_by_id.values())
        if not products or not text.strip():
            return []
        return verify_grounding(text, products)

    @staticmethod
    def _format_findings(issues: list[dict]) -> str:
        lines = []
        for n, issue in enumerate(issues, 1):
            product = issue["product"] or "(not attributable to a product)"
            lines.append(
                f"{n}. product: {product}\n"
                f"   claim:   {issue['claim']!r}\n"
                f"   problem: {issue['issue']}"
            )
        return "\n".join(lines)

    def _record_grounding(self, outcome: str, issues: list[dict], attempt: int) -> None:
        self.grounding_events.append({
            "turn": sum(1 for m in self.messages if m["role"] == "user"),
            "attempt": attempt,
            "outcome": outcome,
            "issue_count": len(issues),
            "issues": issues,
        })

    def chat(self, user_message: str) -> str:
        """Send a user message, run the tool-use loop, return Claude's text reply."""
        self.messages.append({"role": "user", "content": user_message})

        if self.verbose:
            print(f"\n{'='*70}")
            print(f"USER: {user_message}")
            print(f"{'='*70}")

        grounding_attempt = 0

        # Agentic loop — keep calling Claude until it stops requesting tools
        # AND its answer passes the grounding gate.
        while True:
            response = self.client.messages.create(
                model=self.MODEL,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=self.messages,
            )

            if self.verbose:
                print(f"\n--- Claude response (stop_reason={response.stop_reason}) ---")

            # Collect text blocks and tool-use blocks
            assistant_content = []
            tool_uses = []
            text_parts = []

            for block in response.content:
                if block.type == "text":
                    assistant_content.append(block)
                    text_parts.append(block.text)
                    if self.verbose:
                        print(f"TEXT: {block.text}")
                elif block.type == "tool_use":
                    assistant_content.append(block)
                    tool_uses.append(block)
                    if self.verbose:
                        print(f"TOOL_USE: {block.name}({json.dumps(block.input, indent=2)})")

            # Append assistant message with ALL content blocks, verbatim.
            # Passing response.content straight back preserves every block
            # type (including thinking blocks, which must be echoed
            # unchanged when continuing on the same model). Rebuilding the
            # list by hand silently drops anything not explicitly handled.
            self.messages.append({
                "role": "assistant",
                "content": response.content,
            })

            # No tool calls — this is a candidate answer, so Rule 4 applies
            # before it can leave the method.
            if response.stop_reason != "tool_use" or not tool_uses:
                candidate = "\n".join(text_parts)
                issues = self._run_gate(candidate)

                if not issues:
                    # A turn with nothing retrieved yet was never actually
                    # checked. Logging it as a pass would inflate the
                    # grounding pass rate with turns the gate never saw, so
                    # the two outcomes stay distinguishable in the metrics.
                    outcome = "pass" if self.retrieved_by_id else "not_applicable"
                    if self.verbose and self.retrieved_by_id:
                        print("GROUNDING: pass")
                    self._record_grounding(outcome, [], grounding_attempt)
                    return candidate

                if grounding_attempt >= self.MAX_GROUNDING_RETRIES:
                    if self.verbose:
                        print(f"GROUNDING: BLOCKED after "
                              f"{grounding_attempt} correction(s); "
                              f"{len(issues)} issue(s) remain")
                    self._record_grounding("blocked", issues, grounding_attempt)
                    return _GROUNDING_FALLBACK

                grounding_attempt += 1
                findings = self._format_findings(issues)
                if self.verbose:
                    print(f"GROUNDING: {len(issues)} issue(s), requesting "
                          f"correction {grounding_attempt}/"
                          f"{self.MAX_GROUNDING_RETRIES}")
                    print(findings)
                self._record_grounding("correction_requested", issues,
                                       grounding_attempt)

                self.messages.append({
                    "role": "user",
                    "content": _CORRECTION_TEMPLATE.format(
                        count=len(issues), findings=findings,
                    ),
                })
                continue

            # Execute each tool call and build tool_result messages
            tool_results = []
            for tool_block in tool_uses:
                result = _execute_tool(tool_block.name, tool_block.input)

                # Remember what was retrieved so the gate has something to
                # match claims against. Accumulated across the whole
                # session, keyed by id.
                if tool_block.name == "catalog_search" and isinstance(result, list):
                    for item in result:
                        if isinstance(item, dict) and item.get("id"):
                            self.retrieved_by_id[str(item["id"])] = item

                result_json = json.dumps(result, ensure_ascii=False, default=str)

                if self.verbose:
                    # Truncate for readability
                    preview = result_json[:500] + ("..." if len(result_json) > 500 else "")
                    print(f"TOOL_RESULT ({tool_block.name}): {preview}")

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_block.id,
                    "content": result_json,
                })

            self.messages.append({"role": "user", "content": tool_results})


# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------

def run_test(test_id: str, user_messages: list[str], expected_note: str):
    """Run a single test conversation and print the full transcript."""
    print(f"\n{'#'*70}")
    print(f"# TEST {test_id}")
    print(f"# Expected: {expected_note}")
    print(f"{'#'*70}")

    orch = Orchestrator(verbose=True)
    for msg in user_messages:
        reply = orch.chat(msg)
        print(f"\n>>> FINAL REPLY <<<")
        print(reply)
        print(f">>> END REPLY <<<\n")


def main():
    """Run all 5 test conversations end to end.

    Each script runs until the agent has budget + use case + priority (and
    connectivity type for headphones) so that catalog_search actually fires.
    Single-turn scripts only ever exercised the clarifying-question path —
    the whole recommendation half went untested.
    """
    # Verify API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set.")
        print("Set it via environment variable or create a .env file in the project root:")
        print("  ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    tests = [
        (
            "G01",
            [
                "laptop for video editing, ₹60k budget",
                "performance",
            ],
            "Turn 1: ONE clarifying question on performance vs. battery. "
            "Turn 2: calls catalog_search(laptop, 60000, performance) and "
            "presents at most 3 options, each with a reason tied to renders/"
            "editing speed — not a spec dump",
        ),
        (
            "G03",
            [
                "headphones for gym, budget flexible",
                "true wireless, and let's cap it at ₹5,000",
                "battery life",
            ],
            "Never assumes wireless — confirms connectivity. Once wireless is "
            "known, the priority menu offered must be sound_quality/battery/"
            "value (never performance). Final turn searches true_wireless",
        ),
        (
            "G19",
            [
                "wired headphones under ₹1,500 for music at home",
                "sound quality",
            ],
            "The word 'battery' must not appear ANYWHERE in either turn. "
            "Searches wired + sound_quality; every claimed spec must exist "
            "in the returned data",
        ),
        (
            "G20",
            [
                "wireless earbuds for gym, priority is battery life",
                "under ₹5,000",
            ],
            "parse_constraints must now extract priority=battery from "
            "'priority is battery life'. Top pick should be the highest "
            "battery_hours option within ₹5,000, not the best audio_score",
        ),
        (
            "G23",
            [
                "I'm looking for cheap mobile headphones",
                "under ₹2,000 — wired, and I mostly care about sound",
            ],
            "Turn 1: asks what 'cheap' means in ₹ — does NOT guess a number, "
            "and reads 'mobile headphones' as headphones (not a phone). "
            "Turn 2: searches wired + sound_quality under ₹2,000",
        ),
    ]

    for test_id, messages, expected in tests:
        run_test(test_id, messages, expected)


if __name__ == "__main__":
    main()

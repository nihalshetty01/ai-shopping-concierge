# -*- coding: utf-8 -*-
"""
tests/test_orchestrator_gate.py
-------------------------------
Tests for Rule 4 — the grounding gate inside Orchestrator.chat().

The API client is stubbed with a scripted sequence of responses, so these
run offline and deterministically. What is under test is the gate's control
flow, not the model: does an unsupported claim actually get sent back, does
a corrected draft get through, and does an unfixable draft get blocked
rather than shown?
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agent.orchestrator import (
    Orchestrator,
    _CORRECTION_TEMPLATE,
    _GROUNDING_FALLBACK,
)

sys.path.insert(0, os.path.dirname(__file__))
from test_verify_grounding import LAPTOP_06, LAPTOP_08


# ---------------------------------------------------------------------------
# Minimal stand-ins for the SDK response objects
# ---------------------------------------------------------------------------

class _TextBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _ToolUseBlock:
    type = "tool_use"

    def __init__(self, name, tool_input, block_id="tu_1"):
        self.name = name
        self.input = tool_input
        self.id = block_id


class _Response:
    def __init__(self, content, stop_reason):
        self.content = content
        self.stop_reason = stop_reason


def _text(msg):
    return _Response([_TextBlock(msg)], "end_turn")


def _tool(name, tool_input):
    return _Response([_ToolUseBlock(name, tool_input)], "tool_use")


class _StubMessages:
    def __init__(self, script):
        self._script = list(script)
        self.call_count = 0

    def create(self, **kwargs):
        self.call_count += 1
        if not self._script:
            raise AssertionError("stub client ran out of scripted responses")
        return self._script.pop(0)


class _StubClient:
    def __init__(self, script):
        self.messages = _StubMessages(script)


def _orchestrator(script, retrieved=()):
    orch = Orchestrator(api_key="test-key-not-used")
    orch.client = _StubClient(script)
    for product in retrieved:
        orch.retrieved_by_id[product["id"]] = product
    return orch


GOOD_DRAFT = "**Lenovo IdeaPad Slim 3 — ₹59,990**\nGets you 9 hours of battery."
BAD_DRAFT = "**Lenovo IdeaPad Slim 3 — ₹59,990**\nGets you 18 hours of battery."


# ---------------------------------------------------------------------------

class TestGatePasses:

    def test_clean_draft_is_returned_unchanged(self):
        orch = _orchestrator([_text(GOOD_DRAFT)], retrieved=[LAPTOP_06])
        assert orch.chat("which one?") == GOOD_DRAFT

    def test_one_api_call_when_clean(self):
        orch = _orchestrator([_text(GOOD_DRAFT)], retrieved=[LAPTOP_06])
        orch.chat("which one?")
        assert orch.client.messages.call_count == 1

    def test_pass_is_logged(self):
        orch = _orchestrator([_text(GOOD_DRAFT)], retrieved=[LAPTOP_06])
        orch.chat("which one?")
        assert [e["outcome"] for e in orch.grounding_events] == ["pass"]
        assert orch.grounding_events[0]["issue_count"] == 0


class TestGateCorrects:

    def test_bad_draft_triggers_a_second_call(self):
        orch = _orchestrator([_text(BAD_DRAFT), _text(GOOD_DRAFT)],
                             retrieved=[LAPTOP_06])
        assert orch.chat("which one?") == GOOD_DRAFT
        assert orch.client.messages.call_count == 2

    def test_unverified_text_never_reaches_the_caller(self):
        orch = _orchestrator([_text(BAD_DRAFT), _text(GOOD_DRAFT)],
                             retrieved=[LAPTOP_06])
        assert "18 hours" not in orch.chat("which one?")

    def test_correction_message_is_appended_as_operator_text(self):
        orch = _orchestrator([_text(BAD_DRAFT), _text(GOOD_DRAFT)],
                             retrieved=[LAPTOP_06])
        orch.chat("which one?")
        corrections = [
            m for m in orch.messages
            if m["role"] == "user" and isinstance(m["content"], str)
            and "AUTOMATED GROUNDING CHECK" in m["content"]
        ]
        assert len(corrections) == 1
        body = corrections[0]["content"]
        assert "not a message from the user" in body
        assert "18 hours" in body, "the rejected claim should be quoted back"
        assert "9 hours" in body, "the real value should be given"

    def test_events_record_correction_then_pass(self):
        orch = _orchestrator([_text(BAD_DRAFT), _text(GOOD_DRAFT)],
                             retrieved=[LAPTOP_06])
        orch.chat("which one?")
        assert [e["outcome"] for e in orch.grounding_events] == [
            "correction_requested", "pass",
        ]
        assert orch.grounding_events[0]["issues"][0]["claim"] == "18 hours"

    def test_two_corrections_are_allowed(self):
        orch = _orchestrator(
            [_text(BAD_DRAFT), _text(BAD_DRAFT), _text(GOOD_DRAFT)],
            retrieved=[LAPTOP_06],
        )
        assert orch.chat("which one?") == GOOD_DRAFT
        assert orch.client.messages.call_count == 3


class TestGateBlocks:

    def test_persistent_failure_returns_the_fallback(self):
        orch = _orchestrator([_text(BAD_DRAFT)] * 3, retrieved=[LAPTOP_06])
        assert orch.chat("which one?") == _GROUNDING_FALLBACK

    def test_fallback_leaks_no_unverified_claim(self):
        orch = _orchestrator([_text(BAD_DRAFT)] * 3, retrieved=[LAPTOP_06])
        reply = orch.chat("which one?")
        assert "18" not in reply and "₹" not in reply

    def test_retries_are_bounded(self):
        """Must not loop forever on a draft Claude cannot fix."""
        orch = _orchestrator([_text(BAD_DRAFT)] * 3, retrieved=[LAPTOP_06])
        orch.chat("which one?")
        assert orch.client.messages.call_count == orch.MAX_GROUNDING_RETRIES + 1

    def test_block_is_logged_with_the_outstanding_issues(self):
        orch = _orchestrator([_text(BAD_DRAFT)] * 3, retrieved=[LAPTOP_06])
        orch.chat("which one?")
        last = orch.grounding_events[-1]
        assert last["outcome"] == "blocked"
        assert last["issue_count"] >= 1


class TestGateScope:

    def test_gate_is_skipped_before_any_search(self):
        """A clarifying question turn has nothing to verify against."""
        question = "What's your budget ceiling?"
        orch = _orchestrator([_text(question)])
        assert orch.chat("need a laptop") == question
        # Logged as not_applicable rather than pass, so the grounding pass
        # rate is not diluted by turns the gate had nothing to check.
        assert [e["outcome"] for e in orch.grounding_events] == ["not_applicable"]

    def test_clarifying_question_after_a_search_still_passes(self):
        follow_up = "Which way is your budget leaning?"
        orch = _orchestrator([_text(follow_up)], retrieved=[LAPTOP_06])
        assert orch.chat("hmm") == follow_up
        assert orch.grounding_events[-1]["outcome"] == "pass"

    def test_wrong_product_attribution_is_caught(self):
        """9h is real for the Lenovo but not the TUF — must not slip through."""
        borrowed = "**ASUS TUF Gaming A15 — ₹67,990**\nGets you 9 hours of battery."
        fixed = "**ASUS TUF Gaming A15 — ₹67,990**\nGets you 8 hours of battery."
        orch = _orchestrator([_text(borrowed), _text(fixed)],
                             retrieved=[LAPTOP_06, LAPTOP_08])
        assert orch.chat("the ASUS?") == fixed


class TestRetrievedProductCapture:

    def test_search_results_are_captured_for_the_gate(self):
        orch = _orchestrator([
            _tool("catalog_search",
                  {"category": "laptop", "budget": 60000,
                   "priority": "performance"}),
            _text("Nothing to add."),
        ])
        orch.chat("laptop, 60k, performance")
        assert orch.retrieved_by_id, "catalog_search results were not captured"
        assert all(p["price"] <= 60000 * 1.15
                   for p in orch.retrieved_by_id.values())

    def test_results_accumulate_across_searches(self):
        """A re-search must not orphan products already shown to the user."""
        orch = _orchestrator([
            _tool("catalog_search",
                  {"category": "laptop", "budget": 60000, "priority": "performance"}),
            _tool("catalog_search",
                  {"category": "headphones", "budget": 1500,
                   "priority": "sound_quality", "connectivity_type": "wired"}),
            _text("Nothing to add."),
        ])
        orch.chat("compare laptops and wired headphones")
        categories = {p["category"] for p in orch.retrieved_by_id.values()}
        assert categories == {"laptop", "headphones"}

    def test_parse_constraints_results_are_not_captured(self):
        orch = _orchestrator([
            _tool("parse_constraints", {"user_message": "laptop under 60k"}),
            _text("What's your priority?"),
        ])
        orch.chat("laptop under 60k")
        assert orch.retrieved_by_id == {}


class TestSystemPromptRules:
    """Rule 4 was missing from the prompt entirely; guard against regression."""

    def test_grounding_rule_is_present(self):
        from agent.orchestrator import SYSTEM_PROMPT
        assert "field-matched" in SYSTEM_PROMPT

    def test_rules_are_numbered_without_a_gap(self):
        from agent.orchestrator import SYSTEM_PROMPT
        for n in range(1, 8):
            assert f"\n{n}. " in SYSTEM_PROMPT, f"rule {n} missing"

    def test_absent_dimension_rule_is_present(self):
        from agent.orchestrator import SYSTEM_PROMPT
        assert "wired" in SYSTEM_PROMPT and "no battery" in SYSTEM_PROMPT

# -*- coding: utf-8 -*-
"""
tests/test_parse_constraints.py
--------------------------------
Unit tests for parse_constraints().

Coverage plan (10 tests):
  1. Fully-specified message (all 5 fields populated)
  2. Vague message — nothing extractable (all None)
  3. Budget "60k" format
  4. Budget "₹60,000" format
  5. Budget "under 15000" format
  6. Explicit priority stated → priority is set
  7. Use-case alone does NOT set priority (gaming → no priority)
  8. Headphones WITH connectivity_type mentioned
  9. Headphones WITHOUT connectivity_type mentioned
 10. prior_context carries forward missing fields
 Bonus:
 11. true_wireless detection
 12. Wired headphones correctly identified (not wireless)
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tools.parse_constraints import parse_constraints


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _r(category=None, connectivity_type=None, budget=None,
        use_case=None, priority=None,
        budget_min=None, budget_max=None, ambiguous_signals=None):
    """Shorthand for building an expected result dict.

    New fields default to None / [] so that existing tests that call
    ``result == _r()`` continue to work after the schema expansion.
    """
    return {
        "category":          category,
        "connectivity_type": connectivity_type,
        "budget":            budget,
        "budget_min":        budget_min,
        "budget_max":        budget_max,
        "use_case":          use_case,
        "priority":          priority,
        "ambiguous_signals": ambiguous_signals if ambiguous_signals is not None else [],
    }


# ---------------------------------------------------------------------------
# Test 1 — Fully-specified message
# ---------------------------------------------------------------------------

class TestFullySpecified:
    """All five fields should be populated from a single rich message."""

    def test_all_fields_extracted(self):
        """
        'I need wireless headphones under ₹8000 for working out,
         battery life matters most'
        → category=headphones, connectivity=wireless, budget=8000,
          use_case=..., priority=battery
        """
        result = parse_constraints(
            "I need wireless headphones under ₹8000 for working out, "
            "battery life matters most"
        )
        assert result["category"] == "headphones"
        assert result["connectivity_type"] == "wireless"
        assert result["budget"] == 8000.0
        assert result["use_case"] is not None
        assert "work" in result["use_case"] or "out" in result["use_case"]
        assert result["priority"] == "battery"

    def test_laptop_fully_specified(self):
        """
        'Looking for a laptop around 60k for office work,
         best performance matters'
        → category=laptop, budget=60000, use_case contains 'office',
          priority=performance
        """
        result = parse_constraints(
            "Looking for a laptop around 60k for office work, "
            "best performance matters"
        )
        assert result["category"] == "laptop"
        assert result["budget"] == 60_000.0
        assert result["connectivity_type"] is None  # laptops don't have this
        assert result["use_case"] is not None
        assert "office" in result["use_case"] or "work" in result["use_case"]
        assert result["priority"] == "performance"


# ---------------------------------------------------------------------------
# Test 2 — Vague message, nothing extractable
# ---------------------------------------------------------------------------

class TestVagueMessage:
    """Vague messages should return all None — never guess."""

    def test_nothing_extracted_from_vague_message(self):
        result = parse_constraints("I need something good")
        assert result == _r()

    def test_nothing_extracted_from_generic_shopping(self):
        result = parse_constraints("Help me find a good product")
        assert result == _r()

    def test_empty_string_returns_all_none(self):
        result = parse_constraints("")
        assert result == _r()

    def test_whitespace_only_returns_all_none(self):
        result = parse_constraints("   ")
        assert result == _r()


# ---------------------------------------------------------------------------
# Test 3 — Budget format: "60k" / "60K"
# ---------------------------------------------------------------------------

class TestBudgetFormatK:
    """'60k' and variants must parse to 60000."""

    def test_60k_lowercase(self):
        result = parse_constraints("I want a laptop around 60k")
        assert result["budget"] == 60_000.0

    def test_60K_uppercase(self):
        result = parse_constraints("My budget is 60K for a phone")
        assert result["budget"] == 60_000.0

    def test_budget_is_60k(self):
        result = parse_constraints("budget is 60k for wireless headphones")
        assert result["budget"] == 60_000.0

    def test_fractional_k(self):
        """'7.5k' should parse to 7500."""
        result = parse_constraints("earphones under 7.5k")
        assert result["budget"] == 7_500.0


# ---------------------------------------------------------------------------
# Test 4 — Budget format: "₹60,000"
# ---------------------------------------------------------------------------

class TestBudgetFormatRupeeSymbol:
    """Rupee symbol + comma-separated number must parse correctly."""

    def test_rupee_symbol_with_commas(self):
        result = parse_constraints("I have a budget of ₹60,000 for a laptop")
        assert result["budget"] == 60_000.0

    def test_rupee_symbol_no_commas(self):
        result = parse_constraints("₹25000 for a smartphone")
        assert result["budget"] == 25_000.0

    def test_rs_prefix(self):
        """'Rs. 60,000' should parse correctly."""
        result = parse_constraints("Rs. 60,000 budget for headphones")
        assert result["budget"] == 60_000.0

    def test_rupee_in_sentence(self):
        result = parse_constraints("Looking for a phone under ₹20,000")
        assert result["budget"] == 20_000.0


# ---------------------------------------------------------------------------
# Test 5 — Budget format: "under 15000", "below", "less than"
# ---------------------------------------------------------------------------

class TestBudgetFormatKeywords:
    """Keyword-anchored budget extraction."""

    def test_under_15000(self):
        result = parse_constraints("I want a phone under 15000")
        assert result["budget"] == 15_000.0

    def test_below_15000(self):
        result = parse_constraints("headphones below 15000")
        assert result["budget"] == 15_000.0

    def test_less_than_15000(self):
        result = parse_constraints("Something less than 15000")
        assert result["budget"] == 15_000.0

    def test_lakh_format(self):
        """'1.5 lakh' should parse to 150000."""
        result = parse_constraints("laptop within 1.5 lakh")
        assert result["budget"] == 150_000.0


# ---------------------------------------------------------------------------
# Test 6 — Explicit priority stated
# ---------------------------------------------------------------------------

class TestExplicitPriority:
    """Priority must be set only when the user clearly states it."""

    def test_battery_matters_most(self):
        result = parse_constraints(
            "I need a phone, battery life matters most, budget around 20k"
        )
        assert result["priority"] == "battery"

    def test_cheapest_option(self):
        result = parse_constraints(
            "Just give me the cheapest option for wireless earbuds"
        )
        assert result["priority"] == "value"

    def test_best_performance(self):
        result = parse_constraints(
            "I want a laptop with the best performance, budget 80k"
        )
        assert result["priority"] == "performance"

    def test_best_sound_quality_headphones(self):
        result = parse_constraints(
            "Looking for wired headphones where best sound quality matters"
        )
        assert result["priority"] == "sound_quality"

    def test_value_for_money(self):
        result = parse_constraints(
            "Recommend a phone that gives the best value for money under 25000"
        )
        assert result["priority"] == "value"

    def test_balanced_priority(self):
        result = parse_constraints(
            "I want a balanced laptop — I don't have a specific priority"
        )
        assert result["priority"] == "balanced"


# ---------------------------------------------------------------------------
# Test 7 — Use-case alone must NOT set priority
# ---------------------------------------------------------------------------

class TestNoPriorityFromUseCase:
    """
    The spec requires: priority stays None unless the user explicitly states
    it.  Use-case words like 'gaming' or 'video editing' must NOT trigger
    priority inference — that's the orchestrator's job.
    """

    def test_gaming_laptop_no_priority(self):
        result = parse_constraints(
            "I need a laptop for gaming, budget 70k"
        )
        # gaming implies performance could matter, but priority must be None
        assert result["priority"] is None
        assert result["category"] == "laptop"
        assert result["budget"] == 70_000.0

    def test_video_editing_no_priority(self):
        result = parse_constraints(
            "Looking for a laptop for video editing"
        )
        assert result["priority"] is None

    def test_music_listening_no_priority(self):
        result = parse_constraints(
            "I want headphones for listening to music"
        )
        assert result["priority"] is None

    def test_calls_and_meetings_no_priority(self):
        result = parse_constraints(
            "Need a phone for work calls and meetings"
        )
        assert result["priority"] is None

    def test_use_case_captured_even_without_priority(self):
        """use_case should still be extracted even when priority is None."""
        result = parse_constraints(
            "I need a laptop for coding, budget around 60k"
        )
        assert result["priority"] is None
        assert result["use_case"] is not None
        assert "cod" in result["use_case"]  # "coding"


# ---------------------------------------------------------------------------
# Test 8 — Headphones WITH connectivity_type mentioned
# ---------------------------------------------------------------------------

class TestHeadphonesWithConnectivity:
    """Connectivity type must be extracted when mentioned."""

    def test_wireless_headphones(self):
        result = parse_constraints("I want wireless headphones under 5000")
        assert result["category"] == "headphones"
        assert result["connectivity_type"] == "wireless"

    def test_wired_headphones(self):
        result = parse_constraints("Looking for wired headphones for studio use")
        assert result["category"] == "headphones"
        assert result["connectivity_type"] == "wired"

    def test_true_wireless_earbuds(self):
        result = parse_constraints(
            "Recommend some true wireless earbuds under ₹3000"
        )
        assert result["category"] == "headphones"
        assert result["connectivity_type"] == "true_wireless"

    def test_bluetooth_earphones(self):
        result = parse_constraints(
            "I want bluetooth earphones for the gym, budget 2000"
        )
        assert result["category"] == "headphones"
        assert result["connectivity_type"] == "wireless"

    def test_35mm_jack_wired(self):
        result = parse_constraints(
            "Need headphones with a 3.5mm jack, budget under 1500"
        )
        assert result["category"] == "headphones"
        assert result["connectivity_type"] == "wired"


# ---------------------------------------------------------------------------
# Test 9 — Headphones WITHOUT connectivity_type mentioned
# ---------------------------------------------------------------------------

class TestHeadphonesWithoutConnectivity:
    """connectivity_type must remain None when not specified."""

    def test_headphones_no_connectivity(self):
        result = parse_constraints(
            "I need headphones under 2000 for everyday use"
        )
        assert result["category"] == "headphones"
        assert result["connectivity_type"] is None

    def test_earphones_no_connectivity(self):
        result = parse_constraints(
            "Recommend me some good earphones under 1000"
        )
        assert result["category"] == "headphones"
        assert result["connectivity_type"] is None

    def test_headset_no_connectivity(self):
        result = parse_constraints(
            "Looking for a headset for online gaming"
        )
        assert result["category"] == "headphones"
        assert result["connectivity_type"] is None


# ---------------------------------------------------------------------------
# Test 10 — prior_context carries forward missing fields
# ---------------------------------------------------------------------------

class TestPriorContext:
    """Fields absent from the current message should be filled from prior_context."""

    def test_prior_category_carried_forward(self):
        """User said 'under 30k' in a follow-up — category from prior turn."""
        prior = _r(category="phone", budget=20_000.0)
        result = parse_constraints("Actually make it under 30k", prior_context=prior)
        assert result["category"] == "phone"       # carried from prior
        assert result["budget"] == 30_000.0        # overridden by current

    def test_current_message_wins_over_prior(self):
        """If current message mentions a category, it overrides prior."""
        prior = _r(category="phone")
        result = parse_constraints(
            "Wait, I actually want a laptop under 50k", prior_context=prior
        )
        assert result["category"] == "laptop"   # current wins
        assert result["budget"] == 50_000.0

    def test_prior_connectivity_carried_forward(self):
        """connectivity_type from prior fills in headphones follow-up."""
        prior = _r(category="headphones", connectivity_type="wireless")
        result = parse_constraints(
            "My budget is ₹5000", prior_context=prior
        )
        assert result["category"] == "headphones"
        assert result["connectivity_type"] == "wireless"
        assert result["budget"] == 5_000.0

    def test_none_prior_has_no_effect(self):
        """prior_context=None must behave identically to not passing it."""
        msg = "I want a phone under 15000"
        result_no_prior = parse_constraints(msg)
        result_none_prior = parse_constraints(msg, prior_context=None)
        assert result_no_prior == result_none_prior


# ---------------------------------------------------------------------------
# Bonus test 11 — true_wireless detection over plain wireless
# ---------------------------------------------------------------------------

class TestTrueWirelessPriority:
    """true_wireless signal must take precedence over generic wireless."""

    def test_true_wireless_wins_over_wireless_keyword(self):
        result = parse_constraints(
            "I want true wireless earbuds with ANC under 10000"
        )
        assert result["connectivity_type"] == "true_wireless"

    def test_earbuds_alone_implies_true_wireless(self):
        """Standalone 'earbuds' is a true_wireless signal."""
        result = parse_constraints(
            "Suggest me some good earbuds under ₹2000"
        )
        assert result["category"] == "headphones"
        assert result["connectivity_type"] == "true_wireless"


# ---------------------------------------------------------------------------
# Bonus test 12 — Wired vs. wireless disambiguation
# ---------------------------------------------------------------------------

class TestWiredVsWirelessDisambiguation:
    """Wired signals must not be mistaken for wireless."""

    def test_aux_cable_means_wired(self):
        result = parse_constraints(
            "I need earphones with an aux cable for my old amplifier"
        )
        assert result["category"] == "headphones"
        assert result["connectivity_type"] == "wired"

    def test_wired_keyword_explicit(self):
        result = parse_constraints(
            "Give me wired headphones, I don't like Bluetooth"
        )
        assert result["category"] == "headphones"
        assert result["connectivity_type"] == "wired"


# ===========================================================================
# NEW TESTS — Category 1: Real parsing-bug fixes
# ===========================================================================

class TestWordFormNumbers:
    """Category 1 Fix 1 — word-form numbers like 'sixty thousand'."""

    def test_sixty_thousand_word_form(self):
        """Exact failing case from stress test: pure word number."""
        result = parse_constraints("somewhere around sixty thousand would work")
        assert result["budget"] == 60_000.0, (
            f"Expected 60000, got {result['budget']!r}"
        )

    def test_fifteen_thousand_word_form(self):
        result = parse_constraints("under fifteen thousand please")
        assert result["budget"] == 15_000.0

    def test_twenty_five_thousand_compound(self):
        """Tens + ones compound: 'twenty five thousand'."""
        result = parse_constraints("something around twenty five thousand")
        assert result["budget"] == 25_000.0

    def test_ninety_thousand(self):
        result = parse_constraints("budget ninety thousand")
        assert result["budget"] == 90_000.0

    def test_one_lakh_word_form(self):
        result = parse_constraints("my budget is one lakh")
        assert result["budget"] == 100_000.0

    def test_two_lakh_word_form(self):
        result = parse_constraints("looking for a laptop around two lakh")
        assert result["budget"] == 200_000.0

    def test_isolated_number_word_no_budget(self):
        """'nineteen' without a multiplier should NOT set a budget."""
        result = parse_constraints("I am nineteen years old, need a phone")
        assert result["budget"] is None
        assert result["category"] == "phone"


class TestDigitPlusThousandWord:
    """Category 1 Fix 1 (mixed) — digit + 'thousand' word."""

    def test_under_10_thousand_rupees(self):
        """Exact failing case from stress test: returns 10, not 10000."""
        result = parse_constraints("budget's tight, under 10 thousand rupees please")
        assert result["budget"] == 10_000.0, (
            f"Expected 10000, got {result['budget']!r} — "
            "keyword pattern must not grab '10' before 'thousand' is seen"
        )

    def test_around_5_thousand(self):
        result = parse_constraints("looking for earphones around 5 thousand")
        assert result["budget"] == 5_000.0

    def test_2point5_thousand(self):
        result = parse_constraints("headphones under 2.5 thousand")
        assert result["budget"] == 2_500.0


class TestRangeBudget:
    """Category 1 Fix 3 — range budgets add budget_min / budget_max."""

    def test_hyphen_range_shared_k(self):
        """Exact failing case: '50-60k range' → min=50000, max=60000."""
        result = parse_constraints("looking to spend maybe 50-60k range")
        assert result["budget"]     == 60_000.0, "budget should equal budget_max"
        assert result["budget_min"] == 50_000.0
        assert result["budget_max"] == 60_000.0

    def test_hyphen_range_both_k(self):
        """'30k-50k' — both sides explicit k."""
        result = parse_constraints("laptop budget 30k-50k")
        assert result["budget_min"] == 30_000.0
        assert result["budget_max"] == 50_000.0
        assert result["budget"]     == 50_000.0

    def test_to_range(self):
        """'50k to 60k' form."""
        result = parse_constraints("I want to spend 50k to 60k on a laptop")
        assert result["budget_min"] == 50_000.0
        assert result["budget_max"] == 60_000.0

    def test_between_and_range(self):
        """'between 40k and 80k' form."""
        result = parse_constraints("between 40k and 80k for a gaming laptop")
        assert result["budget_min"] == 40_000.0
        assert result["budget_max"] == 80_000.0

    def test_single_budget_leaves_range_fields_none(self):
        """A single value must not populate budget_min / budget_max."""
        result = parse_constraints("I want a laptop around 60k")
        assert result["budget"]     == 60_000.0
        assert result["budget_min"] is None
        assert result["budget_max"] is None

    def test_non_price_hyphen_range_ignored(self):
        """'50-60 minutes' has no k suffix → must not be treated as budget."""
        result = parse_constraints("battery life of 50-60 minutes is fine")
        assert result["budget_min"] is None
        assert result["budget_max"] is None

    def test_range_mixed_k_large_left(self):
        """'8000-10k' should have min=8000 and max=10000, not min=8000000."""
        result = parse_constraints("budget of 8000-10k")
        assert result["budget_min"] == 8000.0
        assert result["budget_max"] == 10000.0
        assert result["budget"] == 10000.0

    def test_range_no_k_price(self):
        """'500-800' with no k anywhere should have min=500 and max=800."""
        result = parse_constraints("budget of 500-800")
        assert result["budget_min"] == 500.0
        assert result["budget_max"] == 800.0
        assert result["budget"] == 800.0


class TestBatteryWisePriority:
    """Category 1 Fix 2 — '-wise' and workday phrasing triggers priority=battery."""

    def test_battery_wise_suffix(self):
        """Exact failing case from stress test."""
        result = parse_constraints(
            "laptop, needs to last me the whole workday battery-wise"
        )
        assert result["priority"] == "battery", (
            f"Expected 'battery', got {result['priority']!r}"
        )
        assert result["category"] == "laptop"

    def test_battery_wise_standalone(self):
        result = parse_constraints(
            "battery-wise it should be really strong, around 60k phone"
        )
        assert result["priority"] == "battery"
        assert result["budget"]   == 60_000.0

    def test_all_day_battery_wise(self):
        result = parse_constraints("needs to last all day battery-wise")
        assert result["priority"] == "battery"

    def test_gaming_without_battery_still_none(self):
        """Ensure we didn't accidentally broaden the battery pattern."""
        result = parse_constraints("laptop for gaming, budget 70k")
        assert result["priority"] is None


# ===========================================================================
# NEW TESTS — Category 2: ambiguous_signals field
# ===========================================================================

class TestAmbiguousSignalsBudget:
    """ambiguous_signals: budget entries appear when no numeric budget is set."""

    def test_cheap_headphones_flags_budget_ambiguous(self):
        """'cheap' → ambiguous_signals budget entry; budget stays None."""
        result = parse_constraints("cheap headphones")
        assert result["budget"] is None
        assert any(
            s["type"] == "budget" and s["term"] == "cheap"
            for s in result["ambiguous_signals"]
        ), f"Expected 'cheap' in ambiguous_signals, got {result['ambiguous_signals']}"

    def test_nothing_crazy_expensive_flags_budget(self):
        """Multi-word phrase wins over shorter 'expensive' substring."""
        result = parse_constraints("nothing crazy expensive, I'm a student")
        budget_sigs = [s for s in result["ambiguous_signals"] if s["type"] == "budget"]
        assert len(budget_sigs) == 1
        assert budget_sigs[0]["term"] == "nothing crazy expensive", (
            f"Longer phrase should win; got {budget_sigs[0]['term']!r}"
        )

    def test_affordable_flags_budget(self):
        result = parse_constraints("looking for an affordable laptop")
        budget_sigs = [s for s in result["ambiguous_signals"] if s["type"] == "budget"]
        assert len(budget_sigs) == 1
        assert budget_sigs[0]["term"] == "affordable"

    def test_explicit_budget_suppresses_ambiguous_entry(self):
        """When a numeric budget IS present, no budget ambiguous_signals entry."""
        result = parse_constraints("I don't wanna spend a ton, maybe 15k tops")
        assert result["budget"] == 15_000.0
        budget_sigs = [s for s in result["ambiguous_signals"] if s["type"] == "budget"]
        assert budget_sigs == [], (
            f"Numeric budget present — no budget ambiguous entry expected; "
            f"got {budget_sigs}"
        )

    def test_affordable_with_explicit_budget_suppressed(self):
        """'affordable laptop under 50k' — numeric budget wins, no ambiguous entry."""
        result = parse_constraints("affordable laptop under 50k")
        assert result["budget"] == 50_000.0
        budget_sigs = [s for s in result["ambiguous_signals"] if s["type"] == "budget"]
        assert budget_sigs == []


class TestAmbiguousSignalsPriority:
    """ambiguous_signals: priority entries appear when no explicit priority is set."""

    def test_cheap_headphones_also_flags_nothing_fancy(self):
        """'don't care about anything fancy' → priority ambiguous_signals entry."""
        result = parse_constraints(
            "cheap headphones, don't care about anything fancy"
        )
        pri_sigs = [s for s in result["ambiguous_signals"] if s["type"] == "priority"]
        assert len(pri_sigs) == 1
        assert pri_sigs[0]["term"] == "nothing fancy"

    def test_great_sound_flags_priority(self):
        result = parse_constraints("want something with great sound")
        pri_sigs = [s for s in result["ambiguous_signals"] if s["type"] == "priority"]
        assert len(pri_sigs) == 1
        assert pri_sigs[0]["term"] == "great sound"

    def test_the_best_flags_priority(self):
        result = parse_constraints("cost is really not a concern here, get me the best")
        pri_sigs = [s for s in result["ambiguous_signals"] if s["type"] == "priority"]
        assert len(pri_sigs) == 1
        assert pri_sigs[0]["term"] == "the best"

    def test_explicit_priority_suppresses_ambiguous_entry(self):
        """'battery matters most' sets priority → no priority ambiguous entry."""
        result = parse_constraints(
            "I need a phone, battery life matters most, budget around 20k"
        )
        assert result["priority"] == "battery"
        pri_sigs = [s for s in result["ambiguous_signals"] if s["type"] == "priority"]
        assert pri_sigs == [], (
            f"Explicit priority set — no priority ambiguous entry expected; "
            f"got {pri_sigs}"
        )

    def test_ambiguous_signals_empty_for_plain_message(self):
        """A plain message with no ambiguous terms has an empty list."""
        result = parse_constraints("I want a phone under 15000")
        assert result["ambiguous_signals"] == []

    def test_ambiguous_signals_always_present_as_list(self):
        """The field must always be a list, even when empty."""
        result = parse_constraints("laptop for coding")
        assert isinstance(result["ambiguous_signals"], list)


class TestAmbiguousSignalsCombined:
    """Both budget and priority ambiguous signals can appear together."""

    def test_both_budget_and_priority_ambiguous(self):
        """'cheap headphones, don't care about anything fancy' → both entries."""
        result = parse_constraints(
            "cheap headphones, don't care about anything fancy"
        )
        types = {s["type"] for s in result["ambiguous_signals"]}
        assert "budget"   in types, "Expected a budget ambiguous_signal"
        assert "priority" in types, "Expected a priority ambiguous_signal"
        assert len(result["ambiguous_signals"]) == 2

    def test_at_most_one_budget_entry(self):
        """Even if two budget-ambiguous words appear, only one entry returned."""
        result = parse_constraints("cheap and affordable headphones")
        budget_sigs = [s for s in result["ambiguous_signals"] if s["type"] == "budget"]
        assert len(budget_sigs) == 1

    def test_at_most_one_priority_entry(self):
        """Even if two priority-ambiguous phrases appear, only one entry."""
        result = parse_constraints("I want great sound and high quality headphones")
        pri_sigs = [s for s in result["ambiguous_signals"] if s["type"] == "priority"]
        assert len(pri_sigs) == 1


class TestInvertedPriorityPhrasing:
    """Regression — "priority is X" was not matched (only "X is priority").

    Surfaced by golden case G20 ("wireless earbuds for gym, priority is
    battery life"), where the tool returned priority=None despite the user
    stating it in plain words.
    """

    @pytest.mark.parametrize("message,expected", [
        ("wireless earbuds for gym, priority is battery life", "battery"),
        ("priority is battery",            "battery"),
        ("my priority is performance",     "performance"),
        ("priority is sound quality",      "sound_quality"),
        ("priority is value",              "value"),
        ("priority: value",                "value"),
        ("focus is on battery",            "battery"),
        ("prioritise battery",             "battery"),
        ("prioritize performance",         "performance"),
        ("prioritise sound",               "sound_quality"),
        ("prioritize price",               "value"),
    ])
    def test_inverted_priority_is_detected(self, message, expected):
        assert parse_constraints(message)["priority"] == expected

    def test_original_phrasing_still_works(self):
        """The pre-existing "X matters most" form must not regress."""
        assert parse_constraints("battery life matters most")["priority"] == "battery"


class TestCategoryPrecedence:
    """Regression — a host-device word outranked the actual product.

    Surfaced by golden case G23 ("cheap mobile headphones"), which parsed as
    category="phone" because _detect_category checked phone before
    headphones. Headphone nouns are unambiguous; "mobile"/"laptop" are often
    just the device the headphones plug into.
    """

    @pytest.mark.parametrize("message", [
        "cheap mobile headphones",
        "mobile headphones",
        "headphones for my mobile",
        "earbuds for my phone",
        "headphones for my laptop",
        "wired earphones for my iphone",
    ])
    def test_headphones_win_over_host_device(self, message):
        assert parse_constraints(message)["category"] == "headphones"

    @pytest.mark.parametrize("message,expected", [
        ("looking for a mobile",        "phone"),
        ("need a smartphone under 20k", "phone"),
        ("laptop for video editing",    "laptop"),
        ("macbook for coding",          "laptop"),
    ])
    def test_bare_device_still_detected(self, message, expected):
        """Reordering must not break messages with no headphone signal."""
        assert parse_constraints(message)["category"] == expected


class TestConnectivityFromPriorContext:
    """Regression — connectivity was gated on the current message's category.

    Surfaced by golden case G03 turn 2: the agent asks about connectivity,
    the user replies "true wireless, and let's cap it at ₹5,000", and the
    tool returned connectivity_type=None because that message contains no
    headphone noun. The answer to our own clarifying question was discarded.
    """

    HP_CONTEXT = {"category": "headphones", "connectivity_type": None,
                  "use_case": "gym"}

    @pytest.mark.parametrize("message,expected", [
        ("true wireless, and let's cap it at 5000", "true_wireless"),
        ("true wireless",                           "true_wireless"),
        ("wired is fine",                           "wired"),
        ("bluetooth please",                        "wireless"),
    ])
    def test_prior_headphones_context_unlocks_connectivity(self, message, expected):
        result = parse_constraints(message, prior_context=self.HP_CONTEXT)
        assert result["connectivity_type"] == expected

    def test_no_context_still_yields_none(self):
        """Without any category, connectivity has nothing to qualify."""
        assert parse_constraints("true wireless")["connectivity_type"] is None

    def test_non_headphone_context_does_not_unlock(self):
        """A laptop conversation must never acquire a connectivity_type."""
        result = parse_constraints("wireless", prior_context={"category": "laptop"})
        assert result["connectivity_type"] is None

    def test_current_message_still_wins(self):
        """An explicit connectivity in this message overrides prior context."""
        ctx = {"category": "headphones", "connectivity_type": "wireless"}
        result = parse_constraints("actually wired headphones", prior_context=ctx)
        assert result["connectivity_type"] == "wired"

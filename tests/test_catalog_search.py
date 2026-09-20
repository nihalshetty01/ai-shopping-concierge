"""
tests/test_catalog_search.py
-----------------------------
Unit tests for the catalog_search() function.

Fixture design (6 products, all made-up scores):
  P1 - laptop   : perf=6.0, battery_hours=10, storage_gb=512, price=60000
  P2 - phone    : perf=4.0, battery_hours=30, storage_gb=128, price=25000
  P3 - wireless : audio=7.0, battery_hours=30, price=5000
  P4 - wireless : audio=9.0, battery_hours=20, price=8000
  P5 - wired    : audio=5.0, price=1000
  P6 - wired    : audio=9.0, price=4000

Hand-calculated expected final_scores are embedded in each test assertion.
Derivations are in the inline comments below the constants.
"""

import math
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tools.catalog_search import catalog_search

FIXTURE_PRODUCTS = [
    {"id": "test_laptop_01", "name": "Test Laptop",
     "category": "laptop", "price": 60000,
     "perf_score": 6.0, "battery_hours": 10, "storage_gb": 512},
    {"id": "test_phone_01", "name": "Test Phone",
     "category": "phone", "price": 25000,
     "perf_score": 4.0, "battery_hours": 30, "storage_gb": 128},
    {"id": "test_wireless_01", "name": "Test Wireless HP A",
     "category": "headphones", "connectivity_type": "wireless",
     "price": 5000, "audio_score": 7.0, "battery_hours": 30},
    {"id": "test_wireless_02", "name": "Test Wireless HP B",
     "category": "headphones", "connectivity_type": "wireless",
     "price": 8000, "audio_score": 9.0, "battery_hours": 20},
    {"id": "test_wired_01", "name": "Test Wired HP A",
     "category": "headphones", "connectivity_type": "wired",
     "price": 1000, "audio_score": 5.0},
    {"id": "test_wired_02", "name": "Test Wired HP B",
     "category": "headphones", "connectivity_type": "wired",
     "price": 4000, "audio_score": 9.0},
]

TOLERANCE = 0.01


def fixture_source():
    return [dict(p) for p in FIXTURE_PRODUCTS]


# ---------------------------------------------------------------------------
# Hand-calculated expected values
# ---------------------------------------------------------------------------
#
# LAPTOP (P1 only), priority="balanced", budget=55000
#   perf_norm=10, bat_norm=10, stor_norm=10  (single item -> 10 each)
#   budget_fit = 10 - (60000-55000)/55000*20 = 10 - 1.8182 = 8.1818
#   value_raw  = (10+10)/(60000/1000) = 20/60  -> single -> norm=10
#   score = 0.25*10 + 0.20*10 + 0.15*10 + 0.20*10 + 0.20*8.1818 = 9.6364
EXPECTED_LAPTOP_BALANCED = 9.636364

#
# PHONE (P2 only), priority="performance", budget=30000
#   all norms = 10.0  (single item)
#   budget_fit = 10 - (30000-25000)/30000*5 = 9.1667
#   score = 0.40*10 + 0.15*10 + 0.10*10 + 0.20*10 + 0.15*9.1667 = 9.875
EXPECTED_PHONE_PERFORMANCE = 9.875

#
# NOTE ON THE BUDGETS BELOW: catalog_search drops anything priced more than
# BUDGET_TOLERANCE (15%) above budget.  The two-candidate fixtures use a
# budget that keeps BOTH products inside the band, so these tests exercise
# normalization and the weight tables rather than the filter.  The filter
# itself is covered separately in TestBudgetToleranceBand.
#
# WIRELESS HP (P3=5000, P4=8000), budget=8000 -- both inside the band
#   audio_norm: P3=0, P4=10
#   bat_norm:   P3=10, P4=0
#   budget_fit: P3 = 10 - (8000-5000)/8000*5 = 8.125,  P4 = 10.0 (at budget)
#   val_raw:    P3=(0+10)/5=2.0,  P4=(10+0)/8=1.25
#   val_norm:   P3=10, P4=0
#
#   priority="sound_quality"  (audio .45, battery .20, value .20, bf .15)
#     P3 = 0.45*0  + 0.20*10 + 0.20*10 + 0.15*8.125 = 5.21875
#     P4 = 0.45*10 + 0.20*0  + 0.20*0  + 0.15*10    = 6.0     -> P4 wins
EXPECTED_WIRELESS_P3_SOUND_QUALITY = 5.21875
EXPECTED_WIRELESS_P4_SOUND_QUALITY = 6.0
#
#   priority="battery"  (audio .20, battery .45, value .20, bf .15)
#     P3 = 0.20*0  + 0.45*10 + 0.20*10 + 0.15*8.125 = 7.71875
#     P4 = 0.20*10 + 0.45*0  + 0.20*0  + 0.15*10    = 3.5     -> P3 wins
EXPECTED_WIRELESS_P3_BATTERY = 7.71875
EXPECTED_WIRELESS_P4_BATTERY = 3.5

#
# WIRED HP (P5=1000, P6=4000), priority="balanced", budget=4000
#   audio_norm: P5=0, P6=10
#   budget_fit: P5 = 10 - (4000-1000)/4000*5 = 6.25,  P6 = 10.0 (at budget)
#   val_raw:    P5=0/1=0, P6=10/4=2.5  -> val_norm: P5=0, P6=10
#   P5 score = 0.40*0  + 0.35*0  + 0.25*6.25 = 1.5625
#   P6 score = 0.40*10 + 0.35*10 + 0.25*10   = 10.0
EXPECTED_WIRED_P5_BALANCED = 1.5625
EXPECTED_WIRED_P6_BALANCED = 10.0


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLaptopSearch:

    def test_laptop_balanced_score(self):
        """Single laptop; all dims normalize to 10 except budget_fit."""
        results = catalog_search(
            {"category": "laptop", "budget": 55000, "priority": "balanced"},
            data_source=fixture_source,
        )
        assert len(results) == 1
        assert math.isclose(results[0]["final_score"], EXPECTED_LAPTOP_BALANCED, abs_tol=TOLERANCE), (
            f"Expected ~{EXPECTED_LAPTOP_BALANCED}, got {results[0]['final_score']}"
        )

    def test_laptop_result_id(self):
        results = catalog_search(
            {"category": "laptop", "budget": 55000, "priority": "balanced"},
            data_source=fixture_source,
        )
        assert results[0]["id"] == "test_laptop_01"

    def test_laptop_invalid_priority_raises(self):
        with pytest.raises(ValueError):
            catalog_search(
                {"category": "laptop", "budget": 55000, "priority": "sound_quality"},
                data_source=fixture_source,
            )


class TestPhoneSearch:

    def test_phone_performance_score(self):
        """Single phone; expected final_score = 9.875."""
        results = catalog_search(
            {"category": "phone", "budget": 30000, "priority": "performance"},
            data_source=fixture_source,
        )
        assert len(results) == 1
        assert math.isclose(results[0]["final_score"], EXPECTED_PHONE_PERFORMANCE, abs_tol=TOLERANCE), (
            f"Expected ~{EXPECTED_PHONE_PERFORMANCE}, got {results[0]['final_score']}"
        )

    def test_phone_result_id(self):
        results = catalog_search(
            {"category": "phone", "budget": 30000, "priority": "performance"},
            data_source=fixture_source,
        )
        assert results[0]["id"] == "test_phone_01"


class TestWirelessHeadphonesSearch:

    def test_wireless_sound_quality_ranking_and_scores(self):
        """P4 wins on audio once both candidates are inside budget; P3 second."""
        results = catalog_search(
            {"category": "headphones", "connectivity_type": "wireless",
             "budget": 8000, "priority": "sound_quality"},
            data_source=fixture_source,
        )
        assert len(results) == 2
        assert results[0]["id"] == "test_wireless_02", (
            f"Expected test_wireless_02 first; got {results[0]['id']}"
        )
        assert results[1]["id"] == "test_wireless_01"
        assert math.isclose(results[0]["final_score"], EXPECTED_WIRELESS_P4_SOUND_QUALITY, abs_tol=TOLERANCE)
        assert math.isclose(results[1]["final_score"], EXPECTED_WIRELESS_P3_SOUND_QUALITY, abs_tol=TOLERANCE)

    def test_wireless_battery_priority_flips_the_winner(self):
        """Same two candidates, same budget - only the priority changes.

        P3 has worse audio but 30h vs 20h battery and a better value
        ratio, so switching the priority must swing the ranking. This is
        the check that the weight table actually drives the outcome (PRD
        10.3) rather than one product dominating every dimension.
        """
        results = catalog_search(
            {"category": "headphones", "connectivity_type": "wireless",
             "budget": 8000, "priority": "battery"},
            data_source=fixture_source,
        )
        assert len(results) == 2
        assert results[0]["id"] == "test_wireless_01", (
            f"Expected test_wireless_01 first on battery; got {results[0]['id']}"
        )
        assert results[1]["id"] == "test_wireless_02"
        assert math.isclose(results[0]["final_score"], EXPECTED_WIRELESS_P3_BATTERY, abs_tol=TOLERANCE)
        assert math.isclose(results[1]["final_score"], EXPECTED_WIRELESS_P4_BATTERY, abs_tol=TOLERANCE)

    def test_wireless_results_contain_only_wireless(self):
        results = catalog_search(
            {"category": "headphones", "connectivity_type": "wireless",
             "budget": 10000, "priority": "balanced"},
            data_source=fixture_source,
        )
        for r in results:
            assert r["connectivity_type"] == "wireless"


class TestWiredHeadphonesSearch:

    def test_wired_balanced_scores_and_ranking(self):
        """P6 wins on audio; P5 is cheap but scores 0 on audio and value."""
        results = catalog_search(
            {"category": "headphones", "connectivity_type": "wired",
             "budget": 4000, "priority": "balanced"},
            data_source=fixture_source,
        )
        assert len(results) == 2
        assert results[0]["id"] == "test_wired_02"
        assert results[1]["id"] == "test_wired_01"
        assert math.isclose(results[0]["final_score"], EXPECTED_WIRED_P6_BALANCED, abs_tol=TOLERANCE)
        assert math.isclose(results[1]["final_score"], EXPECTED_WIRED_P5_BALANCED, abs_tol=TOLERANCE)

    def test_wired_no_battery_field_no_crash(self):
        """Wired headphones have no battery_hours; must not raise KeyError."""
        results = catalog_search(
            {"category": "headphones", "connectivity_type": "wired",
             "budget": 3000, "priority": "sound_quality"},
            data_source=fixture_source,
        )
        assert len(results) > 0

    def test_wired_results_contain_only_wired(self):
        results = catalog_search(
            {"category": "headphones", "connectivity_type": "wired",
             "budget": 10000, "priority": "balanced"},
            data_source=fixture_source,
        )
        for r in results:
            assert r["connectivity_type"] == "wired"


class TestBatteryPriorityWiredRejection:
    """
    Chosen behaviour: RAISE ValueError.
    Wired headphones have no battery dimension. Silently falling back to 'balanced'
    would mask a caller error. Raising makes the contract explicit and testable.
    """

    def test_wired_battery_priority_raises_value_error(self):
        """priority='battery' on wired headphones must raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            catalog_search(
                {"category": "headphones", "connectivity_type": "wired",
                 "budget": 3000, "priority": "battery"},
                data_source=fixture_source,
            )
        assert "battery" in str(exc_info.value).lower()

    def test_wired_battery_error_mentions_valid_options(self):
        """Error message should hint at valid priorities."""
        with pytest.raises(ValueError) as exc_info:
            catalog_search(
                {"category": "headphones", "connectivity_type": "wired",
                 "budget": 3000, "priority": "battery"},
                data_source=fixture_source,
            )
        msg = str(exc_info.value).lower()
        assert any(p in msg for p in ["sound_quality", "balanced", "value"])

    def test_wireless_battery_priority_valid(self):
        """Sanity check: 'battery' IS valid for wireless headphones."""
        results = catalog_search(
            {"category": "headphones", "connectivity_type": "wireless",
             "budget": 10000, "priority": "battery"},
            data_source=fixture_source,
        )
        assert len(results) > 0


class TestEdgeCases:

    def test_invalid_category_raises(self):
        with pytest.raises(ValueError):
            catalog_search(
                {"category": "tablet", "budget": 50000, "priority": "balanced"},
                data_source=fixture_source,
            )

    def test_headphones_missing_connectivity_raises(self):
        with pytest.raises(ValueError, match="connectivity_type"):
            catalog_search(
                {"category": "headphones", "budget": 5000, "priority": "balanced"},
                data_source=fixture_source,
            )

    def test_near_miss_over_budget_is_kept(self):
        """A product just over budget must still be offered.

        4000 against a 3600 budget is 11% over - inside the band, so it
        survives the filter and is penalised by budget_fit instead.
        """
        results = catalog_search(
            {"category": "headphones", "connectivity_type": "wired",
             "budget": 3600, "priority": "balanced"},
            data_source=fixture_source,
        )
        ids = {r["id"] for r in results}
        assert "test_wired_02" in ids, "Near-miss product was wrongly excluded"

    def test_source_data_not_mutated(self):
        """catalog_search must not modify the caller's product dicts."""
        original = fixture_source()
        original_snapshots = [dict(p) for p in original]
        catalog_search(
            {"category": "laptop", "budget": 55000, "priority": "balanced"},
            data_source=lambda: [dict(p) for p in original],
        )
        for before, after in zip(original_snapshots, original):
            assert before == after, "Source data was mutated!"

    def test_returns_at_most_five(self):
        """Real catalog; result count must not exceed 5."""
        from tools.catalog_search import load_catalog_json
        results = catalog_search(
            {"category": "laptop", "budget": 200000, "priority": "balanced"},
            data_source=load_catalog_json,
        )
        assert len(results) <= 5

    def test_true_wireless_uses_wireless_table(self):
        """true_wireless has battery dimension; must not crash and must rank correctly."""
        tw_fixture = [
            {"id": "tw_01", "name": "TW A", "category": "headphones",
             "connectivity_type": "true_wireless", "price": 5000,
             "audio_score": 7.0, "battery_hours": 6},
            {"id": "tw_02", "name": "TW B", "category": "headphones",
             "connectivity_type": "true_wireless", "price": 10000,
             "audio_score": 9.0, "battery_hours": 8},
        ]
        results = catalog_search(
            {"category": "headphones", "connectivity_type": "true_wireless",
             "budget": 10000, "priority": "sound_quality"},
            data_source=lambda: tw_fixture,
        )
        assert len(results) == 2
        assert results[0]["id"] == "tw_02"


class TestBudgetToleranceBand:
    """The soft budget filter (BUDGET_TOLERANCE, default 15%).

    Products above budget are not dropped outright — a near-miss is often
    the right recommendation. But anything beyond the band is excluded, so
    a wildly over-budget product can never win on raw specs alone.
    """

    def test_beyond_band_is_excluded(self):
        """P6 at 4000 is 33% over a 3000 budget — outside the band."""
        results = catalog_search(
            {"category": "headphones", "connectivity_type": "wired",
             "budget": 3000, "priority": "balanced"},
            data_source=fixture_source,
        )
        ids = {r["id"] for r in results}
        assert "test_wired_02" not in ids, (
            "Product 33% over budget should have been filtered out"
        )
        assert "test_wired_01" in ids, "In-budget product must still appear"

    def test_exactly_at_budget_is_kept(self):
        results = catalog_search(
            {"category": "headphones", "connectivity_type": "wired",
             "budget": 4000, "priority": "balanced"},
            data_source=fixture_source,
        )
        assert "test_wired_02" in {r["id"] for r in results}

    @pytest.mark.parametrize("budget,expected_in", [
        (4000 / 1.15, True),    # exactly at the +15% boundary
        (4000 / 1.16, False),   # a hair beyond it
    ])
    def test_band_boundary(self, budget, expected_in):
        """The boundary itself is inclusive."""
        results = catalog_search(
            {"category": "headphones", "connectivity_type": "wired",
             "budget": budget, "priority": "balanced"},
            data_source=fixture_source,
        )
        assert ("test_wired_02" in {r["id"] for r in results}) is expected_in

    def test_returns_empty_when_nothing_fits(self):
        """No candidate in band → empty list, not a forced bad recommendation.

        This is what lets the orchestrator honour golden case G17 ("budget
        infeasible") instead of presenting an unaffordable product as if it
        were a fit.
        """
        results = catalog_search(
            {"category": "laptop", "budget": 5000, "priority": "performance"},
            data_source=fixture_source,
        )
        assert results == []

    def test_real_catalog_respects_band(self):
        """Regression: a 60k laptop search must not return lakh-plus laptops."""
        from tools.catalog_search import load_catalog_json, BUDGET_TOLERANCE
        budget = 60000
        for priority in ("performance", "battery", "value", "balanced"):
            results = catalog_search(
                {"category": "laptop", "budget": budget, "priority": priority},
                data_source=load_catalog_json,
            )
            assert results, f"Expected in-band laptops for priority={priority}"
            for r in results:
                assert r["price"] <= budget * (1 + BUDGET_TOLERANCE), (
                    f"priority={priority}: {r['name']} at {r['price']} is "
                    f"beyond the band for a {budget} budget"
                )

    def test_budget_fit_floor_unreachable_inside_band(self):
        """Every surviving candidate scores >= 7.0 on budget_fit.

        At the band edge budget_fit is 10 - 0.15*20 = 7.0, so the max(0.0, …)
        floor in _budget_fit can never bind for a product that passed the
        filter. Documents why the floor is no longer a ranking hazard.
        """
        from tools.catalog_search import load_catalog_json
        results = catalog_search(
            {"category": "laptop", "budget": 60000, "priority": "performance"},
            data_source=load_catalog_json,
        )
        for r in results:
            assert r["_budget_fit"] >= 7.0 - 1e-9, (
                f"{r['name']}: budget_fit {r['_budget_fit']} below band minimum"
            )
